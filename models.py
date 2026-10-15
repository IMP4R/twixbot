"""TWIX Models — dataclasses for all domain entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional


@dataclass
class User:
    id: Optional[int] = None
    telegram_id: int = 0
    username: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    locale: str = "ru"
    is_anonymous: bool = False
    tos_accepted: bool = False
    total_volume: Decimal = field(default_factory=lambda: Decimal("0"))
    total_volume_rub: Decimal = field(default_factory=lambda: Decimal("0"))
    deal_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None


@dataclass
class Manager:
    id: Optional[int] = None
    telegram_id: int = 0
    username: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool = True
    is_online: bool = True
    can_receive_deals: bool = True
    total_volume: Decimal = field(default_factory=lambda: Decimal("0"))
    deal_count: int = 0
    cancel_count: int = 0
    profit: Decimal = field(default_factory=lambda: Decimal("0"))
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    last_assigned_at: Optional[datetime] = None


@dataclass
class Deal:
    id: Optional[str] = None
    user_id: int = 0
    user_username: Optional[str] = None
    user_telegram_id: int = 0
    manager_id: Optional[int] = None
    status: str = "created"  # created, queued, active, pinned, closed, cancelled
    amount_usdt: Decimal = field(default_factory=lambda: Decimal("0"))
    client_rate: Decimal = field(default_factory=lambda: Decimal("0"))
    internal_rate: Decimal = field(default_factory=lambda: Decimal("0"))
    revenue: Decimal = field(default_factory=lambda: Decimal("0"))
    cost: Decimal = field(default_factory=lambda: Decimal("0"))
    profit: Decimal = field(default_factory=lambda: Decimal("0"))
    tier_index: int = 0
    is_pinned: bool = False
    pinned_at: Optional[datetime] = None
    promoted_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.status in ("created", "queued", "active", "pinned")

    @property
    def is_finished(self) -> bool:
        return self.status in ("closed", "cancelled")


@dataclass
class Ticket:
    id: Optional[int] = None
    ticket_number: str = ""
    user_id: int = 0
    deal_id: Optional[str] = None
    amount_threshold: Decimal = field(default_factory=lambda: Decimal("0"))
    created_at: Optional[datetime] = None
    used_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None


@dataclass
class Rate:
    id: Optional[int] = None
    name: str = ""
    min_amount: Decimal = field(default_factory=lambda: Decimal("0"))
    max_amount: Decimal = field(default_factory=lambda: Decimal("0"))
    rate: Decimal = field(default_factory=lambda: Decimal("0"))
    rapira_percent: Optional[Decimal] = None  # percent over rapira price in rapira_percent mode
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None


@dataclass
class RateHistory:
    id: Optional[int] = None
    rate_id: int = 0
    old_rate: Decimal = field(default_factory=lambda: Decimal("0"))
    new_rate: Decimal = field(default_factory=lambda: Decimal("0"))
    actor_id: int = 0
    created_at: Optional[datetime] = None


@dataclass
class AuditLog:
    id: Optional[int] = None
    event_type: str = ""
    actor_id: int = 0
    object_type: str = ""
    object_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None


@dataclass
class Notification:
    id: Optional[int] = None
    user_id: Optional[int] = None
    manager_id: Optional[int] = None
    type: str = ""
    message: str = ""
    is_read: bool = False
    created_at: Optional[datetime] = None


@dataclass
class Session:
    id: Optional[int] = None
    manager_id: int = 0
    deal_id: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


@dataclass
class Statistic:
    id: Optional[int] = None
    date: str = ""
    total_deals: int = 0
    total_profit: Decimal = field(default_factory=lambda: Decimal("0"))
    total_volume: Decimal = field(default_factory=lambda: Decimal("0"))
    manager_id: Optional[int] = None
    user_id: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass
class DealQueue:
    id: Optional[int] = None
    deal_id: str = ""
    manager_id: Optional[int] = None
    queue_position: int = 0
    is_active: bool = False
    created_at: Optional[datetime] = None


@dataclass
class Promocode:
    id: Optional[int] = None
    code: str = ""  # e.g. "SUMMER2024"
    bonus_percent: Decimal = field(default_factory=lambda: Decimal("0"))  # e.g. 5.0 = +5%
    max_activations: int = 0  # 0 = unlimited
    used_count: int = 0
    created_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None


@dataclass
class ShiftReport:
    id: Optional[int] = None
    manager_id: int = 0
    work_date: str = ""  # YYYY-MM-DD
    opening_balance: Decimal = field(default_factory=lambda: Decimal("0"))   # площадка начало
    start_kb: Decimal = field(default_factory=lambda: Decimal("0"))          # КБ начало
    closing_balance: Decimal = field(default_factory=lambda: Decimal("0"))   # площадка конец
    end_kb: Decimal = field(default_factory=lambda: Decimal("0"))            # КБ конец
    system_profit: Decimal = field(default_factory=lambda: Decimal("0"))
    salary_percent: Decimal = field(default_factory=lambda: Decimal("0"))
    top_place: int = 0
    top_bonus: Decimal = field(default_factory=lambda: Decimal("0"))
    is_locked: bool = False
    is_top_fixed: bool = False
    admin_note: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
