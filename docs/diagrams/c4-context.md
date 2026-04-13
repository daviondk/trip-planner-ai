# C4 Context Diagram — Trip Planner AI

Система, пользователь, внешние сервисы и границы доверия.

```mermaid
flowchart TB
    traveler["<b>Путешественник</b><br/>Планирует поездку,<br/>задаёт предпочтения,<br/>получает маршрут"]

    subgraph tripplanner ["Trip Planner AI"]
        direction TB
        system["<b>Trip Planner AI</b><br/>Мульти-агентная система<br/>планирования путешествий<br/>(FastAPI + LangGraph + Streamlit)"]
    end

    yandexgpt[/"<b>YandexGPT/OpenRouter API</b><br/>Генерация текста,<br/>классификация, эмбеддинги"/]
    orsapi[/"<b>OpenRouteService API</b><br/>Построение маршрутов<br/>(бесплатно, 2000/день)"/]
    amadeus[/"<b>Amadeus API</b><br/>Поиск отелей/рейсов<br/>(бесплатно, 2000/месяц)"/]
    nominatim[/"<b>Nominatim (OSM)</b><br/>Геокодинг, POI<br/>(бесплатно, 1/сек)"/]
    chromadb[("<b>ChromaDB</b><br/>Векторная БД<br/>знаний о местах")]
    langfuse["<b>Langfuse</b><br/>Трейсинг и<br/>observability"]
    prometheus["<b>Prometheus + Grafana</b><br/>Метрики и алертинг"]

    traveler -- "Запрос на планирование<br/>(HTTP / WebSocket)" --> system
    system -- "Маршрут, карта,<br/>варианты бронирования" --> traveler

    system -- "LLM-запросы<br/>(HTTPS REST)" --> yandexgpt
    system -- "Геокодирование, маршруты<br/>(HTTPS REST)" --> mapsapi
    system -- "Поиск отелей/билетов<br/>(HTTPS REST)" --> bookingapi
    system -- "Векторный поиск<br/>(gRPC / HTTP)" --> chromadb
    system -.-> langfuse
    system -.-> prometheus
```

## Описание границ

| Граница | Внутри | Снаружи |
|:---|:---|:---|
| **Trip Planner AI** | Streamlit UI, FastAPI Backend, LangGraph Orchestrator, агенты (Planner, Info/RAG, Booking, Mapper), Session State, ChromaDB | — |
| **Внешние LLM** | — | YandexGPT/OpenRouter API (генерация, эмбеддинги) |
| **Внешние Data APIs** | — | OpenRouteService (маршруты), Amadeus (отели/рейсы), Nominatim (геокодинг) |
| **Observability** | — | Langfuse (трейсинг), Prometheus + Grafana (метрики, алерты) |

## Потоки данных на уровне контекста

| Поток | Направление | Протокол | Данные |
|:---|:---|:---|:---|
| Пользователь → Система | Входящий | HTTP / WebSocket | Текстовый запрос (город, даты, интересы, бюджет) |
| Система → Пользователь | Исходящий | HTTP / WebSocket | Маршрут (JSON + карта), варианты бронирования, PDF/ICS |
| Система → YandexGPT | Исходящий | HTTPS REST | Промпт + контекст (до 4000 токенов) |
| YandexGPT → Система | Входящий | HTTPS REST | Структурированный ответ (JSON) |
| Система → Maps API | Исходящий | HTTPS REST | Координаты, waypoints, режим транспорта |
| Maps API → Система | Входящий | HTTPS REST | Маршрут (polyline), расстояния, время |
| Система → Booking APIs | Исходящий | HTTPS REST | Параметры поиска (город, даты, бюджет) |
| Booking APIs → Система | Входящий | HTTPS REST | Список отелей/билетов (JSON) |
| Система → ChromaDB | Двусторонний | gRPC / HTTP | Запрос эмбеддинга → топ-K документов |

## Границы доверия

```mermaid
flowchart LR
    subgraph trusted ["Доверенная зона (наша инфраструктура)"]
        UI["Streamlit UI"]
        Backend["FastAPI"]
        Orchestrator["LangGraph"]
        VectorDB[("ChromaDB")]
    end

    subgraph untrusted_user ["Недоверенная зона: пользователь"]
        User["Путешественник"]
    end

    subgraph untrusted_apis ["Недоверенная зона: внешние API"]
        LLM["YandexGPT"]
        Maps["Maps API"]
        Hotels["Booking APIs"]
    end

    User -- "Sanitize + validate" --> UI
    UI --> Backend --> Orchestrator
    Orchestrator --> VectorDB
    Orchestrator -- "Circuit breaker<br/>+ timeout" --> LLM
    Orchestrator -- "Circuit breaker<br/>+ timeout" --> Maps
    Orchestrator -- "Circuit breaker<br/>+ timeout" --> Hotels
```

Пользовательский ввод проходит через анонимизацию PII и injection-сканер перед попаданием в оркестратор. Все внешние API защищены circuit breaker, timeout и retry-политиками. Ответы внешних API валидируются перед использованием.
