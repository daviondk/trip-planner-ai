import structlog
import httpx
import re
import requests
from langchain_core.messages import HumanMessage, AIMessage
from app.models.schemas import TripPlannerState
from app.utils.langfuse_client import langfuse_client
from app.config.settings import settings
from app.utils.metrics import llm_invocations_total, llm_duration_seconds, llm_tokens_total

logger = structlog.get_logger(__name__)


def classify_intent_rule_based(text: str) -> str:
    """
    Rule-based intent classification (priority over LLM).
    
    Args:
        text: User input text
    
    Returns:
        Intent classification: plan_trip, change_plan, ask_question, export
    """
    text_lower = text.lower()
    
    # Export keywords
    export_keywords = ["экспорт", "export", "скачать", "download", "pdf", "ics", "календарь"]
    if any(keyword in text_lower for keyword in export_keywords):
        return "export"
    
    # Change plan keywords
    change_keywords = ["измени", "изменить", "замени", "убери", "добавь", "измени план", "change plan", "change the plan", "modify itinerary", "update plan", "change day", "remove activity", "add activity"]
    if any(keyword in text_lower for keyword in change_keywords):
        return "change_plan"
    
    # Question keywords
    question_keywords = ["расскажи", "что такое", "какой", "где", "когда", "почему", "почему", "?"]
    if any(keyword in text_lower for keyword in question_keywords):
        return "ask_question"
    
    # Default to plan_trip
    return "plan_trip"


def classify_intent_llm(text: str) -> tuple[str | None, int]:
    """
    LLM-based intent classification (fallback when rule-based is uncertain).
    
    Args:
        text: User input text
    
    Returns:
        Tuple of (Intent classification or None if LLM fails, tokens used)
    """
    import time
    start_time = time.time()
    
    try:
        response = requests.post(
            "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            headers={
                "Authorization": f"Bearer {settings.YANDEX_GPT_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "modelUri": f"gpt://{settings.YANDEX_GPT_FOLDER_ID}/{settings.YANDEX_GPT_MODEL}",
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.3,
                    "maxTokens": 100
                },
                "messages": [
                    {
                        "role": "system",
                        "content": "Classify the user's intent into one of: plan_trip, change_plan, ask_question, export. Return only the intent name."
                    },
                    {
                        "role": "user",
                        "content": text
                    }
                ]
            },
            timeout=10.0
        )
        response.raise_for_status()
        data = response.json()
        
        # Track metrics
        duration = time.time() - start_time
        llm_invocations_total.labels(model=settings.YANDEX_GPT_MODEL, agent="router").inc()
        llm_duration_seconds.labels(model=settings.YANDEX_GPT_MODEL, agent="router").observe(duration)
        
        total_tokens = 0
        if "usage" in data:
            completion_tokens = data["usage"].get("completionTokens", 0)
            prompt_tokens = data["usage"].get("promptTokens", 0)
            total_tokens = completion_tokens + prompt_tokens
            llm_tokens_total.labels(model=settings.YANDEX_GPT_MODEL, type="input").inc(prompt_tokens)
            llm_tokens_total.labels(model=settings.YANDEX_GPT_MODEL, type="output").inc(completion_tokens)
        
        result = data["choices"][0]["message"]["content"].strip().lower()
        
        # Validate result
        valid_intents = ["plan_trip", "change_plan", "ask_question", "export"]
        if result in valid_intents:
            return result, total_tokens
        else:
            logger.warning("router_llm_invalid_intent", result=result)
            return None, total_tokens
            
    except Exception as e:
        logger.error("router_llm_classification_failed", error=str(e))
        return None, 0


@langfuse_client.observe()
def router_node(state: TripPlannerState) -> TripPlannerState:
    """
    Router node: Classify user intent and route to appropriate agent.
    
    Args:
        state: Current TripPlannerState
    
    Returns:
        Updated state with current_intent
    """
    # Get the last message
    if not state["messages"]:
        logger.error("router_no_messages")
        state["current_intent"] = "ask_question"
        return state
    
    last_message = state["messages"][-1]
    
    if not isinstance(last_message, HumanMessage):
        return state
    
    # Try rule-based classification first
    intent = classify_intent_rule_based(last_message.content)
    
    # If rule-based is uncertain (defaulted to plan_trip), try LLM fallback
    if intent == "plan_trip":
        # Check if the input is actually asking a question (rule-based might have missed it)
        text_lower = last_message.content.lower()
        question_indicators = ["?", "как", "что", "где", "когда", "почему", "расскажи"]
        if any(indicator in text_lower for indicator in question_indicators):
            # Use LLM for better classification
            llm_intent, tokens_used = classify_intent_llm(last_message.content)
            state["token_count"] = state.get("token_count", 0) + tokens_used
            if llm_intent:
                intent = llm_intent
                logger.info("router_used_llm_fallback", intent=llm_intent)
    
    state["current_intent"] = intent
    
    logger.info(
        "router_classified",
        intent=intent,
        content_preview=last_message.content[:50]
    )
    
    return state
