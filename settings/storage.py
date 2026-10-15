from __future__ import annotations
import json
import os
import sqlite3
import time
from decimal import Decimal
from typing import Protocol, runtime_checkable


class _DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


@runtime_checkable
class StorageBackend(Protocol):
    def load(self) -> dict:
        ...

    def save(self, data: dict) -> None:
        ...


class JSONBackend:
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
            json.dump(data, f, indent=2, ensure_ascii=False, cls=_DecimalEncoder)
        self._cache = data.copy()
        self._cache_time = time.monotonic()

    def invalidate_cache(self):
        self._cache = None


class SQLiteBackend:
    def __init__(self, path: str):
        self._path = path
        self._ensure_table()

    def _ensure_table(self):
        with sqlite3.connect(self._path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS settings ("
                "  key TEXT PRIMARY KEY,"
                "  value TEXT NOT NULL"
                ")"
            )

    def load(self) -> dict:
        try:
            with sqlite3.connect(self._path) as conn:
                rows = conn.execute("SELECT key, value FROM settings").fetchall()
            result = {}
            for key, raw in rows:
                try:
                    result[key] = json.loads(raw)
                except json.JSONDecodeError:
                    result[key] = raw
            return result
        except sqlite3.Error:
            return {}

    def save(self, data: dict) -> None:
        with sqlite3.connect(self._path) as conn:
            conn.execute("DELETE FROM settings")
            conn.executemany(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                [(k, json.dumps(v, ensure_ascii=False, cls=_DecimalEncoder)) for k, v in data.items()],
            )


class MemoryBackend:
    def __init__(self, initial: dict | None = None):
        self._data: dict = initial or {}

    def load(self) -> dict:
        return self._data.copy()

    def save(self, data: dict) -> None:
        self._data = data.copy()


_global_backend: StorageBackend | None = None


def set_backend(backend: StorageBackend):
    global _global_backend
    _global_backend = backend


def get_backend() -> StorageBackend:
    global _global_backend
    if _global_backend is None:
        _global_backend = JSONBackend(os.path.join("data", "settings.json"))
    return _global_backend


def reset_backend():
    global _global_backend
    _global_backend = None