# tpl/storage.py
"""Абстракция хранилища шаблонов: JSON, Memory и др."""

from __future__ import annotations
import json
import os
import time
from typing import Protocol, runtime_checkable
from functools import lru_cache


@runtime_checkable
class StorageBackend(Protocol):
    """Протокол бэкенда хранилища шаблонов."""

    def load(self) -> dict:
        """Вернуть всё хранилище как dict."""
        ...

    def save(self, data: dict) -> None:
        """Атомарно сохранить dict."""
        ...


class MemoryBackend:
    """Хранилище в памяти (для тестов и ephemeral-режима)."""

    def __init__(self, initial: dict | None = None):
        self._data: dict = initial or {}

    def load(self) -> dict:
        return self._data.copy()

    def save(self, data: dict) -> None:
        self._data = data.copy()


class JSONBackend:
    """JSON-файл на диске с автосозданием директорий и кешированием."""

    def __init__(self, path: str, cache_ttl: float = 0.5):
        self._path = path
        self._cache_ttl = cache_ttl
        self._cache: dict | None = None
        self._cache_time: float = 0.0
        self._ensure_dir()

    def _ensure_dir(self):
        d = os.path.dirname(self._path)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)

    def load(self) -> dict:
        now = time.monotonic()
        if self._cache is not None and (now - self._cache_time) < self._cache_ttl:
            return self._cache.copy()

        if not os.path.exists(self._path):
            self._cache = {}
            self._cache_time = now
            return {}

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            data = {}

        self._cache = data.copy()
        self._cache_time = now
        return self._cache.copy()

    def save(self, data: dict) -> None:
        self._ensure_dir()
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._cache = data.copy()
        self._cache_time = time.monotonic()

    def invalidate_cache(self):
        self._cache = None


_global_backend: StorageBackend | None = None


def set_backend(backend: StorageBackend):
    global _global_backend
    _global_backend = backend


def get_backend() -> StorageBackend:
    global _global_backend
    if _global_backend is None:
        _global_backend = JSONBackend(os.path.join("data", "templates.json"))
    return _global_backend


def reset_backend():
    global _global_backend
    _global_backend = None
