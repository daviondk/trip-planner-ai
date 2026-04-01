# Спецификация модуля: Serving / Config

## 1. Назначение

Описание запуска, конфигурации, секретов, версий компонентов и операционных аспектов системы Trip Planner AI.

---

## 2. Docker Compose

Все компоненты разворачиваются через единый `docker-compose.yml`.

### Сервисы

```yaml
services:
  # === Frontend ===
  streamlit:
    build:
      context: .
      dockerfile: Dockerfile.streamlit
    ports: ["8501:8501"]
    env_file: .env
    depends_on:
      fastapi:
        condition: service_healthy
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 512M

  # === Backend ===
  fastapi:
    build:
      context: .
      dockerfile: Dockerfile.fastapi
    ports: ["8000:8000"]
    env_file: .env
    depends_on:
      chromadb:
        condition: service_healthy
      langfuse:
        condition: service_started
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 1536M

  # === Vector DB ===
  chromadb:
    image: chromadb/chroma:latest
    ports: ["8100:8000"]
    volumes:
      - chroma_data:/chroma/chroma
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
      interval: 10s
      timeout: 5s
      retries: 3
    deploy:
      resources:
        limits:
          cpus: "0.25"
          memory: 512M

  # === Observability ===
  langfuse:
    image: langfuse/langfuse:latest
    ports: ["3000:3000"]
    environment:
      DATABASE_URL: postgresql://${LANGFUSE_PG_USER}:${LANGFUSE_PG_PASSWORD}@langfuse-postgres:5432/langfuse
      NEXTAUTH_SECRET: ${LANGFUSE_SECRET}
      NEXTAUTH_URL: http://localhost:3000
    depends_on:
      langfuse-postgres:
        condition: service_healthy
    deploy:
      resources:
        limits:
          cpus: "0.25"
          memory: 512M

  langfuse-postgres:
    image: postgres:16-alpine
    volumes:
      - langfuse_pg_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: langfuse
      POSTGRES_USER: ${LANGFUSE_PG_USER}
      POSTGRES_PASSWORD: ${LANGFUSE_PG_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${LANGFUSE_PG_USER}"]
      interval: 5s
      timeout: 3s
      retries: 5

  prometheus:
    image: prom/prometheus:latest
    ports: ["9090:9090"]
    volumes:
      - ./config/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    deploy:
      resources:
        limits:
          cpus: "0.25"
          memory: 256M

  grafana:
    image: grafana/grafana:latest
    ports: ["3100:3000"]
    volumes:
      - grafana_data:/var/lib/grafana
      - ./config/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
      - ./config/grafana/datasources:/etc/grafana/provisioning/datasources:ro
    depends_on:
      - prometheus
    deploy:
      resources:
        limits:
          cpus: "0.25"
          memory: 256M

volumes:
  chroma_data:
  langfuse_pg_data:
  prometheus_data:
  grafana_data:
```

### Суммарные ресурсы

| Сервис | CPU | Memory | Порт |
|:---|:---|:---|:---|
| Streamlit | 0.5 vCPU | 512 MB | 8501 |
| FastAPI + Orchestrator | 1.0 vCPU | 1536 MB | 8000 |
| ChromaDB | 0.25 vCPU | 512 MB | 8100 |
| Langfuse | 0.25 vCPU | 512 MB | 3000 |
| Langfuse PostgreSQL | — | 256 MB | 5432 (internal) |
| Prometheus | 0.25 vCPU | 256 MB | 9090 |
| Grafana | 0.25 vCPU | 256 MB | 3100 |
| **Итого** | **~2.5 vCPU** | **~3.8 GB** | — |

Укладывается в ограничения PoC: 2 vCPU / 4 GB RAM (с учётом burst).

---

## 3. Переменные окружения

Конфигурация через `pydantic-settings` (`BaseSettings`) и `.env` файл.

### YandexGPT

