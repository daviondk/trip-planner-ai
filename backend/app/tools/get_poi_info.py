from typing import Literal
import asyncio
import structlog
from app.retriever.chroma_client import retriever
from app.models.schemas import POIInfo, ToolError, ToolErrorType
from app.utils.opentripmap_client import opentripmap_client
from app.tools.search_wikipedia import search_poi_info
from app.utils.llm_client import get_llm_client
from tenacity import retry, stop_after_attempt, wait_fixed

logger = structlog.get_logger(__name__)


@retry(
    stop=stop_after_attempt(1),
    wait=wait_fixed(0.5),
    reraise=True
)
def get_poi_info(
    city: str,
    categories: list[str] | None = None,
    query: str | None = None,
    limit: int = 5,
    budget_level: Literal["budget", "medium", "premium"] | None = None
) -> list[POIInfo] | ToolError:
    """
    Search for points of interest using OpenTripMap API with ChromaDB fallback.
    
    Priority:
    1. OpenTripMap API (real-time POI data)
    2. ChromaDB (indexed POI data)
    
    Args:
        city: City to search in
        categories: List of categories to filter (museum, restaurant, park, etc.)
        query: Text query for semantic search
        limit: Maximum number of results (1-20)
        budget_level: Budget level filter (budget, medium, premium)
    
    Returns:
        List of POIInfo or ToolError on failure
    """
    try:
        # Validate parameters
        if not city or len(city) > 100:
            raise ValueError("Invalid city name")
        if limit < 1 or limit > 20:
            raise ValueError("Limit must be between 1 and 20")
        if budget_level and budget_level not in ["budget", "medium", "premium"]:
            raise ValueError("Invalid budget level")
        
        # Try OpenTripMap API first
        if opentripmap_client:
            logger.info("poi_search_opentripmap_attempt", city=city)
            poi_list = _search_opentripmap(city, categories, query, limit)
            if poi_list:
                logger.info("poi_search_opentripmap_success", results=len(poi_list))
                return poi_list
            else:
                logger.warning("poi_search_opentripmap_empty", city=city)

        # Fallback to ChromaDB
        logger.info("poi_search_chromadb_fallback", city=city)
        return _search_chromadb(city, categories, query, limit, budget_level)
        
    except ValueError as e:
        logger.warning("invalid_poi_params", error=str(e))
        return ToolError(
            error_type=ToolErrorType.INVALID_PARAMS,
            message=str(e),
            retryable=False,
            tool_name="get_poi_info"
        )
    except Exception as e:
        logger.error("poi_search_error", error=str(e))
        return ToolError(
            error_type=ToolErrorType.INTERNAL_ERROR,
            message="Error searching for points of interest",
            retryable=False,
            tool_name="get_poi_info"
        )


def _search_opentripmap(
    city: str,
    categories: list[str] | None,
    query: str | None,
    limit: int
) -> list[POIInfo]:
    """Search POI using OpenTripMap API."""
    # Get city coordinates
    coords = opentripmap_client.get_city_coordinates(city)
    if not coords:
        logger.warning("opentripmap_city_not_found", city=city)
        return []

    lat, lon = coords

    # Use categories directly from LLM (already mapped to valid OpenTripMap kinds)
    # Filter to only valid OpenTripMap kinds
    valid_kinds = ["tourism", "culture", "natural", "historic", "amusement", "sport", "infrastructure", "shops", "adult", "food", "religion", "accommodation"]
    kinds = "tourism"  # Default to tourism if no categories specified
    if categories:
        # Filter categories to only valid kinds
        filtered_categories = [cat for cat in categories if cat in valid_kinds]
        if filtered_categories:
            # Use first valid category, but if it's 'culture', try 'tourism' instead (API might have issues with culture)
            if filtered_categories[0] == "culture":
                kinds = "tourism"
            else:
                kinds = filtered_categories[0]

    # Search in radius
    places = opentripmap_client.get_places_in_radius(
        lat=lat,
        lon=lon,
        radius=5000,  # 5km radius
        kinds=kinds,
        limit=limit,
        lang="ru"
    )

    # Convert to POIInfo
    poi_list = []
    for place in places[:limit]:
        # Get detailed info for each place
        details = opentripmap_client.get_place_details(place.get("xid"))

        # Get description from OpenTripMap
        description = details.get("wikipedia_extracts", {}).get("text", "") if details else ""

        # If OpenTripMap description is empty, try Wikipedia
        if not description or len(description) < 50:
            poi_name = place.get("name", "Unknown")
            try:
                # Always include city in search for more specific results
                search_query = f"{city} {poi_name}" if city else poi_name
                wiki_result = asyncio.run(search_poi_info(search_query, city, lang="ru"))
                if isinstance(wiki_result, dict) and wiki_result.get("content"):
                    wiki_content = wiki_result.get("content", "")
                    # Use LLM to summarize the Wikipedia content
                    llm_client = get_llm_client()
                    summary_prompt = f"""Сделай краткое и понятное описание этого места на русском языке, не более 2-3 предложений:

{wiki_content}

Название места: {poi_name}
Город: {city}

Ответ только описанием, без лишнего текста."""
                    summary = llm_client.chat_completion(
                        messages=[{"role": "user", "content": summary_prompt}],
                        temperature=0.3
                    )
                    if summary:
                        description = summary
                        logger.info("wikipedia_description_summarized", poi_name=poi_name, city=city, description_length=len(description))
            except Exception as e:
                logger.warning("wikipedia_search_failed", poi_name=poi_name, city=city, error=str(e))

        poi = POIInfo(
            name=place.get("name", "Unknown"),
            description=description,
            category=place.get("kinds", "").split(",")[0],
            rating=None,  # OpenTripMap doesn't provide rating
            coordinates=(place.get("point", {}).get("lat"), place.get("point", {}).get("lon")),
            opening_hours=details.get("opening_hours") if details else None,
            estimated_duration_minutes=None,
            estimated_cost=None,
            source="opentripmap",
            relevance_score=1.0
        )
        poi_list.append(poi)

    return poi_list


def _search_chromadb(
    city: str,
    categories: list[str] | None,
    query: str | None,
    limit: int,
    budget_level: Literal["budget", "medium", "premium"] | None
) -> list[POIInfo]:
    """Search POI using ChromaDB retriever."""
    # Build category filter
    category_filter = categories[0] if categories else None

    # Use retriever to search
    retrieval_results = retriever.search_places(
        query=query or f"places in {city}",
        collection="points_of_interest",
        city=city,
        category=category_filter,
        budget_level=budget_level,
        limit=limit,
        score_threshold=0.5
    )
    
    # Convert RetrievalResult to POIInfo
    poi_list = []
    for result in retrieval_results:
        poi = POIInfo(
            name=result.title,
            description=result.text,
            category=result.metadata.category,
            rating=result.metadata.rating,
            coordinates=result.metadata.coordinates,
            opening_hours=None,
            estimated_duration_minutes=None,
            estimated_cost=None,
            source="chromadb",
            relevance_score=result.score
        )
        poi_list.append(poi)
    
    logger.info(
        "poi_searched_chromadb",
        city=city,
        query=query,
        results_count=len(poi_list)
    )
    
    return poi_list
