import pytest
from datetime import date, timedelta
from app.tools.search_hotels import search_hotels, _validate_hotel_params
from app.models.schemas import ToolError, ToolErrorType


class TestHotelSearch:
    """Test suite for hotel search functionality."""
    
    def test_validate_hotel_params_success(self):
        """Test successful parameter validation."""
        _validate_hotel_params(
            city="Moscow",
            checkin=date.today() + timedelta(days=7),
            checkout=date.today() + timedelta(days=10),
            guests=2,
            min_rating=4.0,
            hotel_type="hotel"
        )
        # Should not raise exception
    
    def test_validate_hotel_params_invalid_city(self):
        """Test validation with invalid city."""
        with pytest.raises(ValueError, match="Invalid city name"):
            _validate_hotel_params(
                city="",  # Empty city
                checkin=date.today() + timedelta(days=7),
                checkout=date.today() + timedelta(days=10),
                guests=1,
                min_rating=0.0,
                hotel_type=None
            )
    
    def test_validate_hotel_params_invalid_dates(self):
        """Test validation with invalid date range."""
        with pytest.raises(ValueError, match="Check-out date must be after check-in"):
            _validate_hotel_params(
                city="Moscow",
                checkin=date.today() + timedelta(days=10),
                checkout=date.today() + timedelta(days=7),  # Before checkin
                guests=1,
                min_rating=0.0,
                hotel_type=None
            )
    
    def test_validate_hotel_params_invalid_guests(self):
        """Test validation with invalid guest count."""
        with pytest.raises(ValueError, match="Guests must be between 1 and 10"):
            _validate_hotel_params(
                city="Moscow",
                checkin=date.today() + timedelta(days=7),
                checkout=date.today() + timedelta(days=10),
                guests=11,  # Invalid
                min_rating=0.0,
                hotel_type=None
            )
    
    def test_validate_hotel_params_invalid_rating(self):
        """Test validation with invalid rating."""
        with pytest.raises(ValueError, match="Rating must be between 0 and 5"):
            _validate_hotel_params(
                city="Moscow",
                checkin=date.today() + timedelta(days=7),
                checkout=date.today() + timedelta(days=10),
                guests=1,
                min_rating=6.0,  # Invalid
                hotel_type=None
            )
    
    @pytest.mark.asyncio
    async def test_search_hotels_success(self):
        """Test successful hotel search."""
        result = await search_hotels(
            city="Moscow",
            checkin=date.today() + timedelta(days=7),
            checkout=date.today() + timedelta(days=10),
            guests=2,
            min_rating=4.0,
            hotel_type="hotel"
        )
        
        # Should return list of HotelOption
        assert isinstance(result, list)
        assert len(result) > 0
        assert result[0].city == "Moscow"
        assert result[0].rating >= 4.0
    
    @pytest.mark.asyncio
    async def test_search_hotels_with_max_price(self):
        """Test hotel search with price filter."""
        result = await search_hotels(
            city="Moscow",
            checkin=date.today() + timedelta(days=7),
            checkout=date.today() + timedelta(days=10),
            guests=1,
            max_price_per_night=4000,
            min_rating=0.0,
            hotel_type=None
        )
        
        # Should filter by price
        assert isinstance(result, list)
        for hotel in result:
            assert hotel.price_per_night.amount <= 4000
    
    @pytest.mark.asyncio
    async def test_search_hotels_invalid_params(self):
        """Test hotel search with invalid parameters."""
        result = await search_hotels(
            city="",  # Invalid
            checkin=date.today() + timedelta(days=7),
            checkout=date.today() + timedelta(days=10),
            guests=1,
            min_rating=0.0,
            hotel_type=None
        )
        
        # Should return ToolError
        assert isinstance(result, ToolError)
        assert result.error_type == ToolErrorType.INVALID_PARAMS
        assert result.tool_name == "search_hotels"
