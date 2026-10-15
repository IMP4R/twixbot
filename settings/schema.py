from __future__ import annotations
from collections import OrderedDict
from typing import Any
from settings.types import SettingDef

_registry: OrderedDict[str, SettingDef] = OrderedDict()


def register(s: SettingDef):
    _registry[s.key] = s


def get_def(key: str) -> SettingDef | None:
    return _registry.get(key)


def get_all() -> list[SettingDef]:
    return list(_registry.values())


def get_by_category(category: str) -> list[SettingDef]:
    return [s for s in _registry.values() if s.category == category]


def get_categories() -> list[str]:
    seen = OrderedDict()
    for s in _registry.values():
        if s.category not in seen:
            seen[s.category] = True
    return list(seen)


def get_defaults() -> dict[str, Any]:
    return {s.key: s.default for s in _registry.values()}


def clear():
    _registry.clear()