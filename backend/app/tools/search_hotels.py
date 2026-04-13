from datetime import date
from typing import Literal
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.config.settings import settings
from app.models.schemas import HotelOption, Money, ToolError, ToolErrorType
from app.middleware.circuit_breaker import with_circuit_breaker
from app.utils.serpapi_client import serpapi_client

logger = structlog.get_logger(__name__)


class HotelSearchError(Exception):
    """Custom exception for hotel search errors."""
    pass


def _validate_hotel_params(
    city: str,
    checkin: date,
    checkout: date,
    guests: int,
    min_rating: float,
    hotel_type: str | None
) -> None:
    """Validate hotel search parameters."""
    if not city or len(city) > 100:
        raise ValueError("Invalid city name")
    if checkin < date.today():
        raise ValueError("Check-in date cannot be in the past")
    if checkout <= checkin:
        raise ValueError("Check-out date must be after check-in date")
    if guests < 1 or guests > 10:
        raise ValueError("Guests must be between 1 and 10")
    if min_rating < 0 or min_rating > 5:
        raise ValueError("Rating must be between 0 and 5")
    if hotel_type and hotel_type not in ["hotel", "hostel", "apartment"]:
        raise ValueError("Hotel type must be hotel, hostel, or apartment")


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=2),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    reraise=True
)
@with_circuit_breaker("booking_api")
def _fetch_hotels_from_api(
    city: str,
    checkin: date,
    checkout: date,
    guests: int,
    max_price_per_night: int | None,
    min_rating: float,
    hotel_type: str | None
) -> list[HotelOption]:
    """
    Fetch hotels from SerpApi Google Hotels API with fallback to mock.
    
    Uses SerpApi Google Hotels (free tier: 100 searches/month).
    Falls back to mock data if API fails or no API key.
    """
    from datetime import timedelta
    
    # Try SerpApi Google Hotels
    if settings.SERPAPI_API_KEY:
        response = serpapi_client.search_hotels(
            query=city,
            check_in=checkin.strftime("%Y-%m-%d"),
            check_out=checkout.strftime("%Y-%m-%d"),
            adults=guests,
            currency="USD",  # SerpApi uses USD by default
            gl="us",
            hl="en"
        )
        
        if response and "properties" in response:
            hotels = []
            nights = (checkout - checkin).days
            
            for prop in response["properties"][:10]:  # Limit to 10 results
                # Extract price
                rate_info = prop.get("rate_per_night", {})
                price_per_night = int(rate_info.get("extracted_lowest", 0))
                total_info = prop.get("total_rate", {})
                total_price = int(total_info.get("extracted_lowest", 0))
                
                # Extract amenities
                amenities = prop.get("amenities", [])
                
                # Extract coordinates
                gps = prop.get("gps_coordinates", {})
                lat = gps.get("latitude", 0)
                lon = gps.get("longitude", 0)
                
                # Extract rating
                rating = prop.get("overall_rating", 0)
                
                # Extract hotel class (stars)
                hotel_class = prop.get("extracted_hotel_class", 0)
                
                # Determine hotel type
                prop_type = prop.get("type", "hotel")
                if prop_type == "vacation rental":
                    final_hotel_type = "apartment"
                else:
                    final_hotel_type = "hotel"
                
                # Check if has child facilities (kid-friendly)
                has_child = "Kid-friendly" in amenities or "Crib" in amenities
                
                hotels.append(HotelOption(
                    name=prop.get("name", "Unknown Hotel"),
                    address="",  # Google Hotels doesn't provide address in basic search
                    city=city,
                    rating=rating,
                    stars=hotel_class,
                    price_per_night=Money(amount=price_per_night, currency="USD"),
                    total_price=Money(amount=total_price, currency="USD"),
                    amenities=amenities,
                    hotel_type=final_hotel_type,
                    coordinates=(lat, lon),
                    booking_url=prop.get("link", "https://www.google.com/travel/hotels"),
                    source="serpapi",
                    has_child_facilities=has_child
                ))
            
            if hotels:
                return hotels
    
    # Fallback to mock implementation
    logger.warning("using_mock_hotel_fallback")
    nights = (checkout - checkin).days
    mock_hotels = [
        HotelOption(
            name="Гостиница Пушкин",
            address="ул. Пушкина, д. 10",
            city=city,
            rating=4.5,
            stars=4,
            price_per_night=Money(amount=5000, currency="RUB"),
            total_price=Money(amount=5000 * nights, currency="RUB"),
            amenities=["wifi", "breakfast", "parking"],
            hotel_type="hotel",
            coordinates=(55.7558, 37.6173),
            booking_url="https://booking.example.com/hotels/pushkin",
            source="mock",
            has_child_facilities=True
        ),
        HotelOption(
            name="Отель Центральный",
            address="пл. Центральная, д. 5",
            city=city,
            rating=4.0,
            stars=3,
            price_per_night=Money(amount=3500, currency="RUB"),
            total_price=Money(amount=3500 * nights, currency="RUB"),
            amenities=["wifi"],
            hotel_type="hotel",
            coordinates=(55.7560, 37.6175),
            booking_url="https://booking.example.com/hotels/central",
            source="mock",
            has_child_facilities=False
        )
    ]
    
    # Apply filters
    filtered_hotels = mock_hotels
    
    if max_price_per_night:
        filtered_hotels = [h for h in filtered_hotels if h.price_per_night.amount <= max_price_per_night]
    
    if min_rating > 0:
        filtered_hotels = [h for h in filtered_hotels if h.rating >= min_rating]
    
    if hotel_type:
        filtered_hotels = [h for h in filtered_hotels if h.hotel_type == hotel_type]
    
    return filtered_hotels


