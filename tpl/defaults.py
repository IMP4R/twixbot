"""Дефолтные шаблоны с поддержкой мультиязычности."""

from tpl.types import TemplateData

_DEFAULTS: dict[str, dict] = {}


def get_defaults() -> dict[str, dict]:
    return _DEFAULTS


def set_defaults(defaults: dict[str, dict]):
    global _DEFAULTS
    _DEFAULTS = defaults


def is_multilang(template_dict: dict) -> bool:
    if not template_dict:
        return False
    if "text" in template_dict:
        return False
    return all(
        isinstance(v, dict) and "text" in v
        for v in template_dict.values()
    )


def _blank_template() -> TemplateData:
    return {
        "text": "",
        "media_type": "none",
        "media_file_id": "",
        "parse_mode": "HTML",
        "buttons": [],
        "reply_buttons": [],
        "custom_emoji_ids": [],
    }