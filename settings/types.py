from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable


@dataclass
class SettingDef:
    key: str
    title: str
    description: str = ""
    category: str = "general"
    default: Any = None
    validate: Callable[[Any], bool] | None = None


@dataclass
class BoolSetting(SettingDef):
    default: bool = False

    def __post_init__(self):
        self.validate = lambda v: isinstance(v, bool)


@dataclass
class IntSetting(SettingDef):
    default: int = 0
    min_value: int | None = None
    max_value: int | None = None

    def __post_init__(self):
        self.validate = lambda v: isinstance(v, int) and (
            (self.min_value is None or v >= self.min_value) and
            (self.max_value is None or v <= self.max_value)
        )


@dataclass
class FloatSetting(SettingDef):
    default: float = 0.0
    min_value: float | None = None
    max_value: float | None = None

    def __post_init__(self):
        self.validate = lambda v: isinstance(v, (int, float)) and (
            (self.min_value is None or v >= self.min_value) and
            (self.max_value is None or v <= self.max_value)
        )


@dataclass
class DecimalSetting(SettingDef):
    default: Decimal = field(default_factory=lambda: Decimal("0"))
    min_value: Decimal | None = None
    max_value: Decimal | None = None

    def __post_init__(self):
        if isinstance(self.default, (int, float)):
            self.default = Decimal(str(self.default))

        def _validate(v):
            try:
                d = Decimal(str(v))
            except Exception:
                return False
            return (self.min_value is None or d >= self.min_value) and \
                   (self.max_value is None or d <= self.max_value)
        self.validate = _validate


@dataclass
class StrSetting(SettingDef):
    default: str = ""
    choices: list[str] | None = None
    max_length: int | None = None

    def __post_init__(self):
        def _validate(v):
            if not isinstance(v, str):
                return False
            if self.choices is not None and v not in self.choices:
                return False
            if self.max_length is not None and len(v) > self.max_length:
                return False
            return True
        self.validate = _validate


@dataclass
class EnumSetting(SettingDef):
    default: str = ""
    options: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.validate = lambda v: isinstance(v, str) and v in self.options


@dataclass
class JsonSetting(SettingDef):
    default: dict | list | None = None

    def __post_init__(self):
        self.validate = lambda v: isinstance(v, (dict, list, type(None)))


@dataclass
class ListSetting(SettingDef):
    default: list = field(default_factory=list)
    item_type: str = "str"

    def __post_init__(self):
        self.validate = lambda v: isinstance(v, list)


@dataclass
class TierSetting(SettingDef):
    default: list[dict] = field(default_factory=list)

    def __post_init__(self):
        def _validate(v):
            if not isinstance(v, list):
                return False
            for item in v:
                if not isinstance(item, dict):
                    return False
                if "max" not in item or "rate" not in item:
                    return False
            return True
        self.validate = _validate


@dataclass
class DurationSetting(SettingDef):
    default: int = 3600
    min_seconds: int = 0
    max_seconds: int | None = None

    def __post_init__(self):
        self.validate = lambda v: isinstance(v, int) and v >= self.min_seconds and \
            (self.max_seconds is None or v <= self.max_seconds)