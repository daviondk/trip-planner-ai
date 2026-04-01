# Workflow Diagram — Trip Planner AI

Пошаговое выполнение запроса, включая ветки ошибок и механизмы отказоустойчивости.

## Основной workflow (Happy Path)

```mermaid
flowchart TD
    Start(["Пользователь отправляет запрос"])

    Start --> Sanitize["<b>Sanitizer</b><br/>PII-анонимизация,<br/>injection scan,<br/>валидация длины"]

    Sanitize --> SanitizeOK{"Запрос безопасен?"}
    SanitizeOK -- "Нет: injection" --> SafeReject["Сообщение:<br/>Пожалуйста,<br/>перефразируйте запрос"]
    SanitizeOK -- "Да" --> Router["<b>Router</b><br/>Классификация интента"]

    Router --> IntentSwitch{"Интент"}

    IntentSwitch -- "plan_trip" --> PlanFlow["Полный цикл<br/>планирования"]
    IntentSwitch -- "change_plan" --> ChangeFlow["Частичное<br/>перепланирование"]
    IntentSwitch -- "ask_question" --> AskFlow["Поиск информации<br/>(Info/RAG)"]
    IntentSwitch -- "export" --> ExportFlow["Экспорт маршрута<br/>(PDF / ICS)"]

    PlanFlow --> Planner["<b>Planner Agent</b><br/>Разбивка по дням,<br/>структура маршрута"]
    Planner --> InfoRAG["<b>Info/RAG Agent</b><br/>Поиск мест,<br/>описания"]
    InfoRAG --> Booking["<b>Booking Agent</b><br/>Отели, билеты"]
    Booking --> Mapper["<b>Mapper Agent</b><br/>Маршрут на карте"]

    ChangeFlow --> Planner
    AskFlow --> InfoRAG

    Mapper --> Validator["<b>Validator</b><br/>Проверка полноты:<br/>даты, бюджет, города"]
    InfoRAG --> ValidatorAsk["<b>Validator</b><br/>(упрощённая проверка)"]

    Validator --> ValidOK{"Валидация пройдена?"}
    ValidOK -- "Да" --> Responder
    ValidOK -- "Нет, iteration < 3" --> Planner
    ValidOK -- "Нет, max iterations" --> PartialResponse["Частичный ответ<br/>с пояснением"]

    ValidatorAsk --> Responder
    ExportFlow --> Responder
    PartialResponse --> Responder

    Responder["<b>Responder</b><br/>Сборка финального ответа"] --> End(["Ответ пользователю"])
    SafeReject --> End
```

## Workflow вызова внешнего API (Tool Call)

Применяется к каждому вызову: YandexGPT, Maps API, Booking APIs.

```mermaid
flowchart TD
    AgentCall(["Агент вызывает tool"])

    AgentCall --> ParamValidate["<b>Parameter Validator</b><br/>Pydantic-валидация"]
    ParamValidate --> ParamOK{"Параметры валидны?"}
    ParamOK -- "Нет" --> ParamError["Ошибка:<br/>INVALID_PARAMS"]
    ParamOK -- "Да" --> CBCheck{"Circuit Breaker<br/>состояние?"}

    CBCheck -- "OPEN" --> Fallback["Fallback-ответ:<br/>кэш / пустой результат<br/>+ флаг degraded"]
    CBCheck -- "CLOSED / HALF_OPEN" --> HTTPCall["HTTP-запрос<br/>с timeout"]

    HTTPCall --> HTTPResult{"Ответ получен?"}
    HTTPResult -- "Timeout / 5xx" --> RetryCheck{"retry_count < max?"}
    RetryCheck -- "Да" --> Backoff["Exponential backoff<br/>(1s, 2s, 4s)"]
    Backoff --> HTTPCall
    RetryCheck -- "Нет" --> CBTrip["Circuit Breaker:<br/>инкремент ошибок"]
    CBTrip --> CBThreshold{"Порог ошибок<br/>превышен?"}
    CBThreshold -- "Да" --> CBOpen["Circuit Breaker → OPEN<br/>(cooldown 60s)"]
    CBThreshold -- "Нет" --> Fallback
    CBOpen --> Fallback

    HTTPResult -- "200 OK" --> ParseResponse["Парсинг и нормализация<br/>ответа"]
    ParseResponse --> PIIMask["PII-маскирование<br/>в логах"]
    PIIMask --> ToolResult(["Результат → State"])

    ParamError --> ToolResult
    Fallback --> ToolResult
```

