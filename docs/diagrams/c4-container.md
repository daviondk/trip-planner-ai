# C4 Container Diagram — Trip Planner AI

Внутренняя структура системы: контейнеры, хранилища, протоколы взаимодействия.

```mermaid
flowchart TB
    traveler["<b>Путешественник</b><br/>Браузер"]

    subgraph platform ["Trip Planner AI (Docker Compose)"]
        direction TB

        subgraph frontend ["Презентационный слой"]
            streamlit["<b>Streamlit UI</b><br/>Python · Port 8501<br/>Чат, карта, экспорт"]
        end

        subgraph backend ["Бизнес-логика"]
            fastapi["<b>FastAPI Backend</b><br/>Python · Port 8000<br/>REST API, валидация,<br/>health checks"]
            orchestrator["<b>LangGraph Orchestrator</b><br/>Python-модуль<br/>Граф агентов,<br/>управление состоянием"]
        end

        subgraph agents ["Специализированные агенты"]
            planner["<b>Planner Agent</b><br/>Разбивка по дням,<br/>логика маршрута"]
            inforag["<b>Info/RAG Agent</b><br/>Поиск информации,<br/>генерация описаний"]
            booking["<b>Booking Agent</b><br/>Поиск отелей<br/>и билетов"]
            mapper["<b>Mapper Agent</b><br/>Геокодирование,<br/>маршруты на карте"]
        end

        subgraph storage ["Хранение"]
            session[("<b>Session Store</b><br/>In-memory dict<br/>TTL 1 час")]
            chromadb[("<b>ChromaDB</b><br/>Port 8100<br/>Векторное хранилище")]
        end

        subgraph observability ["Наблюдаемость"]
            langfuse["<b>Langfuse</b><br/>Port 3000<br/>LLM-трейсинг"]
            prometheus["<b>Prometheus</b><br/>Port 9090<br/>Метрики"]
            grafana["<b>Grafana</b><br/>Port 3100<br/>Дашборды, алерты"]
        end
    end

    yandexgpt[/"<b>YandexGPT API</b><br/>LLM + Embeddings"/]
    mapsapi[/"<b>Google Maps API</b><br/>Places, Directions"/]
    bookingapi[/"<b>Booking APIs</b><br/>Отели, билеты"/]

    traveler -- "HTTP :8501" --> streamlit
    streamlit -- "HTTP :8000<br/>REST JSON" --> fastapi
    fastapi -- "In-process call" --> orchestrator

    orchestrator --> planner
    orchestrator --> inforag
    orchestrator --> booking
    orchestrator --> mapper

    planner -- "HTTPS REST" --> yandexgpt
    inforag -- "HTTPS REST" --> yandexgpt
    inforag -- "HTTP :8100" --> chromadb
    booking -- "HTTPS REST" --> bookingapi
    mapper -- "HTTPS REST" --> mapsapi

    orchestrator -- "Read/Write" --> session

    fastapi -.-> langfuse
    orchestrator -.-> langfuse
    fastapi -.-> prometheus
    grafana -- "PromQL" --> prometheus
```

## Контейнеры и технологии

| Контейнер | Технология | Порт | Назначение | Ресурсы (PoC) |
|:---|:---|:---|:---|:---|
| **Streamlit UI** | Python / Streamlit | 8501 | Интерфейс пользователя: чат, интерактивная карта, кнопки действий, экспорт | 0.5 vCPU, 512 MB |
| **FastAPI Backend** | Python / FastAPI + Uvicorn | 8000 | HTTP API, входная валидация, PII-анонимизация, health checks, CORS | 0.5 vCPU, 512 MB |
| **LangGraph Orchestrator** | Python / LangGraph (in-process) | — | Граф агентов, маршрутизация по интентам, управление состоянием, retry/fallback | Работает внутри FastAPI |
| **ChromaDB** | ChromaDB (Docker) | 8100 | Векторное хранилище описаний мест, POI, визовых правил | 0.25 vCPU, 512 MB |
| **Session Store** | In-memory (Python dict) | — | Состояние сессии (TripPlannerState), TTL 1 час | Часть процесса FastAPI |
| **Langfuse** | Langfuse (Docker) | 3000 | Трейсинг LLM-вызовов, стоимость токенов, latency | 0.25 vCPU, 512 MB |
| **Prometheus** | Prometheus (Docker) | 9090 | Сбор метрик (request_duration, tool_errors, circuit_breaker_state) | 0.25 vCPU, 256 MB |
| **Grafana** | Grafana (Docker) | 3100 | Визуализация метрик, настройка алертов | 0.25 vCPU, 256 MB |

## Протоколы взаимодействия

| Источник | Назначение | Протокол | Формат данных |
|:---|:---|:---|:---|
| Streamlit → FastAPI | HTTP | REST | JSON |
| FastAPI → Orchestrator | In-process | Python call | TypedDict (TripPlannerState) |
| Agents → YandexGPT | HTTPS | REST | JSON (OpenAI-compatible) |
| Info/RAG → ChromaDB | HTTP | REST / gRPC | Embedding vector + metadata filters |
| Booking Agent → Booking APIs | HTTPS | REST | JSON |
| Mapper Agent → Maps API | HTTPS | REST | JSON |
| FastAPI → Langfuse | HTTPS | REST | Trace / Span / Generation |
| Prometheus → FastAPI | HTTP | Scrape /metrics | Prometheus text format |
| Grafana → Prometheus | HTTP | PromQL | Time series |

## Зависимости при запуске

```mermaid
flowchart LR
    ChromaDB["ChromaDB"] --> FastAPI["FastAPI + Orchestrator"]
    Langfuse["Langfuse"] --> FastAPI
    Prometheus["Prometheus"] --> Grafana["Grafana"]
    FastAPI --> Streamlit["Streamlit UI"]
```

Порядок запуска в Docker Compose: ChromaDB и Langfuse запускаются первыми (`depends_on` с health check), затем FastAPI, затем Streamlit. Prometheus и Grafana запускаются параллельно.
