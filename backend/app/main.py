from contextlib import asynccontextmanager
from datetime import datetime
import time
import uuid
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
import structlog
from langchain_core.messages import HumanMessage

from app.config.settings import settings
from app.agents.orchestrator import trip_planner_graph
from app.models.schemas import TripPlannerState, UserPreferences, TravelerGroup, BudgetInfo
from app.middleware.circuit_breaker import _circuit_breakers
from app.utils.langfuse_client import langfuse_client
from app.utils.metrics import (
    http_requests_total,
    http_request_duration_seconds,
    active_sessions
)

logger = structlog.get_logger(__name__)

# In-memory session storage (PoC)
sessions: dict[str, TripPlannerState] = {}
startup_time = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    global startup_time
    startup_time = time.time()
    
    # Startup
    logger.info("application_startup")
    
    # Start session cleanup background task
    cleanup_task = asyncio.create_task(cleanup_expired_sessions())
    app.state.cleanup_task = cleanup_task
    
    yield
    
    # Shutdown
    logger.info("application_shutdown")
    langfuse_client.flush()
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Trip Planner AI",
    description="Multi-agent trip planning system",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


# Middleware for HTTP metrics
@app.middleware("http")
async def track_requests(request, call_next):
    """Track HTTP request metrics."""
    import time
    
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    http_requests_total.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    http_request_duration_seconds.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)
    
    return response


async def cleanup_expired_sessions():
    """Background task to clean up expired sessions."""
    while True:
        try:
            now = datetime.utcnow()
            expired_sessions = [
                session_id for session_id, state in sessions.items()
                if (now - state["last_activity_at"]).total_seconds() > settings.SESSION_TTL_SECONDS
            ]
            
            for session_id in expired_sessions:
                del sessions[session_id]
                logger.info("session_expired", session_id=session_id)
            
            await asyncio.sleep(300)  # Check every 5 minutes
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("cleanup_error", error=str(e))
            await asyncio.sleep(300)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    from app.middleware.circuit_breaker import CircuitState
    
    circuit_states = {
        name: cb.state.value
        for name, cb in _circuit_breakers.items()
    }
    
    return {
        "status": "healthy",
        "version": "0.1.0",
        "uptime_seconds": 0,  # TODO: track actual uptime
        "active_sessions": len(sessions),
        "circuit_breakers": circuit_states,
        "chromadb": "connected",  # TODO: actual check
        "langfuse": "connected"  # TODO: actual check
    }


# Update active sessions gauge periodically
@app.on_event("startup")
async def update_metrics():
    """Update metrics periodically."""
    while True:
        active_sessions.set(len(sessions))
        await asyncio.sleep(5)


@app.post("/api/chat")
async def chat(request: dict):
    """
    Main chat endpoint for trip planning.
    
    Args:
        request: JSON with 'message' and optional 'session_id'
    
    Returns:
        JSON with assistant response and session_id
    """
    message = request.get("message")
    session_id = request.get("session_id")
    
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    
    # Create or get session
    if not session_id or session_id not in sessions:
        session_id = str(uuid.uuid4())
        sessions[session_id] = TripPlannerState(
            messages=[],
            session_id=session_id,
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
            is_blocked=False
        )
        logger.info("session_created", session_id=session_id)
    
    # Update last activity
    state = sessions[session_id]
    state["last_activity_at"] = datetime.utcnow()
    
    # Add user message
    state["messages"].append(HumanMessage(content=message))
    
    # Run the graph
    try:
        config = {"configurable": {"thread_id": session_id}}
        result = await trip_planner_graph.ainvoke(state, config)
        
        # Update session state
        sessions[session_id] = result
        
        # Get last AI message
        last_message = result["messages"][-1]
        response = last_message.content
        
        logger.info(
            "chat_completed",
            session_id=session_id,
            message_length=len(response)
        )
        
        return {
            "response": response,
            "session_id": session_id,
            "intent": result.get("current_intent"),
            "has_itinerary": len(result.get("itinerary_draft", [])) > 0
        }
        
    except Exception as e:
        logger.error("chat_error", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/plan")
async def plan_trip(request: dict):
    """
    Explicit trip planning endpoint.
    
    Args:
        request: JSON with user preferences and optional session_id
    
    Returns:
        JSON with planned itinerary
    """
    session_id = request.get("session_id")
    prefs_data = request.get("preferences")
    
    if not prefs_data:
        raise HTTPException(status_code=400, detail="Preferences are required")
    
    # Create or get session
    if not session_id or session_id not in sessions:
        session_id = str(uuid.uuid4())
        sessions[session_id] = TripPlannerState(
            messages=[],
            session_id=session_id,
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
            is_blocked=False
        )
    
    # Parse preferences
    from datetime import date
    user_prefs = UserPreferences(
        city=prefs_data.get("city", ""),
        country=prefs_data.get("country"),
        start_date=date.fromisoformat(prefs_data.get("start_date", "")),
        end_date=date.fromisoformat(prefs_data.get("end_date", "")),
        travelers=TravelerGroup(
            adults=prefs_data.get("adults", 1),
            children=prefs_data.get("children", 0),
            children_ages=prefs_data.get("children_ages", [])
        ),
        budget=BudgetInfo(
            total=prefs_data.get("budget_total"),
            per_day=prefs_data.get("budget_per_day"),
            level=prefs_data.get("budget_level", "medium")
        ),
        interests=prefs_data.get("interests", []),
        constraints=prefs_data.get("constraints", []),
        accommodation_type=prefs_data.get("accommodation_type")
    )
    
    state = sessions[session_id]
    state["user_preferences"] = user_prefs
    state["current_intent"] = "plan_trip"
    state["last_activity_at"] = datetime.utcnow()
    
    # Add initial message
    state["messages"].append(HumanMessage(content=f"Plan a trip to {user_prefs.city}"))
    
    # Run the graph
    try:
        config = {"configurable": {"thread_id": session_id}}
        result = await trip_planner_graph.ainvoke(state, config)
        
        sessions[session_id] = result
        
        itinerary = result.get("itinerary_draft", [])
        
        logger.info(
            "plan_completed",
            session_id=session_id,
            days=len(itinerary)
        )
        
        return {
            "session_id": session_id,
            "itinerary": [day.model_dump() for day in itinerary],
            "booking_candidates": [opt.model_dump() for opt in result.get("booking_candidates", [])],
            "map_data": result.get("map_data").model_dump() if result.get("map_data") else None
        }
        
    except Exception as e:
        logger.error("plan_error", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Get current session state."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    state = sessions[session_id]
    
    # Extract map data if available
    map_data = None
    if state.get("map_data"):
        map_obj = state["map_data"]
        map_data = {
            "polylines": map_obj.polylines,
            "center_coordinates": map_obj.center_coordinates,
            "zoom_level": map_obj.zoom_level,
            "map_url": map_obj.map_url
        }
    
    return {
        "session_id": session_id,
        "created_at": state["created_at"].isoformat(),
        "last_activity_at": state["last_activity_at"].isoformat(),
        "current_intent": state.get("current_intent"),
        "has_itinerary": len(state.get("itinerary_draft", [])) > 0,
        "map_data": map_data,
        "token_count": state.get("token_count", 0)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
