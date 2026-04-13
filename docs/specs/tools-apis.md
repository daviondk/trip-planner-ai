# Спецификация модуля: Tools / APIs

Все обращения к внешним сервисам проходят через tool layer. Агенты не ходят в Maps API или Booking API напрямую — только через типизированные функции. Каждый tool обёрнут в Pydantic-валидацию, circuit breaker и retry.

---

## 1. Каталог инструментов

### search_flights

Поиск авиабилетов по заданным параметрам.

```python
async def search_flights(
    origin: str,
    destination: str,
    departure_date: date,
    return_date: date | None = None,
    passengers: int = 1,
    max_price: int | None = None,
    cabin_class: str = "economy",
) -> list[FlightOption] | ToolError:
    """Поиск авиабилетов через Booking API."""
```

**Модели данных:**

```python
class FlightOption(BaseModel):
    airline: str                  # "Аэрофлот"
    flight_number: str            # "SU1234"
    origin_airport: str           # "SVO"
    destination_airport: str      # "LED"
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int
    price: Money
    cabin_class: str              # economy | business
    stops: int                    # 0 = прямой
    booking_url: str              # Ссылка на внешний сайт
    source: str                   # "aviasales" | "mock"

class Money(BaseModel):
    amount: int
    currency: str = "RUB"
```

**Тип**: Read-only | **Idempotent**: Да | **Side effects**: HTTP-запрос наружу

---

### search_hotels

Поиск вариантов размещения.

```python
async def search_hotels(
    city: str,
    checkin: date,
    checkout: date,
    guests: int = 1,
    max_price_per_night: int | None = None,
    min_rating: float = 0.0,
    hotel_type: str | None = None,
) -> list[HotelOption] | ToolError:
    """Поиск отелей через Booking API."""
```

**Модели данных:**

```python
class HotelOption(BaseModel):
    name: str                     # "Гостиница Пушкин"
    address: str
    city: str
    rating: float                 # 0.0-5.0
    stars: int | None             # 1-5 или None
    price_per_night: Money
    total_price: Money
    amenities: list[str]          # ["wifi", "breakfast", "parking"]
    hotel_type: str               # hotel | hostel | apartment
    coordinates: tuple[float, float]  # (lat, lon)
    booking_url: str
    source: str                   # "booking_api" | "mock"
    has_child_facilities: bool
```

**Тип**: Read-only | **Idempotent**: Да | **Side effects**: HTTP-запрос наружу

---

### get_poi_info

Поиск информации о достопримечательностях через RAG-retriever.

```python
async def get_poi_info(
    city: str,
    categories: list[str] | None = None,
    query: str | None = None,
    limit: int = 5,
    budget_level: str | None = None,
) -> list[POIInfo] | ToolError:
    """Поиск мест через ChromaDB retriever."""
```

**Модели данных:**

```python
class POIInfo(BaseModel):
    name: str                     # "Суздальский Кремль"
    description: str              # Сгенерированное описание (до 200 слов)
    category: str                 # museum | restaurant | park | church | etc.
    rating: float | None
    coordinates: tuple[float, float] | None
    opening_hours: str | None     # "10:00-18:00, Пн-Сб"
    estimated_duration_minutes: int | None  # Рекомендуемое время посещения
    estimated_cost: Money | None
    source: str                   # "rag" | "llm_generated"
    relevance_score: float        # 0.0-1.0 от retriever
```

**Тип**: Read-only | **Idempotent**: Да | **Side effects**: Нет (внутренний retriever)

---

### build_route

Построение маршрута между точками на карте.

```python
async def build_route(
    waypoints: list[Waypoint],
    transport_mode: str = "driving",
    optimize_order: bool = False,
) -> RouteResult | ToolError:
    """Построение маршрута через OpenRouteService Directions API (бесплатный tier)."""
```

**Модели данных:**

```python
class Waypoint(BaseModel):
    name: str
    coordinates: tuple[float, float]  # (lat, lon)

class RouteResult(BaseModel):
    total_distance_km: float
    total_duration_minutes: int
    legs: list[RouteLeg]
    polyline: str                  # Encoded polyline для отображения на карте
    map_url: str                   # Ссылка на Google Maps с маршрутом

class RouteLeg(BaseModel):
    start: str                    # Название начальной точки
    end: str                      # Название конечной точки
    distance_km: float
    duration_minutes: int
    transport_mode: str           # driving | walking | transit
```

**Тип**: Read-only | **Idempotent**: Да | **Side effects**: HTTP-запрос к Maps API

---

### export_itinerary

Экспорт готового маршрута в файл.

```python
async def export_itinerary(
    session_id: str,
    format: str = "pdf",
) -> ExportResult | ToolError:
    """Экспорт маршрута в PDF или ICS. Не вызывает внешних API."""
```

**Модели данных:**

```python
class ExportResult(BaseModel):
    format: str                   # "pdf" | "ics"
    filename: str                 # "trip_suzdal_2026-05-01.pdf"
    file_size_bytes: int
    download_url: str             # Временная ссылка (TTL 1 час)
```

**Тип**: Write (создание файла) | **Idempotent**: Да (повторный вызов перезаписывает) | **Side effects**: Создание файла на диске

---

## 2. Общие правила

### Таймауты и retry

| Tool | Timeout | Retry | Backoff | Circuit Breaker |
|:---|:---|:---|:---|:---|
| `search_flights` | 5s | 2x | Exponential: 1s, 2s | 5 err / 60s |
| `search_hotels` | 5s | 2x | Exponential: 1s, 2s | 5 err / 60s |
| `get_poi_info` | 2s | 1x | Fixed: 500ms | Нет (внутренний) |
| `build_route` | 3s | 2x | Exponential: 1s, 2s | 5 err / 60s |
| `export_itinerary` | 10s | 0 | — | Нет |

