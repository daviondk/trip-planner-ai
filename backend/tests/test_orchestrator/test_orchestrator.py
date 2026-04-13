import pytest
from app.agents.orchestrator import truncate_context, route_after_validator
from app.models.schemas import TripPlannerState
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from datetime import date


class TestOrchestrator:
    """Test suite for orchestrator functions."""
    
    def test_truncate_context_with_priority(self):
        """Test context truncation with priority-based ordering."""
        messages = [
            SystemMessage(content="You are a travel planner assistant."),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there"),
            HumanMessage(content="Plan a trip"),
            AIMessage(content="Sure"),
            HumanMessage(content="To Moscow"),
            AIMessage(content="Great choice"),
            HumanMessage(content="a" * 100),  # Long message
            AIMessage(content="b" * 100),
            HumanMessage(content="c" * 100),
            AIMessage(content="d" * 100),
            HumanMessage(content="e" * 100),
        ]
        
        state = TripPlannerState(
            messages=messages,
            session_id="test",
            user_preferences=None,
            current_intent=None,
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
        
        result = truncate_context(state)
        
        # Should truncate to ~10 messages with priority
        assert len(result["messages"]) <= 10
        # System message should be preserved
        assert any(isinstance(m, SystemMessage) for m in result["messages"])
    
    def test_route_after_validator_no_errors(self):
        """Test routing when no validation errors."""
        state = TripPlannerState(
            messages=[],
            session_id="test",
            user_preferences=None,
            current_intent=None,
            itinerary_draft=[],
            booking_candidates=[],
            map_data=None,
            agent_outputs={},
            iteration_count=0,
            error_context=[],  # No errors
            retrieval_degraded=False,
            is_blocked=False,
            llm_degraded=False,
            booking_degraded=False,
            maps_degraded=False,
            token_count=0,
            created_at=date.today(),
            last_activity_at=date.today()
        )
        
        result = route_after_validator(state)
        
        # Should route to responder
        assert result == "responder"
    
    def test_route_after_validator_with_errors(self):
        """Test routing when validation errors exist."""
        state = TripPlannerState(
            messages=[],
            session_id="test",
            user_preferences=None,
            current_intent=None,
            itinerary_draft=[],
            booking_candidates=[],
            map_data=None,
            agent_outputs={},
            iteration_count=0,
            error_context=["Missing activities"],  # Has errors
            retrieval_degraded=False,
            is_blocked=False,
            llm_degraded=False,
            booking_degraded=False,
            maps_degraded=False,
            token_count=0,
            created_at=date.today(),
            last_activity_at=date.today()
        )
        
        result = route_after_validator(state)
        
        # Should route to planner for retry
        assert result == "planner"
    
    def test_route_after_validator_token_limit(self):
        """Test routing when token limit is exceeded."""
        state = TripPlannerState(
            messages=[],
            session_id="test",
            user_preferences=None,
            current_intent=None,
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
            token_count=60000,  # Exceeds MAX_SESSION_TOKENS (50000)
            created_at=date.today(),
            last_activity_at=date.today()
        )
        
        result = route_after_validator(state)
        
        # Should route to responder due to token limit
        assert result == "responder"