def search_hotels(
    city: str,
    checkin: date,
    checkout: date,
    guests: int = 1,
    max_price_per_night: int | None = None,
    min_rating: float = 0.0,
    hotel_type: Literal["hotel", "hostel", "apartment"] | None = None
) -> list[HotelOption] | ToolError:
    """
    Search for hotels in a city.
    
    Args:
        city: City name
        checkin: Check-in date
        checkout: Check-out date
        guests: Number of guests (1-10)
        max_price_per_night: Maximum price per night in RUB (optional)
        min_rating: Minimum rating (0-5)
        hotel_type: Type of accommodation (hotel, hostel, apartment)
    
    Returns:
        List of HotelOption or ToolError on failure
    """
    try:
        # Validate parameters
        _validate_hotel_params(city, checkin, checkout, guests, min_rating, hotel_type)
        
        # Fetch hotels from API
        hotels = _fetch_hotels_from_api(
            city=city,
            checkin=checkin,
            checkout=checkout,
            guests=guests,
            max_price_per_night=max_price_per_night,
            min_rating=min_rating,
            hotel_type=hotel_type
        )
        
        logger.info(
            "hotels_searched",
            city=city,
            checkin=str(checkin),
            checkout=str(checkout),
            results_count=len(hotels)
        )
        
        return hotels
        
    except ValueError as e:
        logger.warning("invalid_hotel_params", error=str(e))
        return ToolError(
            error_type=ToolErrorType.INVALID_PARAMS,
            message=str(e),
            retryable=False,
            tool_name="search_hotels"
        )
    except httpx.TimeoutException:
        logger.error("hotel_search_timeout", city=city)
        return ToolError(
            error_type=ToolErrorType.API_TIMEOUT,
            message="Hotel search API timeout",
            retryable=True,
            tool_name="search_hotels"
        )
    except httpx.HTTPStatusError as e:
        logger.error("hotel_search_api_error", status_code=e.response.status_code)
        return ToolError(
            error_type=ToolErrorType.API_ERROR,
            message=f"Hotel search API error: {e.response.status_code}",
            retryable=True,
            tool_name="search_hotels"
        )
    except Exception as e:
        if "Circuit breaker" in str(e):
            logger.error("hotel_search_circuit_open")
            return ToolError(
                error_type=ToolErrorType.CIRCUIT_OPEN,
                message="Hotel search service temporarily unavailable",
                retryable=False,
                tool_name="search_hotels"
            )
        logger.error("hotel_search_internal_error", error=str(e))
        return ToolError(
            error_type=ToolErrorType.INTERNAL_ERROR,
            message="Internal error in hotel search",
            retryable=False,
            tool_name="search_hotels"
        )
