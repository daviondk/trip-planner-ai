# Спецификация модуля: Retriever (ChromaDB)

## 1. Назначение

Модуль **Retriever** — поисковое ядро системы Trip Planner AI. Инкапсулирует логику взаимодействия с векторной базой данных **ChromaDB** и предоставляет унифицированный интерфейс для семантического поиска по базе знаний о путешествиях: описания городов, достопримечательности, рестораны, визовые правила, сезонные рекомендации.

### Не-цели

- Полнотекстовый поиск (BM25/Elasticsearch) — вне скоупа PoC
- Индексирование пользовательского контента
- Реальное время обновления данных из внешних источников

---

## 2. Источники данных

| Источник | Тип | Описание | Объём (PoC) |
|:---|:---|:---|:---|
| Wikipedia (ru/en) | Статьи | Описания городов, регионов, исторических мест | ~300 статей |
| OpenStreetMap | Structured | POI: рестораны, парки, музеи, отели | ~5000 записей |
| Синтетические данные | Generated | Описания для нетестовых регионов, визовые правила, советы | ~500 записей |
| Публичные travel-блоги | Text | Рекомендации, маршруты, отзывы (с указанием источника) | ~200 статей |

### Пайплайн индексации

```
Исходный документ → Очистка (HTML, markdown) → Chunking (512-1024 токенов, overlap 128)
→ Enrichment (metadata extraction) → Embedding (YandexGPT Embeddings API)
→ Upsert в ChromaDB
```

---

## 3. Интерфейс

### `search_places`

Основной инструмент для поиска информации о местах.

**Сигнатура:**

```python
def search_places(
    query: str,
    collection: str = "points_of_interest",
    city: str | None = None,
    country: str | None = None,
    category: str | None = None,
    season: str | None = None,
    budget_level: str | None = None,
    limit: int = 10,
) -> list[RetrievalResult]:
    """Семантический поиск по базе знаний о путешествиях."""
```

**Входные параметры:**

| Параметр | Тип | Обяз. | По умолчанию | Описание |
|:---|:---|:---:|:---|:---|
| `query` | `str` | Да | — | Семантический запрос на русском или английском |
| `collection` | `str` | Нет | `"points_of_interest"` | Целевая коллекция (см. раздел 4) |
| `city` | `str \| None` | Нет | `None` | Фильтр по городу |
| `country` | `str \| None` | Нет | `None` | Фильтр по стране |
| `category` | `str \| None` | Нет | `None` | Категория: museum, restaurant, park, hotel, transport |
| `season` | `str \| None` | Нет | `None` | Сезон: winter, spring, summer, autumn |
| `budget_level` | `str \| None` | Нет | `None` | Бюджет: budget, medium, premium |
| `limit` | `int` | Нет | `10` | Максимальное кол-во результатов (1-20) |

**Формат ответа:**

```python
class RetrievalResult(BaseModel):
    score: float              # Cosine similarity [0, 1]
    title: str                # Название места / документа
    text: str                 # Текст чанка (до 1024 токенов)
    source: str               # Источник: "wikipedia", "osm", "synthetic"
    metadata: PlaceMetadata   # Структурированные метаданные

class PlaceMetadata(BaseModel):
    city: str
    country: str
    category: str             # museum | restaurant | park | hotel | transport | general
    season: str | None        # Рекомендуемый сезон
    budget_level: str | None  # budget | medium | premium
    rating: float | None      # Рейтинг 0-5 (если есть)
    coordinates: tuple[float, float] | None  # (lat, lon)
```

**Пример ответа (JSON):**

```json
[
  {
    "score": 0.92,
    "title": "Суздальский Кремль",
    "text": "Суздальский Кремль — древнейшая часть города Суздаля...",
    "source": "wikipedia",
    "metadata": {
      "city": "Суздаль",
      "country": "Россия",
      "category": "museum",
      "season": null,
      "budget_level": "budget",
      "rating": 4.8,
      "coordinates": [56.4167, 40.4458]
    }
  }
]
```

---

## 4. Коллекции ChromaDB

| Коллекция | Назначение | Объём (PoC) | Размер чанка |
|:---|:---|:---|:---|
| `destinations` | Описания городов и регионов (обзоры, климат, транспорт) | ~500 | 512-1024 токенов |
| `points_of_interest` | Достопримечательности, рестораны, парки, отели с метаданными | ~5000 | 256-512 токенов |
| `travel_tips` | Визовые правила, советы путешественникам, сезонность | ~300 | 256-512 токенов |

### Схема метаданных (для всех коллекций)

```python
{
    "city": str,           # Нормализованное название города
    "country": str,        # ISO-код или полное название
    "category": str,       # Enum: museum, restaurant, park, hotel, transport, general, visa, tip
    "season": str | None,  # winter, spring, summer, autumn
    "budget_level": str | None,  # budget, medium, premium
    "source": str,         # wikipedia, osm, synthetic, blog
    "language": str,       # ru, en
    "updated_at": str,     # ISO datetime
}
```

