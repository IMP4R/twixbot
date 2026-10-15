from __future__ import annotations
import asyncio
from decimal import Decimal
from typing import Any, Callable, Awaitable

from settings.schema import get_def, get_defaults
from settings.storage import get_backend
from settings.cache import get_default_cache
from settings.types import DecimalSetting, TierSetting, DurationSetting

_change_hooks: list[Callable[[str, Any, Any], Awaitable[None]]] = []


def on_change(hook: Callable[[str, Any, Any], Awaitable[None]]):
    _change_hooks.append(hook)


async def _fire_hooks(key: str, old_value: Any, new_value: Any):
    for hook in _change_hooks:
        try:
            await hook(key, old_value, new_value)
        except Exception:
            pass


async def get(key: str) -> Any:
    cache = get_default_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    backend = get_backend()
    data = backend.load()
    if key in data:
        value = data[key]
    else:
        sd = get_def(key)
        value = sd.default if sd else None

    if isinstance(value, str):
        try:
            import json
            value = json.loads(value)
        except json.JSONDecodeError:
            pass

    cache.set(key, value)
    return value


def get_sync(key: str) -> Any:
    cache = get_default_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    sd = get_def(key)
    if sd:
        return sd.default
    return None


async def get_all() -> dict[str, Any]:
    result = {}
    defs = get_defaults()
    backend = get_backend()
    stored = backend.load()

    for key, default in defs.items():
        if key in stored:
            value = stored[key]
            if isinstance(value, str):
                try:
                    import json
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
        else:
            value = default
        result[key] = value
    return result


async def set(key: str, value: Any):
    sd = get_def(key)
    if sd and sd.validate:
        if not sd.validate(value):
            raise ValueError(f"Invalid value for {key}: {value!r}")

    old = await get(key)
    backend = get_backend()
    data = backend.load()

    import json
    class _DecimalEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Decimal):
                return str(obj)
            return super().default(obj)
    data[key] = json.dumps(value, ensure_ascii=False, cls=_DecimalEncoder)
    backend.save(data)

    get_default_cache().set(key, value)
    await _fire_hooks(key, old, value)


async def reset(key: str):
    backend = get_backend()
    data = backend.load()
    data.pop(key, None)
    backend.save(data)
    get_default_cache().invalidate(key)


async def reset_all():
    backend = get_backend()
    backend.save({})
    get_default_cache().invalidate()


def format_value(key: str, value: Any) -> str:
    sd = get_def(key)
    from settings.types import (
        BoolSetting, DurationSetting, TierSetting,
    )

    if isinstance(sd, BoolSetting):
        val = bool(value)
        return "✅ Вкл" if val else "❌ Выкл"

    if isinstance(sd, DurationSetting):
        seconds = int(value)
        if seconds < 60:
            return f"{seconds}с"
        if seconds < 3600:
            return f"{seconds // 60}м {seconds % 60}с"
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        parts = []
        if h:
            parts.append(f"{h}ч")
        if m:
            parts.append(f"{m}м")
        if s:
            parts.append(f"{s}с")
        return " ".join(parts)

    if isinstance(sd, TierSetting):
        if not value:
            return "—"
        return ", ".join(f"{t['max']}→{t['rate']}" for t in value)

    if isinstance(sd, DecimalSetting):
        return str(Decimal(str(value)))

    return str(value)


def format_value_short(key: str, value: Any) -> str:
    fd = format_value(key, value)
    if len(fd) > 50:
        return fd[:47] + "..."
    return fd