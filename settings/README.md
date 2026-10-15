# SETTINGS — Typed Runtime Settings

> Типизированные runtime-настройки для Telegram-ботов на **aiogram 3.25+**.
>
> Поддерживает: Bool, Int, Float, Decimal, Str, Enum, Json, List, Tier, Duration.

---

## Что делает

- **Типизированные настройки** — `BoolSetting`, `DecimalSetting`, `TierSetting`...
- **Авто-админка** — `/settings` с типовыми редакторами (toggle, ввод числа, JSON)
- **Категории** — `rates`, `timers`, `deals`, `loyalty`, `system`...
- **Кеширование** — чтение из кеша, запись в хранилище
- **on_change hooks** — реакция на изменение значения

---

## Быстрый старт

```python
from settings import schema, types
from settings.runtime import get, set

# 1. Регистрация
schema.register(types.DecimalSetting(
    key="rates.coefficient",
    title="Коэффициент Rapira",
    default=Decimal("1.147"),
    category="rates",
))

# 2. Чтение
value = await get("rates.coefficient")  # Decimal

# 3. Админка
from settings.admin_handler import create_admin_router
dp.include_router(create_admin_router(admin_ids=[0]))
```

---

## Структура

```
settings/
├── __init__.py          # Публичный API (types, schema, runtime)
├── types.py             # Все типы настроек (BoolSetting, DecimalSetting...)
├── schema.py            # Регистрация, поиск, категории
├── runtime.py           # get / set / format_value / on_change
├── storage.py           # JSONBackend / SQLiteBackend / MemoryBackend
├── cache.py             # SettingCache (TTL)
├── admin_handler.py     # Router админки (/settings)
├── admin_kb.py          # Клавиатуры админки
├── admin_states.py      # FSM админки
├── admin_emoji.py       # Emoji для UI
└── inline.py            # Inline-режим (для callback-настроек)
```

---

## Типы настроек

| Тип | UI | Описание |
|-----|:---:|----------|
| `BoolSetting` | Toggle ✅/❌ | Вкл/выкл |
| `IntSetting` | Ввод числа | Целое, min/max |
| `DecimalSetting` | Ввод числа | Decimal, min/max |
| `StrSetting` | Ввод текста | Строка |
| `EnumSetting` | Выбор из списка | Фиксированные варианты |
| `JsonSetting` | Ввод JSON | Произвольный dict |
| `ListSetting` | — | Список строк |
| `TierSetting` | Специальный | `max→rate` tiers (лояльность) |
| `DurationSetting` | Ввод секунд | Число + форматирование |

---

## API

### Регистрация

```python
from settings import schema
from settings.types import DecimalSetting, BoolSetting

schema.register(DecimalSetting(key="rates.coef", title="Коэфф", default=Decimal("1.0")))
```

### Runtime

```python
from settings.runtime import get, set, format_value, on_change

value = await get("rates.coef")           # Decimal
await set("rates.coef", Decimal("1.1"))   # Сохранить
formatted = format_value("rates.coef")    # "1.1" (строка)

# Hook
on_change(lambda key, old, new: print(f"{key}: {old} → {new}"))
```

### Форматы

| Тип | `format_value` | Пример |
|-----|---------------|--------|
| Bool | `Вкл` / `Выкл` | — |
| Int | `3600` | — |
| Decimal | `1.147` | — |
| Str | `строка` | — |
| Enum | `вариант` | — |
| Tier | `500→0.2, 1000→0.4` | Лояльность |
| Duration | `10 мин` | Автоформат |

---

## Админка

```python
from settings.admin_handler import create_admin_router

# /settings — tree-based навигация по категориям
dp.include_router(create_admin_router(admin_ids=[0]))
```

Категории → список настроек → редактирование по типу:
- **Bool**: toggle inline-кнопкой ✅/❌
- **Int/Decimal/Str**: ввод текста (FSM)
- **Enum**: выбор из inline-списка
- **Tier**: специальный редактор tier-массива
- **Duration**: ввод секунд + автоформат

---

## Тестирование

См. `docs/TESTING_SYSTEM.md` → раздел **Settings / TPL Admin Routers**.

Критичные проверки:
- Все типы настроек регистрируются без ошибок
- `format_value()` для каждого типа не падает
- `get()` / `set()` работают для всех зарегистрированных ключей
- Структура данных настроек совпадает с ожиданиями потребителей