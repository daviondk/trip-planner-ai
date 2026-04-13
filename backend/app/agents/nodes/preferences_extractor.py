import structlog
import re
from datetime import date
from langchain_core.messages import HumanMessage
from app.models.schemas import TripPlannerState, UserPreferences, TravelerGroup, BudgetInfo
from app.config.settings import settings
from app.utils.metrics import llm_invocations_total, llm_duration_seconds, llm_tokens_total

logger = structlog.get_logger(__name__)


def extract_preferences_from_text(text: str) -> tuple[dict | None, int]:
    """
    Extract trip preferences from natural language text using LLM only.

    Args:
        text: User input text

    Returns:
        Tuple of (Dictionary with extracted preferences or None if extraction fails, tokens used)
    """
    try:
        from app.utils.llm_client import get_llm_client

        # LLM-based extraction using configured provider (Mistral, OpenRouter, or YandexGPT)
        messages = [
            {
                "role": "system",
                "content": """Extract trip planning information from the user's message. Return a JSON object with these fields:
- city: SPECIFIC CITY NAME in ENGLISH (string, e.g., "Tokyo", "Moscow", "Saint Petersburg", "Antananarivo" - NOT "Токио", "Москва", "Санкт-Петербург", "Madagascar")
  - If the user mentions a country (e.g., "Madagascar", "Japan", "Russia"), return the CAPITAL CITY or a major tourist city
  - For Madagascar, use "Antananarivo"
  - For Japan, use "Tokyo"
  - For Russia, use "Moscow"
  - For France, use "Paris"
- start_date: start date in YYYY-MM-DD format (string, assume tomorrow if not specified)
- end_date: end date in YYYY-MM-DD format (string, calculate based on duration if specified like "на неделю" (7 days total), "на два дня" (2 days total), etc. If no duration specified, default to 3 days from start_date)
  - IMPORTANT: If start_date is 2026-04-14 and duration is 7 days, end_date should be 2026-04-20 (NOT 2026-04-21). The end date is the last day of the trip, not the day after.
- adults: number of adults (integer)
- children: number of children (integer, default 0)
- interests: list of interests (array of strings, max 3-4 categories) - ONLY use these valid OpenTripMap kinds: tourism, culture, natural, historic, amusement, sport, infrastructure, shops, adult, food, religion, accommodation. Map user interests to the closest valid kind (e.g., "museums" → "culture", "parks" → "natural", "walking tours" → "tourism", "riverside" → "natural", "local cuisine" → "food", "architecture" → "historic"). Return ONLY the most relevant 2-3 categories based on user's specific request, not all categories.
- budget_level: one of "budget", "medium", "premium" (string, default "medium")

Important: Handle Russian duration expressions:
- "на неделю" = 7 days total (if start_date is 2026-04-14, end_date is 2026-04-20)
- "на пару дней" = 2 days total
- "на два дня" = 2 days total
- "на три дня" = 3 days total
- "на месяц" = 30 days total

Current date is 2026-04-13. If start_date is not specified, use 2026-04-14 (tomorrow).

If a field is not mentioned in the message, set it to null. Return ONLY valid JSON, no other text."""
            },
            {
                "role": "user",
                "content": text
            }
        ]

        llm_client = get_llm_client()
        response_text, total_tokens = llm_client.call_llm(messages, agent="preferences_extractor")

        if response_text is None:
            logger.error("preferences_extraction_failed_llm_returned_none")
            return None, 0

        logger.info("preferences_extraction_raw_response", response=response_text[:200])

        # Strip markdown code blocks if present
        cleaned_response = response_text.strip()
        if cleaned_response.startswith("```"):
            # Remove markdown code blocks
            cleaned_response = cleaned_response.strip("`").strip()
            if cleaned_response.startswith("json"):
                cleaned_response = cleaned_response[4:].strip()
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3].strip()

        # Parse JSON
        import json
        prefs = json.loads(cleaned_response)

        # Handle None values with defaults
        if prefs.get("adults") is None:
            prefs["adults"] = 1
        if prefs.get("children") is None:
            prefs["children"] = 0

        from datetime import date, timedelta

        # Handle dates - ensure they are in the future
        today = date.today()
        if prefs.get("start_date") is None:
            # Default to tomorrow
            prefs["start_date"] = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            # Check if start_date is in the past
            try:
                start_date_obj = date.fromisoformat(prefs["start_date"])
                if start_date_obj < today:
                    # Override with future date
                    prefs["start_date"] = (today + timedelta(days=1)).strftime("%Y-%m-%d")
            except:
                # Invalid date format, use default
                prefs["start_date"] = (today + timedelta(days=1)).strftime("%Y-%m-%d")

        if prefs.get("end_date") is None:
            # Default to start_date + 2 days (3 day trip)
            start_date_obj = date.fromisoformat(prefs["start_date"])
            prefs["end_date"] = (start_date_obj + timedelta(days=2)).strftime("%Y-%m-%d")
        else:
            # Check if end_date is in the past or before start_date
            try:
                end_date_obj = date.fromisoformat(prefs["end_date"])
                start_date_obj = date.fromisoformat(prefs["start_date"])
                if end_date_obj < today or end_date_obj < start_date_obj:
                    # Override with future date after start_date
                    prefs["end_date"] = (start_date_obj + timedelta(days=2)).strftime("%Y-%m-%d")
            except:
                # Invalid date format, use default
                start_date_obj = date.fromisoformat(prefs["start_date"])
                prefs["end_date"] = (start_date_obj + timedelta(days=2)).strftime("%Y-%m-%d")

        if prefs.get("interests") is None:
            prefs["interests"] = []
        if prefs.get("budget_level") is None:
            prefs["budget_level"] = "medium"

        logger.info("preferences_extracted_llm", prefs=prefs)
        return prefs, total_tokens

    except Exception as e:
        logger.error("preferences_extraction_failed", error=str(e))
        # No regex fallback - LLM extraction is mandatory
        return None, 0


