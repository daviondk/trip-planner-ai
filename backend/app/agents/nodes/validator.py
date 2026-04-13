import structlog
from datetime import date, datetime, timedelta
from langchain_core.messages import AIMessage
from app.models.schemas import TripPlannerState
from app.utils.langfuse_client import langfuse_client

logger = structlog.get_logger(__name__)


def validate_coordinates(lat: float | None, lon: float | None) -> bool:
    """
    Validate latitude and longitude coordinates.
    
    Args:
        lat: Latitude coordinate
        lon: Longitude coordinate
    
    Returns:
        True if coordinates are valid, False otherwise
    """
    if lat is None or lon is None:
        return True  # Optional coordinates are ok
    
    # Latitude: -90 to 90
    # Longitude: -180 to 180
    return -90 <= lat <= 90 and -180 <= lon <= 180


def validate_date_range(start_date: date, end_date: date) -> tuple[bool, str]:
    """
    Validate date range.
    
    Args:
        start_date: Trip start date
        end_date: Trip end date
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    today = date.today()
    
    # Check if dates are in the past
    if end_date < today:
        return False, "End date is in the past"
    
    if start_date < today:
        return False, "Start date is in the past"
    
    # Check if end date is before start date
    if end_date < start_date:
        return False, "End date is before start date"
    
    # Check if trip is too long (> 30 days)
    if (end_date - start_date).days > 30:
        return False, "Trip duration exceeds 30 days"
    
    return True, ""


def calculate_total_cost(itinerary) -> float:
    """
    Calculate total estimated cost from itinerary.
    
    Args:
        itinerary: List of DayPlan objects
    
    Returns:
        Total estimated cost
    """
    total = 0.0
    for day_plan in itinerary:
        for activity in day_plan.activities:
            if activity.estimated_cost:
                total += activity.estimated_cost
        for meal in day_plan.meals:
            if meal.estimated_cost:
                total += meal.estimated_cost
    return total


@langfuse_client.observe()
def validator_node(state: TripPlannerState) -> TripPlannerState:
    """
    Validator node: Performs deterministic checks on itinerary quality.
    
    Args:
        state: Current TripPlannerState
    
    Returns:
        Updated state with error_context if validation fails
    """
    error_context = []
    itinerary = state["itinerary_draft"]
    user_prefs = state["user_preferences"]
    
    if not itinerary:
        logger.warning("validator_no_itinerary")
        return state
    
    # Verifiable check: Date range validation
    if user_prefs and user_prefs.start_date and user_prefs.end_date:
        dates_valid, date_error = validate_date_range(user_prefs.start_date, user_prefs.end_date)
        if not dates_valid:
            error_context.append(date_error)
    
    # Verifiable check: Budget adherence
    if user_prefs and user_prefs.budget and user_prefs.budget.total:
        total_cost = calculate_total_cost(itinerary)
        if total_cost > user_prefs.budget.total:
            error_context.append(f"Budget exceeded: {total_cost:.2f} > {user_prefs.budget.total}")
    
    # Verifiable check: Coordinate validation
    for day_plan in itinerary:
        for activity in day_plan.activities:
            if activity.coordinates:
                lat, lon = activity.coordinates
                if not validate_coordinates(lat, lon):
                    error_context.append(f"Invalid coordinates for activity: {activity.name}")
    
    # Check 1: All days have activities
    for day_plan in itinerary:
        if not day_plan.activities and not day_plan.meals:
            error_context.append(f"Day {day_plan.day_number} has no activities or meals")
    
    # Check 2: Sequential dates
    for i in range(len(itinerary) - 1):
        if itinerary[i + 1].date != itinerary[i].date + timedelta(days=1):
            error_context.append(f"Days {itinerary[i].day_number} and {itinerary[i + 1].day_number} are not sequential")
    
    # Check 3: Activities per day
    for day_plan in itinerary:
        if len(day_plan.activities) < 2:
            error_context.append(f"Day {day_plan.day_number} has fewer than 2 activities")
    
    # Check 4: City consistency
    cities = set()
    for day_plan in itinerary:
        for activity in day_plan.activities:
            if hasattr(activity, 'city') and activity.city:
                cities.add(activity.city)
    if len(cities) > 1:
        error_context.append(f"Multiple cities in itinerary: {', '.join(cities)}")
    
    # Check 5: Duplicate activities (exclude meals)
    activity_names = []
    for day_plan in itinerary:
        for activity in day_plan.activities:
            # Skip meals from duplicate check
            if activity.name not in ["Breakfast", "Lunch", "Dinner"]:
                activity_names.append(activity.name)

    from collections import Counter
    duplicates = [name for name, count in Counter(activity_names).items() if count > 1]
    if duplicates:
        error_context.append(f"Duplicate activities: {', '.join(duplicates)}")
    
    state["error_context"] = error_context
    state["iteration_count"] = state.get("iteration_count", 0) + 1
    
    if error_context:
        logger.warning("validator_failed", errors=error_context)
    else:
        logger.info("validator_passed")
    
    return state
