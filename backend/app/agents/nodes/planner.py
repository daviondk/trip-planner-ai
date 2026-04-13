import structlog
import json
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.models.schemas import TripPlannerState, DayPlan, Activity, UserPreferences
from app.config.settings import settings
from app.utils.langfuse_client import langfuse_client
from app.utils.llm_client import get_llm_client
from app.tools.get_poi_info import get_poi_info

logger = structlog.get_logger(__name__)


@langfuse_client.observe()
def planner_node(state: TripPlannerState) -> TripPlannerState:
    """
    Planner Agent: Generates itinerary structure from user preferences or modifies existing itinerary.

    Args:
        state: Current TripPlannerState

    Returns:
        Updated state with itinerary_draft
    """
    user_prefs = state["user_preferences"]
    current_intent = state.get("current_intent", "plan_trip")

    # Handle change_plan intent - modify existing itinerary
    if current_intent == "change_plan" and state["itinerary_draft"]:
        return _modify_itinerary(state)
    
    # Handle plan_trip intent - generate new itinerary
    if not user_prefs:
        logger.warning("planner_no_preferences")
        # Edge case E4: Incomplete information - ask for clarification
        state["messages"].append(AIMessage(
            content="To plan your trip, I need some information. Please tell me:\n"
                    "- Which city would you like to visit?\n"
                    "- What are your travel dates?\n"
                    "- How many travelers will there be?\n"
                    "- What are your interests (e.g., history, museums, nature)?"
        ))
        return state
    
    # Edge case E4: Check for incomplete information
    clarifying_questions = []
    if not user_prefs.city:
        clarifying_questions.append("- Which city would you like to visit?")
    if not user_prefs.start_date or not user_prefs.end_date:
        clarifying_questions.append("- What are your travel dates?")
    # Don't require interests - use default if not provided
    # if not user_prefs.interests:
    #     clarifying_questions.append("- What are your interests (e.g., history, museums, nature)?")

    if clarifying_questions:
        state["messages"].append(AIMessage(
            content="I need a bit more information:\n" + "\n".join(clarifying_questions)
        ))
        return state
    
    # Edge case E1: Check for conflicting preferences
    if user_prefs.budget and user_prefs.budget.level == "low" and "luxury" in user_prefs.interests:
        state["messages"].append(AIMessage(
            content="I notice you're interested in luxury experiences but have a low budget. "
                    "Would you like me to prioritize luxury within your budget or suggest budget-friendly alternatives?"
        ))
        # For now, proceed with budget-friendly approach
        logger.info("planner_conflicting_preferences", budget="low", interests=user_prefs.interests)
    
    # Calculate number of days
    from datetime import timedelta
    days = (user_prefs.end_date - user_prefs.start_date).days + 1
    
    if days <= 0:
        logger.error("planner_invalid_dates", start=user_prefs.start_date, end=user_prefs.end_date)
        state["messages"].append(AIMessage(
            content="The end date must be after the start date. Please provide valid dates."
        ))
        return state
    
    # Fetch POI from OpenTripMap for planning
    poi_results = get_poi_info(
        city=user_prefs.city,
        categories=user_prefs.interests,
        limit=min(days * 2, 20),  # 2 activities per day, max 20 (OpenTripMap limit)
        budget_level=user_prefs.budget.level
    )
    
    # Generate itinerary using real POI data
    itinerary = []
    poi_index = 0
    
    # Deduplicate POIs by name to avoid duplicate activities
    seen_poi_names = set()
    unique_pois = []
    for poi in poi_results:
        if poi.name not in seen_poi_names:
            seen_poi_names.add(poi.name)
            unique_pois.append(poi)
    
    # Adjust number of days based on available POIs (2 activities per day)
    activities_per_day = 2
    max_days = len(unique_pois) // activities_per_day
    actual_days = min(days, max_days)
    
    if actual_days < days:
        logger.warning("planner_insufficient_pois", available_pois=len(unique_pois), requested_days=days, actual_days=actual_days)
    
    for day_num in range(1, actual_days + 1):
        current_date = user_prefs.start_date + timedelta(days=day_num - 1)

        # Get POI for this day (2 activities per day)
        day_pois = []
        for _ in range(activities_per_day):
            if poi_index < len(unique_pois):
                day_pois.append(unique_pois[poi_index])
                poi_index += 1

        # Create activities and meals scheduled by time
        activities = []

        # Breakfast at 08:00
        activities.append(Activity(
            name="Breakfast",
            description="Breakfast at hotel",
            category="restaurant",
            start_time="08:00",
            duration_minutes=60,
            coordinates=None,
            estimated_cost=500,
            source="planner"
        ))

        # Morning activity at 10:00
        if day_pois and len(day_pois) > 0:
            activities.append(Activity(
                name=day_pois[0].name,
                description=day_pois[0].description,
                category=day_pois[0].category,
                start_time="10:00",
                duration_minutes=120,
                coordinates=day_pois[0].coordinates,
                estimated_cost=day_pois[0].estimated_cost.amount if day_pois[0].estimated_cost else None,
                source=day_pois[0].source
            ))

        # Lunch at 13:00
        activities.append(Activity(
            name="Lunch",
            description="Lunch at local restaurant",
            category="restaurant",
            start_time="13:00",
            duration_minutes=90,
            coordinates=None,
            estimated_cost=1000,
            source="planner"
        ))

        # Afternoon activity at 15:00
        if day_pois and len(day_pois) > 1:
            activities.append(Activity(
                name=day_pois[1].name,
                description=day_pois[1].description,
                category=day_pois[1].category,
                start_time="15:00",
                duration_minutes=120,
                coordinates=day_pois[1].coordinates,
                estimated_cost=day_pois[1].estimated_cost.amount if day_pois[1].estimated_cost else None,
                source=day_pois[1].source
            ))

        # Dinner at 19:00
        activities.append(Activity(
            name="Dinner",
            description="Dinner at local restaurant",
            category="restaurant",
            start_time="19:00",
            duration_minutes=90,
            coordinates=None,
            estimated_cost=1500,
            source="planner"
        ))

        day_plan = DayPlan(
            day_number=day_num,
            date=current_date,
            activities=activities,
            meals=[],  # Meals are now part of activities
            accommodation=None,
            notes=None
        )
        itinerary.append(day_plan)
    
    state["itinerary_draft"] = itinerary
    logger.info(
        "planner_opentripmap_generated",
        days=len(itinerary),
        poi_count=len(poi_results) if isinstance(poi_results, list) else 0
    )
    
    # Add AI message with summary
    summary = f"Created {days}-day itinerary for {user_prefs.city} with {user_prefs.interests} interests."
    state["messages"].append(AIMessage(content=summary))
    
    return state


