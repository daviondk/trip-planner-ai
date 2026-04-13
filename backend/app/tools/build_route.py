from typing import Literal
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.config.settings import settings
from app.models.schemas import Waypoint, RouteResult, RouteLeg, ToolError, ToolErrorType
from app.middleware.circuit_breaker import with_circuit_breaker
from app.utils.openrouteservice_client import ors_client

logger = structlog.get_logger(__name__)


class RouteBuildError(Exception):
    """Custom exception for route building errors."""
    pass


def _validate_route_params(
    waypoints: list[Waypoint],
    transport_mode: str
) -> None:
    """Validate route building parameters."""
    if not waypoints or len(waypoints) < 2:
        raise ValueError("At least 2 waypoints required")
    if len(waypoints) > 25:
        raise ValueError("Maximum 25 waypoints allowed")
    if transport_mode not in ["driving", "walking", "transit"]:
        raise ValueError("Transport mode must be driving, walking, or transit")
    
    for wp in waypoints:
        if not wp.name or len(wp.name) > 100:
            raise ValueError("Invalid waypoint name")
        if not wp.coordinates:
            raise ValueError("Waypoint coordinates required")
        lat, lon = wp.coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            raise ValueError("Invalid coordinates")


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=2),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    reraise=True
)
@with_circuit_breaker("maps_api")
def _fetch_route_from_api(
    waypoints: list[Waypoint],
    transport_mode: str,
    optimize_order: bool
) -> RouteResult:
    """
    Fetch route from OpenRouteService Directions API.
    
    Falls back to mock implementation if API call fails or no API key.
    """
    import random
    
    # Try OpenRouteService API
    if settings.OPENROUTESERVICE_API_KEY:
        # Convert waypoints to ORS format [lon, lat]
        coordinates = [
            [wp.coordinates[1], wp.coordinates[0]]  # ORS expects [lon, lat]
            for wp in waypoints
        ]

        response = ors_client.get_directions(
            coordinates=coordinates,
            profile=transport_mode,
            optimize=optimize_order
        )
        
        if response and "routes" in response and len(response["routes"]) > 0:
            route = response["routes"][0]
            summary = route.get("summary", {})
            
            total_distance = summary.get("distance", 0) / 1000  # Convert to km
            total_duration = summary.get("duration", 0) / 60  # Convert to minutes
            
            # Build legs from segments
            legs = []
            segments = route.get("segments", [])
            for i, segment in enumerate(segments):
                legs.append(RouteLeg(
                    start=waypoints[i].name,
                    end=waypoints[i + 1].name,
                    distance_km=segment.get("distance", 0) / 1000,
                    duration_minutes=segment.get("duration", 0) / 60,
                    transport_mode=transport_mode
                ))
            
            # Get polyline from geometry
            geometry = route.get("geometry", "")
            
            # Build map URL (fallback to Google Maps for display)
            map_url = f"https://maps.google.com/?q={','.join([f'{wp.coordinates[0]},{wp.coordinates[1]}' for wp in waypoints])}"
            
            return RouteResult(
                total_distance_km=total_distance,
                total_duration_minutes=int(total_duration),
                legs=legs,
                polyline=geometry,
                map_url=map_url
            )
    
    # Fallback to mock implementation
    logger.warning("using_mock_route_fallback")
    total_distance = sum(
        random.uniform(1, 10) for _ in range(len(waypoints) - 1)
    )
    total_duration = int(total_distance * 10)
    
    legs = []
    for i in range(len(waypoints) - 1):
        legs.append(RouteLeg(
            start=waypoints[i].name,
            end=waypoints[i + 1].name,
            distance_km=random.uniform(1, 10),
            duration_minutes=random.randint(10, 30),
            transport_mode=transport_mode
        ))
    
    polyline = "mock_encoded_polyline_string"
    map_url = f"https://maps.google.com/?q={','.join([f'{wp.coordinates[0]},{wp.coordinates[1]}' for wp in waypoints])}"
    
    return RouteResult(
        total_distance_km=total_distance,
        total_duration_minutes=total_duration,
        legs=legs,
        polyline=polyline,
        map_url=map_url
    )


def build_route(
    waypoints: list[Waypoint],
    transport_mode: Literal["driving", "walking", "transit"] = "driving",
    optimize_order: bool = False
) -> RouteResult | ToolError:
    """
    Build a route between multiple waypoints.
    
    Args:
        waypoints: List of waypoints with coordinates
        transport_mode: Mode of transport (driving, walking, transit)
        optimize_order: Whether to optimize waypoint order
    
    Returns:
        RouteResult or ToolError on failure
    """
    try:
        # Validate parameters
        _validate_route_params(waypoints, transport_mode)
        
        # Fetch route from API
        route = _fetch_route_from_api(
            waypoints=waypoints,
            transport_mode=transport_mode,
            optimize_order=optimize_order
        )
        
        logger.info(
            "route_built",
            waypoints_count=len(waypoints),
            transport_mode=transport_mode,
            total_distance_km=route.total_distance_km,
            total_duration_minutes=route.total_duration_minutes
        )
        
        return route
        
    except ValueError as e:
        logger.warning("invalid_route_params", error=str(e))
        return ToolError(
            error_type=ToolErrorType.INVALID_PARAMS,
            message=str(e),
            retryable=False,
            tool_name="build_route"
        )
    except httpx.TimeoutException:
        logger.error("route_build_timeout")
        return ToolError(
            error_type=ToolErrorType.API_TIMEOUT,
            message="Route building API timeout",
            retryable=True,
            tool_name="build_route"
        )
    except httpx.HTTPStatusError as e:
        logger.error("route_build_api_error", status_code=e.response.status_code)
        return ToolError(
            error_type=ToolErrorType.API_ERROR,
            message=f"Route building API error: {e.response.status_code}",
            retryable=True,
            tool_name="build_route"
        )
    except Exception as e:
        if "Circuit breaker" in str(e):
            logger.error("route_build_circuit_open")
            return ToolError(
                error_type=ToolErrorType.CIRCUIT_OPEN,
                message="Route building service temporarily unavailable",
                retryable=False,
                tool_name="build_route"
            )
        logger.error("route_build_internal_error", error=str(e))
        return ToolError(
            error_type=ToolErrorType.INTERNAL_ERROR,
            message="Internal error in route building",
            retryable=False,
            tool_name="build_route"
        )
