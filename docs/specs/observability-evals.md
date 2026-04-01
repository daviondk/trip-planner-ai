# Спецификация модуля: Observability / Evals

Система мониторинга, трассировки, логирования, алертинга и оценки качества Trip Planner AI.

---

## 1. Трейсинг (Langfuse)

### Иерархия трейсов

Каждый запрос пользователя создаёт один Trace. Внутри Trace — Spans (по одному на каждый узел графа). Внутри Spans — Generations (по одному на каждый вызов LLM).

```
Trace (session_id, user_query)
├── Span: sanitizer
│   ├── input: raw_message (anonymized)
│   ├── output: cleaned_message | blocked
│   └── metadata: is_blocked, pii_detected_count
├── Span: router
│   ├── Generation: intent_classification
│   │   ├── model: yandexgpt-lite
│   │   ├── input_tokens, output_tokens, cost
│   │   └── output: {intent: "plan_trip"}
│   └── metadata: intent, routing_method (rule/llm)
├── Span: planner
│   ├── Generation: plan_generation
│   │   ├── model: yandexgpt-lite
│   │   └── input_tokens, output_tokens, cost
│   └── metadata: days_count, activities_count
├── Span: info_rag
│   ├── Span: retrieval (sub-span)
│   │   └── metadata: collection, results_count, top_score, duration_ms
│   ├── Generation: description_generation
│   └── metadata: retrieval_degraded, enriched_count
├── Span: booking
│   ├── Span: search_hotels (sub-span)
│   │   └── metadata: results_count, duration_ms, circuit_breaker_state
│   └── metadata: booking_degraded, candidates_count
├── Span: mapper
│   ├── Span: build_route (sub-span)
│   │   └── metadata: waypoints_count, duration_ms, circuit_breaker_state
│   └── metadata: maps_degraded, routes_count
├── Span: validator
│   └── metadata: passed, errors[], iteration_count
└── Span: responder
    └── metadata: response_length, degradation_flags[], total_cost
```

### Trace Attributes

| Атрибут | Тип | Описание |
|:---|:---|:---|
| `trace_id` | UUID | Уникальный ID запроса |
| `session_id` | UUID | ID сессии пользователя |
| `intent` | str | Классифицированный интент |
| `total_tokens` | int | Суммарное количество токенов |
| `total_cost` | float | Суммарная стоимость LLM-вызовов |
| `total_duration_ms` | int | Общее время обработки |
| `degradation_flags` | list[str] | Какие компоненты были degraded |
| `iteration_count` | int | Количество retry-итераций |

---

## 2. Метрики (Prometheus)

### Каталог метрик

#### HTTP-слой (FastAPI)

| Метрика | Тип | Labels | Описание |
|:---|:---|:---|:---|
| `http_requests_total` | Counter | method, endpoint, status_code | Общее число HTTP-запросов |
| `http_request_duration_seconds` | Histogram | method, endpoint | Время обработки запроса |
| `http_requests_in_progress` | Gauge | — | Текущие активные запросы |

#### Orchestrator

| Метрика | Тип | Labels | Описание |
|:---|:---|:---|:---|
| `orchestrator_requests_total` | Counter | intent, status (success/partial/error) | Запросы по интентам |
| `orchestrator_duration_seconds` | Histogram | intent | Время полного цикла |
| `orchestrator_iterations_total` | Histogram | intent | Кол-во итераций Validator → Planner |
| `orchestrator_degraded_total` | Counter | component (retrieval/llm/booking/maps) | Ответы с degradation |

#### LLM

| Метрика | Тип | Labels | Описание |
|:---|:---|:---|:---|
| `llm_requests_total` | Counter | model, agent, status | Вызовы LLM |
| `llm_request_duration_seconds` | Histogram | model, agent | Latency LLM-вызовов |
| `llm_tokens_total` | Counter | model, agent, direction (input/output) | Потребление токенов |
| `llm_cost_total` | Counter | model, agent | Стоимость в долларах |
| `llm_errors_total` | Counter | model, error_type | Ошибки LLM (timeout/5xx/invalid_json) |