def _extract_preferences_regex(text: str) -> dict:
    """
    Fallback regex-based preference extraction.
    
    Args:
        text: User input text
    
    Returns:
        Dictionary with extracted preferences
    """
    text_lower = text.lower()
    prefs = {}
    
    # Extract city (Russian cities)
    cities = ["санкт-петербург", "москва", "казань", "сочи", "владивосток", "калининград", "петербург"]
    for city in cities:
        if city in text_lower:
            prefs["city"] = city.replace("-", " ").title()
            break
    
    # Extract dates - handle formats like "с 15 по 17 мая" or "15-17 мая"
    date_pattern = r'(\d{1,2})\s*(?:по|-)\s*(\d{1,2})\s*(мая|апреля|июня|июля|августа|сентября|октября|ноября|декабря|января|февраля|марта)'
    date_match = re.search(date_pattern, text_lower)
    if date_match:
        # Assume current year
        year = 2025
        month_map = {
            "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5,
            "июня": 6, "июля": 7, "августа": 8, "сентября": 9, "октября": 10,
            "ноября": 11, "декабря": 12
        }
        try:
            start_day = int(date_match.group(1))
            end_day = int(date_match.group(2))
            month = month_map.get(date_match.group(3), 5)
            
            prefs["start_date"] = f"{year}-{month:02d}-{start_day:02d}"
            prefs["end_date"] = f"{year}-{month:02d}-{end_day:02d}"
        except Exception as e:
            logger.error("date_extraction_failed", error=str(e))
    
    # Extract travelers
    adult_match = re.search(r'(\d+)\s*(взрослых|взрослый|человек)', text_lower)
    if adult_match:
        prefs["adults"] = int(adult_match.group(1))
    else:
        prefs["adults"] = 1  # default
    
    prefs["children"] = 0  # default
    
    # Extract interests
    interests = []
    interest_keywords = ["музеи", "история", "природа", "рестораны", "парки", "шопинг", "театры", "искусство"]
    for interest in interest_keywords:
        if interest in text_lower:
            interests.append(interest)
    prefs["interests"] = interests if interests else ["музеи", "история"]  # default
    
    # Extract budget
    if "низкий" in text_lower or "минимальный" in text_lower:
        prefs["budget_level"] = "low"
    elif "высокий" in text_lower or "люкс" in text_lower:
        prefs["budget_level"] = "high"
    else:
        prefs["budget_level"] = "medium"  # default
    
    logger.info("preferences_extracted_regex", prefs=prefs)
    return prefs


def preferences_extractor_node(state: TripPlannerState) -> TripPlannerState:
    """
    Extract user preferences from natural language message.
    
    Args:
        state: Current TripPlannerState
    
    Returns:
        Updated state with user_preferences
    """
    # Only extract if preferences are not already set and intent is plan_trip
    if state.get("user_preferences") or state.get("current_intent") != "plan_trip":
        return state
    
    # Get the last message
    if not state["messages"]:
        return state
    
    last_message = state["messages"][-1]
    if not isinstance(last_message, HumanMessage):
        return state
    
    # Extract preferences
    prefs_dict, tokens_used = extract_preferences_from_text(last_message.content)
    state["token_count"] = state.get("token_count", 0) + tokens_used
    
    if prefs_dict and prefs_dict.get("city"):
        try:
            # Build UserPreferences object
            user_prefs = UserPreferences(
                city=prefs_dict.get("city", ""),
                country=None,
                start_date=date.fromisoformat(prefs_dict["start_date"]) if prefs_dict.get("start_date") else None,
                end_date=date.fromisoformat(prefs_dict["end_date"]) if prefs_dict.get("end_date") else None,
                travelers=TravelerGroup(
                    adults=prefs_dict.get("adults", 1),
                    children=prefs_dict.get("children", 0),
                    children_ages=[]
                ),
                budget=BudgetInfo(
                    total=None,
                    per_day=None,
                    level=prefs_dict.get("budget_level", "medium")
                ),
                interests=prefs_dict.get("interests", []),
                constraints=[],
                accommodation_type=None
            )
            
            state["user_preferences"] = user_prefs
            logger.info("preferences_set_successfully", city=user_prefs.city)
            
        except Exception as e:
            logger.error("preferences_parsing_failed", error=str(e))
    
    return state