## Circuit Breaker — State Machine

```mermaid
stateDiagram-v2
    [*] --> CLOSED

    CLOSED --> CLOSED : Успешный запрос\n(сброс счётчика)
    CLOSED --> OPEN : Ошибка #N\n(N >= threshold=5\nза 60 секунд)

    OPEN --> HALF_OPEN : Cooldown 60s истёк

    HALF_OPEN --> CLOSED : Пробный запрос\nуспешен
    HALF_OPEN --> OPEN : Пробный запрос\nне удался

    note right of CLOSED
        Все запросы проходят.
        Ошибки считаются в
        скользящем окне 60s.
    end note

    note right of OPEN
        Запросы не отправляются.
        Возвращается fallback.
        Через 60s → HALF_OPEN.
    end note

    note left of HALF_OPEN
        Один пробный запрос.
        Успех → CLOSED.
        Ошибка → OPEN.
    end note
```

## Перепланирование маршрута (Change Plan)

```mermaid
flowchart TD
    UserChange(["Пользователь:<br/>Отмени музей на день 2,<br/>предложи парк рядом"])

    UserChange --> Sanitize["Sanitizer"]
    Sanitize --> Router["Router → change_plan"]
    Router --> ExtractDelta["<b>Planner</b><br/>Извлечение дельты:<br/>что удалить,<br/>что добавить"]

    ExtractDelta --> SearchAlt["<b>Info/RAG</b><br/>Поиск альтернатив<br/>с фильтром по<br/>геолокации отеля"]
    SearchAlt --> UpdatePlan["<b>Planner</b><br/>Обновление<br/>структуры дня 2"]
    UpdatePlan --> RebuildRoute["<b>Mapper</b><br/>Пересчёт маршрута"]
    RebuildRoute --> Validate["<b>Validator</b><br/>Проверка<br/>непротиворечивости"]
    Validate --> Respond(["Обновлённый<br/>маршрут"])
```

## Обработка недоступности YandexGPT

```mermaid
flowchart TD
    LLMCall(["Вызов YandexGPT"])

    LLMCall --> CB{"Circuit Breaker"}
    CB -- "OPEN" --> Degraded["Degraded mode:<br/>сообщение пользователю<br/>о временной недоступности"]

    CB -- "CLOSED" --> Request["HTTPS POST"]
    Request --> Result{"Ответ?"}

    Result -- "200 OK" --> Parse["Парсинг JSON"]
    Parse --> JSONValid{"JSON валиден?"}
    JSONValid -- "Да" --> Success(["Результат"])
    JSONValid -- "Нет" --> RetryPrompt["Retry с усиленным<br/>промптом на JSON"]
    RetryPrompt --> RetryResult{"Ответ?"}
    RetryResult -- "OK + valid" --> Success
    RetryResult -- "Снова невалиден" --> TextFallback["Fallback:<br/>текстовый ответ<br/>без структуры"]

    Result -- "429 Rate Limit" --> RateLimitWait["Ожидание<br/>Retry-After"]
    RateLimitWait --> Request

    Result -- "5xx / Timeout" --> Retry["Retry (max 2)<br/>backoff"]
    Retry --> RetryOK{"Успех?"}
    RetryOK -- "Да" --> Parse
    RetryOK -- "Нет" --> CBIncrement["CB: инкремент ошибок"]
    CBIncrement --> Degraded

    TextFallback --> Success
    Degraded --> UserMsg(["Сообщение:<br/>Сервис временно<br/>недоступен"])
```

## Сводка stop conditions

| Условие | Порог | Действие |
|:---|:---|:---|
| Итерации Validator → Planner | max 3 | Возврат частичного результата с пояснением |
| Retry на tool call | max 2 (с backoff) | Переход к fallback |
| Circuit Breaker errors | 5 ошибок за 60s | OPEN → fallback на 60s |
| Токены за сессию | лимит 50 000 | Предупреждение + завершение без новых LLM-вызовов |
| Время обработки запроса | 30s | Таймаут → частичный ответ с тем, что уже готово |