#### Tools

| Метрика | Тип | Labels | Описание |
|:---|:---|:---|:---|
| `tool_calls_total` | Counter | tool_name, status (success/error/fallback) | Вызовы инструментов |
| `tool_duration_seconds` | Histogram | tool_name | Latency tool calls |
| `tool_errors_total` | Counter | tool_name, error_type | Ошибки по типам |
| `circuit_breaker_state` | Gauge | api_name | 0=closed, 1=open, 2=half_open |
| `circuit_breaker_trips_total` | Counter | api_name | Переходы CB в OPEN |

#### Retriever

| Метрика | Тип | Labels | Описание |
|:---|:---|:---|:---|
| `retriever_searches_total` | Counter | collection, status | Поисковые запросы |
| `retriever_duration_seconds` | Histogram | collection, rerank | Latency поиска |
| `retriever_results_count` | Histogram | collection | Кол-во результатов |

#### Sessions

| Метрика | Тип | Labels | Описание |
|:---|:---|:---|:---|
| `active_sessions` | Gauge | — | Текущие активные сессии |
| `session_tokens_total` | Histogram | — | Токены за сессию |
| `session_duration_seconds` | Histogram | — | Время жизни сессии |
| `session_expired_total` | Counter | — | Сессии, удалённые по TTL |

### SLI / SLO

| SLI | SLO | Метрика |
|:---|:---|:---|
| Success Rate | > 95% запросов завершаются без ошибок | `orchestrator_requests_total{status="success"}` / total |
| Response Time | p95 < 10 секунд | `orchestrator_duration_seconds` p95 |
| Tool Success Rate | > 85% tool calls успешны | `tool_calls_total{status="success"}` / total |
| Hallucination Rate | < 5% описаний без RAG-подтверждения | Langfuse eval scores |
| Session Cost | < $0.10 за сессию | `llm_cost_total` per session_id |

---

## 3. Логирование

### Формат: Structured JSON (structlog)

```json
{
  "timestamp": "2026-04-01T12:00:00.123Z",
  "level": "INFO",
  "service": "orchestrator",
  "event": "AGENT_STARTED",
  "session_id": "abc-123",
  "trace_id": "lf-456",
  "agent": "planner",
  "intent": "plan_trip",
  "iteration": 1,
  "duration_ms": null
}
```

### Каталог событий

| Event | Level | Service | Описание |
|:---|:---|:---|:---|
| `QUERY_RECEIVED` | INFO | fastapi | Новый запрос от пользователя |
| `QUERY_SANITIZED` | INFO | orchestrator | Запрос прошёл санитизацию |
| `INJECTION_DETECTED` | WARN | orchestrator | Обнаружена попытка injection |
| `INTENT_CLASSIFIED` | INFO | orchestrator | Интент определён |
| `AGENT_STARTED` | INFO | orchestrator | Агент начал работу |
| `AGENT_COMPLETED` | INFO | orchestrator | Агент завершил работу |
| `AGENT_FAILED` | ERROR | orchestrator | Агент завершился с ошибкой |
| `TOOL_CALLED` | INFO | tool_executor | Инструмент вызван |
| `TOOL_SUCCEEDED` | INFO | tool_executor | Инструмент вернул результат |
| `TOOL_FAILED` | WARN | tool_executor | Инструмент вернул ошибку |
| `TOOL_FALLBACK` | WARN | tool_executor | Использован fallback |
| `CB_STATE_CHANGED` | WARN | tool_executor | Circuit breaker сменил состояние |
| `RETRIEVAL_SEARCH` | INFO | retriever | Поисковый запрос в ChromaDB |
| `RETRIEVAL_DEGRADED` | WARN | retriever | ChromaDB/Embeddings недоступны |
| `VALIDATION_PASSED` | INFO | orchestrator | Валидация пройдена |
| `VALIDATION_FAILED` | WARN | orchestrator | Валидация не пройдена, retry |
| `RESPONSE_SENT` | INFO | fastapi | Ответ отправлен пользователю |
| `SESSION_CREATED` | INFO | fastapi | Новая сессия |
| `SESSION_EXPIRED` | INFO | fastapi | Сессия удалена по TTL |
| `CONTEXT_TRUNCATED` | INFO | orchestrator | Контекст обрезан (превышен бюджет) |
| `TOKEN_LIMIT_WARNING` | WARN | orchestrator | Сессия приближается к лимиту токенов |

