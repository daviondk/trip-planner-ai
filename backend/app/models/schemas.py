from datetime import datetime, date
from typing import Any, Literal
from enum import Enum
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ============================================================================
# Memory / Context Models (from memory-context.md)
# ============================================================================

class TravelerGroup(BaseModel):
    adults: int = 1
    children: int = 0
    children_ages: list[int] = Field(default_factory=list)


class BudgetInfo(BaseModel):
    total: int | None = None
    per_day: int | None = None
    currency: str = "RUB"
    level: Literal["budget", "medium", "premium"] = "medium"


class UserPreferences(BaseModel):
    city: str
    country: str | None = None
    start_date: date
    end_date: date
    travelers: TravelerGroup = Field(default_factory=TravelerGroup)
    budget: BudgetInfo = Field(default_factory=BudgetInfo)
    interests: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    accommodation_type: Literal["hotel", "hostel", "apartment"] | None = None


class Activity(BaseModel):
    name: str
    description: str
    category: str
    start_time: str | None = None
    duration_minutes: int | None = None
    coordinates: tuple[float, float] | None = None
    estimated_cost: int | None = None
    source: Literal["rag", "llm", "api", "planner", "opentripmap"]


class DayPlan(BaseModel):
    day_number: int
    date: date
    activities: list[Activity] = Field(default_factory=list)
    meals: list[Activity] = Field(default_factory=list)
    accommodation: "BookingOption | None" = None
    notes: str | None = None


# ============================================================================
# Tool API Models (from tools-apis.md)
# ============================================================================

class Money(BaseModel):
    amount: int
    currency: str = "RUB"


class FlightOption(BaseModel):
    airline: str
    flight_number: str
    origin_airport: str
    destination_airport: str
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int
    price: Money
    cabin_class: Literal["economy", "business"]
    stops: int = 0
    booking_url: str
    source: Literal["aviasales", "mock"]


class HotelOption(BaseModel):
    name: str
    address: str
    city: str
    rating: float = Field(ge=0.0, le=5.0)
    stars: int | None = Field(None, ge=1, le=5)
    price_per_night: Money
    total_price: Money
    amenities: list[str] = Field(default_factory=list)
    hotel_type: Literal["hotel", "hostel", "apartment"]
    coordinates: tuple[float, float]
    booking_url: str
    source: Literal["booking_api", "mock"]
    has_child_facilities: bool = False


class POIInfo(BaseModel):
    name: str
    description: str
    category: str
    rating: float | None = Field(None, ge=0.0, le=5.0)
    coordinates: tuple[float, float] | None = None
    opening_hours: str | None = None
    estimated_duration_minutes: int | None = None
    estimated_cost: Money | None = None
    source: Literal["rag", "llm_generated", "opentripmap"]
    relevance_score: float = Field(ge=0.0, le=1.0)


class Waypoint(BaseModel):
    name: str
    coordinates: tuple[float, float]


class RouteLeg(BaseModel):
    start: str
    end: str
    distance_km: float
    duration_minutes: int
    transport_mode: Literal["driving", "walking", "transit"]


class RouteResult(BaseModel):
    total_distance_km: float
    total_duration_minutes: int
    legs: list[RouteLeg] = Field(default_factory=list)
    polyline: str
    map_url: str


class ExportResult(BaseModel):
    format: Literal["pdf", "ics"]
    filename: str
    file_size_bytes: int
    download_url: str


class ToolErrorType(str, Enum):
    INVALID_PARAMS = "INVALID_PARAMS"
    API_TIMEOUT = "API_TIMEOUT"
    API_ERROR = "API_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    NOT_FOUND = "NOT_FOUND"
    EXPORT_FAILED = "EXPORT_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ToolError(BaseModel):
    error_type: ToolErrorType
    message: str
    retryable: bool
    tool_name: str


# ============================================================================
# Additional Models (inferred from specs)
# ============================================================================

class BookingOption(BaseModel):
    """Base class for booking options (flights, hotels)"""
    name: str
    price: Money
    booking_url: str
    source: str


class MapData(BaseModel):
    """Map data for itinerary visualization"""
    polylines: list[str] = Field(default_factory=list)
    center_coordinates: tuple[float, float] | None = None
    zoom_level: int = 12
    map_url: str | None = None


class PlaceMetadata(BaseModel):
    """Metadata for retrieved places from ChromaDB"""
    city: str
    country: str
    category: Literal["museum", "restaurant", "park", "hotel", "transport", "general", "visa", "tip"]
    season: Literal["winter", "spring", "summer", "autumn"] | None = None
    budget_level: Literal["budget", "medium", "premium"] | None = None
    rating: float | None = Field(None, ge=0.0, le=5.0)
    coordinates: tuple[float, float] | None = None


class RetrievalResult(BaseModel):
    """Result from ChromaDB semantic search"""
    score: float = Field(ge=0.0, le=1.0)
    title: str
    text: str
    source: Literal["wikipedia", "osm", "synthetic", "blog"]
    metadata: PlaceMetadata


# ============================================================================
# LangGraph State (TypedDict for agent orchestration)
# ============================================================================

from langchain_core.messages import BaseMessage
from typing import Annotated


def add_messages(left: list[BaseMessage], right: list[BaseMessage]) -> list[BaseMessage]:
    """
    Reducer function for adding messages to state.
    
    Args:
        left: Existing messages
        right: New messages to add
    
    Returns:
        Combined message list
    """
    # If left is None, return right
    if left is None:
        return right
    # If right is None, return left
    if right is None:
        return left
    # Otherwise concatenate
    return left + right


class TripPlannerState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    user_preferences: UserPreferences | None
    current_intent: Literal["plan_trip", "change_plan", "ask_question", "export"] | None
    itinerary_draft: list[DayPlan]
    booking_candidates: list[BookingOption]
    map_data: MapData | None
    agent_outputs: dict[str, Any]
    iteration_count: int
    error_context: list[str]
    retrieval_degraded: bool
    is_blocked: bool
    llm_degraded: bool
    booking_degraded: bool
    maps_degraded: bool
    token_count: int
    created_at: datetime
    last_activity_at: datetime
