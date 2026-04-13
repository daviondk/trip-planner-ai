"""
Amadeus API client for hotel and flight search.
Free tier: 2000 calls/month
"""
import httpx
import structlog
import asyncio
from typing import Literal
from datetime import datetime, timedelta
from app.config.settings import settings
from app.middleware.circuit_breaker import with_circuit_breaker

logger = structlog.get_logger(__name__)


class AmadeusClient:
    """Client for Amadeus APIs with OAuth2 authentication."""

    def __init__(self):
        self.api_key = settings.AMADEUS_API_KEY
        self.api_secret = settings.AMADEUS_API_SECRET
        self.base_url = "https://test.api.amadeus.com"
        self.timeout = settings.AMADEUS_TIMEOUT
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None

    async def _get_access_token(self) -> str | None:
        """
        Get OAuth2 access token.

        Returns:
            Access token or None on error
        """
        # Check if token is still valid
        if self._access_token and self._token_expires_at and datetime.now() < self._token_expires_at:
            return self._access_token

        if not self.api_key or not self.api_secret:
            logger.warning("amadeus_no_credentials")
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/security/oauth2/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.api_key,
                        "client_secret": self.api_secret
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded"
                    }
                )
                response.raise_for_status()
                data = response.json()

                self._access_token = data.get("access_token")
                expires_in = data.get("expires_in", 1800)  # Default 30 min
                self._token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)  # Refresh 1 min early

                logger.info("amadeus_token_refreshed")
                return self._access_token

        except Exception as e:
            logger.error("amadeus_token_error", error=str(e))
            return None

    async def search_hotels(
        self,
        city_code: str,
        check_in: str,
        check_out: str,
        adults: int = 1,
        room_quantity: int = 1,
        rating: str | None = None,
        price_range: str | None = None
    ) -> dict | None:
        """
        Search for hotels using Amadeus Hotel Search API.

        Args:
            city_code: IATA city code (e.g., "MOW" for Moscow)
            check_in: Check-in date (YYYY-MM-DD)
            check_out: Check-out date (YYYY-MM-DD)
            adults: Number of adults
            room_quantity: Number of rooms
            rating: Minimum rating (1-5)
            price_range: Price range (e.g., "100-500")

        Returns:
            Amadeus response dict or None on error
        """
        token = await self._get_access_token()
        if not token:
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                params = {
                    "cityCode": city_code,
                    "checkInDate": check_in,
                    "checkOutDate": check_out,
                    "adults": adults,
                    "roomQuantity": room_quantity,
                    "radius": 10,
                    "radiusUnit": "KM"
                }

                if rating:
                    params["rating"] = rating
                if price_range:
                    params["priceRange"] = price_range

                response = await client.get(
                    f"{self.base_url}/v3/shopping/hotel-offers",
                    headers={
                        "Authorization": f"Bearer {token}"
                    },
                    params=params
                )
                response.raise_for_status()
                return response.json()

        except httpx.TimeoutException:
            logger.error("amadeus_hotels_timeout")
            return None
        except httpx.HTTPStatusError as e:
            logger.error("amadeus_hotels_http_error", status_code=e.response.status_code)
            return None
        except Exception as e:
            logger.error("amadeus_hotels_error", error=str(e))
            return None

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        adults: int = 1,
        travel_class: str = "ECONOMY",
        max_price: int | None = None
    ) -> dict | None:
        """
        Search for flights using Amadeus Flight Offers Search API.

        Args:
            origin: Origin airport code (IATA, e.g., "SVO")
            destination: Destination airport code (IATA, e.g., "LED")
            departure_date: Departure date (YYYY-MM-DD)
            return_date: Return date (YYYY-MM-DD) for round-trip
            adults: Number of adults
            travel_class: Travel class (ECONOMY, BUSINESS, FIRST)
            max_price: Maximum price

        Returns:
            Amadeus response dict or None on error
        """
        token = await self._get_access_token()
        if not token:
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                params = {
                    "origin": origin,
                    "destination": destination,
                    "departureDate": departure_date,
                    "adults": adults,
                    "travelClass": travel_class,
                    "currencyCode": "RUB"
                }

                if return_date:
                    params["returnDate"] = return_date
                if max_price:
                    params["maxPrice"] = max_price

                response = await client.get(
                    f"{self.base_url}/v2/shopping/flight-offers",
                    headers={
                        "Authorization": f"Bearer {token}"
                    },
                    params=params
                )
                response.raise_for_status()
                return response.json()

        except httpx.TimeoutException:
            logger.error("amadeus_flights_timeout")
            return None
        except httpx.HTTPStatusError as e:
            logger.error("amadeus_flights_http_error", status_code=e.response.status_code)
            return None
        except Exception as e:
            logger.error("amadeus_flights_error", error=str(e))
            return None


# Global client instance
amadeus_client = AmadeusClient()
