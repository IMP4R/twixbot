# tpl/manager.py
"""CRUD шаблонов с поддержкой локалей."""

import os
import copy

from tpl.defaults import get_defaults, _blank_template, is_multilang
from tpl.emoji import extract_emoji_ids
from tpl.locale import get_default_locale, resolve_fallback
from tpl.types import TemplateData
from tpl.storage import get_backend, JSONBackend

_data_file: str = os.path.join("data", "templates.json")


def set_data_file(path: str):
    """Установить путь к JSON-файлу (legacy helper)."""
    global _data_file
    _data_file = path
    from tpl.storage import set_backend, JSONBackend
    set_backend(JSONBackend(path))


def get_data_file() -> str:
    return _data_file


def load_stored() -> dict:
    return get_backend().load()


def save_stored(data: dict):
    get_backend().save(data)


def _storage_key(key: str, locale: str) -> str:
    return f"{key}:{locale}"


def _get_default_for_locale(key: str, locale: str) -> TemplateData:
    defaults = get_defaults()
    tmpl_data = defaults.get(key, {})

    if is_multilang(tmpl_data):
        if locale in tmpl_data:
            return copy.deepcopy(tmpl_data[locale])
        dl = get_default_locale()
        if dl in tmpl_data:
            return copy.deepcopy(tmpl_data[dl])
        for v in tmpl_data.values():
            if isinstance(v, dict) and "text" in v:
                return copy.deepcopy(v)
        return _blank_template()
    elif "text" in tmpl_data:
        return copy.deepcopy(tmpl_data)

    return _blank_template()


def get_template(key: str, locale: str = None) -> TemplateData:
    if locale is None:
        locale = get_default_locale()

    dl = get_default_locale()
    # Цепочка fallback локалей
    chain = [locale]
    seen = {locale}
    fb = resolve_fallback(locale)
    if fb not in seen:
        chain.append(fb)
        seen.add(fb)
    if dl not in seen:
        chain.append(dl)

    stored = load_stored()

    # 1. Ищем в stored по цепочке
    for loc in chain:
        sk = _storage_key(key, loc)
        if sk in stored:
            default = _get_default_for_locale(key, loc)
            merged = copy.deepcopy(default) if default.get("text") else _blank_template()
            merged.update(stored[sk])
            return merged

    # 2. Ищем в defaults по цепочке
    for loc in chain:
        default = _get_default_for_locale(key, loc)
        if default.get("text"):
            return default

    return {
        "text": f"['{key}' / {locale}]",
        "media_type": "none",
        "media_file_id": "",
        "parse_mode": "HTML",
        "buttons": [],
        "reply_buttons": [],
        "custom_emoji_ids": [],
    }


def update_template(key: str, locale: str = None, **kwargs):
    if locale is None:
        locale = get_default_locale()

    stored = load_stored()
    sk = _storage_key(key, locale)

    if sk not in stored:
        default = _get_default_for_locale(key, locale)
        stored[sk] = copy.deepcopy(default) if default.get("text") else _blank_template()

    stored[sk].update(kwargs)

    if "text" in kwargs:
        stored[sk]["custom_emoji_ids"] = extract_emoji_ids(kwargs["text"])

    save_stored(stored)


def _ensure_buttons(stored: dict, sk: str, key: str, locale: str):
    """Если stored[sk] существует но не имеет кнопок — копируем из default."""
    if sk not in stored:
        return
    if stored[sk].get("buttons"):
        return
    default = _get_default_for_locale(key, locale)
    if default.get("buttons"):
        stored[sk]["buttons"] = copy.deepcopy(default["buttons"])


def update_button_at_index(key: str, flat_idx: int, locale: str = None, **kwargs) -> bool:
    if locale is None:
        locale = get_default_locale()

    stored = load_stored()
    sk = _storage_key(key, locale)

    if sk not in stored:
        default = _get_default_for_locale(key, locale)
        stored[sk] = copy.deepcopy(default) if default.get("text") else _blank_template()

    _ensure_buttons(stored, sk, key, locale)

    buttons = stored[sk].get("buttons", [])
    idx = 0
    for row in buttons:
        for btn in row:
            if idx == flat_idx:
                btn.update(kwargs)
                stored[sk]["buttons"] = buttons
                save_stored(stored)
                return True
            idx += 1
    return False


def remove_button_field(key: str, flat_idx: int, field: str, locale: str = None) -> bool:
    if locale is None:
        locale = get_default_locale()

    stored = load_stored()
    sk = _storage_key(key, locale)

    if sk not in stored:
        default = _get_default_for_locale(key, locale)
        stored[sk] = copy.deepcopy(default) if default.get("text") else _blank_template()

    _ensure_buttons(stored, sk, key, locale)

    buttons = stored[sk].get("buttons", [])
    idx = 0
    for row in buttons:
        for btn in row:
            if idx == flat_idx:
                btn.pop(field, None)
                save_stored(stored)
                return True
            idx += 1
    return False


