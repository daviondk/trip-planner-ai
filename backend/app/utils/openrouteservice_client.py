"""
OpenRouteService client for directions API.
Free tier: 2000 requests/day
"""
import requests
import structlog
from typing import Literal
from app.config.settings import settings
from app.middleware.circuit_breaker import with_circuit_breaker

logger = structlog.get_logger(__name__)

# Profile mapping
PROFILE_MAP = {
    "driving": "driving-car",
    "walking": "foot-walking",
    "transit": "driving-public-transport",
}


class OpenRouteServiceClient:
    """Client for OpenRouteService Directions API."""

    def __init__(self):
        self.api_key = settings.OPENROUTESERVICE_API_KEY
        self.base_url = "https://api.openrouteservice.org"
        self.timeout = settings.OPENROUTESERVICE_TIMEOUT

    def _map_profile(self, transport_mode: str) -> str:
        """Map transport mode to ORS profile."""
        return PROFILE_MAP.get(transport_mode, "driving-car")

    def get_directions(
        self,
        coordinates: list[list[float]],
        profile: str = "driving",
        optimize: bool = False
    ) -> dict | None:
        """
        Get directions between waypoints.

        Args:
            coordinates: List of [lon, lat] pairs
            profile: Transport mode (driving, walking, transit)
            optimize: Whether to optimize waypoint order

        Returns:
            ORS response dict or None on error
        """
        if not self.api_key:
            logger.warning("openrouteservice_no_api_key")
            return None

        ors_profile = self._map_profile(profile)

        try:
            response = requests.post(
                f"{self.base_url}/v2/directions/{ors_profile}",
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8"
                },
                json={
                    "coordinates": coordinates,
                    "optimize": optimize
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

        except requests.Timeout:
            logger.error("openrouteservice_timeout")
            return None
        except requests.HTTPError as e:
            logger.error("openrouteservice_http_error", status_code=e.response.status_code)
            return None
        except Exception as e:
            logger.error("openrouteservice_error", error=str(e))
            return None


# Global client instance
ors_client = OpenRouteServiceClient()