| Переменная | Тип | Default | Описание |
|:---|:---|:---|:---|
| `YANDEX_GPT_API_KEY` | str | — (обязательно) | API-ключ YandexGPT |
| `YANDEX_GPT_FOLDER_ID` | str | — (обязательно) | ID каталога в Yandex Cloud |
| `YANDEX_GPT_MODEL` | str | `yandexgpt-lite/latest` | Модель для генерации |
| `YANDEX_GPT_EMBEDDING_MODEL` | str | `text-search-query/latest` | Модель для эмбеддингов |
| `YANDEX_GPT_TIMEOUT` | int | `10` | Timeout в секундах |
| `YANDEX_GPT_MAX_TOKENS` | int | `2000` | Max tokens на генерацию |
| `YANDEX_GPT_TEMPERATURE` | float | `0.3` | Temperature (низкая для структурированных ответов) |

### ChromaDB

| Переменная | Тип | Default | Описание |
|:---|:---|:---|:---|
| `CHROMA_HOST` | str | `chromadb` | Hostname ChromaDB |
| `CHROMA_PORT` | int | `8100` | Порт ChromaDB |

### External APIs

| Переменная | Тип | Default | Описание |
|:---|:---|:---|:---|
| `GOOGLE_MAPS_API_KEY` | str | — (обязательно) | Ключ Google Maps |
| `GOOGLE_MAPS_TIMEOUT` | int | `3` | Timeout Maps API |
| `BOOKING_API_KEY` | str | — (обязательно) | Ключ Booking API |
| `BOOKING_API_TIMEOUT` | int | `5` | Timeout Booking API |

### Observability

| Переменная | Тип | Default | Описание |
|:---|:---|:---|:---|
| `LANGFUSE_PUBLIC_KEY` | str | — (обязательно) | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | str | — (обязательно) | Langfuse secret key |
| `LANGFUSE_HOST` | str | `http://langfuse:3000` | Langfuse endpoint |
| `LANGFUSE_PG_USER` | str | `langfuse` | PostgreSQL user для Langfuse |
| `LANGFUSE_PG_PASSWORD` | str | — (обязательно) | PostgreSQL password для Langfuse |
| `LANGFUSE_SECRET` | str | — (обязательно) | NextAuth secret для Langfuse |
| `LOG_LEVEL` | str | `INFO` | Уровень логирования |

### Application

| Переменная | Тип | Default | Описание |
|:---|:---|:---|:---|
| `SESSION_TTL_SECONDS` | int | `3600` | TTL сессии (1 час) |
| `SESSION_TOKEN_LIMIT` | int | `50000` | Max токенов за сессию |
| `MAX_ITERATIONS` | int | `3` | Max retry Validator → Planner |
| `REQUEST_TIMEOUT_SECONDS` | int | `30` | Общий таймаут на запрос |
| `CIRCUIT_BREAKER_THRESHOLD` | int | `5` | Порог ошибок для CB |
| `CIRCUIT_BREAKER_COOLDOWN` | int | `60` | Cooldown CB в секундах |
| `CORS_ORIGINS` | str | `http://localhost:8501` | Разрешённые origins |

### Пример `.env`

```bash
# YandexGPT
YANDEX_GPT_API_KEY=AQVN...
YANDEX_GPT_FOLDER_ID=b1g...
YANDEX_GPT_MODEL=yandexgpt-lite/latest

# External APIs
GOOGLE_MAPS_API_KEY=AIza...
BOOKING_API_KEY=...

# Langfuse
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PG_USER=langfuse
LANGFUSE_PG_PASSWORD=changeme
LANGFUSE_SECRET=mysecret

# Application
LOG_LEVEL=INFO
SESSION_TTL_SECONDS=3600
```

---

## 4. Секреты

| Правило | Описание |
|:---|:---|
| Хранение | Файл `.env` в корне проекта, **не коммитится в git** (`.gitignore`) |
| Пример | `.env.example` с плейсхолдерами, коммитится |
| Логирование | API-ключи маскируются: `AQVN...****` |
| Docker | Передаются через `env_file`, не через `environment` inline |
| Ротация | При компрометации — пересоздание ключей в Yandex Cloud / Google Console |

