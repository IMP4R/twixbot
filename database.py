"""TWIX Database — SQLite with WAL, UUID, Decimal, UTC, soft delete."""
import sqlite3
import uuid
import json
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from pathlib import Path

from config import DB_PATH


class DecimalAdapter:
    """SQLite adapter for Python Decimal."""

    @staticmethod
    def adapt(d: Decimal) -> str:
        return str(d)

    @staticmethod
    def convert(s: bytes) -> Decimal:
        return Decimal(s.decode())


class UUIDAdapter:
    """SQLite adapter for Python UUID."""

    @staticmethod
    def adapt(u: uuid.UUID) -> str:
        return str(u)

    @staticmethod
    def convert(s: bytes) -> uuid.UUID:
        return uuid.UUID(s.decode())


def _json_dumps(obj: Any) -> str:
    """Serialize object to JSON (handles Decimal and UUID)."""

    def _default(o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, uuid.UUID):
            return str(o)
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    return json.dumps(obj, ensure_ascii=False, default=_default)


def _json_loads(s: str) -> Any:
    """Deserialize JSON string."""
    return json.loads(s)


class TimestampAdapter:
    """SQLite adapter for Python datetime (replaces deprecated default converter)."""

    @staticmethod
    def adapt(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    @staticmethod
    def convert(s: bytes) -> datetime:
        val = s.decode()
        # Handle ISO format with timezone
        if val.endswith("+00:00"):
            val = val[:-6]
        try:
            return datetime.fromisoformat(val).replace(tzinfo=timezone.utc)
        except ValueError:
            # Fallback for older formats
            return datetime.strptime(val, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def register_adapters():
    """Register SQLite type adapters."""
    sqlite3.register_adapter(Decimal, DecimalAdapter.adapt)
    sqlite3.register_converter("DECIMAL", DecimalAdapter.convert)
    sqlite3.register_adapter(uuid.UUID, UUIDAdapter.adapt)
    sqlite3.register_converter("UUID", UUIDAdapter.convert)
    sqlite3.register_adapter(datetime, TimestampAdapter.adapt)
    sqlite3.register_converter("TIMESTAMP", TimestampAdapter.convert)


def get_connection() -> sqlite3.Connection:
    """Create a new SQLite connection with proper settings."""
    conn = sqlite3.connect(
        str(DB_PATH),
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        isolation_level=None,
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database schema."""
    register_adapters()
    conn = get_connection()
    cursor = conn.cursor()

    # Users
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            full_name TEXT,
            phone TEXT,
            locale TEXT DEFAULT 'ru',
            is_anonymous INTEGER DEFAULT 0,
            tos_accepted INTEGER DEFAULT 0,
            total_volume DECIMAL DEFAULT 0,
            total_volume_rub DECIMAL DEFAULT 0,
            deal_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP DEFAULT NULL
        )
        """
    )

    # Managers
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS managers (
            id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            full_name TEXT,
            is_active INTEGER DEFAULT 1,
            is_online INTEGER DEFAULT 1,
            can_receive_deals INTEGER DEFAULT 1,
            total_volume DECIMAL DEFAULT 0,
            deal_count INTEGER DEFAULT 0,
            cancel_count INTEGER DEFAULT 0,
            profit DECIMAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP DEFAULT NULL
        )
        """
    )

    # Deals
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS deals (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            user_username TEXT DEFAULT NULL,
            user_telegram_id INTEGER DEFAULT 0,
            manager_id INTEGER DEFAULT NULL,
            status TEXT DEFAULT 'created',
            amount_usdt DECIMAL NOT NULL,
            client_rate DECIMAL NOT NULL,
            internal_rate DECIMAL NOT NULL,
            revenue DECIMAL DEFAULT 0,
            cost DECIMAL DEFAULT 0,
            profit DECIMAL DEFAULT 0,
            tier_index INTEGER DEFAULT 0,
            is_pinned INTEGER DEFAULT 0,
            pinned_at TIMESTAMP DEFAULT NULL,
            promoted_at TIMESTAMP DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP DEFAULT NULL,
            cancelled_at TIMESTAMP DEFAULT NULL,
            deleted_at TIMESTAMP DEFAULT NULL,
            metadata TEXT DEFAULT '{}',
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (manager_id) REFERENCES managers(id)
        )
        """
    )

    # Migration: add user_username / user_telegram_id if table already exists without them
    try:
        cursor.execute("ALTER TABLE deals ADD COLUMN user_username TEXT DEFAULT NULL")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE deals ADD COLUMN user_telegram_id INTEGER DEFAULT 0")
    except Exception:
        pass

    # Deal queue (global + per-manager ordering)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS deal_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id TEXT UNIQUE NOT NULL,
            manager_id INTEGER DEFAULT NULL,
            queue_position INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (deal_id) REFERENCES deals(id),
            FOREIGN KEY (manager_id) REFERENCES managers(id)
        )
        """
    )

    # Tickets
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY,
            ticket_number TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            deal_id TEXT DEFAULT NULL,
            amount_threshold DECIMAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used_at TIMESTAMP DEFAULT NULL,
            deleted_at TIMESTAMP DEFAULT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (deal_id) REFERENCES deals(id)
        )
        """
    )

    # Rates
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rates (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            min_amount DECIMAL DEFAULT 0,
            max_amount DECIMAL DEFAULT 0,
            rate DECIMAL NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP DEFAULT NULL
        )
        """
    )

    # Rate history (for rollback)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rate_history (
            id INTEGER PRIMARY KEY,
            rate_id INTEGER NOT NULL,
            old_rate DECIMAL NOT NULL,
            new_rate DECIMAL NOT NULL,
            actor_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (rate_id) REFERENCES rates(id)
        )
        """
    )

    # Audit log
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY,
            event_type TEXT NOT NULL,
            actor_id INTEGER NOT NULL,
            object_type TEXT NOT NULL,
            object_id TEXT NOT NULL,
            payload TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Notifications
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            manager_id INTEGER,
            type TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Sessions (for manager activity tracking)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY,
            manager_id INTEGER NOT NULL,
            deal_id TEXT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP DEFAULT NULL,
            FOREIGN KEY (manager_id) REFERENCES managers(id),
            FOREIGN KEY (deal_id) REFERENCES deals(id)
        )
        """
    )

    # Statistics (daily snapshots)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS statistics (
            id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            total_deals INTEGER DEFAULT 0,
            total_profit DECIMAL DEFAULT 0,
            total_volume DECIMAL DEFAULT 0,
            manager_id INTEGER,
            user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Shift reports (salary/shift tracking)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS shift_reports (
            id INTEGER PRIMARY KEY,
            manager_id INTEGER NOT NULL,
            work_date TEXT NOT NULL,
            opening_balance DECIMAL DEFAULT 0,
            start_kb DECIMAL DEFAULT 0,
            closing_balance DECIMAL DEFAULT 0,
            end_kb DECIMAL DEFAULT 0,
            system_profit DECIMAL DEFAULT 0,
            salary_percent DECIMAL DEFAULT 0,
            top_place INTEGER DEFAULT 0,
            top_bonus DECIMAL DEFAULT 0,
            is_locked INTEGER DEFAULT 0,
            is_top_fixed INTEGER DEFAULT 0,
            admin_note TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP DEFAULT NULL,
            FOREIGN KEY (manager_id) REFERENCES managers(id)
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_shift_reports_mgr_date ON shift_reports(manager_id, work_date)")
    # Migration: add deleted_at to shift_reports if table already exists without it
    try:
        cursor.execute("ALTER TABLE shift_reports ADD COLUMN deleted_at TIMESTAMP DEFAULT NULL")
    except Exception:
        pass

    # Migration: add start_kb / end_kb if table already exists without them
    try:
        cursor.execute("ALTER TABLE shift_reports ADD COLUMN start_kb DECIMAL DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE shift_reports ADD COLUMN end_kb DECIMAL DEFAULT 0")
    except Exception:
        pass

    # Promocodes
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS promocodes (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            bonus_percent DECIMAL NOT NULL,
            max_activations INTEGER DEFAULT 0,
            used_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP DEFAULT NULL
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_promocodes_code ON promocodes(code)")

    # Migration: add promocode_id to deals if not exists
    try:
        cursor.execute("ALTER TABLE deals ADD COLUMN promocode_id INTEGER DEFAULT NULL")
    except Exception:
        pass

    # Migration: add last_assigned_at to managers if not exists
    try:
        cursor.execute("ALTER TABLE managers ADD COLUMN last_assigned_at TIMESTAMP DEFAULT NULL")
    except Exception:
        pass

    # Migration: add rapira_percent to rates if not exists
    try:
        cursor.execute("ALTER TABLE rates ADD COLUMN rapira_percent DECIMAL DEFAULT NULL")
    except Exception:
        pass

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_deals_user ON deals(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_deals_manager ON deals(manager_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_deals_status ON deals(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_deals_deleted ON deals(deleted_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_deal_queue_manager ON deal_queue(manager_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_deal_queue_active ON deal_queue(is_active)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_object ON audit_log(object_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_managers_active ON managers(is_active)")

    conn.close()


from contextlib import contextmanager


@contextmanager
def transaction():
    """SQLite transaction context manager (BEGIN ... COMMIT/ROLLBACK)."""
    conn = get_connection()
    conn.execute("BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def now_utc() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(timezone.utc)


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())
