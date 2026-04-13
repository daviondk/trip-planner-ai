import structlog
from app.models.schemas import TripPlannerState
from app.tools.get_poi_info import get_poi_info
from app.utils.langfuse_client import langfuse_client

logger = structlog.get_logger(__name__)


@langfuse_client.observe()
async def info_rag_node(state: TripPlannerState) -> TripPlannerState:
    """
    Info/RAG Agent: Enriches itinerary with detailed information from ChromaDB.
    
    Args:
        state: Current TripPlannerState
    
    Returns:
        Updated state with enriched itinerary_draft
    """
    itinerary = state["itinerary_draft"]
    user_prefs = state["user_preferences"]
    
    if not itinerary:
        logger.warning("info_rag_no_itinerary")
        return state
    
    # Enrich each activity with POI information
    enriched_itinerary = []
    degraded = False
    
    for day_plan in itinerary:
        enriched_activities = []
        
        for activity in day_plan.activities:
            # Try to get POI info
            try:
                poi_results = await get_poi_info(
                    city=user_prefs.city,
                    categories=[activity.category],
                    query=activity.name,
                    limit=1,
                    budget_level=user_prefs.budget.level
                )
                
                if isinstance(poi_results, list) and poi_results:
                    # Enrich with POI data
                    poi = poi_results[0]
                    activity.description = poi.description
                    activity.coordinates = poi.coordinates
                    activity.estimated_cost = poi.estimated_cost.amount if poi.estimated_cost else None
                    activity.source = "rag"
                else:
                    # POI search failed, keep LLM-generated description
                    degraded = True
                    
            except Exception as e:
                logger.error("info_rag_poi_error", error=str(e))
                degraded = True
            
            enriched_activities.append(activity)
        
        # Update day plan
        enriched_day = day_plan.model_copy(update={"activities": enriched_activities})
        enriched_itinerary.append(enriched_day)
    
    state["itinerary_draft"] = enriched_itinerary
    state["retrieval_degraded"] = degraded
    
    logger.info(
        "info_rag_enriched",
        days=len(enriched_itinerary),
        degraded=degraded
    )
    
    return state
