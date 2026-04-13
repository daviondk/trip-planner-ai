"""
Unified LLM client abstraction supporting multiple providers.
Supports YandexGPT, OpenRouter, and Mistral.
"""
import structlog
import requests
from typing import Literal
from app.config.settings import settings
from app.utils.langfuse_client import langfuse_client
from app.utils.metrics import llm_invocations_total, llm_duration_seconds, llm_tokens_total

logger = structlog.get_logger(__name__)

LLMProvider = Literal["yandexgpt", "openrouter", "mistral"]


class BaseLLMClient:
    """Base class for LLM clients."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def call_llm(self, messages: list[dict[str, str]], agent: str = "unknown") -> tuple[str | None, int]:
        """
        Call LLM API for completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            agent: Agent name for metrics tracking

        Returns:
            Tuple of (LLM response text, total tokens used)
        """
        raise NotImplementedError


class YandexGPTClient(BaseLLMClient):
    """YandexGPT client implementation."""

    def call_llm(self, messages: list[dict[str, str]], agent: str = "unknown") -> tuple[str | None, int]:
        """
        Call YandexGPT API for completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            agent: Agent name for metrics tracking

        Returns:
            Tuple of (LLM response text, total tokens used)
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
                        "temperature": settings.YANDEX_GPT_TEMPERATURE,
                        "maxTokens": settings.YANDEX_GPT_MAX_TOKENS
                    },
                    "messages": messages
                },
                timeout=settings.YANDEX_GPT_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            # Track metrics
            duration = time.time() - start_time
            llm_invocations_total.labels(model=settings.YANDEX_GPT_MODEL, agent=agent).inc()
            llm_duration_seconds.labels(model=settings.YANDEX_GPT_MODEL, agent=agent).observe(duration)

            # Track tokens (if available)
            total_tokens = 0
            if "usage" in data:
                completion_tokens = data["usage"].get("completionTokens", 0)
                prompt_tokens = data["usage"].get("promptTokens", 0)
                total_tokens = completion_tokens + prompt_tokens
                llm_tokens_total.labels(model=settings.YANDEX_GPT_MODEL, type="input").inc(prompt_tokens)
                llm_tokens_total.labels(model=settings.YANDEX_GPT_MODEL, type="output").inc(completion_tokens)

            return data["choices"][0]["message"]["content"], total_tokens

        except Exception as e:
            logger.error("yandexgpt_call_failed", error=str(e))
            # Fallback to mock on error
            return None, 0
    
    def get_embedding(self, text: str) -> list[float] | None:
        """
        Get embedding from YandexGPT.

        Args:
            text: Text to embed

        Returns:
            Embedding vector or None on error
        """
        try:
            response = requests.post(
                "https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding",
                headers={
                    "Authorization": f"Bearer {settings.YANDEX_GPT_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "modelUri": f"emb://{settings.YANDEX_GPT_FOLDER_ID}/{settings.YANDEX_GPT_EMBEDDING_MODEL}",
                    "text": text
                },
                timeout=3.0
            )
            response.raise_for_status()
            data = response.json()
            return data["embedding"]
        except Exception as e:
            logger.error("yandexgpt_embedding_failed", error=str(e))
            return None


