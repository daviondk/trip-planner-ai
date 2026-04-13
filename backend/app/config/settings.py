from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # LLM Provider Selection
    LLM_PROVIDER: str = "yandexgpt"  # Options: yandexgpt, openrouter, mistral

    # YandexGPT
    YANDEX_GPT_API_KEY: str = ""
    YANDEX_GPT_FOLDER_ID: str = ""
    YANDEX_GPT_MODEL: str = "yandexgpt-lite/latest"
    YANDEX_GPT_EMBEDDING_MODEL: str = "text-search-query/latest"
    YANDEX_GPT_TIMEOUT: int = 10
    YANDEX_GPT_MAX_TOKENS: int = 2000
    YANDEX_GPT_TEMPERATURE: float = 0.3

    # OpenRouter
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "meta-llama/llama-3.3-70b-instruct:free"
    OPENROUTER_EMBEDDING_MODEL: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    OPENROUTER_TIMEOUT: int = 30
    OPENROUTER_MAX_TOKENS: int = 2000
    OPENROUTER_TEMPERATURE: float = 0.7

    # Mistral
    MISTRAL_API_KEY: str = ""
    MISTRAL_MODEL: str = "mistral-small-latest"
    MISTRAL_EMBEDDING_MODEL: str = "mistral-embed"
    MISTRAL_TIMEOUT: int = 30
    MISTRAL_MAX_TOKENS: int = 2000
    MISTRAL_TEMPERATURE: float = 0.3

    # ChromaDB
    CHROMA_HOST: str = "chromadb"
    CHROMA_PORT: int = 8100

    # External APIs (replaced with free alternatives)
    # Google Maps replaced with OpenRouteService
    # Booking.com replaced with Amadeus API

    # OpenRouteService (Free: 2000 requests/day)
    OPENROUTESERVICE_API_KEY: str = ""
    OPENROUTESERVICE_TIMEOUT: int = 10

    # Amadeus API (Free: 2000 calls/month)
    AMADEUS_API_KEY: str = ""
    AMADEUS_API_SECRET: str = ""
    AMADEUS_TIMEOUT: int = 10

    # Nominatim (OpenStreetMap, Free: 1 req/sec)
    NOMINATIM_USER_AGENT: str = "trip-planner-ai-poc"

    # OpenTripMap API (Free: 5000 requests/day)
    # Get API key at: https://dev.opentripmap.org/
    OPENTRIPMAP_API_KEY: str = "your-opentripmap-api-key-here"
    OPENTRIPMAP_TIMEOUT: int = 10

    # SerpApi (Google Hotels & Flights)
    # Free tier: 100 searches/month
    # Get API key at: https://serpapi.com/
    SERPAPI_API_KEY: str = ""
    SERPAPI_TIMEOUT: int = 10

    # Observability
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "http://langfuse:3000"
    LANGFUSE_PG_USER: str = "langfuse"
    LANGFUSE_PG_PASSWORD: str = ""
    LANGFUSE_SECRET: str = ""
    LOG_LEVEL: str = "INFO"

    # Application
    SESSION_TTL_SECONDS: int = 3600
    SESSION_TOKEN_LIMIT: int = 50000
    MAX_ITERATIONS: int = 3
    REQUEST_TIMEOUT_SECONDS: int = 30
    CIRCUIT_BREAKER_THRESHOLD: int = 5
    CIRCUIT_BREAKER_COOLDOWN: int = 60
    CORS_ORIGINS: str = "http://localhost:8501"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


# Global settings instance
settings = Settings()
