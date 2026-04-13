from datetime import date, datetime, timedelta
from typing import Literal
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.config.settings import settings
from app.models.schemas import FlightOption, Money, ToolError, ToolErrorType
from app.middleware.circuit_breaker import with_circuit_breaker
from app.utils.metrics import tool_invocations_total, tool_duration_seconds, tool_errors_total
from app.utils.serpapi_client import serpapi_client

logger = structlog.get_logger(__name__)


class FlightSearchError(Exception):
    """Custom exception for flight search errors."""
    pass


def _validate_flight_params(
    origin: str,
    destination: str,
    departure_date: date,
    passengers: int,
    cabin_class: str
) -> None:
    """Validate flight search parameters."""
    if not origin or len(origin) > 100:
        raise ValueError("Invalid origin airport code")
    if not destination or len(destination) > 100:
        raise ValueError("Invalid destination airport code")
    if departure_date < date.today():
        raise ValueError("Departure date cannot be in the past")
    if passengers < 1 or passengers > 10:
        raise ValueError("Passengers must be between 1 and 10")
    if cabin_class not in ["economy", "business"]:
        raise ValueError("Cabin class must be economy or business")


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=2),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    reraise=True
)
@with_circuit_breaker("booking_api")
async def _fetch_flights_from_api(
    origin: str,
    destination: str,
    departure_date: date,
    return_date: date | None,
    passengers: int,
    max_price: int | None,
    cabin_class: str
) -> list[FlightOption]:
    """
    Fetch flights from SerpApi Google Flights API with fallback to mock.
    
    Uses SerpApi Google Flights (free tier: 100 searches/month).
    Falls back to mock data if API fails or no API key.
    """
    # Try SerpApi Google Flights
    if settings.SERPAPI_API_KEY:
        trip_type = "1" if return_date else "2"  # 1 = round trip, 2 = one way
        
        response = await serpapi_client.search_flights(
            departure_id=origin,
            arrival_id=destination,
            outbound_date=departure_date.strftime("%Y-%m-%d"),
            return_date=return_date.strftime("%Y-%m-%d") if return_date else None,
            type=trip_type,
            currency="USD",  # SerpApi uses USD by default
            gl="us",
            hl="en"
        )
        
        if response and "best_flights" in response:
            flights = []
            
            for flight_data in response["best_flights"][:5]:  # Limit to 5 results
                flight_segments = flight_data.get("flights", [])
                
                if flight_segments:
                    first_segment = flight_segments[0]
                    last_segment = flight_segments[-1]
                    
                    # Extract airline info
                    airline = first_segment.get("airline", "Unknown")
                    flight_number = first_segment.get("flight_number", "")
                    
                    # Extract times
                    dep_time_str = first_segment.get("departure_airport", {}).get("time", "")
                    arr_time_str = last_segment.get("arrival_airport", {}).get("time", "")
                    
                    try:
                        departure_time = datetime.fromisoformat(dep_time_str)
                        arrival_time = datetime.fromisoformat(arr_time_str)
                    except:
                        departure_time = datetime.combine(departure_date, datetime.min.time())
                        arrival_time = departure_time + timedelta(hours=2)
                    
                    # Duration
                    total_duration = flight_data.get("total_duration", 0)
                    duration_minutes = total_duration  # Already in minutes
                    
                    # Price
                    price = flight_data.get("price", 0)
                    
                    # Stops (layovers)
                    layovers = flight_data.get("layovers", [])
                    stops = len(layovers)
                    
                    flights.append(FlightOption(
                        airline=airline,
                        flight_number=flight_number,
                        origin_airport=origin,
                        destination_airport=destination,
                        departure_time=departure_time,
                        arrival_time=arrival_time,
                        duration_minutes=duration_minutes or 120,
                        price=Money(amount=price, currency="USD"),
                        cabin_class=cabin_class,
                        stops=stops,
                        booking_url="https://www.google.com/travel/flights",
                        source="serpapi"
                    ))
            
            if flights:
                return flights
    
    # Fallback to mock implementation
    logger.warning("using_mock_flight_fallback")
    mock_flights = [
        FlightOption(
            airline="Аэрофлот",
            flight_number="SU1234",
            origin_airport=origin,
            destination_airport=destination,
            departure_time=datetime.combine(departure_date, datetime.min.time()) + timedelta(hours=10),
            arrival_time=datetime.combine(departure_date, datetime.min.time()) + timedelta(hours=12),
            duration_minutes=120,
            price=Money(amount=15000, currency="RUB"),
            cabin_class=cabin_class,
            stops=0,
            booking_url="https://booking.example.com/flights/SU1234",
            source="mock"
        ),
        FlightOption(
            airline="S7 Airlines",
            flight_number="S7567",
            origin_airport=origin,
            destination_airport=destination,
            departure_time=datetime.combine(departure_date, datetime.min.time()) + timedelta(hours=14),
            arrival_time=datetime.combine(departure_date, datetime.min.time()) + timedelta(hours=16),
            duration_minutes=120,
            price=Money(amount=12000, currency="RUB"),
            cabin_class=cabin_class,
            stops=0,
            booking_url="https://booking.example.com/flights/S7567",
            source="mock"
        )
    ]
    
    # Filter by max price if specified
    if max_price:
        mock_flights = [f for f in mock_flights if f.price.amount <= max_price]
    
    return mock_flights


