import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.agents.nodes.mapper import mapper_node
from app.models.schemas import TripPlannerState, DayPlan, Activity, UserPreferences, TravelerGroup, BudgetInfo
from datetime import date, timedelta


class TestMapper:
    """Test suite for mapper node."""
    
    @pytest.mark.asyncio
    async def test_mapper_node_generates_map_data(self):
        """Test mapper node generates map data from itinerary."""
        state = TripPlannerState(
            messages=[],
            session_id="test-123",
            user_preferences=UserPreferences(
                city="Moscow",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=1),
                travelers=TravelerGroup(adults=2),
                budget=BudgetInfo(level="medium")
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
                            coordinates=(55.7539, 37.6208),
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
        
        # Mock build_route
        with patch('app.agents.nodes.mapper.build_route', new_callable=AsyncMock) as mock_route:
            mock_route.return_value = {
                "waypoints": [(55.7539, 37.6208)],
                "distance_km": 5.0
            }
            
            result = await mapper_node(state)
            
            # Check that map data was generated
            assert result["map_data"] is not None
            assert result["map_data"]["waypoints"] == [(55.7539, 37.6208)]
    
    @pytest.mark.asyncio
    async def test_mapper_node_handles_insufficient_waypoints(self):
        """Test mapper node handles insufficient waypoints."""
        state = TripPlannerState(
            messages=[],
            session_id="test-123",
            user_preferences=UserPreferences(
                city="Moscow",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=1),
                travelers=TravelerGroup(adults=2),
                budget=BudgetInfo(level="medium")
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
                            coordinates=None,  # No coordinates
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
        
        result = await mapper_node(state)
        
        # Should set maps_degraded flag
        assert result["maps_degraded"] is True