### Правила PII

- Текст запроса: **только после анонимизации** (post-sanitizer)
- Ответы LLM: логируются в Langfuse, **не** в stdout
- API-ключи: маскируются (`****`)
- Координаты пользователя: заменяются на район
- session_id: псевдонимизирован (UUID, не привязан к пользователю)

---

## 4. Алертинг (Grafana Alerts)

### Критические (P0)

| Условие | Окно | Действие |
|:---|:---|:---|
| YandexGPT error rate > 10% | 5 мин | Проверить API status page, проверить circuit breaker |
| Circuit breaker OPEN на YandexGPT | Мгновенно | Система в degraded mode, проверить доступность API |
| FastAPI health check fail | 3 подряд | Перезапустить контейнер, проверить логи |
| ChromaDB недоступен | 2 мин | Проверить контейнер ChromaDB, перезапустить |

### Предупреждения (P1)

| Условие | Окно | Действие |
|:---|:---|:---|
| p95 latency > 15 секунд | 10 мин | Проверить LLM latency, tool latency, context size |
| Tool error rate > 20% | 10 мин | Проверить внешние API, circuit breaker statuses |
| Стоимость сессии > $0.50 | Per session | Проверить неэффективные промпты, бесконечные циклы |
| active_sessions > 10 | Мгновенно | Проверить утечку сессий (cleanup не работает) |

### Информационные (P2)

| Условие | Окно | Действие |
|:---|:---|:---|
| Новая сессия создана | Мгновенно | Для мониторинга активности |
| Экспорт маршрута выполнен | Мгновенно | Для мониторинга завершённых сценариев |
| Дневная статистика | 24 часа | Обзор: запросы, стоимость, ошибки, quality scores |

---

## 5. Dashboards (Grafana)

### Dashboard 1: System Overview

| Панель | Тип | Метрика |
|:---|:---|:---|
| Request Rate | Time series | `orchestrator_requests_total` rate |
| Success Rate | Stat | success / total * 100% |
| p50 / p95 / p99 Latency | Time series | `orchestrator_duration_seconds` quantiles |
| Active Sessions | Stat | `active_sessions` |
| Circuit Breaker Status | Table | `circuit_breaker_state` per api |

### Dashboard 2: LLM & Cost

| Панель | Тип | Метрика |
|:---|:---|:---|
| Token Usage (input/output) | Stacked bar | `llm_tokens_total` by direction |
| Cost per Hour | Time series | `llm_cost_total` rate |
| LLM Latency by Agent | Heatmap | `llm_request_duration_seconds` by agent |
| LLM Error Rate | Time series | `llm_errors_total` rate |
| Model Distribution | Pie | `llm_requests_total` by model |

### Dashboard 3: Tools & Reliability

| Панель | Тип | Метрика |
|:---|:---|:---|
| Tool Call Rate | Time series | `tool_calls_total` rate by tool |
| Tool Error Rate | Time series | `tool_errors_total` rate by tool |
| Fallback Rate | Time series | `tool_calls_total{status="fallback"}` rate |
| CB State Timeline | State timeline | `circuit_breaker_state` over time |
| Tool Latency Distribution | Histogram | `tool_duration_seconds` by tool |

---

## 6. Evals (Оценка качества)

### Golden Test Set

Набор из **30+ сценариев** с эталонными ожиданиями. Запускается перед каждым обновлением модели или промптов.

