# C4 Component Diagram — Trip Planner AI

Внутреннее устройство ядра системы: компоненты LangGraph Orchestrator и Retrieval Pipeline.

## Orchestrator (LangGraph Graph)

```mermaid
flowchart TB
    entry(["Входящий запрос<br/>от FastAPI"])

    subgraph orchestrator ["LangGraph Orchestrator"]
        direction TB

        sanitizer["<b>Sanitizer</b><br/>PII-анонимизация,<br/>injection-сканер,<br/>валидация длины"]
        router["<b>Router</b><br/>Классификация интента<br/>(code-based rules +<br/>LLM fallback)"]
        planner["<b>Planner Agent</b><br/>Разбивка по дням,<br/>приоритизация<br/>активностей"]
        inforag["<b>Info/RAG Agent</b><br/>Поиск по ChromaDB,<br/>генерация описаний"]
        booking["<b>Booking Agent</b><br/>Поиск отелей<br/>и билетов"]
        mapper["<b>Mapper Agent</b><br/>Геокодирование,<br/>построение маршрутов"]
        validator["<b>Validator</b><br/>Проверка полноты,<br/>дат, бюджета,<br/>городов"]
        responder["<b>Responder</b><br/>Сборка финального<br/>ответа пользователю"]
    end

    state[("<b>TripPlannerState</b><br/>messages, preferences,<br/>itinerary, bookings,<br/>map_data, errors")]

    entry --> sanitizer
    sanitizer -- "valid" --> router
    sanitizer -- "injection detected" --> responder

    router -- "plan_trip" --> planner
    router -- "ask_question" --> inforag
    router -- "change_plan" --> planner
    router -- "export" --> responder

    planner --> inforag
    inforag --> booking
    booking --> mapper
    mapper --> validator

    validator -- "ok" --> responder
    validator -- "incomplete / retry" --> planner

    responder --> exit(["Ответ клиенту"])

    sanitizer -.-> state
    router -.-> state
    planner -.-> state
    inforag -.-> state
    booking -.-> state
    mapper -.-> state
    validator -.-> state
    responder -.-> state
```

## Retrieval Pipeline (Info/RAG Agent)

```mermaid
flowchart LR
    query["Семантический<br/>запрос от агента"]

    subgraph retrieval ["Retrieval Pipeline"]
        direction LR

        embedder["<b>Embedder</b><br/>YandexGPT<br/>Embeddings API"]
        search["<b>Vector Search</b><br/>ChromaDB<br/>cosine similarity"]
        filter["<b>Metadata Filter</b><br/>country, city,<br/>category, season,<br/>budget_level"]
        reranker["<b>Reranker</b><br/>LLM-based<br/>top-K → top-3"]
        formatter["<b>Context Formatter</b><br/>Сборка контекста<br/>для LLM"]
    end

    chromadb[("<b>ChromaDB</b><br/>destinations,<br/>points_of_interest,<br/>travel_tips")]

    query --> embedder --> search
    search --> filter --> reranker --> formatter

    search <--> chromadb

    formatter --> result["Структурированный<br/>контекст для LLM"]
```

## Tool Execution Layer

```mermaid
flowchart LR
    agent["Агент<br/>(LLM предлагает<br/>вызов tool)"]

    subgraph toolexec ["Tool Executor"]
        direction TB

        paramval["<b>Parameter Validator</b><br/>Pydantic-модели,<br/>типы, диапазоны"]
        cb["<b>Circuit Breaker</b><br/>CLOSED / OPEN /<br/>HALF_OPEN"]
        httpclient["<b>HTTP Client</b><br/>Timeout, retry,<br/>exponential backoff"]
        responseparser["<b>Response Parser</b><br/>Нормализация,<br/>обрезка,<br/>PII-маскирование"]
    end

    externalapi[/"<b>External API</b><br/>YandexGPT / Maps /<br/>Booking"/]

    agent --> paramval --> cb
    cb -- "CLOSED" --> httpclient
    cb -- "OPEN" --> fallback["Fallback:<br/>кэш / пустой<br/>результат + флаг"]
    httpclient --> externalapi
    externalapi --> responseparser
    responseparser --> result2["Результат<br/>в State"]
```

## Компоненты и их обязанности

| Компонент | Слой | Обязанности | Входные данные | Выходные данные |
|:---|:---|:---|:---|:---|
| **Sanitizer** | Input Guard | PII-анонимизация, injection detection, лимит символов | Сырой текст пользователя | Очищенный текст или rejection |
| **Router** | Orchestration | Определение интента (plan_trip, change_plan, ask_question, export) | Очищенный запрос + history | intent + параметры маршрутизации |
| **Planner Agent** | Agent | Декомпозиция поездки на дни, расстановка активностей | UserPreferences, intent | list[DayPlan] |
| **Info/RAG Agent** | Agent | Семантический поиск + генерация описаний мест | Запрос + context из Planner | Описания, факты, рейтинги |
| **Booking Agent** | Agent | Поиск отелей и билетов через внешние API | Город, даты, бюджет | list[BookingOption] |
| **Mapper Agent** | Agent | Геокодирование точек, построение маршрута | list[DayPlan] с адресами | MapData (координаты, polylines) |
| **Validator** | Output Guard | Проверка полноты (все дни заполнены, даты валидны, бюджет не превышен) | Собранный черновик | ok / retry с описанием проблемы |
| **Responder** | Output | Сборка финального JSON, форматирование для UI | Все agent_outputs | Структурированный ответ |
| **Embedder** | Retrieval | Преобразование текстового запроса в вектор | Текст | float[384] |
| **Vector Search** | Retrieval | Поиск ближайших соседей в ChromaDB | Вектор + metadata filters | top-K документов |
| **Reranker** | Retrieval | Переранжирование по релевантности через LLM | top-K документов + запрос | top-3 документа |
| **Parameter Validator** | Tool Exec | Валидация типов и диапазонов параметров tool call | Raw args от LLM | Validated Pydantic model |
| **Circuit Breaker** | Tool Exec | Защита от каскадных сбоев | Запрос к API | Pass / fallback |
| **HTTP Client** | Tool Exec | Выполнение запроса с timeout и retry | Validated request | Raw response |
| **Response Parser** | Tool Exec | Нормализация, обрезка, PII-маскирование ответа | Raw API response | Cleaned result |