def _modify_itinerary(state: TripPlannerState) -> TripPlannerState:
    """
    Modify existing itinerary based on user change request using OpenTripMap.

    Args:
        state: Current TripPlannerState with existing itinerary_draft

    Returns:
        Updated state with modified itinerary_draft
    """
    from datetime import timedelta
    import re

    # Get the last user message
    last_message = state["messages"][-1]
    if not isinstance(last_message, HumanMessage):
        return state

    change_request = last_message.content.lower()
    logger.info("planner_change_plan", request=change_request[:100])

    # Parse the change request
    # Example: "change day 2 to include more restaurants"
    # Example: "remove the museum from day 1"
    # Example: "add a park to the third day"

    modified = False
    itinerary = state["itinerary_draft"]
    user_prefs = state["user_preferences"]

    # Check for day number in request
    day_match = re.search(r'day\s*(\d+)', change_request)
    if day_match:
        day_num = int(day_match.group(1))

        # Find the day
        for day_plan in itinerary:
            if day_plan.day_number == day_num:
                # Check for "add" or "include"
                if any(word in change_request for word in ["add", "include", "more"]):
                    # Add activity based on category mentioned
                    category_match = re.search(r'(restaurant|museum|park|shop|activity)', change_request)
                    if category_match:
                        category = category_match.group(1)
                        # Fetch new POI from OpenTripMap
                        poi_results = get_poi_info(
                            city=user_prefs.city,
                            categories=[category],
                            limit=1,
                            budget_level=user_prefs.budget.level
                        )
                        
                        if isinstance(poi_results, list) and poi_results:
                            poi = poi_results[0]
                            new_activity = Activity(
                                name=poi.name,
                                description=poi.description,
                                category=poi.category,
                                start_time="15:00",
                                duration_minutes=120,
                                coordinates=poi.coordinates,
                                estimated_cost=poi.estimated_cost.amount if poi.estimated_cost else None,
                                source="opentripmap"
                            )
                            day_plan.activities.append(new_activity)
                            modified = True
                            logger.info("planner_added_activity", day=day_num, category=category)
                
                # Check for "remove"
                elif "remove" in change_request:
                    category_match = re.search(r'(restaurant|museum|park|shop|activity)', change_request)
                    if category_match:
                        category = category_match.group(1)
                        day_plan.activities = [
                            a for a in day_plan.activities 
                            if a.category != category
                        ]
                        modified = True
                        logger.info("planner_removed_activities", day=day_num, category=category)
    
    # If no specific day found, apply change to all days
    if not modified:
        if "more restaurants" in change_request:
            # Fetch additional restaurants from OpenTripMap
            poi_results = get_poi_info(
                city=user_prefs.city,
                categories=["restaurant"],
                limit=len(itinerary),
                budget_level=user_prefs.budget.level
            )
            
            for i, day_plan in enumerate(itinerary):
                if isinstance(poi_results, list) and i < len(poi_results):
                    poi = poi_results[i]
                    new_activity = Activity(
                        name=poi.name,
                        description=poi.description,
                        category=poi.category,
                        start_time="17:00",
                        duration_minutes=90,
                        coordinates=poi.coordinates,
                        estimated_cost=poi.estimated_cost.amount if poi.estimated_cost else None,
                        source="opentripmap"
                    )
                    day_plan.activities.append(new_activity)
            modified = True
            logger.info("planner_added_restaurants_all_days")
    
    if modified:
        summary = "Itinerary has been updated based on your request."
    else:
        summary = "I couldn't understand the change request. Please specify which day and what you'd like to change."
    
    state["messages"].append(AIMessage(content=summary))
    state["itinerary_draft"] = itinerary
    
    return state


