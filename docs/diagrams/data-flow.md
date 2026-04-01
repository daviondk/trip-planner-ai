# Data Flow Diagram — Trip Planner AI

Как данные проходят через систему: что передаётся, что хранится, что логируется, что маскируется.

## Основной data path (запрос → обработка → ответ)

```mermaid
flowchart LR
    subgraph input ["Входные данные"]
        UserMsg["Текст пользователя<br/>(город, даты,<br/>интересы, бюджет)"]
        KnowledgeBase["База знаний<br/>(описания мест,<br/>POI, визовые правила)"]
    end

    subgraph processing ["Обработка"]
        Sanitizer["Sanitizer<br/>(PII → плейсхолдеры,<br/>injection scan)"]
        Router["Router<br/>(intent classification)"]
        Agents["Агенты<br/>(Planner, Info/RAG,<br/>Booking, Mapper)"]
        Validator["Validator<br/>(проверка полноты)"]
        Responder["Responder<br/>(сборка ответа)"]
    end

    subgraph external ["Внешние API"]
        YandexGPT["YandexGPT"]
        MapsAPI["Maps API"]
        BookingAPI["Booking APIs"]
    end

    subgraph storage ["Хранение"]
        ChromaDB[("ChromaDB<br/>(embeddings)")]
        SessionStore[("Session Store<br/>(in-memory)")]
    end

    Output["Ответ пользователю<br/>(маршрут + карта +<br/>варианты бронирования)"]

    UserMsg --> Sanitizer --> Router --> Agents
    Agents --> Validator --> Responder --> Output

    Agents -- "LLM prompts" --> YandexGPT
    YandexGPT -- "JSON response" --> Agents

    Agents -- "Geocode, directions" --> MapsAPI
    MapsAPI -- "Coordinates, polylines" --> Agents

    Agents -- "Search params" --> BookingAPI
    BookingAPI -- "Hotels, flights JSON" --> Agents

    Agents -- "Vector query" --> ChromaDB
    ChromaDB -- "Top-K docs" --> Agents

    KnowledgeBase -- "Embedding pipeline" --> ChromaDB

    Router -- "Read state" --> SessionStore
    Agents -- "Write outputs" --> SessionStore
    Responder -- "Read all" --> SessionStore
```

## Observability data path (метрики, логи, трейсы)

```mermaid
flowchart LR
    subgraph sources ["Источники телеметрии"]
        FastAPI2["FastAPI Backend"]
        Orch2["LangGraph Orchestrator"]
        Tools2["Tool Executor"]
    end

    subgraph collect ["Инструментация"]
        LangfuseSDK["Langfuse SDK<br/>(декораторы на узлах)"]
        PromClient["prometheus_client<br/>(Counter, Histogram)"]
        Structlog["structlog<br/>(JSON logger)"]
    end

    subgraph store_obs ["Хранение телеметрии"]
        Langfuse[("Langfuse<br/>retention: 14 дней")]
        Prometheus[("Prometheus<br/>retention: 30 дней")]
        Stdout["Container stdout<br/>(JSON logs)"]
    end

    subgraph visualize ["Визуализация"]
        LangfuseUI["Langfuse UI<br/>Traces, costs"]
        Grafana["Grafana<br/>Дашборды, алерты"]
    end

    FastAPI2 -- "Request spans" --> LangfuseSDK
    Orch2 -- "Agent spans,<br/>LLM generations" --> LangfuseSDK
    Tools2 -- "Tool call spans" --> LangfuseSDK

    FastAPI2 -- "HTTP metrics" --> PromClient
    Tools2 -- "Tool metrics,<br/>CB state" --> PromClient
    Orch2 -- "Token counts" --> PromClient

    FastAPI2 -- "Events" --> Structlog
    Orch2 -- "Events" --> Structlog
    Tools2 -- "Events" --> Structlog

    LangfuseSDK --> Langfuse
    PromClient --> Prometheus
    Structlog --> Stdout

    Langfuse --> LangfuseUI
    Prometheus --> Grafana
```

