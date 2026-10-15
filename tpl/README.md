# TPL — Template & Locale Library

> Мультиязычная библиотека шаблонов для Telegram-ботов на **aiogram 3.25+**.
>
> Полная документация: [`docs.md`](docs.md)

---

## Что делает

- **Шаблоны сообщений** — текст, кнопки, фото/видео, Premium emoji (`<tg-emoji>`)
- **Мультиязычность** — fallback-цепочка (`uk` → `ru` → `en`), автоопределение locale
- **Админ-панель** — `/templates` для редактирования шаблонов прямо в Telegram
- **Дерево ключей** — `main.profile.balance` → группировка по папкам в админке
- **CRUD шаблонов** — JSON-хранилище с кешированием

---

## Быстрый старт

```python
import tpl

# 1. Дефолтные шаблоны (дерево ключей)
tpl.set_defaults({
    "main.greeting": {
        "ru": {
            "text": "Привет, {name}!",
            "buttons": [[
                {"text": "Профиль", "callback_data": "main_profile"},
            ]],
        },
    },
})

# 2. Отправка
await tpl.send_template(callback, "main.greeting", {"name": "User"})

# 3. Админка
from tpl import create_admin_router
dp.include_router(create_admin_router(admin_ids=[0]))
```

---

## Структура

```
tpl/
├── __init__.py          # Публичный API
├── types.py             # TemplateData, ButtonData, ReplyButtonData
├── locale.py            # Управление языками + fallback-цепочка
├── defaults.py          # Дефолтные шаблоны
├── emoji.py             # Custom Emoji (Premium)
├── manager.py           # CRUD шаблонов
├── storage.py           # JSONBackend / MemoryBackend
├── keyboards.py         # Построение клавиатур
├── sender.py            # send / edit / answer / render
├── tree.py              # Дерево ключей, callback ↔ key конвертация
├── middleware.py          # TplI18nMiddleware
├── admin_handler.py     # Router админки (/templates)
├── admin_kb.py          # Клавиатуры админки
├── admin_states.py      # FSM админки (префикс tpl_)
├── admin_emoji.py       # Emoji для UI админки
└── docs.md              # Полная документация
```

---

## API

### Отправка

| Функция | Описание |
|---------|----------|
| `send_template(target, key, vars, ...)` | Новое сообщение |
| `edit_template(target, key, vars, ...)` | Редактировать |
| `answer_template(callback, key, ...)` | Popup на callback |
| `render_text(tmpl, vars)` | Подставить переменные |
| `build_keyboard(buttons, extra)` | InlineKeyboardMarkup |

### CRUD

| Функция | Описание |
|---------|----------|
| `get_template(key, locale)` | Получить шаблон |
| `update_template(key, locale, **kw)` | Обновить |
| `reset_template(key, locale)` | Сбросить дефолт |
| `list_all_keys()` | Все ключи |

### Дерево

| Функция | Описание |
|---------|----------|
| `normalize_key(key)` | `Main Profile` → `main.profile` |
| `key_to_callback(key)` | `main.profile` → `main_profile` |
| `callback_to_key(cb)` | `main_profile` → `main.profile` |
| `get_tree_nodes(keys, prefix)` | `(folders, leaves)` |

---

## Конвенция ключей

- **Всегда точечная нотация:** `main.greeting`, `deal.confirm`
- **Без точек** → плоский список в админке, без папок
- **callback_data ↔ ключ:** `main_profile_balance` ↔ `main.profile.balance`

---

## Тестирование

См. `docs/TESTING_SYSTEM.md` → раздел **TPL Syntax Checker**.

Критичные проверки контента шаблонов:
- `icon_custom_emoji_id` — строго numeric (`\d+`)
- Нет Unicode emoji в `text` кнопки если есть `icon_custom_emoji_id`
- Нет HTML-тегов (`<tg-emoji>`, `<b>`) в `button.text`
- `media_type: photo` → обязателен `media_file_id`
- `{var}` в шаблоне совпадает с тем, что передаёт код
