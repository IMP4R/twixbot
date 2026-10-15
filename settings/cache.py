from __future__ import annotations
import time
from typing import Any


class SettingCache:
    def __init__(self, ttl: float = 5.0):
        self._ttl = ttl
        self._data: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        value, ts = entry
        if time.monotonic() - ts > self._ttl:
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: Any):
        self._data[key] = (value, time.monotonic())

    def invalidate(self, key: str | None = None):
        if key is None:
            self._data.clear()
        else:
            self._data.pop(key, None)

    def keys(self) -> list[str]:
        now = time.monotonic()
        expired = [k for k, (_, ts) in self._data.items() if now - ts > self._ttl]
        for k in expired:
            del self._data[k]
        return list(self._data.keys())


_default_cache = SettingCache()


def get_default_cache() -> SettingCache:
    return _default_cache