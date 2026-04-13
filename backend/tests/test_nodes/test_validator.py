import pytest
from datetime import date, timedelta
from app.agents.nodes.validator import validator_node
from app.models.schemas import TripPlannerState, UserPreferences, TravelerGroup, BudgetInfo, DayPlan, Activity


class TestValidator:
    """Test suite for validator node."""
    
    def test_validator_valid_itinerary(self):
        """Test validator with valid itinerary."""
        state = TripPlannerState(
            messages=[],
            session_id="test-123",
            user_preferences=UserPreferences(
                city="Moscow",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=2),
                travelers=TravelerGroup(adults=2),
                budget=BudgetInfo(total=10000)
            ),
            current_intent="plan_trip",
            itinerary_draft=[
                DayPlan(
                    day_number=1,
                    date=date.today(),
                    activities=[
                        Activity(
                            name="Red Square",
                            description="Visit Red Square",
                            category="museum",
                            start_time="10:00",
                            duration_minutes=60,
                            coordinates=None,
                            estimated_cost=0,
                            source="rag"
                        ),
                        Activity(
                            name="Kremlin",
                            description="Visit Kremlin",
                            category="museum",
                            start_time="12:00",
                            duration_minutes=60,
                            coordinates=None,
                            estimated_cost=0,
                            source="rag"
                        )
                    ],
                    meals=[],
                    accommodation=None,
                    notes=None
                )
            ],
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
        
        result = validator_node(state)
        
        # Should have no errors
        assert len(result["error_context"]) == 0
        assert result["iteration_count"] == 1
    
    def test_validator_missing_activities(self):
        """Test validator with day without activities."""
        state = TripPlannerState(
            messages=[],
            session_id="test-123",
            user_preferences=UserPreferences(
                city="Moscow",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=1),
                travelers=TravelerGroup(adults=2),
                budget=BudgetInfo(total=10000)
            ),
            current_intent="plan_trip",
            itinerary_draft=[
                DayPlan(
                    day_number=1,
                    date=date.today(),
                    activities=[],  # No activities
                    meals=[],
                    accommodation=None,
                    notes=None
                )
            ],
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
        
        result = validator_node(state)
        
        # Should have error about no activities
        assert len(result["error_context"]) > 0
        assert "no activities" in result["error_context"][0].lower()
    
    def test_validator_budget_exceeded(self):
        """Test validator with budget exceeded."""
        state = TripPlannerState(
            messages=[],
            session_id="test-123",
            user_preferences=UserPreferences(
                city="Moscow",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=1),
                travelers=TravelerGroup(adults=2),
                budget=BudgetInfo(total=100)  # Low budget
            ),
            current_intent="plan_trip",
            itinerary_draft=[
                DayPlan(
                    day_number=1,
                    date=date.today(),
                    activities=[
                        Activity(
                            name="Expensive Activity",
                            description="Very expensive",
                            category="museum",
                            start_time="10:00",
                            duration_minutes=60,
                            coordinates=None,
                            estimated_cost=10000,  # Exceeds budget
                            source="rag"
                        )
                    ],
                    meals=[],
                    accommodation=None,
                    notes=None
                )
            ],
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
        
        result = validator_node(state)
        
        # Should have error about budget
        assert len(result["error_context"]) > 0
        assert any("budget" in error.lower() for error in result["error_context"])
    
    def test_validator_duplicate_activities(self):
        """Test validator with duplicate activities."""
        activity = Activity(
            name="Red Square",
            description="Visit Red Square",
            category="museum",
            start_time="10:00",
            duration_minutes=60,
            coordinates=None,
            estimated_cost=0,
            source="rag"
        )
        
        state = TripPlannerState(
            messages=[],
            session_id="test-123",
            user_preferences=UserPreferences(
                city="Moscow",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=1),
                travelers=TravelerGroup(adults=2),
                budget=BudgetInfo(total=10000)
            ),
            current_intent="plan_trip",
            itinerary_draft=[
                DayPlan(
                    day_number=1,
                    date=date.today(),
                    activities=[activity, activity],  # Duplicate
                    meals=[],
                    accommodation=None,
                    notes=None
                )
            ],
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
        
        result = validator_node(state)
        
        # Should have error about duplicates
        assert len(result["error_context"]) > 0
        assert "duplicate" in result["error_context"][0].lower()
