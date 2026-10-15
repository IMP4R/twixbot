"""TWIX Services — core business logic."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, Sequence

from database import now_utc, transaction
from models import AuditLog, Deal, DealQueue, Manager, Notification, Promocode, Rate, ShiftReport, Ticket, User
from repositories import (
    AuditRepository,
    DealQueueRepository,
    DealRepository,
    ManagerRepository,
    NotificationRepository,
    PromocodeRepository,
    RateRepository,
    ShiftReportRepository,
    TicketRepository,
    UserRepository,
)


# ── Rate Service ──────────────────────────────────────────────────────────

class RateService:
    def __init__(self):
        self.repo = RateRepository()
        self.audit = AuditRepository()

    def get_tiers(self) -> Sequence[Rate]:
        return self.repo.list_active()

    def get_rate_for_amount(self, amount: Decimal) -> Optional[Rate]:
        return self.repo.find_for_amount(amount)

    def calculate_internal_rate(self, rapira_rate: Decimal, coefficient: Decimal) -> Decimal:
        return rapira_rate * coefficient

    def apply_loyalty_bonus(self, base_rate: Decimal, user_volume: Decimal, tiers: list[tuple[Decimal, Decimal]]) -> Decimal:
        """Apply loyalty bonus based on user total volume.
        tiers: list of (threshold, bonus) sorted ascending.
        """
        bonus = Decimal("0")
        for threshold, b in sorted(tiers, key=lambda x: x[0]):
            if user_volume >= threshold:
                bonus = b
        return base_rate + bonus

    def create_tier(self, name: str, min_amount: Decimal, max_amount: Decimal, rate: Decimal, actor_id: int = 0, *, rapira_percent: Optional[Decimal] = None) -> Rate:
        if not name.strip():raise ValueError('Название не может быть пустым')
        if any(not isinstance(value,Decimal) or not value.is_finite() for value in (min_amount,max_amount,rate)):
            raise ValueError('Суммы и курс должны быть конечными числами')
        if min_amount<0 or max_amount<0 or rate<=0 or (max_amount!=0 and max_amount<min_amount):
            raise ValueError('Проверьте диапазон сумм и положительный курс')
        if rapira_percent is not None and (not isinstance(rapira_percent,Decimal) or not rapira_percent.is_finite() or rapira_percent<0):
            raise ValueError('Процент Rapira должен быть конечным числом >= 0')
        r = Rate(name=name, min_amount=min_amount, max_amount=max_amount, rate=rate,rapira_percent=rapira_percent)
        created = self.repo.create(r)
        self.audit.create(
            AuditLog(
                event_type="rate_created",
                actor_id=actor_id,
                object_type="rate",
                object_id=str(created.id),
                payload={"name": name, "min": str(min_amount), "max": str(max_amount), "rate": str(rate)},
            )
        )
        return created

    def update_rate(self, rate_id: int, new_rate: Decimal, actor_id: int = 0) -> Optional[Rate]:
        r = self.repo.find_by_id(rate_id)
        if not r:
            return None
        old = r.rate
        r.rate = new_rate
        updated = self.repo.update(r)
        self.audit.create(
            AuditLog(
                event_type="rate_updated",
                actor_id=actor_id,
                object_type="rate",
                object_id=str(rate_id),
                payload={"old": str(old), "new": str(new_rate)},
            )
        )
        return updated

    def shift_all_rates(self, delta: Decimal, actor_id: int = 0) -> int:
        """Shift all active rates by delta. Returns count updated."""
        tiers = self.get_tiers()
        count = 0
        for t in tiers:
            old = t.rate
            t.rate = t.rate + delta
            self.repo.update(t)
            self.audit.create(
                AuditLog(
                    event_type="rate_shifted",
                    actor_id=actor_id,
                    object_type="rate",
                    object_id=str(t.id),
                    payload={"old": str(old), "delta": str(delta), "new": str(t.rate)},
                )
            )
            count += 1
        return count

    def recalculate_tiers_from_rapira(self, rapira_price: Decimal, actor_id: int = 0) -> int:
        """Recalculate all tier rates as rapira_price * (1 + rapira_percent/100).
        Only tiers with rapira_percent set are updated."""
        tiers = list(self.get_tiers())
        count = 0
        for t in tiers:
            if t.rapira_percent is None:
                continue
            old = t.rate
            percent = t.rapira_percent
            new_rate = (rapira_price * (Decimal("1") + percent / Decimal("100"))).quantize(Decimal("0.01"))
            t.rate = new_rate
            self.repo.update(t)
            self.audit.create(
                AuditLog(
                    event_type="rate_recalculated_rapira",
                    actor_id=actor_id,
                    object_type="rate",
                    object_id=str(t.id),
                    payload={"old": str(old), "rapira": str(rapira_price), "percent": str(percent), "new": str(new_rate)},
                )
            )
            count += 1
        return count

    def backup_fixed_rates(self) -> list[dict]:
        """Return JSON-able backup of current tier rates."""
        tiers = list(self.get_tiers())
        return [{"id": t.id, "rate": str(t.rate)} for t in tiers]

    def restore_fixed_rates(self, backup: list[dict], actor_id: int = 0) -> int:
        """Restore tier rates from JSON backup."""
        count = 0
        for item in backup:
            tier_id = item.get("id")
            rate_val = Decimal(str(item.get("rate", "0")))
            t = self.repo.find_by_id(tier_id)
            if t:
                old = t.rate
                t.rate = rate_val
                self.repo.update(t)
                self.audit.create(
                    AuditLog(
                        event_type="rate_restored_fixed",
                        actor_id=actor_id,
                        object_type="rate",
                        object_id=str(tier_id),
                        payload={"old": str(old), "new": str(rate_val)},
                    )
                )
                count += 1
        return count


# ── Promocode Service ─────────────────────────────────────────────────────

class PromocodeService:
    def __init__(self):
        self.repo = PromocodeRepository()

    def validate(self, code: str) -> Optional[Promocode]:
        """Return promocode if valid (not expired by usage), else None."""
        pc = self.repo.find_by_code(code)
        if not pc:
            return None
        if pc.max_activations > 0 and pc.used_count >= pc.max_activations:
            return None
        return pc

    def apply(self, code: str, base_rate: Decimal) -> tuple[Decimal, Optional[Promocode]]:
        """Return (adjusted_rate, promocode or None). Rate increased by bonus_percent."""
        pc = self.validate(code)
        if not pc:
            return base_rate, None
        adjusted = base_rate * (Decimal("1") + pc.bonus_percent / Decimal("100"))
        return adjusted, pc

    def create(self, code: str, bonus_percent: Decimal, max_activations: int = 0) -> Promocode:
        pc = Promocode(code=code, bonus_percent=bonus_percent, max_activations=max_activations)
        return self.repo.create(pc)

    def list_all(self) -> Sequence[Promocode]:
        return self.repo.list_all()

    def mark_used(self, promocode_id: int) -> None:
        self.repo.increment_used(promocode_id)

    def soft_delete(self, promocode_id: int) -> None:
        from database import now_utc
        with transaction() as conn:
            conn.execute(
                "UPDATE promocodes SET deleted_at = ? WHERE id = ?",
                (now_utc(), promocode_id),
            )


# ── Deal Service ──────────────────────────────────────────────────────────

class DealService:
    def __init__(self):
        self.deals = DealRepository()
        self.users = UserRepository()
        self.managers = ManagerRepository()
        self.queue = DealQueueRepository()
        self.audit = AuditRepository()
        self.notifications = NotificationRepository()
        self.tickets = TicketRepository()
        self.rate_service = RateService()
        self.promocode_service = PromocodeService()

    async def create_deal(
        self,
        user_id: int,
        amount_usdt: Decimal,
        client_rate: Decimal,
        internal_rate: Decimal,
        manager_id: Optional[int] = None,
        tier_index: int = 0,
        metadata: Optional[dict] = None,
        actor_id: int = 0,
        promocode_code: Optional[str] = None,
    ) -> Deal:
        """Create a new deal. User must not have other open deals."""
        with transaction() as conn:
            existing = self.deals.find_open_by_user(user_id, conn=conn)
            if existing:
                raise ValueError("User already has an open deal")

            if amount_usdt <= 0:
                raise ValueError("Amount must be positive")

            # Validate manager is active before assigning
            assigned_manager_id = manager_id
            if manager_id:
                mgr = self.managers.find_by_id(manager_id, conn=conn)
                if not mgr or mgr.deleted_at is not None:
                    assigned_manager_id = None

            # Apply promocode if provided
            applied_pc = None
            final_client_rate = client_rate
            if promocode_code:
                final_client_rate, applied_pc = self.promocode_service.apply(
                    promocode_code.strip().upper(), client_rate
                )
                if applied_pc:
                    self.promocode_service.mark_used(applied_pc.id)

            # Snapshot client info into deal (like we do for manager in UI)
            user = self.users.find_by_id(user_id, conn=conn)
            deal_metadata = metadata or {}
            if applied_pc:
                deal_metadata["promocode_id"] = applied_pc.id
                deal_metadata["promocode_code"] = applied_pc.code
                deal_metadata["promocode_bonus_percent"] = str(applied_pc.bonus_percent)

            deal = Deal(
                id=str(uuid.uuid4()),
                user_id=user_id,
                user_username=user.username if user else None,
                user_telegram_id=user.telegram_id if user else 0,
                manager_id=assigned_manager_id,
                status="created" if assigned_manager_id is None else "queued",
                amount_usdt=amount_usdt,
                client_rate=final_client_rate,
                internal_rate=internal_rate,
                revenue=Decimal("0"),
                cost=Decimal("0"),
                profit=Decimal("0"),
                tier_index=tier_index,
                metadata=deal_metadata,
            )
            created = self.deals.create(deal, conn=conn)

            # Add to queue
            self.queue.add(created.id, assigned_manager_id, conn=conn)

            # If assigned to manager, set status to queued
            if assigned_manager_id:
                created.status = "queued"
                self.deals.update(created, conn=conn)

            # Audit log
            self.audit.create(
                AuditLog(
                    event_type="deal_created",
                    actor_id=actor_id,
                    object_type="deal",
                    object_id=created.id,
                    payload={
                        "user_id": user_id,
                        "amount_usdt": str(amount_usdt),
                        "client_rate": str(client_rate),
                        "internal_rate": str(internal_rate),
                        "manager_id": assigned_manager_id,
                        "requested_manager_id": manager_id,
                    },
                ),
                conn=conn,
            )

            # Notify manager if assigned
            if assigned_manager_id:
                self.notifications.create(
                    Notification(
                        manager_id=assigned_manager_id,
                        type="new_deal",
                        message=f"Новая сделка #{created.id[:8]} на {amount_usdt} USDT",
                    ),
                    conn=conn,
                )

            return created

    async def assign_manager(self, deal_id: str, manager_id: int, actor_id: int = 0) -> Deal:
        with transaction() as conn:
            deal = self.deals.find_by_id(deal_id, conn=conn)
            if not deal:
                raise ValueError("Deal not found")
            if deal.status not in ("created", "queued"):
                raise ValueError("Deal cannot be assigned")

            # Validate target manager is active
            mgr = self.managers.find_by_id(manager_id, conn=conn)
            if not mgr or mgr.deleted_at is not None:
                raise ValueError("Target manager is not active")

            deal.manager_id = manager_id
            deal.status = "queued"
            updated = self.deals.update(deal, conn=conn)

            # Update manager's last assigned timestamp for round-robin
            mgr.last_assigned_at = now_utc()
            self.managers.update(mgr, conn=conn)

            self.queue.assign_manager(deal_id, manager_id, conn=conn)
            self.queue.reorder_manager_queue(manager_id, conn=conn)

            self.audit.create(
                AuditLog(
                    event_type="deal_assigned",
                    actor_id=actor_id,
                    object_type="deal",
                    object_id=deal_id,
                    payload={"manager_id": manager_id},
                ),
                conn=conn,
            )

            self.notifications.create(
                Notification(
                    manager_id=manager_id,
                    type="new_deal",
                    message=f"Вам назначена сделка #{deal_id[:8]}",
                ),
                conn=conn,
            )

            return updated

    async def activate_deal(self, deal_id: str, actor_id: int = 0) -> Deal:
        """Mark deal as active (first in manager's queue)."""
        deal = self.deals.find_by_id(deal_id)
        if not deal:
            raise ValueError("Deal not found")
        if deal.status not in ("queued", "pinned"):
            raise ValueError("Deal must be queued or pinned to activate")

        deal.status = "active"
        updated = self.deals.update(deal)
        self.queue.set_active(deal_id, True)

        self.audit.create(
            AuditLog(
                event_type="deal_activated",
                actor_id=actor_id,
                object_type="deal",
                object_id=deal_id,
                payload={"manager_id": deal.manager_id},
            )
        )

        return updated

    async def promote_deal(self, deal_id: str, actor_id: int = 0) -> Deal:
        deal = self.deals.find_by_id(deal_id)
        if not deal:
            raise ValueError("Deal not found")
        if deal.is_finished:
            raise ValueError("Cannot promote finished deal")
        if not deal.manager_id:
            raise ValueError("Deal has no manager")

        deal.promoted_at = now_utc()
        if deal.status == "queued":
            deal.status = "active"
        updated = self.deals.update(deal)

        self.audit.create(
            AuditLog(
                event_type="deal_promoted",
                actor_id=actor_id,
                object_type="deal",
                object_id=deal_id,
                payload={"manager_id": deal.manager_id},
            )
        )

        return updated

    async def pin_deal(self, deal_id: str, actor_id: int = 0) -> Deal:
        deal = self.deals.find_by_id(deal_id)
        if not deal:
            raise ValueError("Deal not found")
        if deal.status not in ("queued", "active"):
            raise ValueError("Can only pin queued or active deals")

        deal.is_pinned = True
        deal.pinned_at = now_utc()
        deal.status = "pinned"
        updated = self.deals.update(deal)
        self.queue.set_active(deal_id, True)

        self.audit.create(
            AuditLog(
                event_type="deal_pinned",
                actor_id=actor_id,
                object_type="deal",
                object_id=deal_id,
                payload={"manager_id": deal.manager_id},
            )
        )

        return updated

    async def unpin_deal(self, deal_id: str, actor_id: int = 0) -> Deal:
        deal = self.deals.find_by_id(deal_id)
        if not deal:
            raise ValueError("Deal not found")
        if deal.status != "pinned":
            raise ValueError("Deal is not pinned")

        deal.is_pinned = False
        deal.pinned_at = None
        deal.status = "queued"
        updated = self.deals.update(deal)
        self.queue.set_active(deal_id, False)

        # Reorder queue
        if deal.manager_id:
            self.queue.reorder_manager_queue(deal.manager_id)

        self.audit.create(
            AuditLog(
                event_type="deal_unpinned",
                actor_id=actor_id,
                object_type="deal",
                object_id=deal_id,
                payload={"manager_id": deal.manager_id},
            )
        )

        return updated

    async def close_deal(self, deal_id: str, actor_id: int = 0, actual_amount=None) -> Deal:
        """Close a deal. Profit is finalized on close (fixed-profit model). Updates user and manager stats.
        If actual_amount is provided (Decimal), it overrides deal.amount_usdt for profit/stats calculation."""
        from decimal import Decimal
        calc_amount = Decimal(str(actual_amount)) if actual_amount is not None else None
        with transaction() as conn:
            deal = self.deals.find_by_id(deal_id, conn=conn)
            if not deal:
                raise ValueError("Deal not found")
            if deal.is_finished:
                raise ValueError("Deal already finished")
            if calc_amount is None:
                calc_amount = deal.amount_usdt

            # Calculate revenue, cost and profit at close time
            deal.cost = calc_amount * deal.client_rate
            deal.revenue = calc_amount * deal.internal_rate
            deal.profit = deal.revenue - deal.cost

            deal.status = "closed"
            deal.closed_at = now_utc()
            updated = self.deals.update(deal, conn=conn)

            # Remove from queue
            self.queue.remove(deal_id, conn=conn)

            # Update user stats (turnover in client's currency)
            self.users.increment_stats(deal.user_id, calc_amount, deal.cost, conn=conn)

            # Update manager stats
            if deal.manager_id:
                self.managers.increment_stats(deal.manager_id, calc_amount, deal.profit, conn=conn)

            # Award tickets based on client's turnover (deal.cost)
            from twix_settings import get as settings_get
            tickets_enabled = await settings_get("tickets.enabled")
            if tickets_enabled:
                threshold = await settings_get("tickets.threshold")
                self._award_tickets(
                    deal.user_id, calc_amount, deal_id,
                    threshold=Decimal(str(threshold)) if threshold else Decimal("2000"),
                    conn=conn,
                )

            self.audit.create(
                AuditLog(
                    event_type="deal_closed",
                    actor_id=actor_id,
                    object_type="deal",
                    object_id=deal_id,
                    payload={
                        "amount": str(deal.amount_usdt),
                        "profit": str(deal.profit),
                        "manager_id": deal.manager_id,
                    },
                ),
                conn=conn,
            )

            # Notify user
            self.notifications.create(
                Notification(
                    user_id=deal.user_id,
                    type="deal_closed",
                    message=f"Ваша сделка #{deal_id[:8]} на {deal.amount_usdt} USDT завершена",
                ),
                conn=conn,
            )

            return updated

    async def cancel_deal(self, deal_id: str, actor_id: int = 0) -> Deal:
        with transaction() as conn:
            deal = self.deals.find_by_id(deal_id, conn=conn)
            if not deal:
                raise ValueError("Deal not found")
            if deal.is_finished:
                raise ValueError("Deal already finished")

            deal.status = "cancelled"
            deal.cancelled_at = now_utc()
            updated = self.deals.update(deal, conn=conn)

            # Remove from queue
            self.queue.remove(deal_id, conn=conn)

            # Update manager cancel count
            if deal.manager_id:
                self.managers.increment_cancels(deal.manager_id, conn=conn)

            self.audit.create(
                AuditLog(
                    event_type="deal_cancelled",
                    actor_id=actor_id,
                    object_type="deal",
                    object_id=deal_id,
                    payload={"manager_id": deal.manager_id},
                ),
                conn=conn,
            )

            # Notify user
            self.notifications.create(
                Notification(
                    user_id=deal.user_id,
                    type="deal_cancelled",
                    message=f"Сделка #{deal_id[:8]} отменена",
                ),
                conn=conn,
            )

            return updated

    async def transfer_deal(self, deal_id: str, actor_id: int = 0, queue_service=None) -> Deal:
        with transaction() as conn:
            deal = self.deals.find_by_id(deal_id, conn=conn)
            if not deal:
                raise ValueError("Deal not found")
            if deal.is_finished:
                raise ValueError("Cannot transfer finished deal")

            old_manager = deal.manager_id
            print(f"[TRANSFER] deal={deal_id[:8]} old_mgr={old_manager} — clearing manager_id")
            deal.manager_id = None
            deal.status = "created"
            deal.is_pinned = False
            deal.pinned_at = None
            deal.promoted_at = None
            updated = self.deals.update(deal, conn=conn)
            print(f"[TRANSFER] DB updated: manager_id={updated.manager_id} status={updated.status}")

            self.queue.assign_manager(deal_id, None, conn=conn)
            if old_manager:
                self.queue.reorder_manager_queue(old_manager, conn=conn)
                print(f"[TRANSFER] Queue cleared for old_mgr={old_manager}")

            self.audit.create(
                AuditLog(
                    event_type="deal_transferred_to_queue",
                    actor_id=actor_id,
                    object_type="deal",
                    object_id=deal_id,
                    payload={"from_manager": old_manager},
                ),
                conn=conn,
            )

            self.notifications.create(
                Notification(
                    user_id=deal.user_id,
                    type="deal_transferred",
                    message=f"Ваша сделка передана в общую очередь. Ожидайте назначения нового менеджера.",
                ),
                conn=conn,
            )

        # Auto-reassign to next available manager so deal never gets lost
        if queue_service is not None:
            new_mgr_id = await queue_service.distribute_new_deal(deal_id, old_manager_id=old_manager)
            if new_mgr_id:
                return await self.assign_manager(deal_id, new_mgr_id, actor_id=actor_id)

        # Return fresh deal from DB (may have new manager after distribute)
        reassigned = self.deals.find_by_id(deal_id)
        print(f"[TRANSFER] fresh DB read: manager_id={reassigned.manager_id if reassigned else None} status={reassigned.status if reassigned else None}")

        # Audit log with new manager info for debugging
        self.audit.create(
            AuditLog(
                event_type="deal_transferred_to_queue",
                actor_id=actor_id,
                object_type="deal",
                object_id=deal_id,
                payload={
                    "from_manager": old_manager,
                    "to_manager": reassigned.manager_id if reassigned else None,
                    "auto_reassigned": bool(reassigned and reassigned.manager_id),
                },
            )
        )

        return reassigned if reassigned else updated

    def _award_tickets(self, user_id: int, amount: Decimal, deal_id: str, threshold: Decimal = Decimal("2000"), conn=None):
        deal = self.deals.find_by_id(deal_id, conn=conn)
        worth_rub = deal.cost if deal and deal.cost else amount
        ticket_count = int(worth_rub // threshold)
        for i in range(ticket_count):
            ticket_number = f"TKT-{uuid.uuid4().hex[:8].upper()}"
            self.tickets.create(
                Ticket(
                    ticket_number=ticket_number,
                    user_id=user_id,
                    deal_id=deal_id,
                    amount_threshold=threshold,
                ),
                conn=conn,
            )

    def get_user_active_deal(self, user_id: int) -> Optional[Deal]:
        return self.deals.find_open_by_user(user_id)

    def get_user_history(self, user_id: int) -> Sequence[Deal]:
        return self.deals.list_by_user(user_id)

    def get_manager_deals(self, manager_id: int, status: Optional[str] = None) -> Sequence[Deal]:
        if status:
            return self.deals.list_by_manager(manager_id, status)
        return self.deals.list_open_for_manager(manager_id)

    def get_manager_history(self, manager_id: int) -> Sequence[Deal]:
        return self.deals.list_finished_for_manager(manager_id)


# ── Queue Service ─────────────────────────────────────────────────────────

class QueueService:
    def __init__(self):
        self.deal_repo = DealRepository()
        self.managers = ManagerRepository()
        self.queue = DealQueueRepository()

    async def distribute_new_deal(self, deal_id: str, old_manager_id: int | None = None) -> Optional[int]:
        """Find best manager for a deal and return manager_id. Caller must assign via DealService.
        Falls back to all active managers if no one is online.
        If old_manager_id is provided, that manager is excluded from candidates."""
        deal = self.deal_repo.find_by_id(deal_id)
        print(f"[DISTRIBUTE] deal={deal_id[:8]} current_mgr={deal.manager_id if deal else None}")
        if not deal or deal.manager_id:
            print(f"[DISTRIBUTE] skip — deal missing or already assigned")
            return None

        # Try online managers first, then fallback to all active
        candidates = self.managers.list_online()
        pool_name = "online"
        if not candidates:
            candidates = self.managers.list_all_active()
            pool_name = "active (offline fallback)"

        # Exclude the manager who transferred this deal so it never bounces back
        # unless there are no other candidates — then give it back to them
        if old_manager_id is not None:
            filtered = [m for m in candidates if m.id != old_manager_id]
            if filtered:
                candidates = filtered
                print(f"[DISTRIBUTE] excluded old_mgr={old_manager_id}")
            else:
                print(f"[DISTRIBUTE] no other managers after excluding old_mgr={old_manager_id}, keeping them")

        if not candidates:
            print(f"[DISTRIBUTE] no managers at all")
            return None  # No managers at all - stay in queue

        print(f"[DISTRIBUTE] pool={pool_name} count={len(candidates)}")
        for m in candidates:
            name = m.username or m.full_name or f"ID:{m.telegram_id}"
            count = len(self.deal_repo.list_by_manager(m.id, status="active"))
            print(f"[DISTRIBUTE] candidate mgr={m.id} @{name} online={m.is_online} can_receive={m.can_receive_deals} active_deals={count}")

        # Find manager with least active deals, tie-break by last_assigned_at
        best_manager = None
        min_deals = float("inf")
        oldest_assignment = None
        for m in candidates:
            count = len(self.deal_repo.list_by_manager(m.id, status="active"))
            if count < min_deals:
                min_deals = count
                best_manager = m
                oldest_assignment = m.last_assigned_at
            elif count == min_deals:
                # Tie-break: prefer manager who was assigned longest ago (or never)
                m_time = m.last_assigned_at or datetime(1970, 1, 1, tzinfo=timezone.utc)
                best_time = oldest_assignment or datetime(1970, 1, 1, tzinfo=timezone.utc)
                if m_time < best_time:
                    best_manager = m
                    oldest_assignment = m.last_assigned_at

        if best_manager:
            chosen_name = best_manager.username or best_manager.full_name or f"ID:{best_manager.telegram_id}"
            print(f"[DISTRIBUTE] chosen mgr={best_manager.id} @{chosen_name} reason=least active deals ({min_deals}) last_assigned={best_manager.last_assigned_at}")
            return best_manager.id

        print(f"[DISTRIBUTE] no best manager found")
        return None

    def activate_next_for_manager(self, manager_id: int) -> Optional[str]:
        """Return deal_id of the next queued deal for a manager. Caller must activate via DealService."""
        queue_items = self.queue.list_for_manager(manager_id)
        for qi in queue_items:
            deal = self.deal_repo.find_by_id(qi.deal_id)
            if deal and deal.status == "queued" and not deal.is_pinned:
                return deal.id
        return None

    async def auto_cancel_expired(self, timeout_seconds: int, deal_service) -> Sequence[Deal]:
        """Auto-cancel deals that have been queued too long."""
        from datetime import timedelta
        cutoff = now_utc() - timedelta(seconds=timeout_seconds)
        open_deals = self.deal_repo.list_open()
        cancelled = []
        for deal in open_deals:
            if deal.created_at and deal.created_at < cutoff and not deal.is_pinned and deal.status in ("created", "queued"):
                cancelled.append(await deal_service.cancel_deal(deal.id, actor_id=0))
        return cancelled


# ── Ticket Service ────────────────────────────────────────────────────────

class TicketService:
    def __init__(self):
        self.repo = TicketRepository()
        self.audit = AuditRepository()

    def get_user_tickets(self, user_id: int) -> Sequence[Ticket]:
        return self.repo.list_by_user(user_id)

    def get_ticket_count(self, user_id: int) -> int:
        return self.repo.count_by_user(user_id)

    def get_progress_to_next(self, user_id: int, user_volume: Decimal, threshold: Decimal = Decimal("2000")) -> tuple[int, Decimal]:
        """Returns (tickets_earned, progress_to_next)."""
        tickets = self.get_ticket_count(user_id)
        progress = user_volume % threshold
        return tickets, progress

    def draw_winner(self, excluded: Optional[set[int]] = None) -> Optional[Ticket]:
        """Randomly select an unused ticket."""
        import random
        all_tickets = self.repo.list_all()
        eligible = [t for t in all_tickets if t.used_at is None and (excluded is None or t.user_id not in excluded)]
        if not eligible:
            return None
        winner = random.choice(eligible)
        self.repo.mark_used(winner.id)
        self.audit.create(
            AuditLog(
                event_type="ticket_drawn",
                actor_id=0,
                object_type="ticket",
                object_id=str(winner.id),
                payload={"ticket_number": winner.ticket_number, "user_id": winner.user_id},
            )
        )
        return winner

    def clear_all(self, actor_id: int = 0) -> int:
        """Burn all unused tickets. Returns count deleted."""
        count = self.repo.clear_all()
        self.audit.create(
            AuditLog(
                event_type="tickets_cleared",
                actor_id=actor_id,
                object_type="ticket",
                object_id="",
                payload={"count": count},
            )
        )
        return count


# ── Notification Service ──────────────────────────────────────────────────

class NotificationService:
    def __init__(self):
        self.repo = NotificationRepository()

    def create(self, user_id: Optional[int] = None, manager_id: Optional[int] = None, type: str = "", message: str = "") -> Notification:
        return self.repo.create(Notification(user_id=user_id, manager_id=manager_id, type=type, message=message))

    def get_unread_for_user(self, user_id: int) -> Sequence[Notification]:
        return self.repo.list_unread_for_user(user_id)

    def get_unread_for_manager(self, manager_id: int) -> Sequence[Notification]:
        return self.repo.list_unread_for_manager(manager_id)

    def mark_read(self, notification_id: int) -> bool:
        return self.repo.mark_read(notification_id)


# ── Stats Service ─────────────────────────────────────────────────────────

class StatsService:
    def __init__(self):
        self.deals = DealRepository()
        self.managers = ManagerRepository()
        self.users = UserRepository()

    def get_daily_stats(self, days: int = 7) -> Sequence[dict]:
        return self.deals.get_daily_stats(days)

    def get_weekly_stats(self, weeks: int = 4) -> Sequence[dict]:
        return self.deals.get_weekly_stats(weeks)

    def get_monthly_stats(self, months: int = 12) -> Sequence[dict]:
        return self.deals.get_monthly_stats(months)

    def get_manager_weekly_report(self, manager_id: int, weeks: int = 12) -> Sequence[dict]:
        return self.deals.get_manager_weekly_report(manager_id, weeks)

    def get_manager_monthly_report(self, manager_id: int, months: int = 12) -> Sequence[dict]:
        return self.deals.get_manager_monthly_report(manager_id, months)

    def get_top_managers(self, limit: int = 10) -> Sequence[dict]:
        rows = self.deals.get_top_managers(limit)
        result = []
        for row in rows:
            mgr = self.managers.find_by_id(row["manager_id"])
            name = mgr.full_name or mgr.username or f"ID:{mgr.telegram_id}" if mgr else "Unknown"
            result.append({
                "name": name,
                "deals": row["deals"],
                "volume": Decimal(str(row["volume"])),
                "profit": Decimal(str(row["profit"])),
            })
        return result

    def get_top_users(self, limit: int = 10) -> Sequence[dict]:
        rows = self.deals.get_top_users(limit)
        result = []
        for row in rows:
            user = self.users.find_by_id(row["user_id"])
            name = user.full_name or user.username or f"ID:{user.telegram_id}" if user else "Unknown"
            result.append({
                "name": name,
                "deals": row["deals"],
                "volume": Decimal(str(row["volume"])),
                "profit": Decimal(str(row["profit"])),
            })
        return result

    def get_manager_daily_report(self, manager_id: int, days: int = 30) -> Sequence[dict]:
        """Return daily breakdown of turnover + profit for a specific manager."""
        rows = self.deals.get_manager_daily_report(manager_id, days)
        result = []
        for row in rows:
            result.append({
                "day": row["day"],
                "deals": row["deals"],
                "volume": Decimal(str(row["volume"])) if row["volume"] else Decimal("0"),
                "profit": Decimal(str(row["profit"])) if row["profit"] else Decimal("0"),
            })
        return result

    def get_all_managers_summary(self, days: int = 30) -> Sequence[dict]:
        """Return list of all managers with aggregated turnover + profit for period."""
        rows = self.deals.get_all_managers_summary(days)
        result = []
        for row in rows:
            mgr = self.managers.find_by_id(row["manager_id"])
            name = mgr.full_name or mgr.username or f"ID:{mgr.telegram_id}" if mgr else "Unknown"
            result.append({
                "manager_id": row["manager_id"],
                "name": name,
                "deals": row["deals"],
                "volume": Decimal(str(row["volume"])) if row["volume"] else Decimal("0"),
                "profit": Decimal(str(row["profit"])) if row["profit"] else Decimal("0"),
            })
        return result

    def get_manager_stats(self, manager_id: int, days: int = 30) -> dict:
        """Return aggregated stats for a specific manager over last N days."""
        return self.deals.get_manager_stats(manager_id, days)


# ── Audit Service ─────────────────────────────────────────────────────────

class AuditService:
    def __init__(self):
        self.repo = AuditRepository()

    def log(self, event_type: str, actor_id: int, object_type: str, object_id: str, payload: Optional[dict] = None) -> AuditLog:
        return self.repo.create(
            AuditLog(
                event_type=event_type,
                actor_id=actor_id,
                object_type=object_type,
                object_id=object_id,
                payload=payload or {},
            )
        )

    def get_history(self, object_type: str, object_id: str) -> Sequence[AuditLog]:
        return self.repo.list_by_object(object_type, object_id)

    def get_actor_history(self, actor_id: int) -> Sequence[AuditLog]:
        return self.repo.list_by_actor(actor_id)

    def get_all_recent(self, limit: int = 50) -> Sequence[AuditLog]:
        return self.repo.list_all_recent(limit)

# ── Shift Report Service ──────────────────────────────────────────────────

class ShiftReportService:
    def __init__(self):
        self.repo = ShiftReportRepository()
        self.deals = DealRepository()
        self.audit = AuditRepository()

    async def open_shift(self, manager_id: int, work_date: str, opening_balance: Decimal, start_kb: Decimal = Decimal("0")) -> ShiftReport:
        """Create or update opening balance (platform + KB)."""
        existing = self.repo.find_by_manager_and_date(manager_id, work_date)
        if existing:
            if existing.is_locked:
                raise ValueError("Смена уже закрыта (locked).")
            existing.opening_balance = opening_balance
            existing.start_kb = start_kb
            return self.repo.update(existing)
        report = ShiftReport(
            manager_id=manager_id,
            work_date=work_date,
            opening_balance=opening_balance,
            start_kb=start_kb,
        )
        return self.repo.create(report)

    async def close_shift(self, manager_id: int, work_date: str, closing_balance: Decimal, end_kb: Decimal = Decimal("0")) -> ShiftReport:
        """Close shift: save closing balance + KB, calculate income."""
        report = self.repo.find_by_manager_and_date(manager_id, work_date)
        if not report:
            raise ValueError("Сначала откройте смену (укажите начальный баланс).")
        if report.is_locked:
            raise ValueError("Смена уже закрыта администратором.")
        report.closing_balance = closing_balance
        report.end_kb = end_kb
        # Income = (end_platform + end_kb) - (start_platform + start_kb)
        start_total = report.opening_balance + report.start_kb
        end_total = report.closing_balance + report.end_kb
        report.system_profit = end_total - start_total
        # Snapshot current salary percent from settings
        from twix_settings import get as settings_get
        pct = await settings_get("manager.salary_percent")
        report.salary_percent = Decimal(str(pct)) if pct else Decimal("10.0")
        return self.repo.update(report)

    def calculate_salary(self, report: ShiftReport) -> Decimal:
        """Salary = income * percent / 100 + top_bonus."""
        base = report.system_profit * report.salary_percent / Decimal("100")
        return base + report.top_bonus

    def lock_report(self, report_id: int, actor_id: int = 0) -> ShiftReport:
        """Admin locks report so manager can no longer edit it."""
        report = self.repo.find_by_id(report_id)
        if not report:
            raise ValueError("Отчёт не найден.")
        report.is_locked = True
        updated = self.repo.update(report)
        self.audit.create(
            AuditLog(
                event_type="shift_report_locked",
                actor_id=actor_id,
                object_type="shift_report",
                object_id=str(report_id),
            )
        )
        return updated

    def set_top_bonus(self, report_id: int, place: int, bonus: Decimal, actor_id: int = 0) -> ShiftReport:
        """Admin sets top place and bonus for a report."""
        report = self.repo.find_by_id(report_id)
        if not report:
            raise ValueError("Отчёт не найден.")
        report.top_place = place
        report.top_bonus = bonus
        report.is_top_fixed = True
        updated = self.repo.update(report)
        self.audit.create(
            AuditLog(
                event_type="shift_report_top_set",
                actor_id=actor_id,
                object_type="shift_report",
                object_id=str(report_id),
                payload={"place": place, "bonus": str(bonus)},
            )
        )
        return updated

    def rank_managers_by_profit(self, work_date: str) -> list[dict]:
        """Return managers ranked by system_profit for a date (desc)."""
        reports = self.repo.list_by_date(work_date)
        # Also include managers without reports who have deals that day
        mgr_ids = {r.manager_id for r in reports}
        # Find managers with deals but no report
        conn = self.repo._conn()
        cursor = conn.execute(
            """
            SELECT manager_id, COALESCE(SUM(profit), 0) as profit
            FROM deals
            WHERE status = 'closed' AND DATE(closed_at) = ? AND deleted_at IS NULL AND manager_id IS NOT NULL
            GROUP BY manager_id
            ORDER BY profit DESC
            """,
            (work_date,),
        )
        rows = cursor.fetchall()
        conn.close()
        result = []
        seen = set()
        for row in rows:
            mgr_id = row["manager_id"]
            profit = Decimal(str(row["profit"])) if row["profit"] else Decimal("0")
            seen.add(mgr_id)
            # Try to find existing report
            report = next((r for r in reports if r.manager_id == mgr_id), None)
            if report:
                # Use stored system profit (should match, but prefer stored)
                profit = report.system_profit if report.system_profit else profit
            result.append({
                "manager_id": mgr_id,
                "profit": profit,
                "report": report,
            })
        # Append remaining reports with zero deal profit (if any)
        for r in reports:
            if r.manager_id not in seen:
                result.append({
                    "manager_id": r.manager_id,
                    "profit": r.system_profit,
                    "report": r,
                })
        return result
