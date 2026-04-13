"""SerpApi client for Google Hotels and Google Flights APIs.

SerpApi provides free access to Google Hotels and Google Flights search results.
Free tier: 100 searches/month (check https://serpapi.com/ for current pricing).

Documentation:
- Google Hotels: https://serpapi.com/google-hotels-api
- Google Flights: https://serpapi.com/google-flights-api
"""

import httpx
from typing import Any
from app.config.settings import settings
import structlog

logger = structlog.get_logger(__name__)


class SerpApiClient:
    """Client for SerpApi Google Hotels and Flights APIs."""
    
    BASE_URL = "https://serpapi.com/search"
    
    def __init__(self):
        self.api_key = settings.SERPAPI_API_KEY
        self.timeout = settings.SERPAPI_TIMEOUT
    
    async def search_hotels(
        self,
        query: str,
        check_in: str,
        check_out: str,
        adults: int = 1,
        currency: str = "USD",
        gl: str = "us",
        hl: str = "en"
    ) -> dict[str, Any] | None:
        """
        Search for hotels using Google Hotels API via SerpApi.
        
        Args:
            query: Search query (e.g., "Bali Resorts" or city name)
            check_in: Check-in date (YYYY-MM-DD)
            check_out: Check-out date (YYYY-MM-DD)
            adults: Number of adults
            currency: Currency code (e.g., USD, EUR, RUB)
            gl: Geolocation (e.g., us, ru)
            hl: Language (e.g., en, ru)
        
        Returns:
            JSON response from SerpApi or None on error
        """
        if not self.api_key:
            logger.warning("serpapi_api_key_not_set")
            return None
        
        params = {
            "engine": "google_hotels",
            "q": query,
            "check_in_date": check_in,
            "check_out_date": check_out,
            "adults": adults,
            "currency": currency,
            "gl": gl,
            "hl": hl,
            "api_key": self.api_key
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()
                
                logger.info(
                    "serpapi_hotels_search_success",
                    query=query,
                    results_count=len(data.get("properties", []))
                )
                return data
                
        except httpx.HTTPStatusError as e:
            logger.error("serpapi_hotels_http_error", status_code=e.response.status_code)
            return None
        except httpx.TimeoutException:
            logger.error("serpapi_hotels_timeout")
            return None
        except Exception as e:
            logger.error("serpapi_hotels_error", error=str(e))
            return None
    
    async def search_flights(
        self,
        departure_id: str,
        arrival_id: str,
        outbound_date: str,
        return_date: str | None = None,
        type: str = "2",  # 1 = round trip, 2 = one way
        currency: str = "USD",
        gl: str = "us",
        hl: str = "en"
    ) -> dict[str, Any] | None:
        """
        Search for flights using Google Flights API via SerpApi.
        
        Args:
            departure_id: Departure airport code (e.g., CDG, SVO)
            arrival_id: Arrival airport code (e.g., AUS, LED)
            outbound_date: Departure date (YYYY-MM-DD)
            return_date: Return date (YYYY-MM-DD) for round trip
            type: Trip type (1 = round trip, 2 = one way)
            currency: Currency code (e.g., USD, EUR, RUB)
            gl: Geolocation (e.g., us, ru)
            hl: Language (e.g., en, ru)
        
        Returns:
            JSON response from SerpApi or None on error
        """
        if not self.api_key:
            logger.warning("serpapi_api_key_not_set")
            return None
        
        params = {
            "engine": "google_flights",
            "departure_id": departure_id,
            "arrival_id": arrival_id,
            "outbound_date": outbound_date,
            "type": type,
            "currency": currency,
            "gl": gl,
            "hl": hl,
            "api_key": self.api_key
        }
        
        if return_date:
            params["return_date"] = return_date
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()
                
                logger.info(
                    "serpapi_flights_search_success",
                    departure_id=departure_id,
                    arrival_id=arrival_id,
                    results_count=len(data.get("best_flights", []))
                )
                return data
                
        except httpx.HTTPStatusError as e:
            logger.error("serpapi_flights_http_error", status_code=e.response.status_code)
            return None
        except httpx.TimeoutException:
            logger.error("serpapi_flights_timeout")
            return None
        except Exception as e:
            logger.error("serpapi_flights_error", error=str(e))
            return None


# Global instance
serpapi_client = SerpApiClient()
