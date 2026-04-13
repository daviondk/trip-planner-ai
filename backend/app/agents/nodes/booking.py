import structlog
from app.models.schemas import TripPlannerState
from app.tools.search_hotels import search_hotels
from app.tools.search_flights import search_flights

logger = structlog.get_logger(__name__)


def booking_node(state: TripPlannerState) -> TripPlannerState:
    """
    Booking Agent: Searches for booking options (hotels, flights).

    Args:
        state: Current TripPlannerState

    Returns:
        Updated state with booking_candidates
    """
    user_prefs = state["user_preferences"]
    itinerary = state["itinerary_draft"]

    if not user_prefs:
        logger.warning("booking_no_preferences")
        return state

    booking_candidates = []
    degraded = False

    # Search for hotels
    try:
        hotels = search_hotels(
            city=user_prefs.city,
            checkin=user_prefs.start_date,
            checkout=user_prefs.end_date,
            guests=user_prefs.travelers.adults + user_prefs.travelers.children,
            max_price_per_night=user_prefs.budget.per_day,
            min_rating=4.0,
            hotel_type=user_prefs.accommodation_type
        )

        if isinstance(hotels, list):
            booking_candidates.extend(hotels)
            # Add hotels to itinerary
            if itinerary:
                for day_plan in itinerary:
                    day_plan.accommodation = hotels[0] if hotels else None
        else:
            degraded = True

    except Exception as e:
        logger.error("booking_hotels_error", error=str(e))
        degraded = True

    # Search for flights (if needed - for PoC, just log)
    # In production, would need origin/destination from user preferences

    state["booking_candidates"] = booking_candidates
    state["booking_degraded"] = degraded

    logger.info(
        "booking_searched",
        candidates_count=len(booking_candidates),
        degraded=degraded
    )

    return state
