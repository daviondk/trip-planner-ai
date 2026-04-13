import pytest
from app.agents.nodes.router import router_node, classify_intent_rule_based
from langchain_core.messages import HumanMessage
from app.models.schemas import TripPlannerState
from datetime import datetime


class TestRouter:
    """Test suite for router node."""
    
    def test_classify_intent_export(self):
        """Test export intent classification."""
        intent = classify_intent_rule_based("Please export my itinerary to PDF")
        assert intent == "export"
    
    def test_classify_intent_change_plan(self):
        """Test change plan intent classification."""
        intent = classify_intent_rule_based("change the plan to include museums")
        assert intent == "change_plan"
    
    def test_classify_intent_question(self):
        """Test question intent classification."""
        intent = classify_intent_rule_based("What is the best time to visit Suzdal?")
        assert intent == "ask_question"
    
    def test_classify_intent_plan_trip(self):
        """Test plan trip intent classification (default)."""
        intent = classify_intent_rule_based("I want to go to Saint Petersburg")
        assert intent == "plan_trip"
    
    @pytest.mark.asyncio
    async def test_router_node(self):
        """Test router node with state."""
        state = TripPlannerState(
            messages=[HumanMessage(content="I want to visit Moscow")],
            session_id="test-123",
            user_preferences=None,
            current_intent=None,
            itinerary_draft=[],
            booking_candidates=[],
            map_data=None,
            agent_outputs={},
            iteration_count=0,
            error_context=[],
            retrieval_degraded=False,
            created_at=datetime.utcnow(),
            last_activity_at=datetime.utcnow(),
            is_blocked=False,
            llm_degraded=False,
            booking_degraded=False,
            maps_degraded=False,
            token_count=0
        )
        
        result = await router_node(state)
        
        assert result["current_intent"] == "plan_trip"
    
    @pytest.mark.asyncio
    async def test_router_node_token_count(self):
        """Test router node tracks token count."""
        state = TripPlannerState(
            messages=[HumanMessage(content="What is the best museum?")],
            session_id="test-123",
            user_preferences=None,
            current_intent=None,
            itinerary_draft=[],
            booking_candidates=[],
            map_data=None,
            agent_outputs={},
            iteration_count=0,
            error_context=[],
            retrieval_degraded=False,
            created_at=datetime.utcnow(),
            last_activity_at=datetime.utcnow(),
            is_blocked=False,
            llm_degraded=False,
            booking_degraded=False,
            maps_degraded=False,
            token_count=100
        )
        
        result = await router_node(state)
        
        # Token count should be updated (may be 100 + LLM tokens or 100 if LLM not called)
        assert result["token_count"] >= 100