async def search_flights(
    origin: str,
    destination: str,
    departure_date: date,
    return_date: date | None = None,
    passengers: int = 1,
    max_price: int | None = None,
    cabin_class: Literal["economy", "business"] = "economy"
) -> list[FlightOption] | ToolError:
    """
    Search for flights between two airports.
    
    Args:
        origin: Origin airport code (e.g., SVO)
        destination: Destination airport code (e.g., LED)
        departure_date: Departure date
        return_date: Return date (optional for one-way)
        passengers: Number of passengers (1-10)
        max_price: Maximum price in RUB (optional)
        cabin_class: Cabin class (economy or business)
    
    Returns:
        List of FlightOption or ToolError on failure
    """
    import time
    start_time = time.time()
    
    try:
        tool_invocations_total.labels(tool_name="search_flights").inc()
        
        # Validate parameters
        _validate_flight_params(origin, destination, departure_date, passengers, cabin_class)
        
        # Fetch flights from API
        flights = await _fetch_flights_from_api(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            passengers=passengers,
            max_price=max_price,
            cabin_class=cabin_class
        )
        
        duration = time.time() - start_time
        tool_duration_seconds.labels(tool_name="search_flights").observe(duration)
        
        logger.info(
            "flights_searched",
            origin=origin,
            destination=destination,
            departure_date=str(departure_date),
            results_count=len(flights),
            duration_seconds=duration
        )
        
        return flights
        
    except ValueError as e:
        tool_errors_total.labels(tool_name="search_flights", error_type="INVALID_PARAMS").inc()
        logger.warning("invalid_flight_params", error=str(e))
        return ToolError(
            error_type=ToolErrorType.INVALID_PARAMS,
            message=str(e),
            retryable=False,
            tool_name="search_flights"
        )
    except httpx.TimeoutException:
        tool_errors_total.labels(tool_name="search_flights", error_type="API_TIMEOUT").inc()
        logger.error("flight_search_timeout", origin=origin, destination=destination)
        return ToolError(
            error_type=ToolErrorType.API_TIMEOUT,
            message="Flight search API timeout",
            retryable=True,
            tool_name="search_flights"
        )
    except httpx.HTTPStatusError as e:
        tool_errors_total.labels(tool_name="search_flights", error_type="API_ERROR").inc()
        logger.error("flight_search_api_error", status_code=e.response.status_code)
        return ToolError(
            error_type=ToolErrorType.API_ERROR,
            message=f"Flight search API error: {e.response.status_code}",
            retryable=True,
            tool_name="search_flights"
        )
    except Exception as e:
        if "Circuit breaker" in str(e):
            tool_errors_total.labels(tool_name="search_flights", error_type="CIRCUIT_OPEN").inc()
            logger.error("flight_search_circuit_open")
            return ToolError(
                error_type=ToolErrorType.CIRCUIT_OPEN,
                message="Flight search service temporarily unavailable",
                retryable=False,
                tool_name="search_flights"
            )
        tool_errors_total.labels(tool_name="search_flights", error_type="INTERNAL_ERROR").inc()
        logger.error("flight_search_internal_error", error=str(e))
        return ToolError(
            error_type=ToolErrorType.INTERNAL_ERROR,
            message="Internal error in flight search",
            retryable=False,
            tool_name="search_flights"
        )