---

## 5. Model Pinning

| Параметр | Значение | Назначение |
|:---|:---|:---|
| `YANDEX_GPT_MODEL` | `yandexgpt-lite/latest` | Основная модель (дешёвая, быстрая) |
| Fallback model | `yandexgpt/latest` | Для сложных задач (reranking, сложные маршруты) |
| `YANDEX_GPT_EMBEDDING_MODEL` | `text-search-query/latest` | Embedding model |

Модели пинятся через переменные окружения. Перед обновлением модели — обязательный прогон regression test suite (golden dataset).

---

## 6. Запуск и остановка

### Запуск

```bash
# 1. Создать .env из примера
cp .env.example .env
# 2. Заполнить реальные ключи
nano .env
# 3. Запустить все сервисы
docker compose up -d
# 4. Проверить health
curl http://localhost:8000/health
# 5. Открыть UI
open http://localhost:8501
```

### Последовательность запуска (через depends_on)

```
langfuse-postgres → langfuse ─┐
                               ├── fastapi → streamlit
chromadb ─────────────────────┘
prometheus → grafana
```

### Health Checks

| Сервис | Endpoint | Interval | Что проверяет |
|:---|:---|:---|:---|
| FastAPI | `GET /health` | 10s | Доступность API, состояние circuit breaker'ов |
| ChromaDB | `GET /api/v1/heartbeat` | 10s | Доступность vector DB |
| Langfuse PostgreSQL | `pg_isready` | 5s | Доступность БД |

### `GET /health` Response

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "uptime_seconds": 3600,
  "active_sessions": 1,
  "circuit_breakers": {
    "yandex_gpt": "CLOSED",
    "maps_api": "CLOSED",
    "booking_api": "HALF_OPEN"
  },
  "chromadb": "connected",
  "langfuse": "connected"
}
```

### Graceful Shutdown

1. FastAPI получает `SIGTERM`
2. Прекращает приём новых запросов
3. Ожидает завершения активных запросов (timeout: 30s)
4. Flush traces в Langfuse
5. Логирование `shutdown_complete`
6. Выход с кодом 0

```python
@app.on_event("shutdown")
async def shutdown():
    logger.info("shutdown_initiated")
    await langfuse_client.flush()
    logger.info("shutdown_complete")
```

---

## 7. Prometheus Configuration

```yaml
# config/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: "fastapi"
    static_configs:
      - targets: ["fastapi:8000"]
    metrics_path: /metrics

  - job_name: "chromadb"
    static_configs:
      - targets: ["chromadb:8000"]
```

---

## 8. Индексация ChromaDB

### Первоначальная загрузка данных

```bash
# Запуск скрипта индексации (после запуска ChromaDB)
docker compose exec fastapi python -m scripts.index_knowledge_base

# Проверка количества документов
curl http://localhost:8100/api/v1/collections
```

### Структура скрипта

```
scripts/
├── index_knowledge_base.py    # Основной скрипт индексации
├── data/
│   ├── destinations/          # JSON/MD файлы с описаниями городов
│   ├── points_of_interest/    # JSON файлы с POI
│   └── travel_tips/           # MD файлы с советами
```

Индексация идемпотентна: повторный запуск обновляет существующие записи по `document_id`.

---

## 9. Ограничения инфраструктуры (PoC)

| Ограничение | Описание | Влияние |
|:---|:---|:---|
| 2 vCPU / 4 GB RAM | Минимальные ресурсы сервера | Ограничивает параллелизм, один пользователь |
| Нет HTTPS | PoC работает по HTTP | Не для production |
| Нет persistent volumes backup | Данные ChromaDB в Docker volume | Потеря при удалении volume |
| Single node | Нет горизонтального масштабирования | Один экземпляр каждого сервиса |
| Docker Compose | Нет K8s | Нет auto-healing, rolling updates |
