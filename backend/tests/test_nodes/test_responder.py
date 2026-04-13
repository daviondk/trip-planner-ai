import pytest
from langchain_core.messages import AIMessage, HumanMessage
from app.models.schemas import TripPlannerState, UserPreferences, TravelerGroup, BudgetInfo, DayPlan, Activity
from app.agents.nodes.responder import responder_node
from datetime import date, timedelta


class TestResponder:
    """Test suite for responder node."""
    
    def test_responder_node_generates_response(self):
        """Test responder generates response from itinerary."""
        state = TripPlannerState(
            messages=[HumanMessage(content="Plan a trip to Moscow")],
            session_id="test-123",
            user_preferences=UserPreferences(
                city="Moscow",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=2),
                travelers=TravelerGroup(adults=2),
                budget=BudgetInfo(level="medium"),
                interests=["history", "museums"]
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
        
        result = responder_node(state)
        
        # Check that AI message was added
        assert len(result["messages"]) > 1
        assert isinstance(result["messages"][-1], AIMessage)
        assert "Moscow" in result["messages"][-1].content or "itinerary" in result["messages"][-1].content.lower()
    
    def test_responder_node_with_errors(self):
        """Test responder handles error context."""
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
            error_context=["Budget exceeded", "Missing activities"],
            retrieval_degraded=False,
            is_blocked=False,
            llm_degraded=False,
            booking_degraded=False,
            maps_degraded=False,
            token_count=0,
            created_at=date.today(),
            last_activity_at=date.today()
        )
        
        result = responder_node(state)
        
        # Check that response mentions errors (responder uses Russian)
        response = result["messages"][-1].content.lower()
        assert "error" in response or "issue" in response or "problem" in response or "проблем" in response or "ошибк" in response
