"""
OpenTripMap API client for POI data.

OpenTripMap provides free access to 10+ million tourist attractions worldwide.
Free tier: 5,000 requests/day, 10 requests/second for non-commercial use.
Data sources: OpenStreetMap, Wikidata, Wikipedia, Ministry of Culture (Russia)
"""
import requests
import structlog
from typing import Literal
from app.config.settings import settings

logger = structlog.get_logger(__name__)


class OpenTripMapClient:
    """OpenTripMap API client."""

    BASE_URL = "https://api.opentripmap.com/0.1"  # Base URL without language code
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.timeout = 10.0
    
    def get_places_in_radius(
        self,
        lat: float,
        lon: float,
        radius: int = 1000,
        kinds: str = "tourism",
        limit: int = 10,
        lang: str = "ru"  # Added Russian as default language
    ) -> list[dict]:
        """
        Get places within a radius from coordinates.

        Args:
            lat: Latitude
            lon: Longitude
            radius: Radius in meters (default 1000)
            kinds: Place types (tourism, culture, etc.)
            limit: Number of results
            lang: Language code (ru, en)

        Returns:
            List of place dictionaries
        """
        url = f"{self.BASE_URL}/{lang}/places/radius"

        params = {
            "radius": radius,
            "lon": lon,
            "lat": lat,
            "kinds": kinds,
            "limit": limit,
            "apikey": self.api_key,
            "format": "json"
        }
        
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            logger.info(
                "opentripmap_radius_search",
                lat=lat,
                lon=lon,
                results=len(data) if isinstance(data, list) else 0
            )
            
            return data if isinstance(data, list) else []
            
        except Exception as e:
            logger.error("opentripmap_radius_failed", error=str(e))
            return []
    
    def get_place_details(
        self,
        xid: str,
        lang: str = "ru"
    ) -> dict | None:
        """
        Get detailed information about a place by XID.

        Args:
            xid: Place XID (unique identifier)
            lang: Language code (ru, en)

        Returns:
            Place details dictionary or None
        """
        url = f"{self.BASE_URL}/{lang}/places/xid/{xid}"

        params = {"apikey": self.api_key}

        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            logger.info("opentripmap_details", xid=xid)

            return data

        except Exception as e:
            logger.error("opentripmap_details_failed", xid=xid, error=str(e))
            return None
    
    def get_city_coordinates(
        self,
        city_name: str,
        lang: str = "ru"
    ) -> tuple[float, float] | None:
        """
        Get coordinates for a city name.

        Args:
            city_name: City name
            lang: Language code

        Returns:
            Tuple of (lat, lon) or None
        """
        url = f"{self.BASE_URL}/{lang}/places/geoname"

        params = {
            "name": city_name,
            "apikey": self.api_key
        }

        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            # Handle different response formats
            if isinstance(data, list) and len(data) > 0:
                # List format
                first_item = data[0]
                if "point" in first_item:
                    point = first_item.get("point")
                    lat = point.get("lat")
                    lon = point.get("lon")
                elif "lat" in first_item and "lon" in first_item:
                    lat = first_item.get("lat")
                    lon = first_item.get("lon")
                else:
                    return None
            elif isinstance(data, dict):
                # Single object format
                if "lat" in data and "lon" in data:
                    lat = data.get("lat")
                    lon = data.get("lon")
                else:
                    return None
            else:
                return None

            if lat is not None and lon is not None:
                logger.info("opentripmap_geoname", city=city_name, lat=lat, lon=lon)
                return (lat, lon)

            return None

        except Exception as e:
            logger.error("opentripmap_geoname_failed", city=city_name, error=str(e))
            return None
    
    def search_places(
        self,
        query: str,
        lat: float,
        lon: float,
        radius: int = 10000,
        limit: int = 10,
        lang: str = "ru"
    ) -> list[dict]:
        """
        Search for places by query near location.

        Args:
            query: Search query
            lat: Center latitude
            lon: Center longitude
            radius: Search radius in meters
            limit: Number of results
            lang: Language code

        Returns:
            List of place dictionaries
        """
        url = f"{self.BASE_URL}/{lang}/places/autosuggest"

        params = {
            "name": query,
            "radius": radius,
            "lon": lon,
            "lat": lat,
            "limit": limit,
            "apikey": self.api_key
        }

        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            logger.info(
                "opentripmap_search",
                query=query,
                results=len(data) if isinstance(data, list) else 0
            )

            return data if isinstance(data, list) else []

        except Exception as e:
            logger.error("opentripmap_search_failed", query=query, error=str(e))
            return []


def get_opentripmap_client() -> OpenTripMapClient | None:
    """
    Factory function to get OpenTripMap client.
    
    Returns:
        OpenTripMapClient instance or None if API key not configured
    """
    if not settings.OPENTRIPMAP_API_KEY or settings.OPENTRIPMAP_API_KEY == "your-opentripmap-api-key-here":
        logger.warning("opentripmap_not_configured")
        return None
    
    return OpenTripMapClient(settings.OPENTRIPMAP_API_KEY)


# Global client instance
opentripmap_client = get_opentripmap_client()