def _generate_mock_itinerary(state: TripPlannerState, user_prefs: UserPreferences, days: int):
    """Generate mock itinerary as fallback."""
    from datetime import timedelta
    
    itinerary = []
    for i in range(days):
        current_date = user_prefs.start_date + timedelta(days=i)
        
        # Create mock activities based on interests
        activities = []
        for interest in user_prefs.interests[:3]:  # Top 3 interests
            activity = Activity(
                name=f"{interest.capitalize()} activity",
                description=f"Visit a {interest} in {user_prefs.city}",
                category=interest,
                start_time="10:00",
                duration_minutes=120,
                coordinates=None,
                estimated_cost=None,
                source="llm"
            )
            activities.append(activity)
        
        # Add meals
        meals = [
            Activity(
                name="Breakfast",
                description="Breakfast at hotel",
                category="restaurant",
                start_time="08:00",
                duration_minutes=60,
                coordinates=None,
                estimated_cost=500,
                source="llm"
            ),
            Activity(
                name="Lunch",
                description="Lunch at local restaurant",
                category="restaurant",
                start_time="13:00",
                duration_minutes=90,
                coordinates=None,
                estimated_cost=1000,
                source="llm"
            )
        ]
        
        day_plan = DayPlan(
            day_number=i + 1,
            date=current_date,
            activities=activities,
            meals=meals,
            accommodation=None,
            notes=None
        )
        itinerary.append(day_plan)
    
    state["itinerary_draft"] = itinerary
    
    logger.info(
        "planner_mock_generated",
        days=days,
        city=user_prefs.city,
        activities_total=sum(len(d.activities) + len(d.meals) for d in itinerary)
    )
