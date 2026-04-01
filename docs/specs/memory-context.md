# Спецификация модуля: Memory / Context

## 1. Session State

### Схема состояния

Состояние сессии хранится в `TripPlannerState` — TypedDict, передаваемый между узлами LangGraph. Каждый узел читает нужные ему поля и записывает свои результаты.

```python
class TripPlannerState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    user_preferences: UserPreferences
    current_intent: str                    # plan_trip | change_plan | ask_question | export
    itinerary_draft: list[DayPlan]
    booking_candidates: list[BookingOption]
    map_data: MapData | None
    agent_outputs: dict[str, Any]
    iteration_count: int
    error_context: list[str]
    retrieval_degraded: bool               # True если ChromaDB/Embeddings недоступны
    created_at: datetime
    last_activity_at: datetime

class UserPreferences(BaseModel):
    city: str
    country: str | None = None
    start_date: date
    end_date: date
    travelers: TravelerGroup
    budget: BudgetInfo
    interests: list[str]                   # ["история", "кухня", "природа"]
    constraints: list[str]                 # ["с детьми", "без машины"]
    accommodation_type: str | None = None  # hotel | hostel | apartment

class TravelerGroup(BaseModel):
    adults: int = 1
    children: int = 0
    children_ages: list[int] = []

class BudgetInfo(BaseModel):
    total: int | None = None
    per_day: int | None = None
    currency: str = "RUB"
    level: str = "medium"                  # budget | medium | premium

class DayPlan(BaseModel):
    day_number: int
    date: date
    activities: list[Activity]
    meals: list[Activity]
    accommodation: BookingOption | None
    notes: str | None

class Activity(BaseModel):
    name: str
    description: str
    category: str
    start_time: str | None                 # "10:00"
    duration_minutes: int | None
    coordinates: tuple[float, float] | None
    estimated_cost: int | None
    source: str                            # "rag" | "llm" | "api"
```

### Жизненный цикл сессии

| Этап | Триггер | Изменения в State |
|:---|:---|:---|
| Создание | Первый запрос пользователя | `session_id`, `created_at`, `last_activity_at`, пустые коллекции |
| Сбор предпочтений | Router → intent: plan_trip | `user_preferences` заполняется |
| Планирование | Planner Agent | `itinerary_draft` создаётся |
| Обогащение | Info/RAG Agent | `itinerary_draft` дополняется описаниями |
| Бронирование | Booking Agent | `booking_candidates` заполняется |
| Карта | Mapper Agent | `map_data` заполняется |
| Перепланирование | Router → intent: change_plan | `itinerary_draft` модифицируется, `iteration_count` инкрементируется |
| Ошибка | Любой узел | `error_context` пополняется, флаги degraded |
| Завершение | TTL 1 час неактивности | State удаляется из памяти |

---

## 2. Что видит каждый агент

Не все агенты получают полный state. Каждый узел получает только релевантные поля для минимизации контекстного окна.

| Агент | Читает из State | Записывает в State |
|:---|:---|:---|
| **Sanitizer** | `messages` (последнее) | `messages` (очищенное) |
| **Router** | `messages` (последние 3), `user_preferences` | `current_intent` |
| **Planner** | `user_preferences`, `current_intent`, `itinerary_draft` (для change_plan) | `itinerary_draft` |
| **Info/RAG** | `itinerary_draft`, `user_preferences.interests` | `itinerary_draft` (обогащённый), `retrieval_degraded` |
| **Booking** | `user_preferences` (город, даты, бюджет), `itinerary_draft` | `booking_candidates` |
| **Mapper** | `itinerary_draft` (координаты), `user_preferences.city` | `map_data` |
| **Validator** | `itinerary_draft`, `booking_candidates`, `user_preferences` | `error_context` (при проблемах) |
| **Responder** | Всё (для сборки ответа) | `messages` (финальный ответ) |

---

## 3. Context Budget

### Бюджет на один вызов LLM

Общий лимит: **~4000 токенов** на вызов (для YandexGPT с контекстным окном ~8000 токенов, оставляем ~4000 на генерацию).

| Компонент контекста | Max токенов | Приоритет |
|:---|:---|:---|
| System prompt (per agent) | 500-800 | Высший (всегда включается) |
| Текущий черновик маршрута (сжатый) | 800-1200 | Высокий (всегда для Planner/Validator) |
| Предпочтения пользователя (JSON) | 200-300 | Высокий (всегда) |
| Последние 3 сообщения диалога | 600-900 | Средний |
| Результаты tool calls | 500-1000 | Средний |
| RAG-контекст (top-3 документа) | 600-900 | Средний (только для Info/RAG) |
| Предыдущие agent_outputs | 200-400 | Низкий (обрезается первым) |

### Правила обрезки (Truncation)

