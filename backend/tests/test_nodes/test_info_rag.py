import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.agents.nodes.info_rag import info_rag_node
from langchain_core.messages import AIMessage
from app.models.schemas import TripPlannerState, DayPlan, Activity, UserPreferences, TravelerGroup, BudgetInfo
from datetime import date, timedelta


class TestInfoRAG:
    """Test suite for info_rag node."""
    
    @pytest.mark.asyncio
    async def test_info_rag_node_enriches_activities(self):
        """Test info_rag enriches activities with POI data."""
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
                            coordinates=None,
                            estimated_cost=0,
                            source="llm"
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
        
        # Mock get_poi_info
        with patch('app.agents.nodes.info_rag.get_poi_info', new_callable=AsyncMock) as mock_poi:
            mock_poi.return_value = {
                "description": "Famous square in Moscow",
                "coordinates": (55.7539, 37.6208),
                "estimated_cost": 0
            }
            
            result = await info_rag_node(state)
            
            # Check that activity was enriched
            assert len(result["itinerary_draft"]) == 1
            activity = result["itinerary_draft"][0].activities[0]
            assert activity.description == "Famous square in Moscow"
            assert activity.coordinates == (55.7539, 37.6208)
    
    @pytest.mark.asyncio
    async def test_info_rag_node_handles_retrieval_failure(self):
        """Test info_rag handles retrieval failure gracefully."""
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
                            name="Unknown Place",
                            description="Test",
                            category="museum",
                            start_time="10:00",
                            duration_minutes=60,
                            coordinates=None,
                            estimated_cost=0,
                            source="llm"
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
        
        # Mock get_poi_info to return None (failure)
        with patch('app.agents.nodes.info_rag.get_poi_info', new_callable=AsyncMock) as mock_poi:
            mock_poi.return_value = None
            
            result = await info_rag_node(state)
            
            # Should set retrieval_degraded flag
            assert result["retrieval_degraded"] is True
