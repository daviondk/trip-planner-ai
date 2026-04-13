import structlog
from langchain_core.messages import AIMessage
from app.models.schemas import TripPlannerState
from app.utils.langfuse_client import langfuse_client
from app.utils.llm_client import get_llm_client

logger = structlog.get_logger(__name__)


def _translate_to_russian(text: str) -> str:
    """Translate text to Russian using LLM if it's not already in Russian."""
    if not text or len(text) < 10:
        return text
    
    # Simple heuristic: if text contains mostly Cyrillic characters, assume it's Russian
    cyrillic_chars = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
    if cyrillic_chars / len(text) > 0.3:
        return text
    
    try:
        llm_client = get_llm_client()
        messages = [
            {
                "role": "system",
                "content": "You are a translator. Translate the following text to Russian. Keep the translation natural and accurate. Return only the translated text, nothing else."
            },
            {
                "role": "user",
                "content": text
            }
        ]
        translated, _ = llm_client.call_llm(messages, agent="translator")
        return translated if translated else text
    except Exception as e:
        logger.warning("translation_failed", error=str(e))
        return text


@langfuse_client.observe()
def responder_node(state: TripPlannerState) -> TripPlannerState:
    """
    Responder: Assembles final response for the user.
    
    Collects all state fields and generates a human-readable response.
    
    Args:
        state: Current TripPlannerState
    
    Returns:
        Updated state with final AIMessage
    """
    intent = state.get("current_intent", "ask_question")
    is_blocked = state.get("is_blocked", False)
    error_context = state.get("error_context", [])
    itinerary = state.get("itinerary_draft", [])
    booking_candidates = state.get("booking_candidates", [])
    map_data = state.get("map_data")
    
    # Handle blocked input
    if is_blocked:
        response = "Извините, я не могу выполнить этот запрос. Он содержит недопустимый контент."
        state["messages"].append(AIMessage(content=response))
        logger.info("responder_blocked")
        return state
    
    # Handle export intent
    if intent == "export":
        response = "Для экспорта маршрута, пожалуйста, используйте кнопку экспорта в интерфейсе."
        state["messages"].append(AIMessage(content=response))
        logger.info("responder_export")
        return state
    
    # Handle ask_question intent
    if intent == "ask_question":
        if itinerary:
            response = f"Вот информация, которую я нашел по вашему запросу. {itinerary[0].activities[0].description if itinerary[0].activities else 'Нет доступной информации.'}"
        else:
            response = "К сожалению, я не нашел информацию по вашему запросу. Попробуйте переформулировать вопрос."
        state["messages"].append(AIMessage(content=response))
        logger.info("responder_question")
        return state
    
    # Handle plan_trip / change_plan
    if error_context:
        response = f"При планировании возникли следующие проблемы:\n" + "\n".join(f"- {e}" for e in error_context)
        response += "\n\nПожалуйста, уточните ваши предпочтения и попробуйте снова."
    else:
        # Build success response
        if itinerary:
            response = f"Я составил для вас маршрут на {len(itinerary)} дней в {state['user_preferences'].city}.\n\n"

            for day in itinerary:
                response += f"\n### День {day.day_number}: {day.date.strftime('%d.%m.%Y')}\n"
                for activity in day.activities:
                    description = _translate_to_russian(activity.description)
                    response += f"- **{activity.name}**: {description}\n"
                for meal in day.meals:
                    response += f"- {meal.name}\n"
                response += "\n"
            
            if booking_candidates:
                response += f"Найдено вариантов размещения: {len(booking_candidates)}\n"
            
            if map_data:
                response += "Карта маршрута доступна в интерфейсе.\n"
            
            # Add degradation warnings
            if state.get("retrieval_degraded"):
                response += "\n⚠️ Некоторые данные могут быть менее точны из-за ограничений доступа к базе знаний."
            if state.get("booking_degraded"):
                response += "\n⚠️ Информация о ценах может быть недоступна."
            if state.get("maps_degraded"):
                response += "\n⚠️ Карта маршрута недоступна."
        else:
            response = "Не удалось составить маршрут. Пожалуйста, попробуйте снова с другими параметрами."
    
    state["messages"].append(AIMessage(content=response))
    
    logger.info(
        "responder_completed",
        intent=intent,
        response_length=len(response),
        has_errors=len(error_context) > 0
    )
    
    return state
    return state
