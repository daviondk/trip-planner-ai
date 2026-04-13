from typing import Literal
import structlog
import time
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from app.models.schemas import TripPlannerState
from app.agents.nodes import (
    sanitizer,
    router,
    preferences_extractor,
    planner,
    booking,
    mapper,
    validator,
    responder
    # info_rag  # Temporarily disabled - using Wikipedia tool instead
)
from app.utils.metrics import (
    orchestrator_invocations_total,
    orchestrator_duration_seconds,
    orchestrator_iterations_total,
    orchestrator_degraded_total,
    session_expired_total
)

logger = structlog.get_logger(__name__)

# Constants
MAX_ITERATIONS = 3
MAX_SESSION_TOKENS = 50000
SESSION_TIMEOUT_SECONDS = 30
CONTEXT_BUDGET_TOKENS = 4000


def route_after_sanitizer(state: TripPlannerState) -> Literal["router", "reject_response"]:
    """Route after sanitizer: check if input was blocked."""
    if state.get("is_blocked", False):
        return "reject_response"
    return "router"


def route_after_router(state: TripPlannerState) -> Literal["preferences_extractor", "responder"]:
    """Route after router: based on intent."""
    intent = state.get("current_intent", "ask_question")
    
    if intent == "export":
        return "responder"
    elif intent == "ask_question":
        return "responder"  # Using Wikipedia tool instead of RAG
    else:  # plan_trip or change_plan
        return "preferences_extractor"


def route_after_validator(state: TripPlannerState) -> Literal["planner", "responder"]:
    """Route after validator: retry or finish."""
    # Check token limit
    if state.get("token_count", 0) >= MAX_SESSION_TOKENS:
        logger.warning("orchestrator_token_limit_exceeded", tokens=state.get("token_count", 0))
        orchestrator_degraded_total.labels(degradation_type="token_limit").inc()
        return "responder"
    
    error_context = state.get("error_context", [])
    iteration_count = state.get("iteration_count", 0)
    
    if error_context and iteration_count < MAX_ITERATIONS:
        logger.info("validator_retry", iteration=iteration_count, max=MAX_ITERATIONS)
        return "planner"
    
    return "responder"


def truncate_context(state: TripPlannerState) -> TripPlannerState:
    """
    Truncate messages to stay within context budget with priority-based truncation.
    
    Priority order (highest to lowest):
    1. System prompt (first message if it's a system message)
    2. Recent itinerary context (messages with itinerary data)
    3. Recent user messages
    4. Older messages
    
    Args:
        state: Current TripPlannerState
    
    Returns:
        Updated state with truncated messages
    """
    messages = state["messages"]
    
    if len(messages) <= 10:
        return state
    
    # Separate messages by type
    system_messages = [m for m in messages if hasattr(m, 'type') and m.type == 'system']
    user_messages = [m for m in messages if hasattr(m, 'type') and m.type == 'human']
    ai_messages = [m for m in messages if hasattr(m, 'type') and m.type == 'ai']
    
    # Priority: keep system message, last 5 user messages, last 3 AI messages
    truncated = []
    
    # Add system messages (highest priority)
    if system_messages:
        truncated.extend(system_messages[-1:])  # Keep only the most recent system message
    
    # Add recent user messages
    if user_messages:
        truncated.extend(user_messages[-5:])
    
    # Add recent AI messages
    if ai_messages:
        truncated.extend(ai_messages[-3:])
    
    # Sort by original order (approximately)
    truncated.sort(key=lambda m: messages.index(m))
    
    state["messages"] = truncated
    
    logger.info(
        "context_truncated",
        original=len(messages),
        truncated=len(truncated),
        system_count=len([m for m in truncated if hasattr(m, 'type') and m.type == 'system']),
        user_count=len([m for m in truncated if hasattr(m, 'type') and m.type == 'human']),
        ai_count=len([m for m in truncated if hasattr(m, 'type') and m.type == 'ai'])
    )
    
    return state


async def run_orchestrator(state: TripPlannerState, config: dict = None) -> TripPlannerState:
    """
    Run orchestrator with metrics and stop conditions.
    
    Args:
        state: Initial TripPlannerState
        config: LangGraph config
    
    Returns:
        Final TripPlannerState
    """
    start_time = time.time()
    
    try:
        # Track invocation
        intent = state.get("current_intent", "unknown")
        orchestrator_invocations_total.labels(intent=intent).inc()
        
        # Apply context budget
        state = truncate_context(state)
        
        # Run graph
        if config:
            result = await trip_planner_graph.ainvoke(state, config)
        else:
            result = await trip_planner_graph.ainvoke(state)
        
        # Track duration
        duration = time.time() - start_time
        orchestrator_duration_seconds.labels(intent=intent).observe(duration)
        
        # Track iterations
        orchestrator_iterations_total.labels(intent=intent).inc(result.get("iteration_count", 0))
        
        # Track degradations
        if result.get("retrieval_degraded"):
            orchestrator_degraded_total.labels(degradation_type="retrieval").inc()
        if result.get("llm_degraded"):
            orchestrator_degraded_total.labels(degradation_type="llm").inc()
        if result.get("booking_degraded"):
            orchestrator_degraded_total.labels(degradation_type="booking").inc()
        if result.get("maps_degraded"):
            orchestrator_degraded_total.labels(degradation_type="maps").inc()
        
        return result
        
    except Exception as e:
        logger.error("orchestrator_error", error=str(e))
        orchestrator_degraded_total.labels(degradation_type="error").inc()
        raise


def create_trip_planner_graph() -> StateGraph:
    """
    Create and compile the Trip Planner LangGraph.
    
    Returns:
        Compiled StateGraph ready for invocation
    """
    # Create the graph
    workflow = StateGraph(TripPlannerState)
    
    # Add nodes (planner and router are now async)
    workflow.add_node("sanitizer", sanitizer.sanitizer_node)
    workflow.add_node("router", router.router_node)
    workflow.add_node("preferences_extractor", preferences_extractor.preferences_extractor_node)
    workflow.add_node("planner", planner.planner_node)
    workflow.add_node("booking", booking.booking_node)
    workflow.add_node("mapper", mapper.mapper_node)
    workflow.add_node("validator", validator.validator_node)
    workflow.add_node("responder", responder.responder_node)
    workflow.add_node("reject_response", responder.responder_node)
    # workflow.add_node("info_rag", info_rag.info_rag_node)  # Temporarily disabled
    
    # Add edges
    workflow.add_edge(START, "sanitizer")
    
    # Conditional edge after sanitizer
    workflow.add_conditional_edges(
        "sanitizer",
        route_after_sanitizer,
        {
            "router": "router",
            "reject_response": "reject_response"
        }
    )
    
    # Conditional edge after router
    workflow.add_conditional_edges(
        "router",
        route_after_router,
        {
            "preferences_extractor": "preferences_extractor",
            "responder": "responder"
        }
    )
    
    # Planning cycle
    workflow.add_edge("preferences_extractor", "planner")
    workflow.add_edge("planner", "booking")
    workflow.add_edge("booking", "mapper")
    workflow.add_edge("mapper", "validator")
    
    # Conditional edge after validator
    workflow.add_conditional_edges(
        "validator",
        route_after_validator,
        {
            "planner": "planner",
            "responder": "responder"
        }
    )
    
    # End edges
    workflow.add_edge("responder", END)
    workflow.add_edge("reject_response", END)
    # workflow.add_edge("info_rag", "responder")  # Temporarily disabled
    
    # Compile with memory for checkpointing
    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)
    
    logger.info("graph_compiled")
    
    return app


# Global graph instance
trip_planner_graph = create_trip_planner_graph()
