import pytest
from datetime import date, timedelta
from app.agents.nodes.planner import planner_node, _generate_mock_itinerary
from langchain_core.messages import HumanMessage
from app.models.schemas import TripPlannerState, UserPreferences, TravelerGroup, BudgetInfo


class TestPlanner:
    """Test suite for planner node."""
    
    @pytest.mark.asyncio
    async def test_planner_node_with_preferences(self):
        """Test planner with valid user preferences."""
        state = TripPlannerState(
            messages=[HumanMessage(content="Plan a trip to Moscow")],
            session_id="test-123",
            user_preferences=UserPreferences(
                city="Moscow",
                country="Russia",
                start_date=date.today() + timedelta(days=7),
                end_date=date.today() + timedelta(days=10),
                travelers=TravelerGroup(adults=2),
                budget=BudgetInfo(level="medium"),
                interests=["history", "culture"],
                constraints=["no car"]
            ),
            current_intent="plan_trip",
            itinerary_draft=[],
            booking_candidates=[],
            map_data=None,
            agent_outputs={},
            iteration_count=0,
            error_context=[],
            retrieval_degraded=False,
            is_blocked=False,
            llm_degraded=False,
            booking_degraded=False,
            maps_degraded=False,
            token_count=0,
            created_at=date.today(),
            last_activity_at=date.today()
        )
        
        result = await planner_node(state)
        
        # Check that itinerary was created (exact day count may vary based on date calculation)
        assert len(result["itinerary_draft"]) >= 2
        assert len(result["messages"]) > 1  # Original + summary
    
    @pytest.mark.asyncio
    async def test_planner_node_without_preferences(self):
        """Test planner without user preferences."""
        state = TripPlannerState(
            messages=[HumanMessage(content="Plan a trip")],
            session_id="test-123",
            user_preferences=None,
            current_intent="plan_trip",
            itinerary_draft=[],
            booking_candidates=[],
            map_data=None,
            agent_outputs={},
            iteration_count=0,
            error_context=[],
            retrieval_degraded=False,
            is_blocked=False,
            llm_degraded=False,
            booking_degraded=False,
            maps_degraded=False,
            token_count=0,
            created_at=date.today(),
            last_activity_at=date.today()
        )
        
        result = await planner_node(state)
        
        # Should not create itinerary without preferences
        assert len(result["itinerary_draft"]) == 0
    
    @pytest.mark.asyncio
    async def test_planner_node_invalid_dates(self):
        """Test planner with invalid date range."""
        state = TripPlannerState(
            messages=[HumanMessage(content="Plan a trip")],
            session_id="test-123",
            user_preferences=UserPreferences(
                city="Moscow",
                country="Russia",
                start_date=date.today() + timedelta(days=10),
                end_date=date.today() + timedelta(days=7),  # Invalid: end before start
                travelers=TravelerGroup(adults=2),
                budget=BudgetInfo(level="medium"),
                interests=["history"]
            ),
            current_intent="plan_trip",
            itinerary_draft=[],
            booking_candidates=[],
            map_data=None,
            agent_outputs={},
            iteration_count=0,
            error_context=[],
            retrieval_degraded=False,
            is_blocked=False,
            llm_degraded=False,
            booking_degraded=False,
            maps_degraded=False,
            token_count=0,
            created_at=date.today(),
            last_activity_at=date.today()
        )
        
        result = await planner_node(state)
        
        # Should not create itinerary with invalid dates
        assert len(result["itinerary_draft"]) == 0
    
    def test_generate_mock_itinerary(self):
        """Test mock itinerary generation."""
        state = TripPlannerState(
            messages=[],
            session_id="test",
            user_preferences=UserPreferences(
                city="Moscow",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=2),
                travelers=TravelerGroup(adults=2),
                budget=BudgetInfo(level="medium"),
                interests=["history", "museums"]
            ),
            current_intent="plan_trip",
            itinerary_draft=[],
            booking_candidates=[],
            map_data=None,
            agent_outputs={},
            iteration_count=0,
            error_context=[],
            retrieval_degraded=False,
            is_blocked=False,
            llm_degraded=False,
            booking_degraded=False,
            maps_degraded=False,
            token_count=0,
            created_at=date.today(),
            last_activity_at=date.today()
        )
        
        _generate_mock_itinerary(state, state["user_preferences"], 2)
        
        assert len(state["itinerary_draft"]) == 2
        assert state["itinerary_draft"][0].day_number == 1
        assert len(state["itinerary_draft"][0].activities) > 0
        assert len(state["itinerary_draft"][0].meals) > 0
