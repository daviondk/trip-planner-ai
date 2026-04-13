import pytest
from datetime import date, datetime, timedelta
from app.tools.search_flights import search_flights, _validate_flight_params
from app.models.schemas import ToolError, ToolErrorType


class TestFlightSearch:
    """Test suite for flight search functionality."""
    
    def test_validate_flight_params_success(self):
        """Test successful parameter validation."""
        _validate_flight_params(
            origin="SVO",
            destination="LED",
            departure_date=date.today() + timedelta(days=7),
            passengers=2,
            cabin_class="economy"
        )
        # Should not raise exception
    
    def test_validate_flight_params_invalid_origin(self):
        """Test validation with invalid origin."""
        with pytest.raises(ValueError, match="Invalid origin"):
            _validate_flight_params(
                origin="",  # Empty origin
                destination="LED",
                departure_date=date.today() + timedelta(days=7),
                passengers=1,
                cabin_class="economy"
            )
    
    def test_validate_flight_params_past_date(self):
        """Test validation with past date."""
        with pytest.raises(ValueError, match="cannot be in the past"):
            _validate_flight_params(
                origin="SVO",
                destination="LED",
                departure_date=date.today() - timedelta(days=1),
                passengers=1,
                cabin_class="economy"
            )
    
    def test_validate_flight_params_invalid_passengers(self):
        """Test validation with invalid passenger count."""
        with pytest.raises(ValueError, match="Passengers must be between 1 and 10"):
            _validate_flight_params(
                origin="SVO",
                destination="LED",
                departure_date=date.today() + timedelta(days=7),
                passengers=0,  # Invalid
                cabin_class="economy"
            )
    
    def test_validate_flight_params_invalid_cabin_class(self):
        """Test validation with invalid cabin class."""
        with pytest.raises(ValueError, match="Cabin class must be economy or business"):
            _validate_flight_params(
                origin="SVO",
                destination="LED",
                departure_date=date.today() + timedelta(days=7),
                passengers=1,
                cabin_class="first"  # Invalid
            )
    
    @pytest.mark.asyncio
    async def test_search_flights_success(self):
        """Test successful flight search."""
        result = await search_flights(
            origin="SVO",
            destination="LED",
            departure_date=date.today() + timedelta(days=7),
            passengers=1,
            cabin_class="economy"
        )
        
        # Should return list of FlightOption
        assert isinstance(result, list)
        assert len(result) > 0
        assert result[0].origin_airport == "SVO"
        assert result[0].destination_airport == "LED"
    
    @pytest.mark.asyncio
    async def test_search_flights_with_max_price(self):
        """Test flight search with price filter."""
        result = await search_flights(
            origin="SVO",
            destination="LED",
            departure_date=date.today() + timedelta(days=7),
            passengers=1,
            max_price=10000,
            cabin_class="economy"
        )
        
        # Should filter by price
        assert isinstance(result, list)
        for flight in result:
            assert flight.price.amount <= 10000
    
    @pytest.mark.asyncio
    async def test_search_flights_invalid_params(self):
        """Test flight search with invalid parameters."""
        result = await search_flights(
            origin="",  # Invalid
            destination="LED",
            departure_date=date.today() + timedelta(days=7),
            passengers=1,
            cabin_class="economy"
        )
        
        # Should return ToolError
        assert isinstance(result, ToolError)
        assert result.error_type == ToolErrorType.INVALID_PARAMS
        assert result.tool_name == "search_flights"
