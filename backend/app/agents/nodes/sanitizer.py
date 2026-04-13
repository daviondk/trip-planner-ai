import re
import structlog
from langchain_core.messages import HumanMessage, AIMessage
from app.models.schemas import TripPlannerState
from app.utils.langfuse_client import langfuse_client

logger = structlog.get_logger(__name__)

# Injection patterns
INJECTION_PATTERNS = [
    r"ignore previous",
    r"you are now",
    r"forget everything",
    r"new instruction",
    r"override",
    r"jailbreak",
    r"developer mode",
    r"admin mode"
]

# PII patterns
PII_PATTERNS = [
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]"),  # Email
    (r"\+?[0-9]{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[PHONE]"),  # Phone
    (r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", "[NAME]"),  # Full name (e.g., John Smith)
    (r"\b[A-Z][a-z]+ [A-Z]\. [A-Z][a-z]+\b", "[NAME]"),  # Name with middle initial
    (r"\bул\.|улица|пр\.|проспект|д\.|дом|кв\.|офис\b.*?\d+[а-яА-Я]?\b", "[ADDRESS]"),  # Russian address
    (r"\b\d{3}-\d{3}\b", "[CARD]"),  # Card number pattern (basic)
    (r"\b\d{11,}\b", "[PHONE]"),  # Russian phone numbers
]


def sanitize_input(text: str) -> tuple[str, bool]:
    """
    Sanitize user input by removing PII and detecting injection attempts.
    
    Args:
        text: Raw user input text
    
    Returns:
        Tuple of (sanitized_text, is_blocked)
    """
    # Check for injection patterns
    text_lower = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text_lower):
            logger.warning("injection_detected", pattern=pattern)
            return text, True  # Return original text but mark as blocked
    
    # Anonymize PII
    sanitized = text
    for pattern, replacement in PII_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized)
    
    # Validate length
    if len(sanitized) > 2000:
        logger.warning("input_too_long", length=len(sanitized))
        return sanitized[:2000], False
    
    if not sanitized.strip():
        logger.warning("empty_input")
        return sanitized, True
    
    return sanitized, False


@langfuse_client.observe()
def sanitizer_node(state: TripPlannerState) -> TripPlannerState:
    """
    Sanitizer node: PII anonymization and injection detection.
    
    Args:
        state: Current TripPlannerState
    
    Returns:
        Updated state with sanitized message and is_blocked flag
    """
    # Get the last message (user input)
    if not state["messages"]:
        logger.error("sanitizer_no_messages")
        return state
    
    last_message = state["messages"][-1]
    
    if not isinstance(last_message, HumanMessage):
        return state
    
    # Sanitize the content
    sanitized_content, is_blocked = sanitize_input(last_message.content)
    
    # Update the message content
    if sanitized_content != last_message.content:
        # Create new message with sanitized content
        state["messages"][-1] = HumanMessage(content=sanitized_content)
    
    # Set blocked flag
    state["is_blocked"] = is_blocked
    
    logger.info(
        "sanitizer_processed",
        is_blocked=is_blocked,
        content_length=len(sanitized_content)
    )
    
    return state
