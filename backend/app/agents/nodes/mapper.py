import structlog
from app.models.schemas import TripPlannerState, Waypoint
from app.tools.build_route import build_route
from app.utils.langfuse_client import langfuse_client

logger = structlog.get_logger(__name__)


@langfuse_client.observe()
def mapper_node(state: TripPlannerState) -> TripPlannerState:
    """
    Mapper Agent: Generates map data and routes for the itinerary.

    Args:
        state: Current TripPlannerState

    Returns:
        Updated state with map_data
    """
    itinerary = state["itinerary_draft"]
    user_prefs = state["user_preferences"]

    if not itinerary:
        logger.warning("mapper_no_itinerary")
        return state

    degraded = False

    # Collect all coordinates from activities
    waypoints = []
    for day_plan in itinerary:
        for activity in day_plan.activities:
            if activity.coordinates:
                waypoints.append(Waypoint(
                    name=activity.name,
                    coordinates=activity.coordinates
                ))

    # Build route if we have enough waypoints
    map_data = None
    if len(waypoints) >= 2:
        try:
            route_result = build_route(
                waypoints=waypoints[:10],  # Limit to 10 waypoints
                transport_mode="driving",
                optimize_order=False
            )
            
            if isinstance(route_result, dict) and "error_type" in route_result:
                degraded = True
            else:
                from app.models.schemas import MapData
                map_data = MapData(
                    polylines=[route_result.polyline],
                    center_coordinates=waypoints[0].coordinates,
                    zoom_level=12,
                    map_url=route_result.map_url
                )
                
        except Exception as e:
            logger.error("mapper_route_error", error=str(e))
            degraded = True
    else:
        logger.info("mapper_insufficient_waypoints", count=len(waypoints))
    
    state["map_data"] = map_data
    state["maps_degraded"] = degraded
    
    logger.info(
        "mapper_processed",
        waypoints_count=len(waypoints),
        degraded=degraded,
        has_map_data=map_data is not None
    )
    
    return state
