"""TWIX Repositories — CRUD with soft delete."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Optional, Sequence

from database import get_connection, now_utc, generate_uuid
from models import (
    AuditLog,
    Deal,
    DealQueue,
    Manager,
    Notification,
    Promocode,
    Rate,
    RateHistory,
    Session,
    ShiftReport,
    Statistic,
    Ticket,
    User,
)


class BaseRepository(ABC):
    table: str = ""

    def _conn(self):
        return get_connection()

    @abstractmethod
    def _row_to_model(self, row) -> Any:
        raise NotImplementedError

    def _execute(self, sql: str, params: tuple = (), conn=None):
        if conn is None:
            conn = self._conn()
            should_close = True
        else:
            should_close = False
        cursor = conn.execute(sql, params)
        return cursor, conn, should_close

    def find_by_id(self, obj_id: Any, conn=None) -> Optional[Any]:
        sql = f"SELECT * FROM {self.table} WHERE id = ? AND deleted_at IS NULL LIMIT 1"
        cursor, conn, should_close = self._execute(sql, (obj_id,), conn=conn)
        row = cursor.fetchone()
        if should_close:
            conn.close()
        return self._row_to_model(row) if row else None

    def list_all(self, limit: int = 1000, offset: int = 0, conn=None) -> Sequence[Any]:
        sql = f"SELECT * FROM {self.table} WHERE deleted_at IS NULL ORDER BY id LIMIT ? OFFSET ?"
        cursor, conn, should_close = self._execute(sql, (limit, offset), conn=conn)
        rows = cursor.fetchall()
        if should_close:
            conn.close()
        return [self._row_to_model(r) for r in rows]

    def count_all(self, conn=None) -> int:
        sql = f"SELECT COUNT(*) FROM {self.table} WHERE deleted_at IS NULL"
        cursor, conn, should_close = self._execute(sql, conn=conn)
        row = cursor.fetchone()
        if should_close:
            conn.close()
        return row[0] if row else 0

    def soft_delete(self, obj_id: Any, actor_id: int = 0, conn=None) -> bool:
        sql = f"UPDATE {self.table} SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL"
        cursor, conn, should_close = self._execute(sql, (now_utc(), obj_id), conn=conn)
        affected = cursor.rowcount
        if should_close:
            conn.close()
        return affected > 0


class UserRepository(BaseRepository):
    table = "users"

    def _row_to_model(self, row) -> User:
        return User(
            id=row["id"],
            telegram_id=row["telegram_id"],
            username=row["username"],
            full_name=row["full_name"],
            phone=row["phone"],
            locale=row["locale"] or "ru",
            is_anonymous=bool(row["is_anonymous"]),
            tos_accepted=bool(row["tos_accepted"]),
            total_volume=Decimal(row["total_volume"]) if row["total_volume"] else Decimal("0"),
            total_volume_rub=Decimal(row["total_volume_rub"]) if row["total_volume_rub"] else Decimal("0"),
            deal_count=row["deal_count"] or 0,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row["deleted_at"],
        )

    def find_by_telegram_id(self, telegram_id: int, conn=None) -> Optional[User]:
        sql = "SELECT * FROM users WHERE telegram_id = ? AND deleted_at IS NULL LIMIT 1"
        cursor, conn, should_close = self._execute(sql, (telegram_id,), conn=conn)
        row = cursor.fetchone()
        if should_close:
            conn.close()
        return self._row_to_model(row) if row else None

    def create(self, user: User, conn=None) -> User:
        sql = """
            INSERT INTO users (telegram_id, username, full_name, phone, locale, is_anonymous,
                               tos_accepted, total_volume, total_volume_rub, deal_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = now_utc()
        cursor, conn, should_close = self._execute(
            sql,
            (
                user.telegram_id,
                user.username,
                user.full_name,
                user.phone,
                user.locale,
                int(user.is_anonymous),
                int(user.tos_accepted),
                user.total_volume,
                user.total_volume_rub,
                user.deal_count,
                now,
                now,
            ),
            conn=conn,
        )
        user.id = cursor.lastrowid
        if should_close:
            conn.close()
        return user

    def update(self, user: User, conn=None) -> User:
        sql = """
            UPDATE users SET username = ?, full_name = ?, phone = ?, locale = ?,
                is_anonymous = ?, tos_accepted = ?, total_volume = ?, total_volume_rub = ?,
                deal_count = ?, updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
        """
        now = now_utc()
        cursor, conn, should_close = self._execute(
            sql,
            (
                user.username,
                user.full_name,
                user.phone,
                user.locale,
                int(user.is_anonymous),
                int(user.tos_accepted),
                user.total_volume,
                user.total_volume_rub,
                user.deal_count,
                now,
                user.id,
            ),
            conn=conn,
        )
        if should_close:
            conn.close()
        return user

    def increment_stats(self, user_id: int, volume: Decimal, volume_rub: Decimal = Decimal("0"), conn=None) -> bool:
        sql = """
            UPDATE users SET total_volume = total_volume + ?,
                              total_volume_rub = total_volume_rub + ?,
                              deal_count = deal_count + 1,
                              updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
        """
        cursor, conn, should_close = self._execute(sql, (volume, volume_rub, now_utc(), user_id), conn=conn)
        affected = cursor.rowcount
        if should_close:
            conn.close()
        return affected > 0


class ManagerRepository(BaseRepository):
    table = "managers"

    def _row_to_model(self, row) -> Manager:
        return Manager(
            id=row["id"],
            telegram_id=row["telegram_id"],
            username=row["username"],
            full_name=row["full_name"],
            is_active=bool(row["is_active"]),
            is_online=bool(row["is_online"]),
            can_receive_deals=bool(row["can_receive_deals"]),
            total_volume=Decimal(row["total_volume"]) if row["total_volume"] else Decimal("0"),
            deal_count=row["deal_count"] or 0,
            cancel_count=row["cancel_count"] or 0,
            profit=Decimal(row["profit"]) if row["profit"] else Decimal("0"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row["deleted_at"],
            last_assigned_at=row["last_assigned_at"] if "last_assigned_at" in row.keys() else None,
        )

    def find_by_telegram_id(self, telegram_id: int, conn=None) -> Optional[Manager]:
        sql = "SELECT * FROM managers WHERE telegram_id = ? AND deleted_at IS NULL LIMIT 1"
        cursor, conn, should_close = self._execute(sql, (telegram_id,), conn=conn)
        row = cursor.fetchone()
        if should_close:
            conn.close()
        return self._row_to_model(row) if row else None

    def create(self, manager: Manager, conn=None) -> Manager:
        sql = """
            INSERT INTO managers (telegram_id, username, full_name, is_active, is_online,
                                  can_receive_deals, total_volume, deal_count, cancel_count,
                                  profit, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = now_utc()
        cursor, conn, should_close = self._execute(
            sql,
            (
                manager.telegram_id,
                manager.username,
                manager.full_name,
                int(manager.is_active),
                int(manager.is_online),
                int(manager.can_receive_deals),
                manager.total_volume,
                manager.deal_count,
                manager.cancel_count,
                manager.profit,
                now,
                now,
            ),
            conn=conn,
        )
        manager.id = cursor.lastrowid
        if should_close:
            conn.close()
        return manager

    def update(self, manager: Manager, conn=None) -> Manager:
        sql = """
            UPDATE managers SET username = ?, full_name = ?, is_active = ?, is_online = ?,
                can_receive_deals = ?, total_volume = ?, deal_count = ?, cancel_count = ?,
                profit = ?, updated_at = ?, last_assigned_at = ?
            WHERE id = ? AND deleted_at IS NULL
        """
        now = now_utc()
        cursor, conn, should_close = self._execute(
            sql,
            (
                manager.username,
                manager.full_name,
                int(manager.is_active),
                int(manager.is_online),
                int(manager.can_receive_deals),
                manager.total_volume,
                manager.deal_count,
                manager.cancel_count,
                manager.profit,
                now,
                manager.last_assigned_at,
                manager.id,
            ),
            conn=conn,
        )
        if should_close:
            conn.close()
        return manager

    def list_online(self, conn=None) -> Sequence[Manager]:
        sql = """
            SELECT * FROM managers
            WHERE is_online = 1 AND can_receive_deals = 1
              AND deleted_at IS NULL
            ORDER BY id
        """
        cursor, conn, should_close = self._execute(sql, conn=conn)
        rows = cursor.fetchall()
        if should_close:
            conn.close()
        return [self._row_to_model(r) for r in rows]

    def list_all_active(self, conn=None) -> Sequence[Manager]:
        sql = """
            SELECT * FROM managers
            WHERE deleted_at IS NULL
            ORDER BY id
        """
        cursor, conn, should_close = self._execute(sql, conn=conn)
        rows = cursor.fetchall()
        if should_close:
            conn.close()
        return [self._row_to_model(r) for r in rows]

    def increment_stats(self, manager_id: int, volume: Decimal, profit: Decimal, conn=None) -> bool:
        sql = """
            UPDATE managers SET total_volume = total_volume + ?,
                              deal_count = deal_count + 1,
                              profit = profit + ?,
                              updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
        """
        cursor, conn, should_close = self._execute(sql, (volume, profit, now_utc(), manager_id), conn=conn)
        affected = cursor.rowcount
        if should_close:
            conn.close()
        return affected > 0

    def increment_cancels(self, manager_id: int, conn=None) -> bool:
        sql = """
            UPDATE managers SET cancel_count = cancel_count + 1, updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
        """
        cursor, conn, should_close = self._execute(sql, (now_utc(), manager_id), conn=conn)
        affected = cursor.rowcount
        if should_close:
            conn.close()
        return affected > 0


class DealRepository(BaseRepository):
    table = "deals"

    def _row_to_model(self, row) -> Deal:
        return Deal(
            id=row["id"],
            user_id=row["user_id"],
            user_username=row["user_username"] if "user_username" in row.keys() else None,
            user_telegram_id=row["user_telegram_id"] if "user_telegram_id" in row.keys() else 0,
            manager_id=row["manager_id"],
            status=row["status"],
            amount_usdt=Decimal(row["amount_usdt"]) if row["amount_usdt"] else Decimal("0"),
            client_rate=Decimal(row["client_rate"]) if row["client_rate"] else Decimal("0"),
            internal_rate=Decimal(row["internal_rate"]) if row["internal_rate"] else Decimal("0"),
            revenue=Decimal(row["revenue"]) if row["revenue"] else Decimal("0"),
            cost=Decimal(row["cost"]) if row["cost"] else Decimal("0"),
            profit=Decimal(row["profit"]) if row["profit"] else Decimal("0"),
            tier_index=row["tier_index"] or 0,
            is_pinned=bool(row["is_pinned"]),
            pinned_at=row["pinned_at"],
            promoted_at=row["promoted_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
            cancelled_at=row["cancelled_at"],
            deleted_at=row["deleted_at"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def create(self, deal: Deal, conn=None) -> Deal:
        if not deal.id:
            deal.id = generate_uuid()
        sql = """
            INSERT INTO deals (id, user_id, user_username, user_telegram_id, manager_id, status, amount_usdt, client_rate,
                             internal_rate, revenue, cost, profit, tier_index, is_pinned,
                             pinned_at, promoted_at, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = now_utc()
        cursor, conn, should_close = self._execute(
            sql,
            (
                deal.id,
                deal.user_id,
                deal.user_username,
                deal.user_telegram_id,
                deal.manager_id,
                deal.status,
                deal.amount_usdt,
                deal.client_rate,
                deal.internal_rate,
                deal.revenue,
                deal.cost,
                deal.profit,
                deal.tier_index,
                int(deal.is_pinned),
                deal.pinned_at,
                deal.promoted_at,
                now,
                now,
                json.dumps(deal.metadata, ensure_ascii=False),
            ),
            conn=conn,
        )
        if should_close:
            conn.close()
        return deal

    def update(self, deal: Deal, conn=None) -> Deal:
        sql = """
            UPDATE deals SET user_username = ?, user_telegram_id = ?, manager_id = ?, status = ?, amount_usdt = ?, client_rate = ?,
                internal_rate = ?, revenue = ?, cost = ?, profit = ?, tier_index = ?,
                is_pinned = ?, pinned_at = ?, promoted_at = ?, updated_at = ?,
                closed_at = ?, cancelled_at = ?, metadata = ?
            WHERE id = ? AND deleted_at IS NULL
        """
        cursor, conn, should_close = self._execute(
            sql,
            (
                deal.user_username,
                deal.user_telegram_id,
                deal.manager_id,
                deal.status,
                deal.amount_usdt,
                deal.client_rate,
                deal.internal_rate,
                deal.revenue,
                deal.cost,
                deal.profit,
                deal.tier_index,
                int(deal.is_pinned),
                deal.pinned_at,
                deal.promoted_at,
                now_utc(),
                deal.closed_at,
                deal.cancelled_at,
                json.dumps(deal.metadata, ensure_ascii=False),
                deal.id,
            ),
            conn=conn,
        )
        if should_close:
            conn.close()
        return deal

    def find_open_by_user(self, user_id: int, conn=None) -> Optional[Deal]:
        sql = """
            SELECT * FROM deals
            WHERE user_id = ? AND status IN ('created','queued','active','pinned')
              AND deleted_at IS NULL
            ORDER BY created_at DESC LIMIT 1
        """
        cursor, conn, should_close = self._execute(sql, (user_id,), conn=conn)
        row = cursor.fetchone()
        if should_close:
            conn.close()
        return self._row_to_model(row) if row else None

    def list_by_manager(self, manager_id: int, status: Optional[str] = None, conn=None) -> Sequence[Deal]:
        if status:
            sql = """
                SELECT * FROM deals
                WHERE manager_id = ? AND status = ? AND deleted_at IS NULL
                ORDER BY created_at DESC
            """
            params = (manager_id, status)
        else:
            sql = """
                SELECT * FROM deals
                WHERE manager_id = ? AND deleted_at IS NULL
                ORDER BY created_at DESC
            """
            params = (manager_id,)
        cursor, conn, should_close = self._execute(sql, params, conn=conn)
        rows = cursor.fetchall()
        if should_close:
            conn.close()
        return [self._row_to_model(r) for r in rows]

    def list_open_for_manager(self, manager_id: int, conn=None) -> Sequence[Deal]:
        sql = """
            SELECT * FROM deals
            WHERE manager_id = ? AND status IN ('created','queued','active','pinned')
              AND deleted_at IS NULL
            ORDER BY promoted_at DESC NULLS LAST, created_at ASC
        """
        cursor, conn, should_close = self._execute(sql, (manager_id,), conn=conn)
        rows = cursor.fetchall()
        if should_close:
            conn.close()
        return [self._row_to_model(r) for r in rows]

    def list_finished_for_manager(self, manager_id: int, limit: int = 50, conn=None) -> Sequence[Deal]:
        sql = """
            SELECT * FROM deals
            WHERE manager_id = ? AND status IN ('closed', 'cancelled')
              AND deleted_at IS NULL
            ORDER BY created_at DESC LIMIT ?
        """
        cursor, conn, should_close = self._execute(sql, (manager_id, limit), conn=conn)
        rows = cursor.fetchall()
        if should_close:
            conn.close()
        return [self._row_to_model(r) for r in rows]

    def list_by_user(self, user_id: int, limit: int = 50, conn=None) -> Sequence[Deal]:
        sql = """
            SELECT * FROM deals
            WHERE user_id = ? AND deleted_at IS NULL
            ORDER BY created_at DESC LIMIT ?
        """
        cursor, conn, should_close = self._execute(sql, (user_id, limit), conn=conn)
        rows = cursor.fetchall()
        if should_close:
            conn.close()
        return [self._row_to_model(r) for r in rows]

    def list_recent(self, limit: int = 10, offset: int = 0) -> Sequence[Deal]:
        sql = """
            SELECT * FROM deals
            WHERE deleted_at IS NULL
            ORDER BY created_at DESC LIMIT ? OFFSET ?
        """
        cursor, conn, _ = self._execute(sql, (limit, offset))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_model(r) for r in rows]

    def list_open(self, conn=None) -> Sequence[Deal]:
        sql = """
            SELECT * FROM deals
            WHERE status IN ('created','queued','active','pinned')
              AND deleted_at IS NULL
            ORDER BY created_at ASC
        """
        cursor, conn, should_close = self._execute(sql, conn=conn)
        rows = cursor.fetchall()
        if should_close:
            conn.close()
        return [self._row_to_model(r) for r in rows]

    def get_daily_stats(self, days: int = 7) -> Sequence[dict]:
        """Return daily aggregated stats for last N days."""
        sql = """
            SELECT
                DATE(closed_at) as day,
                COUNT(*) as deals,
                SUM(amount_usdt) as volume,
                SUM(profit) as profit
            FROM deals
            WHERE status = 'closed'
              AND closed_at >= DATE('now', '-{} days')
              AND deleted_at IS NULL
            GROUP BY DATE(closed_at)
            ORDER BY day DESC
        """.format(days)
        cursor, conn, _ = self._execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_weekly_stats(self, weeks: int = 4) -> Sequence[dict]:
        """Return weekly aggregated stats for last N weeks."""
        sql = """
            SELECT
                strftime('%Y-%W', closed_at) as week,
                COUNT(*) as deals,
                SUM(amount_usdt) as volume,
                SUM(profit) as profit
            FROM deals
            WHERE status = 'closed'
              AND closed_at >= DATE('now', '-{} days')
              AND deleted_at IS NULL
            GROUP BY strftime('%Y-%W', closed_at)
            ORDER BY week DESC
        """.format(weeks * 7)
        cursor, conn, _ = self._execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_monthly_stats(self, months: int = 12) -> Sequence[dict]:
        """Return monthly aggregated stats for last N months."""
        sql = """
            SELECT
                strftime('%Y-%m', closed_at) as month,
                COUNT(*) as deals,
                SUM(amount_usdt) as volume,
                SUM(profit) as profit
            FROM deals
            WHERE status = 'closed'
              AND closed_at >= DATE('now', '-{} months')
              AND deleted_at IS NULL
            GROUP BY strftime('%Y-%m', closed_at)
            ORDER BY month DESC
        """.format(months)
        cursor, conn, _ = self._execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_manager_weekly_report(self, manager_id: int, weeks: int = 12) -> Sequence[dict]:
        """Return weekly aggregated stats for a specific manager."""
        sql = """
            SELECT
                strftime('%Y-%W', closed_at) as week,
                COUNT(*) as deals,
                SUM(amount_usdt) as volume,
                SUM(profit) as profit
            FROM deals
            WHERE manager_id = ?
              AND status = 'closed'
              AND closed_at >= DATE('now', '-{} days')
              AND deleted_at IS NULL
            GROUP BY strftime('%Y-%W', closed_at)
            ORDER BY week DESC
        """.format(weeks * 7)
        cursor, conn, _ = self._execute(sql, (manager_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_manager_monthly_report(self, manager_id: int, months: int = 12) -> Sequence[dict]:
        """Return monthly aggregated stats for a specific manager."""
        sql = """
            SELECT
                strftime('%Y-%m', closed_at) as month,
                COUNT(*) as deals,
                SUM(amount_usdt) as volume,
                SUM(profit) as profit
            FROM deals
            WHERE manager_id = ?
              AND status = 'closed'
              AND closed_at >= DATE('now', '-{} months')
              AND deleted_at IS NULL
            GROUP BY strftime('%Y-%m', closed_at)
            ORDER BY month DESC
        """.format(months)
        cursor, conn, _ = self._execute(sql, (manager_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_manager_stats(self, manager_id: int, days: int = 30) -> dict:
        """Return stats for a specific manager over last N days."""
        sql = """
            SELECT
                COUNT(*) as deals,
                SUM(amount_usdt) as volume,
                SUM(profit) as profit
            FROM deals
            WHERE manager_id = ?
              AND status = 'closed'
              AND closed_at >= DATE('now', '-{} days')
              AND deleted_at IS NULL
        """.format(days)
        cursor, conn, _ = self._execute(sql, (manager_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "deals": row["deals"] or 0,
                "volume": Decimal(row["volume"] or 0),
                "profit": Decimal(row["profit"] or 0),
            }
        return {"deals": 0, "volume": Decimal("0"), "profit": Decimal("0")}

    def get_top_managers(self, limit: int = 10) -> Sequence[dict]:
        """Return top managers by profit."""
        sql = """
            SELECT
                manager_id,
                COUNT(*) as deals,
                SUM(amount_usdt) as volume,
                SUM(profit) as profit
            FROM deals
            WHERE status = 'closed'
              AND deleted_at IS NULL
              AND manager_id IS NOT NULL
            GROUP BY manager_id
            ORDER BY profit DESC
            LIMIT ?
        """
        cursor, conn, _ = self._execute(sql, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_top_users(self, limit: int = 10) -> Sequence[dict]:
        """Return top users by volume."""
        sql = """
            SELECT
                user_id,
                COUNT(*) as deals,
                SUM(amount_usdt) as volume,
                SUM(profit) as profit
            FROM deals
            WHERE status = 'closed'
              AND deleted_at IS NULL
            GROUP BY user_id
            ORDER BY volume DESC
            LIMIT ?
        """
        cursor, conn, _ = self._execute(sql, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_manager_daily_report(self, manager_id: int, days: int = 30) -> Sequence[dict]:
        """Return daily aggregated stats for a specific manager over last N days."""
        sql = """
            SELECT
                DATE(closed_at) as day,
                COUNT(*) as deals,
                SUM(amount_usdt) as volume,
                SUM(profit) as profit
            FROM deals
            WHERE manager_id = ?
              AND status = 'closed'
              AND closed_at >= DATE('now', '-{} days')
              AND deleted_at IS NULL
            GROUP BY DATE(closed_at)
            ORDER BY day DESC
        """.format(days)
        cursor, conn, _ = self._execute(sql, (manager_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_all_managers_summary(self, days: int = 30) -> Sequence[dict]:
        """Return turnover + profit per manager over last N days."""
        sql = """
            SELECT
                manager_id,
                COUNT(*) as deals,
                SUM(amount_usdt) as volume,
                SUM(profit) as profit
            FROM deals
            WHERE status = 'closed'
              AND closed_at >= DATE('now', '-{} days')
              AND deleted_at IS NULL
              AND manager_id IS NOT NULL
            GROUP BY manager_id
            ORDER BY profit DESC
        """.format(days)
        cursor, conn, _ = self._execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]


class RateRepository(BaseRepository):
    table = "rates"

    def _row_to_model(self, row) -> Rate:
        rapira_percent = None
        if "rapira_percent" in row.keys() and row["rapira_percent"] is not None:
            rapira_percent = Decimal(row["rapira_percent"])
        return Rate(
            id=row["id"],
            name=row["name"],
            min_amount=Decimal(row["min_amount"]) if row["min_amount"] else Decimal("0"),
            max_amount=Decimal(row["max_amount"]) if row["max_amount"] else Decimal("0"),
            rate=Decimal(row["rate"]) if row["rate"] else Decimal("0"),
            rapira_percent=rapira_percent,
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row["deleted_at"],
        )

    def create(self, rate: Rate, conn=None) -> Rate:
        sql = """
            INSERT INTO rates (name, min_amount, max_amount, rate, rapira_percent, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = now_utc()
        cursor, conn, should_close = self._execute(
            sql,
            (
                rate.name,
                rate.min_amount,
                rate.max_amount,
                rate.rate,
                rate.rapira_percent,
                int(rate.is_active),
                now,
                now,
            ),
            conn=conn,
        )
        rate.id = cursor.lastrowid
        if should_close:
            conn.close()
        return rate

    def update(self, rate: Rate, conn=None) -> Rate:
        sql = """
            UPDATE rates SET name = ?, min_amount = ?, max_amount = ?, rate = ?, rapira_percent = ?,
                is_active = ?, updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
        """
        cursor, conn, should_close = self._execute(
            sql,
            (
                rate.name,
                rate.min_amount,
                rate.max_amount,
                rate.rate,
                rate.rapira_percent,
                int(rate.is_active),
                now_utc(),
                rate.id,
            ),
            conn=conn,
        )
        if should_close:
            conn.close()
        return rate

    def list_active(self) -> Sequence[Rate]:
        sql = "SELECT * FROM rates WHERE is_active = 1 AND deleted_at IS NULL ORDER BY min_amount ASC"
        cursor, conn, _ = self._execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_model(r) for r in rows]

    def find_for_amount(self, amount: Decimal) -> Optional[Rate]:
        sql = """
            SELECT * FROM rates
            WHERE is_active = 1 AND deleted_at IS NULL
              AND min_amount <= ? AND (max_amount >= ? OR max_amount = 0)
            ORDER BY min_amount DESC LIMIT 1
        """
        cursor, conn, _ = self._execute(sql, (amount, amount))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_model(row) if row else None


class AuditRepository:
    table = "audit_log"

    def _conn(self):
        return get_connection()

    def _row_to_model(self, row) -> AuditLog:
        return AuditLog(
            id=row["id"],
            event_type=row["event_type"],
            actor_id=row["actor_id"],
            object_type=row["object_type"],
            object_id=row["object_id"],
            payload=json.loads(row["payload"]) if row["payload"] else {},
            created_at=row["created_at"],
        )

    def create(self, log: AuditLog, conn=None) -> AuditLog:
        sql = """
            INSERT INTO audit_log (event_type, actor_id, object_type, object_id, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        now = now_utc()
        if conn is None:
            conn = self._conn()
            should_close = True
        else:
            should_close = False
        cursor = conn.execute(
            sql,
            (
                log.event_type,
                log.actor_id,
                log.object_type,
                log.object_id,
                json.dumps(log.payload, ensure_ascii=False),
                now,
            ),
        )
        log.id = cursor.lastrowid
        if should_close:
            conn.close()
        return log

    def list_by_object(self, object_type: str, object_id: str, limit: int = 100) -> Sequence[AuditLog]:
        sql = """
            SELECT * FROM audit_log
            WHERE object_type = ? AND object_id = ?
            ORDER BY created_at DESC LIMIT ?
        """
        conn = self._conn()
        cursor = conn.execute(sql, (object_type, object_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_model(r) for r in rows]

    def list_by_actor(self, actor_id: int, limit: int = 100) -> Sequence[AuditLog]:
        sql = """
            SELECT * FROM audit_log
            WHERE actor_id = ?
            ORDER BY created_at DESC LIMIT ?
        """
        conn = self._conn()
        cursor = conn.execute(sql, (actor_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_model(r) for r in rows]

    def list_all_recent(self, limit: int = 50) -> Sequence[AuditLog]:
        sql = """
            SELECT * FROM audit_log
            ORDER BY created_at DESC LIMIT ?
        """
        conn = self._conn()
        cursor = conn.execute(sql, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_model(r) for r in rows]


class TicketRepository(BaseRepository):
    table = "tickets"

    def _row_to_model(self, row) -> Ticket:
        return Ticket(
            id=row["id"],
            ticket_number=row["ticket_number"],
            user_id=row["user_id"],
            deal_id=row["deal_id"],
            amount_threshold=Decimal(row["amount_threshold"]) if row["amount_threshold"] else Decimal("0"),
            created_at=row["created_at"],
            used_at=row["used_at"],
            deleted_at=row["deleted_at"],
        )

    def create(self, ticket: Ticket, conn=None) -> Ticket:
        sql = """
            INSERT INTO tickets (ticket_number, user_id, deal_id, amount_threshold, created_at)
            VALUES (?, ?, ?, ?, ?)
        """
        now = now_utc()
        if conn is None:
            conn = self._conn()
            should_close = True
        else:
            should_close = False
        cursor = conn.execute(
            sql,
            (
                ticket.ticket_number,
                ticket.user_id,
                ticket.deal_id,
                ticket.amount_threshold,
                now,
            ),
        )
        ticket.id = cursor.lastrowid
        if should_close:
            conn.close()
        return ticket

    def list_by_user(self, user_id: int) -> Sequence[Ticket]:
        sql = "SELECT * FROM tickets WHERE user_id = ? AND deleted_at IS NULL ORDER BY created_at DESC"
        cursor, conn, _ = self._execute(sql, (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_model(r) for r in rows]

    def count_by_user(self, user_id: int) -> int:
        sql = "SELECT COUNT(*) FROM tickets WHERE user_id = ? AND deleted_at IS NULL"
        cursor, conn, _ = self._execute(sql, (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0

    def mark_used(self, ticket_id: int, conn=None) -> bool:
        sql = "UPDATE tickets SET used_at = ? WHERE id = ? AND deleted_at IS NULL"
        cursor, conn, should_close = self._execute(sql, (now_utc(), ticket_id), conn=conn)
        affected = cursor.rowcount
        if should_close:
            conn.close()
        return affected > 0

    def clear_all(self, conn=None) -> int:
        """Soft delete all tickets (burn). Returns count affected."""
        sql = "UPDATE tickets SET deleted_at = ? WHERE deleted_at IS NULL"
        cursor, conn, should_close = self._execute(sql, (now_utc(),), conn=conn)
        affected = cursor.rowcount
        if should_close:
            conn.close()
        return affected


class NotificationRepository(BaseRepository):
    table = "notifications"

    def _row_to_model(self, row) -> Notification:
        return Notification(
            id=row["id"],
            user_id=row["user_id"],
            manager_id=row["manager_id"],
            type=row["type"],
            message=row["message"],
            is_read=bool(row["is_read"]),
            created_at=row["created_at"],
        )

    def create(self, notification: Notification, conn=None) -> Notification:
        sql = """
            INSERT INTO notifications (user_id, manager_id, type, message, is_read, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        now = now_utc()
        if conn is None:
            conn = self._conn()
            should_close = True
        else:
            should_close = False
        cursor = conn.execute(
            sql,
            (
                notification.user_id,
                notification.manager_id,
                notification.type,
                notification.message,
                int(notification.is_read),
                now,
            ),
        )
        notification.id = cursor.lastrowid
        if should_close:
            conn.close()
        return notification

    def list_unread_for_user(self, user_id: int) -> Sequence[Notification]:
        sql = """
            SELECT * FROM notifications
            WHERE user_id = ? AND is_read = 0
            ORDER BY created_at DESC
        """
        cursor, conn, _ = self._execute(sql, (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_model(r) for r in rows]

    def list_unread_for_manager(self, manager_id: int) -> Sequence[Notification]:
        sql = """
            SELECT * FROM notifications
            WHERE manager_id = ? AND is_read = 0
            ORDER BY created_at DESC
        """
        cursor, conn, _ = self._execute(sql, (manager_id,))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_model(r) for r in rows]

    def mark_read(self, notification_id: int) -> bool:
        sql = "UPDATE notifications SET is_read = 1 WHERE id = ?"
        cursor, conn, _ = self._execute(sql, (notification_id,))
        affected = cursor.rowcount
        conn.close()
        return affected > 0


class SessionRepository(BaseRepository):
    table = "sessions"

    def _row_to_model(self, row) -> Session:
        return Session(
            id=row["id"],
            manager_id=row["manager_id"],
            deal_id=row["deal_id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
        )

    def create(self, session: Session, conn=None) -> Session:
        sql = """
            INSERT INTO sessions (manager_id, deal_id, started_at)
            VALUES (?, ?, ?)
        """
        now = now_utc()
        if conn is None:
            conn = self._conn()
            should_close = True
        else:
            should_close = False
        cursor = conn.execute(sql, (session.manager_id, session.deal_id, now))
        session.id = cursor.lastrowid
        if should_close:
            conn.close()
        return session

    def end_session(self, session_id: int, conn=None) -> bool:
        sql = "UPDATE sessions SET ended_at = ? WHERE id = ?"
        cursor, conn, should_close = self._execute(sql, (now_utc(), session_id), conn=conn)
        affected = cursor.rowcount
        if should_close:
            conn.close()
        return affected > 0

    def find_active_for_manager(self, manager_id: int) -> Optional[Session]:
        sql = """
            SELECT * FROM sessions
            WHERE manager_id = ? AND ended_at IS NULL
            ORDER BY started_at DESC LIMIT 1
        """
        cursor, conn, _ = self._execute(sql, (manager_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_model(row) if row else None


class DealQueueRepository:
    table = "deal_queue"

    def _conn(self):
        return get_connection()

    def _row_to_model(self, row) -> DealQueue:
        return DealQueue(
            id=row["id"],
            deal_id=row["deal_id"],
            manager_id=row["manager_id"],
            queue_position=row["queue_position"] or 0,
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
        )

    def add(self, deal_id: str, manager_id: Optional[int] = None, conn=None) -> DealQueue:
        sql = """
            INSERT INTO deal_queue (deal_id, manager_id, queue_position, is_active, created_at)
            VALUES (?, ?, ?, ?, ?)
        """
        now = now_utc()
        if conn is None:
            conn = self._conn()
            should_close = True
        else:
            should_close = False
        # Calculate next position for this manager
        cursor = conn.execute(
            "SELECT COALESCE(MAX(queue_position), 0) + 1 FROM deal_queue WHERE manager_id = ? AND deal_id IN (SELECT id FROM deals WHERE deleted_at IS NULL AND status IN ('queued','active','pinned'))",
            (manager_id,),
        )
        pos = cursor.fetchone()[0] or 1
        cursor = conn.execute(sql, (deal_id, manager_id, pos, 0, now))
        dq = DealQueue(id=cursor.lastrowid, deal_id=deal_id, manager_id=manager_id, queue_position=pos, is_active=False, created_at=now)
        if should_close:
            conn.close()
        return dq

    def assign_manager(self, deal_id: str, manager_id: int, conn=None) -> bool:
        sql = "UPDATE deal_queue SET manager_id = ? WHERE deal_id = ?"
        if conn is None:
            conn = self._conn()
            should_close = True
        else:
            should_close = False
        cursor = conn.execute(sql, (manager_id, deal_id))
        affected = cursor.rowcount
        if should_close:
            conn.close()
        return affected > 0

    def set_active(self, deal_id: str, is_active: bool, conn=None) -> bool:
        sql = "UPDATE deal_queue SET is_active = ? WHERE deal_id = ?"
        if conn is None:
            conn = self._conn()
            should_close = True
        else:
            should_close = False
        cursor = conn.execute(sql, (int(is_active), deal_id))
        affected = cursor.rowcount
        if should_close:
            conn.close()
        return affected > 0

    def remove(self, deal_id: str, conn=None) -> bool:
        sql = "DELETE FROM deal_queue WHERE deal_id = ?"
        if conn is None:
            conn = self._conn()
            should_close = True
        else:
            should_close = False
        cursor = conn.execute(sql, (deal_id,))
        affected = cursor.rowcount
        if should_close:
            conn.close()
        return affected > 0

    def list_for_manager(self, manager_id: int, conn=None) -> Sequence[DealQueue]:
        sql = """
            SELECT dq.* FROM deal_queue dq
            JOIN deals d ON dq.deal_id = d.id
            WHERE dq.manager_id = ? AND d.deleted_at IS NULL
              AND d.status IN ('queued','active','pinned')
            ORDER BY dq.queue_position ASC
        """
        if conn is None:
            conn = self._conn()
            should_close = True
        else:
            should_close = False
        cursor = conn.execute(sql, (manager_id,))
        rows = cursor.fetchall()
        if should_close:
            conn.close()
        return [self._row_to_model(r) for r in rows]

    def list_global(self, conn=None) -> Sequence[DealQueue]:
        sql = """
            SELECT dq.* FROM deal_queue dq
            JOIN deals d ON dq.deal_id = d.id
            WHERE d.deleted_at IS NULL
              AND d.status IN ('created','queued')
            ORDER BY dq.created_at ASC
        """
        if conn is None:
            conn = self._conn()
            should_close = True
        else:
            should_close = False
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        if should_close:
            conn.close()
        return [self._row_to_model(r) for r in rows]

    def reorder_manager_queue(self, manager_id: int, conn=None):
        """Recalculate queue positions for a manager."""
        if conn is None:
            conn = self._conn()
            should_close = True
        else:
            should_close = False
        cursor = conn.execute(
            """
            SELECT dq.id FROM deal_queue dq
            JOIN deals d ON dq.deal_id = d.id
            WHERE dq.manager_id = ? AND d.deleted_at IS NULL
              AND d.status IN ('queued','active','pinned')
            ORDER BY dq.queue_position ASC, dq.created_at ASC
            """,
            (manager_id,),
        )
        rows = cursor.fetchall()
        for i, row in enumerate(rows, 1):
            conn.execute("UPDATE deal_queue SET queue_position = ? WHERE id = ?", (i, row["id"]))
        if should_close:
            conn.close()


class ShiftReportRepository(BaseRepository):
    table = "shift_reports"

    def _row_to_model(self, row) -> ShiftReport:
        return ShiftReport(
            id=row["id"],
            manager_id=row["manager_id"],
            work_date=row["work_date"],
            opening_balance=Decimal(row["opening_balance"]) if row["opening_balance"] else Decimal("0"),
            start_kb=Decimal(row["start_kb"]) if "start_kb" in row.keys() else Decimal("0"),
            closing_balance=Decimal(row["closing_balance"]) if row["closing_balance"] else Decimal("0"),
            end_kb=Decimal(row["end_kb"]) if "end_kb" in row.keys() else Decimal("0"),
            system_profit=Decimal(row["system_profit"]) if row["system_profit"] else Decimal("0"),
            salary_percent=Decimal(row["salary_percent"]) if row["salary_percent"] else Decimal("0"),
            top_place=row["top_place"] or 0,
            top_bonus=Decimal(row["top_bonus"]) if row["top_bonus"] else Decimal("0"),
            is_locked=bool(row["is_locked"]),
            is_top_fixed=bool(row["is_top_fixed"]),
            admin_note=row["admin_note"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create(self, report: ShiftReport, conn=None) -> ShiftReport:
        sql = """
            INSERT INTO shift_reports (manager_id, work_date, opening_balance, start_kb, closing_balance, end_kb,
                                       system_profit, salary_percent, top_place, top_bonus,
                                       is_locked, is_top_fixed, admin_note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = now_utc()
        cursor, conn, should_close = self._execute(
            sql,
            (
                report.manager_id,
                report.work_date,
                report.opening_balance,
                report.start_kb,
                report.closing_balance,
                report.end_kb,
                report.system_profit,
                report.salary_percent,
                report.top_place,
                report.top_bonus,
                int(report.is_locked),
                int(report.is_top_fixed),
                report.admin_note,
                now,
                now,
            ),
            conn=conn,
        )
        report.id = cursor.lastrowid
        if should_close:
            conn.close()
        return report

    def update(self, report: ShiftReport, conn=None) -> ShiftReport:
        sql = """
            UPDATE shift_reports SET opening_balance = ?, start_kb = ?, closing_balance = ?, end_kb = ?, system_profit = ?,
                salary_percent = ?, top_place = ?, top_bonus = ?, is_locked = ?, is_top_fixed = ?,
                admin_note = ?, updated_at = ?
            WHERE id = ?
        """
        now = now_utc()
        cursor, conn, should_close = self._execute(
            sql,
            (
                report.opening_balance,
                report.start_kb,
                report.closing_balance,
                report.end_kb,
                report.system_profit,
                report.salary_percent,
                report.top_place,
                report.top_bonus,
                int(report.is_locked),
                int(report.is_top_fixed),
                report.admin_note,
                now,
                report.id,
            ),
            conn=conn,
        )
        if should_close:
            conn.close()
        return report

    def find_by_manager_and_date(self, manager_id: int, work_date: str) -> ShiftReport | None:
        sql = """
            SELECT * FROM shift_reports
            WHERE manager_id = ? AND work_date = ?
            LIMIT 1
        """
        cursor, conn, _ = self._execute(sql, (manager_id, work_date))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_model(row) if row else None

    def list_by_date(self, work_date: str) -> list[ShiftReport]:
        sql = "SELECT * FROM shift_reports WHERE work_date = ? ORDER BY created_at DESC"
        cursor, conn, _ = self._execute(sql, (work_date,))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_model(r) for r in rows]

    def list_by_manager(self, manager_id: int, limit: int = 30) -> list[ShiftReport]:
        sql = """
            SELECT * FROM shift_reports
            WHERE manager_id = ?
            ORDER BY work_date DESC
            LIMIT ?
        """
        cursor, conn, _ = self._execute(sql, (manager_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_model(r) for r in rows]

    def get_daily_manager_profit(self, manager_id: int, work_date: str) -> Decimal:
        """Sum profit from closed deals for manager on a given date."""
        sql = """
            SELECT COALESCE(SUM(profit), 0) as total
            FROM deals
            WHERE manager_id = ? AND status = 'closed'
              AND DATE(closed_at) = ?
              AND deleted_at IS NULL
        """
        cursor, conn, _ = self._execute(sql, (manager_id, work_date))
        row = cursor.fetchone()
        conn.close()
        return Decimal(str(row["total"])) if row and row["total"] else Decimal("0")


class PromocodeRepository(BaseRepository):
    table = "promocodes"

    def _row_to_model(self, row) -> Promocode:
        return Promocode(
            id=row["id"],
            code=row["code"],
            bonus_percent=Decimal(row["bonus_percent"]) if row["bonus_percent"] else Decimal("0"),
            max_activations=row["max_activations"] or 0,
            used_count=row["used_count"] or 0,
            created_at=row["created_at"],
            deleted_at=row["deleted_at"],
        )

    def create(self, promocode: Promocode, conn=None) -> Promocode:
        sql = """
            INSERT INTO promocodes (code, bonus_percent, max_activations, used_count, created_at)
            VALUES (?, ?, ?, ?, ?)
        """
        now = now_utc()
        cursor, conn, should_close = self._execute(
            sql,
            (
                promocode.code,
                promocode.bonus_percent,
                promocode.max_activations,
                promocode.used_count,
                now,
            ),
            conn=conn,
        )
        promocode.id = cursor.lastrowid
        if should_close:
            conn.close()
        return promocode

    def find_by_code(self, code: str, conn=None) -> Optional[Promocode]:
        sql = f"SELECT * FROM {self.table} WHERE code = ? AND deleted_at IS NULL LIMIT 1"
        cursor, conn, should_close = self._execute(sql, (code,), conn=conn)
        row = cursor.fetchone()
        if should_close:
            conn.close()
        return self._row_to_model(row) if row else None

    def increment_used(self, promocode_id: int, conn=None) -> None:
        sql = f"UPDATE {self.table} SET used_count = used_count + 1 WHERE id = ?"
        cursor, conn, should_close = self._execute(sql, (promocode_id,), conn=conn)
        if should_close:
            conn.close()