class OpenRouterClient(BaseLLMClient):
    """OpenRouter client implementation (OpenAI-compatible API)."""

    def call_llm(self, messages: list[dict[str, str]], agent: str = "unknown") -> tuple[str | None, int]:
        """
        Call OpenRouter API for completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            agent: Agent name for metrics tracking

        Returns:
            Tuple of (LLM response text, total tokens used)
        """
        import time
        start_time = time.time()

        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:8501",
                    "X-Title": "Trip Planner AI"
                },
                json={
                    "model": settings.OPENROUTER_MODEL,
                    "messages": messages,
                    "temperature": settings.OPENROUTER_TEMPERATURE,
                    "max_tokens": settings.OPENROUTER_MAX_TOKENS,
                    "stream": False
                },
                timeout=settings.OPENROUTER_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            # Track metrics
            duration = time.time() - start_time
            llm_invocations_total.labels(model=settings.OPENROUTER_MODEL, agent=agent).inc()
            llm_duration_seconds.labels(model=settings.OPENROUTER_MODEL, agent=agent).observe(duration)

            # Track tokens (if available)
            total_tokens = 0
            if "usage" in data:
                completion_tokens = data["usage"].get("completion_tokens", 0)
                prompt_tokens = data["usage"].get("prompt_tokens", 0)
                total_tokens = completion_tokens + prompt_tokens
                llm_tokens_total.labels(model=settings.OPENROUTER_MODEL, type="input").inc(prompt_tokens)
                llm_tokens_total.labels(model=settings.OPENROUTER_MODEL, type="output").inc(completion_tokens)

            return data["choices"][0]["message"]["content"], total_tokens

        except Exception as e:
            logger.error("openrouter_call_failed", error=str(e))
            # Fallback to mock on error
            return None, 0
    
    def get_embedding(self, text: str) -> list[float] | None:
        """
        Get embedding from OpenRouter.

        Args:
            text: Text to embed

        Returns:
            Embedding vector or None on error
        """
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:8501",
                    "X-Title": "Trip Planner AI"
                },
                json={
                    "model": settings.OPENROUTER_EMBEDDING_MODEL,
                    "input": text
                },
                timeout=3.0
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as e:
            logger.error("openrouter_embedding_failed", error=str(e))
            return None


class MistralClient(BaseLLMClient):
    """Mistral AI client implementation (OpenAI-compatible API)."""

    def call_llm(self, messages: list[dict[str, str]], agent: str = "unknown") -> tuple[str | None, int]:
        """
        Call Mistral API for completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            agent: Agent name for metrics tracking

        Returns:
            Tuple of (LLM response text, total tokens used)
        """
        import time
        start_time = time.time()

        try:
            response = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": settings.MISTRAL_MODEL,
                    "messages": messages,
                    "temperature": settings.MISTRAL_TEMPERATURE,
                    "max_tokens": settings.MISTRAL_MAX_TOKENS,
                    "stream": False
                },
                timeout=settings.MISTRAL_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            # Track metrics
            duration = time.time() - start_time
            llm_invocations_total.labels(model=settings.MISTRAL_MODEL, agent=agent).inc()
            llm_duration_seconds.labels(model=settings.MISTRAL_MODEL, agent=agent).observe(duration)

            # Track tokens (if available)
            total_tokens = 0
            if "usage" in data:
                completion_tokens = data["usage"].get("completion_tokens", 0)
                prompt_tokens = data["usage"].get("prompt_tokens", 0)
                total_tokens = completion_tokens + prompt_tokens
                llm_tokens_total.labels(model=settings.MISTRAL_MODEL, type="input").inc(prompt_tokens)
                llm_tokens_total.labels(model=settings.MISTRAL_MODEL, type="output").inc(completion_tokens)

            return data["choices"][0]["message"]["content"], total_tokens

        except Exception as e:
            logger.error("mistral_call_failed", error=str(e))
            # Fallback to mock on error
            return None, 0

    def get_embedding(self, text: str) -> list[float] | None:
        """
        Get embedding from Mistral.

        Args:
            text: Text to embed

        Returns:
            Embedding vector or None on error
        """
        try:
            response = requests.post(
                "https://api.mistral.ai/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": settings.MISTRAL_EMBEDDING_MODEL,
                    "input": text
                },
                timeout=3.0
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as e:
            logger.error("mistral_embedding_failed", error=str(e))
            return None


def get_llm_client(provider: LLMProvider | None = None) -> BaseLLMClient:
    """
    Factory function to get LLM client based on provider.

    Args:
        provider: Provider name (yandexgpt, openrouter, or mistral). If None, uses settings.LLM_PROVIDER

    Returns:
        LLM client instance
    """
    if provider is None:
        provider = settings.LLM_PROVIDER

    if provider == "yandexgpt":
        return YandexGPTClient("yandexgpt")
    elif provider == "openrouter":
        return OpenRouterClient("openrouter")
    elif provider == "mistral":
        return MistralClient("mistral")
    else:
        logger.warning("unknown_llm_provider", provider=provider, defaulting="yandexgpt")
        return YandexGPTClient("yandexgpt")


# Global client instance
llm_client = get_llm_client()