---

## 5. Алгоритм поиска

### Основной flow

1. **Embedding запроса**: Преобразование `query` в вектор через YandexGPT Embeddings API (384 dimensions)
2. **Metadata-фильтрация**: Построение `where`-фильтра из переданных параметров (city, country, category, season, budget_level)
3. **Vector Search**: Cosine similarity в ChromaDB с `n_results=limit`
4. **Score threshold**: Отсечение результатов с `score < 0.5`
5. **Deduplication**: Удаление дублей по `title` (оставляем чанк с наивысшим score)

### Reranking (опциональный)

Когда Info/RAG Agent запрашивает высокую точность (параметр `rerank=True`):

1. Получить top-K результатов (K = limit * 3)
2. Отправить пары (query, document) в YandexGPT с промптом оценки релевантности
3. Отсортировать по оценке LLM, взять top-`limit`

Reranking увеличивает latency на ~1-2 секунды, поэтому используется только для финальной генерации маршрута, а не для промежуточных поисков.

---

## 6. Обработка ошибок

| Ошибка | Причина | Стратегия |
|:---|:---|:---|
| `CHROMA_UNAVAILABLE` | ChromaDB не отвечает или connection refused | Возврат пустого списка + установка флага `retrieval_degraded=True` в State. Агент переключается на генерацию из знаний LLM с предупреждением пользователю. |
| `EMBEDDING_TIMEOUT` | YandexGPT Embeddings API не ответил за 3s | Retry 1x → при повторном timeout — возврат пустого списка + флаг degraded. |
| `EMBEDDING_ERROR` | 5xx от YandexGPT Embeddings | Retry 2x с exponential backoff (1s, 2s) → пустой список + флаг. |
| `INVALID_COLLECTION` | Запрошена несуществующая коллекция | Fallback на `points_of_interest` + log warning. |
| `EMPTY_RESULTS` | Нет результатов выше score threshold | Расширение поиска: снижение threshold до 0.3, убрать metadata-фильтры → retry. Если всё ещё пусто — сообщение агенту "нет данных по запросу". |

---

## 7. Конфигурация

```bash
# ChromaDB
CHROMA_HOST=chromadb
CHROMA_PORT=8100

# Embeddings
EMBEDDING_MODEL=yandexgpt-embeddings
EMBEDDING_DIMENSIONS=384
EMBEDDING_TIMEOUT_SECONDS=3

# Поиск
RETRIEVER_DEFAULT_COLLECTION=points_of_interest
RETRIEVER_DEFAULT_LIMIT=10
RETRIEVER_SCORE_THRESHOLD=0.5
RETRIEVER_SCORE_THRESHOLD_FALLBACK=0.3
RETRIEVER_MAX_RETRIES=2
RETRIEVER_RERANK_ENABLED=false
```

---

## 8. SLO и ограничения

| Метрика | Целевое значение |
|:---|:---|
| Latency (без reranking) | p95 < 500ms |
| Latency (с reranking) | p95 < 2500ms |
| Availability | 99.5% (зависит от ChromaDB и YandexGPT Embeddings) |
| Max results per query | 20 |
| Embedding batch size | 1 (по одному запросу, без батчинга в PoC) |

---

## 9. Тестирование

### Unit-тесты

- `test_search_basic` — проверка базовой выдачи и структуры `RetrievalResult`
- `test_metadata_filters` — фильтрация по city, category, season возвращает корректные результаты
- `test_empty_results` — при невалидном запросе возвращается пустой список
- `test_deduplication` — в результатах нет дублей по `title`
- `test_score_threshold` — результаты с score < threshold отсечены

### Интеграционные тесты

- `test_chroma_connection` — ChromaDB доступен и отвечает
- `test_embedding_generation` — YandexGPT Embeddings возвращает вектор корректной размерности
- `test_end_to_end_search` — полный цикл: запрос → embedding → search → результат

### Quality-тесты

- Golden dataset: 30 пар (запрос → ожидаемые места в top-5)
- Метрика: Recall@5 >= 0.7, MRR >= 0.6

---

## 10. Мониторинг

### Метрики (Prometheus)

| Метрика | Тип | Labels |
|:---|:---|:---|
| `retriever_search_total` | Counter | collection, status (success/error) |
| `retriever_search_duration_seconds` | Histogram | collection, rerank (true/false) |
| `retriever_results_count` | Histogram | collection |
| `retriever_errors_total` | Counter | error_type (chroma_unavailable/embedding_timeout/embedding_error) |
| `retriever_score_distribution` | Histogram | collection |

### Структура лога

```json
{
  "timestamp": "2026-04-01T10:00:00.123Z",
  "level": "INFO",
  "service": "retriever",
  "operation": "search",
  "session_id": "abc-123",
  "collection": "points_of_interest",
  "query_length": 45,
  "filters": {"city": "Суздаль", "category": "museum"},
  "results_count": 5,
  "top_score": 0.92,
  "duration_ms": 320,
  "rerank": false
}
```