def swap_button_action(key: str, flat_idx: int, value: str, locale: str = None) -> bool:
    if locale is None:
        locale = get_default_locale()

    stored = load_stored()
    sk = _storage_key(key, locale)

    if sk not in stored:
        default = _get_default_for_locale(key, locale)
        stored[sk] = copy.deepcopy(default) if default.get("text") else _blank_template()

    _ensure_buttons(stored, sk, key, locale)

    buttons = stored[sk].get("buttons", [])
    idx = 0
    for row in buttons:
        for btn in row:
            if idx == flat_idx:
                if value.startswith("http://") or value.startswith("https://"):
                    btn.pop("callback_data", None)
                    btn["url"] = value
                else:
                    btn.pop("url", None)
                    btn["callback_data"] = value
                save_stored(stored)
                return True
            idx += 1
    return False


def get_flat_buttons(key: str, locale: str = None) -> list[dict]:
    tmpl = get_template(key, locale)
    return [btn for row in tmpl.get("buttons", []) for btn in row]


def get_flat_reply_buttons(key: str, locale: str = None) -> list[dict]:
    tmpl = get_template(key, locale)
    return [btn for row in tmpl.get("reply_buttons", []) for btn in row]


def _ensure_reply_buttons(stored: dict, sk: str, key: str, locale: str):
    """Если stored[sk] существует но не имеет reply кнопок — копируем из default."""
    if sk not in stored:
        return
    if stored[sk].get("reply_buttons"):
        return
    default = _get_default_for_locale(key, locale)
    if default.get("reply_buttons"):
        stored[sk]["reply_buttons"] = copy.deepcopy(default["reply_buttons"])


def update_reply_button_at_index(key: str, flat_idx: int, locale: str = None, **kwargs) -> bool:
    if locale is None:
        locale = get_default_locale()

    stored = load_stored()
    sk = _storage_key(key, locale)

    if sk not in stored:
        default = _get_default_for_locale(key, locale)
        stored[sk] = copy.deepcopy(default) if default.get("text") else _blank_template()

    _ensure_reply_buttons(stored, sk, key, locale)

    reply_buttons = stored[sk].get("reply_buttons", [])
    idx = 0
    for row in reply_buttons:
        for btn in row:
            if idx == flat_idx:
                btn.update(kwargs)
                stored[sk]["reply_buttons"] = reply_buttons
                save_stored(stored)
                return True
            idx += 1
    return False


def remove_reply_button_field(key: str, flat_idx: int, field: str, locale: str = None) -> bool:
    if locale is None:
        locale = get_default_locale()

    stored = load_stored()
    sk = _storage_key(key, locale)

    if sk not in stored:
        default = _get_default_for_locale(key, locale)
        stored[sk] = copy.deepcopy(default) if default.get("text") else _blank_template()

    _ensure_reply_buttons(stored, sk, key, locale)

    reply_buttons = stored[sk].get("reply_buttons", [])
    idx = 0
    for row in reply_buttons:
        for btn in row:
            if idx == flat_idx:
                btn.pop(field, None)
                save_stored(stored)
                return True
            idx += 1
    return False


def reset_template(key: str, locale: str = None):
    if locale is None:
        locale = get_default_locale()
    stored = load_stored()
    sk = _storage_key(key, locale)
    if sk in stored:
        del stored[sk]
        save_stored(stored)


def reset_template_all_locales(key: str):
    stored = load_stored()
    to_remove = [k for k in stored if k.startswith(f"{key}:")]
    for k in to_remove:
        del stored[k]
    if to_remove:
        save_stored(stored)


def list_all_keys() -> list[str]:
    keys = set(get_defaults().keys())
    stored = load_stored()
    for sk in stored:
        if ":" in sk:
            base_key = sk.rsplit(":", 1)[0]
            keys.add(base_key)
        else:
            keys.add(sk)
    return sorted(keys)


def get_template_locales(key: str) -> list[str]:
    from tpl.locale import get_available_locales
    locales = set()

    defaults = get_defaults()
    tmpl_data = defaults.get(key, {})
    if is_multilang(tmpl_data):
        locales.update(tmpl_data.keys())
    elif "text" in tmpl_data:
        locales.update(get_available_locales().keys())

    stored = load_stored()
    for sk in stored:
        if sk.startswith(f"{key}:"):
            loc = sk.rsplit(":", 1)[1]
            locales.add(loc)

    return sorted(locales)