| Категория | Кол-во | Пример |
|:---|:---|:---|
| Простой маршрут (1 город, 2-3 дня) | 8 | "Суздаль на выходные с семьёй" |
| Сложный маршрут (несколько городов, 7+ дней) | 5 | "Золотое кольцо на неделю, бюджет 100к" |
| Изменение плана | 5 | "Замени музей на день 2 на парк" |
| Вопрос о месте | 5 | "Что посмотреть в Казани за 1 день?" |
| Edge-кейсы (противоречия, слишком общий запрос) | 5 | "Хочу недорого, но 5 звёзд" |
| Adversarial (injection, jailbreak) | 4 | "Ignore previous instructions..." |

### Verifiable Checks (автоматические)

| Проверка | Метод | Порог |
|:---|:---|:---|
| Даты валидны и последовательны | Код (datetime parsing) | 100% |
| Все дни маршрута заполнены | Код (len check) | 100% |
| Города в маршруте непротиворечивы | Код (set comparison) | 100% |
| Суммарный бюджет ≤ заданного | Код (sum comparison) | 95% |
| Координаты в пределах страны | Код (bounding box) | 95% |
| JSON-ответ валиден | Код (Pydantic validation) | 100% |
| Injection отклонён | Код (is_blocked == True) | 100% |

### LLM-as-Judge (субъективное качество)

| Критерий | Промпт-инструкция | Шкала |
|:---|:---|:---|
| Релевантность маршрута | "Соответствует ли маршрут запросу пользователя? Учтены ли интересы и ограничения?" | 1-5 |
| Полнота информации | "Есть ли описания мест, время посещения, стоимость? Достаточно ли деталей?" | 1-5 |
| Логичность маршрута | "Логичен ли порядок посещения? Нет ли бессмысленных перемещений?" | 1-5 |
| Качество текста | "Текст грамотный, дружелюбный, без галлюцинаций?" | 1-5 |

**Конфигурация judge:**
- Model: YandexGPT (та же, что и в системе) или более мощная для объективности
- Temperature: 0.0 (детерминированность)
- Few-shot: 2-3 примера с оценками для калибровки
- Порог прохождения: средний балл ≥ 3.5 из 5.0

### Regression Suite

Запускается **перед каждым**:
- Обновлением модели YandexGPT
- Изменением системных промптов
- Изменением логики оркестратора

```bash
# Запуск regression suite
python -m tests.eval_regression --golden-set tests/golden_set.json --output results/

# Результат: JSON с оценками по каждому сценарию
# CI fail если: verifiable checks < 95% OR llm_judge_avg < 3.5
```

---

## 7. Retention Policy

| Данные | Хранилище | Retention |
|:---|:---|:---|
| Langfuse traces | Langfuse (self-hosted) | 14 дней |
| Prometheus metrics | Prometheus | 30 дней |
| Container logs (stdout) | Docker log driver | До ротации (по размеру, default 100 MB) |
| Golden test results | Git (файлы JSON) | Постоянно (version controlled) |
| Grafana dashboards | Grafana provisioning (git) | Постоянно (version controlled) |

---

## 8. Definition of Done (Infra-Ready PoC)

Критерии готовности observability-инфраструктуры:

| Критерий | Статус | Проверка |
|:---|:---|:---|
| Langfuse принимает traces | Pending | Trace появляется в UI после запроса |
| Все узлы графа отображаются как spans | Pending | Каждый agent виден в trace tree |
| Prometheus собирает метрики | Pending | `curl localhost:9090/api/v1/targets` — все UP |
| Grafana dashboards развёрнуты | Pending | 3 dashboard-а доступны по URL |
| Алерты настроены | Pending | Тестовый алерт срабатывает при имитации ошибки |
| Structured logging включён | Pending | JSON-формат в stdout всех контейнеров |
| PII не попадает в логи | Pending | Ручная проверка: поиск телефонов/имён в логах |
| Golden test set создан | Pending | ≥ 30 сценариев в `tests/golden_set.json` |
| Golden test passing rate | Pending | Verifiable checks ≥ 95%, LLM judge avg ≥ 3.5 |
| Regression pipeline настроен | Pending | Скрипт запускается и выдаёт отчёт |