1. **Приоритетная обрезка**: при превышении бюджета первыми обрезаются компоненты с низким приоритетом
2. **Сообщения**: удаляются самые старые, но последние 3 остаются всегда
3. **Маршрут**: если `itinerary_draft` слишком длинный — сжимается до списка "день N: [место1, место2, ...]" без описаний
4. **RAG-результаты**: сокращаются с top-5 до top-3, затем обрезается `text` каждого документа
5. **Tool results**: обрезаются до первых 500 символов

### Оценка токенов на сценарий

| Сценарий | Агенты | Токенов (input+output) | Вызовов LLM |
|:---|:---|:---|:---|
| Новый маршрут (3 дня, простой) | Router + Planner + Info/RAG + Booking + Mapper + Validator | ~15 000 | 6-8 |
| Новый маршрут (7 дней, сложный) | То же + retry Validator | ~25 000 | 10-14 |
| Изменение плана (один день) | Router + Planner + Info/RAG + Mapper | ~8 000 | 4-5 |
| Вопрос о месте | Router + Info/RAG | ~4 000 | 2-3 |
| Экспорт | Router (только) | ~1 000 | 1 |

### Лимит на сессию

- **Максимум токенов за сессию**: 50 000
- При приближении к лимиту (>80%) — предупреждение пользователю
- При достижении лимита — завершение без новых LLM-вызовов, отдача того, что уже есть

---

## 4. Persistence

### Текущее решение (PoC)

| Хранилище | Технология | Retention | Данные |
|:---|:---|:---|:---|
| Session State | In-memory Python dict | TTL 1 час (по неактивности) | `TripPlannerState` |
| LangGraph Checkpoints | `MemorySaver` (in-memory) | Привязано к session TTL | Snapshot графа для каждого шага |

### Механизм TTL

```python
SESSION_TTL_SECONDS = 3600  # 1 час

# Фоновая задача (asyncio), проверяет каждые 5 минут
async def cleanup_expired_sessions():
    now = datetime.utcnow()
    for session_id, state in list(sessions.items()):
        if (now - state["last_activity_at"]).total_seconds() > SESSION_TTL_SECONDS:
            del sessions[session_id]
            logger.info("session_expired", session_id=session_id)
```

### Что теряется при перезапуске

- Все активные сессии (state, history, draft)
- Checkpoints LangGraph
- Кэш tool results

**Это приемлемо для PoC**, потому что:
- Одновременно обслуживается один пользователь
- Сессия планирования обычно занимает 10-30 минут
- Нет долгосрочных данных, которые нельзя воссоздать

### Будущее расширение (вне PoC)

| Хранилище | Технология | Данные |
|:---|:---|:---|
| User Profiles | PostgreSQL / Redis | Предпочтения, история поездок |
| Session Recovery | Redis + LangGraph SqliteSaver | Восстановление сессии после перезапуска |
| Trip Archive | PostgreSQL | Завершённые маршруты для повторного использования |

---

## 5. PII Policy

### Что НЕ хранится в State

| Данные | Причина |
|:---|:---|
| Паспортные данные | Не требуются для планирования |
| Платёжные данные | Нет бронирования в PoC |
| Сырой текст до анонимизации | PII-risk |
| Точные координаты пользователя | Заменяются на название района |

### Что хранится в State (с мерами защиты)

| Данные | Формат | Защита |
|:---|:---|:---|
| session_id | UUID | Псевдонимизация (не привязан к реальному пользователю) |
| Город, даты, бюджет | Структурированный JSON | Не являются PII |
| Интересы, ограничения | list[str] | Не являются PII |
| Имена (если введены в чат) | Заменены на `[PERSON]` | Sanitizer на входе |
| Телефоны, email | Заменены на `[PHONE]`, `[EMAIL]` | Sanitizer на входе |

### Логирование

- State **никогда** не логируется целиком
- В логи идут: `session_id`, `current_intent`, `iteration_count`, `error_context` (без содержимого запроса)
- В Langfuse traces: анонимизированные промпты (после Sanitizer)

---

## 6. Мониторинг

### Метрики (Prometheus)

| Метрика | Тип | Описание |
|:---|:---|:---|
| `active_sessions` | Gauge | Количество активных сессий в памяти |
| `session_duration_seconds` | Histogram | Время жизни сессии (от создания до cleanup) |
| `session_tokens_total` | Histogram | Суммарное потребление токенов за сессию |
| `context_truncation_total` | Counter | Количество срабатываний обрезки контекста |
| `session_expired_total` | Counter | Количество сессий, удалённых по TTL |

### Алерты

| Условие | Уровень | Действие |
|:---|:---|:---|
| `active_sessions > 10` | Warning | Проверить утечку сессий (cleanup не работает) |
| `session_tokens_total > 40000` | Warning | Сессия приближается к лимиту, проверить неэффективные промпты |
| `context_truncation_total` растёт быстро | Info | Возможно, промпты слишком длинные, оптимизировать |
