"""Управление локалями (языками)."""

from typing import Callable, Awaitable, Optional

_default_locale: str = "ru"

_available_locales: dict[str, str] = {
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
}

# Цепочка фоллбэков: locale -> следующий fallback
_locale_fallbacks: dict[str, str] = {}

_user_locale_getter: Optional[Callable[[int], Awaitable[str]]] = None
_user_locale_setter: Optional[Callable[[int, str], Awaitable[None]]] = None


def set_default_locale(locale: str):
    global _default_locale
    _default_locale = locale


def get_default_locale() -> str:
    return _default_locale


def set_available_locales(locales: dict[str, str]):
    global _available_locales
    _available_locales = locales


def get_available_locales() -> dict[str, str]:
    return _available_locales.copy()


def set_locale_fallbacks(chain: dict[str, str]):
    """Задать цепочку фоллбэков: {"uk": "ru", "ru": "en"}.
    Если шаблон не найден для uk, попробуется ru, потом en (default_locale)."""
    global _locale_fallbacks
    _locale_fallbacks = dict(chain)


def get_locale_fallbacks() -> dict[str, str]:
    return _locale_fallbacks.copy()


def resolve_fallback(locale: str) -> str:
    """Пройти по цепочке фоллбэков до достижения default_locale или отсутствия пути."""
    seen = {locale}
    current = locale
    while current != _default_locale:
        nxt = _locale_fallbacks.get(current)
        if not nxt or nxt in seen:
            break
        seen.add(nxt)
        current = nxt
    return current


def set_user_locale_getter(fn: Callable[[int], Awaitable[str]]):
    global _user_locale_getter
    _user_locale_getter = fn


def set_user_locale_setter(fn: Callable[[int, str], Awaitable[None]]):
    global _user_locale_setter
    _user_locale_setter = fn


async def get_user_locale(user_id: int) -> str:
    if _user_locale_getter:
        try:
            locale = await _user_locale_getter(user_id)
            if locale and locale in _available_locales:
                return locale
        except Exception:
            pass
    return _default_locale


async def set_user_locale(user_id: int, locale: str):
    if _user_locale_setter:
        await _user_locale_setter(user_id, locale)