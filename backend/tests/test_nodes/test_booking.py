import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.agents.nodes.booking import booking_node
from app.models.schemas import TripPlannerState, UserPreferences, TravelerGroup, BudgetInfo
from datetime import date, timedelta


class TestBooking:
    """Test suite for booking node."""
    
    @pytest.mark.asyncio
    async def test_booking_node_searches_hotels(self):
        """Test booking node searches for hotels."""
        state = TripPlannerState(
            messages=[],
            session_id="test-123",
            user_preferences=UserPreferences(
                city="Moscow",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=3),
                travelers=TravelerGroup(adults=2),
                budget=BudgetInfo(level="medium")
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
        
        # Mock search_hotels
        with patch('app.agents.nodes.booking.search_hotels', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [
                {"name": "Hotel Moscow", "price": 5000, "rating": 4.5}
            ]
            
            result = await booking_node(state)
            
            # Check that booking candidates were added
            assert len(result["booking_candidates"]) > 0
            assert result["booking_candidates"][0]["name"] == "Hotel Moscow"
    
    @pytest.mark.asyncio
    async def test_booking_node_handles_search_failure(self):
        """Test booking node handles search failure gracefully."""
        state = TripPlannerState(
            messages=[],
            session_id="test-123",
            user_preferences=UserPreferences(
                city="Moscow",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=3),
                travelers=TravelerGroup(adults=2),
                budget=BudgetInfo(level="medium")
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
        
        # Mock search_hotels to raise exception
        with patch('app.agents.nodes.booking.search_hotels', new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = Exception("Search failed")
            
            result = await booking_node(state)
            
            # Should set booking_degraded flag
            assert result["booking_degraded"] is True