### Side effects

Все tools, кроме `export_itinerary`, являются read-only. Единственные side effects — HTTP-запросы к внешним сервисам и запись в кэш.

`export_itinerary` создаёт файл на диске, но не взаимодействует с внешними API. В PoC бронирование не производится — пользователь получает ссылку на внешний сайт.

### Идемпотентность

Все tools идемпотентны: повторный вызов с теми же параметрами возвращает эквивалентный результат (с учётом обновления данных в реальном времени для search-функций).

---

## 3. Обработка ошибок

### Таксономия ошибок

```python
class ToolError(BaseModel):
    error_type: str       # Код ошибки
    message: str          # Человекочитаемое описание
    retryable: bool       # Можно ли повторить
    tool_name: str        # Какой tool упал

class ToolErrorType(str, Enum):
    INVALID_PARAMS = "INVALID_PARAMS"         # Невалидные входные данные
    API_TIMEOUT = "API_TIMEOUT"               # Таймаут внешнего API
    API_ERROR = "API_ERROR"                   # 5xx от внешнего API
    RATE_LIMITED = "RATE_LIMITED"              # 429 от внешнего API
    CIRCUIT_OPEN = "CIRCUIT_OPEN"             # Circuit breaker в состоянии OPEN
    NOT_FOUND = "NOT_FOUND"                   # Маршрут / город не найден
    EXPORT_FAILED = "EXPORT_FAILED"           # Ошибка генерации файла
    INTERNAL_ERROR = "INTERNAL_ERROR"         # Непредвиденная ошибка
```

### Fallback-стратегии по tool

| Tool | При ошибке | Fallback |
|:---|:---|:---|
| `search_flights` | API_TIMEOUT / CIRCUIT_OPEN | Сообщение: "Не удалось найти билеты. Рекомендуем проверить на [ссылка]" |
| `search_hotels` | API_TIMEOUT / CIRCUIT_OPEN | Список отелей из RAG (без актуальных цен) с пометкой "цены могут отличаться" |
| `get_poi_info` | CHROMA_UNAVAILABLE | Генерация описаний из знаний LLM с предупреждением пользователю |
| `build_route` | API_TIMEOUT / CIRCUIT_OPEN | Текстовое описание маршрута без карты, расстояния по прямой |
| `export_itinerary` | EXPORT_FAILED | Текстовый вариант маршрута в чате |

---

## 4. Circuit Breaker

Отдельный экземпляр circuit breaker для каждого внешнего API.

| Параметр | Значение |
|:---|:---|
| Порог ошибок (failure_threshold) | 5 |
| Окно подсчёта ошибок | 60 секунд (скользящее) |
| Cooldown (OPEN → HALF_OPEN) | 60 секунд |
| Пробный запрос в HALF_OPEN | 1 |
| Успешный probe → CLOSED | Да |
| Неуспешный probe → OPEN | Да, + новый cooldown |

### Что считается ошибкой

- HTTP 5xx
- Timeout (нет ответа за указанный timeout)
- Connection refused / DNS failure

### Что НЕ считается ошибкой circuit breaker

- HTTP 4xx (клиентская ошибка — проблема в параметрах, не в сервисе)
- HTTP 429 (rate limit — обрабатывается отдельно через Retry-After)
- Пустой результат (валидный ответ)

---

## 5. Безопасность

### Валидация параметров

Все входные параметры валидируются через Pydantic до отправки запроса:

- `date` — проверка формата и что дата не в прошлом
- `passengers` / `guests` — диапазон 1-10
- `max_price` — неотрицательное число
- `city`, `origin`, `destination` — строка длиной 1-100, без спецсимволов
- `transport_mode` — enum: driving | walking | transit
- `cabin_class` — enum: economy | business

### Rate Limiting

| API | Лимит (PoC) | Действие при превышении |
|:---|:---|:---|
| OpenRouteService API | 2000 запросов/день | Ожидание до следующего дня, fallback на текстовый маршрут |
| Amadeus APIs | 2000 вызовов/месяц | Retry-After, fallback на mock данные |
| Nominatim (OSM) | 1 запрос/сек | Ожидание 1 сек между запросами |
| YandexGPT/OpenRouter API | По лимиту тарифа | Retry-After, circuit breaker |

### PII в логах

- Параметры tools логируются **без** PII: имена заменены на `[PERSON]`, телефоны на `[PHONE]`
- Ответы API логируются в усечённом виде (первые 500 символов)
- booking_url логируется без query-параметров

---

## 6. Мониторинг

### Метрики (Prometheus)

| Метрика | Тип | Labels |
|:---|:---|:---|
| `tool_call_total` | Counter | tool_name, status (success/error/fallback) |
| `tool_call_duration_seconds` | Histogram | tool_name |
| `tool_error_total` | Counter | tool_name, error_type |
| `circuit_breaker_state` | Gauge | api_name, state (closed=0/open=1/half_open=2) |
| `circuit_breaker_trips_total` | Counter | api_name |

### Структура лога

```json
{
  "timestamp": "2026-04-01T12:00:00.456Z",
  "level": "INFO",
  "service": "tool_executor",
  "operation": "search_hotels",
  "session_id": "abc-123",
  "params": {"city": "Суздаль", "checkin": "2026-05-01", "checkout": "2026-05-03", "guests": 3},
  "status": "success",
  "results_count": 8,
  "duration_ms": 1200,
  "circuit_breaker": "CLOSED"
}
```