## Классификация данных

### Что передаётся (транзитно, не хранится)

| Данные | Откуда | Куда | Формат |
|:---|:---|:---|:---|
| Текст запроса пользователя (после анонимизации) | Streamlit → FastAPI | Orchestrator → Agents | str (очищенный) |
| LLM prompt (system + context + messages) | Agent | YandexGPT API | JSON (OpenAI-compatible) |
| LLM response | YandexGPT API | Agent | JSON (structured output) |
| Параметры поиска отелей/билетов | Booking Agent | Booking APIs | JSON |
| Результаты бронирования | Booking APIs | Booking Agent → State | JSON (нормализованный) |
| Координаты и маршруты | Maps API | Mapper Agent → State | JSON (GeoJSON) |
| Документы из RAG | ChromaDB | Info/RAG Agent → LLM context | text + metadata |

### Что хранится (persistent / semi-persistent)

| Данные | Где | Retention | Формат |
|:---|:---|:---|:---|
| Эмбеддинги описаний мест | ChromaDB | Постоянно | Vectors float[384] + metadata JSON |
| Состояние сессии (TripPlannerState) | In-memory dict | TTL 1 час (по неактивности) | Python TypedDict |
| LLM traces (prompts, completions, tokens, cost) | Langfuse | 14 дней | Spans + generations |
| Time-series метрики | Prometheus | 30 дней | TSDB |
| Структурированные логи | Container stdout | До ротации контейнера | JSON lines |

### Что маскируется (PII Policy)

| Данные | Действие | Где применяется |
|:---|:---|:---|
| Имена пользователей | Замена на `[PERSON]` | Sanitizer (вход), логи |
| Телефоны, email | Замена на `[PHONE]`, `[EMAIL]` | Sanitizer (вход), логи |
| Точные координаты пользователя | Замена на название района | Логи, Langfuse traces |
| Паспортные данные | Не принимаются, не обрабатываются | — |
| Платёжные данные | Не принимаются (no payments in PoC) | — |
| Сырой текст пользователя (до анонимизации) | **Не логируется** | — |

## Жизненный цикл данных одной сессии

```mermaid
flowchart TD
    SessionStart(["Начало сессии"])

    SessionStart --> CreateState["Создание TripPlannerState<br/>в памяти"]
    CreateState --> Dialog["Цикл диалога:<br/>запросы → обработка → ответы"]
    Dialog --> StateUpdates["Обновление state<br/>на каждом шаге"]

    StateUpdates --> Idle{"Активность<br/>за последний час?"}
    Idle -- "Да" --> Dialog
    Idle -- "Нет" --> Cleanup["Удаление state<br/>из памяти"]
    Cleanup --> Traces["Traces и метрики<br/>остаются в Langfuse<br/>и Prometheus"]
    Traces --> Retention["Retention:<br/>Langfuse 14 дней,<br/>Prometheus 30 дней"]
    Retention --> Purge(["Автоматическое удаление"])
```

## Поток данных при экспорте

```mermaid
flowchart LR
    State[("Session State<br/>(itinerary_draft,<br/>booking_candidates,<br/>map_data)")] --> Exporter["Export Module"]

    Exporter -- "format=pdf" --> PDFGen["PDF Generator<br/>(Jinja2 template<br/>+ WeasyPrint)"]
    Exporter -- "format=ics" --> ICSGen["ICS Generator<br/>(icalendar library)"]

    PDFGen --> PDFFile["trip_plan.pdf"]
    ICSGen --> ICSFile["trip_plan.ics"]

    PDFFile --> Download(["Скачивание<br/>пользователем"])
    ICSFile --> Download
```

Экспорт — полностью детерминированный процесс без вызова LLM. Данные берутся из текущего состояния сессии и форматируются по шаблону.
