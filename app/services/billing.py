"""Tariflar, kirish huquqi va to'lov (SPEC Phase 6).

Tariflar **funksiya bo'yicha** farqlanadi:

  Basic (149 000)  — yo'qotilgan pul, qoldiqlar, kunlik hisobot, alertlar
  Pro   (299 000)  — + yunit-iqtisodiyot, FBS yorliqlar, qaytarish tahlili

Sinov (3 kun) — **Pro** darajasida. Seller to'liq qiymatni ko'rsin,
keyin o'zi tanlasin. Cheklangan sinov qiymatni yashiradi va sotmaydi.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import session_scope, utcnow
from app.db.models import (
    Payment,
    PaymentMethod,
    PaymentStatus,
    Plan,
    Shop,
    Subscription,
    SubscriptionStatus,
    User,
)

log = get_logger(__name__)


class Feature(str, enum.Enum):
    """Cheklanadigan bo'limlar."""

    LOST_MONEY = "lost_money"
    STOCK = "stock"
    REPORTS = "reports"
    ECONOMICS = "economics"
    FBS_LABELS = "fbs_labels"
    RETURNS_ANALYSIS = "returns_analysis"


BASIC_FEATURES = frozenset(
    {Feature.LOST_MONEY, Feature.STOCK, Feature.REPORTS}
)
PRO_FEATURES = frozenset(Feature)  # hammasi

PLAN_FEATURES: dict[Plan, frozenset[Feature]] = {
    Plan.TRIAL: frozenset(),   # muddati tugagan — kirish yopiq
    Plan.BASIC: BASIC_FEATURES,
    Plan.PRO: PRO_FEATURES,
}


@dataclass(frozen=True, slots=True)
class Access:
    """Foydalanuvchining hozirgi holati."""

    is_active: bool
    plan: Plan
    days_left: int
    on_trial: bool
    # Obuna umuman boshlanganmi. `False` — do'kon hali ulanmagan, ya'ni
    # "muddat tugadi" emas, "hali boshlanmagan".
    has_subscription: bool = True

    def can(self, feature: Feature) -> bool:
        if not self.is_active:
            return False
        return feature in PLAN_FEATURES.get(self.plan, frozenset())


NO_ACCESS = Access(
    is_active=False,
    plan=Plan.TRIAL,
    days_left=0,
    on_trial=False,
    has_subscription=False,
)


async def get_access(telegram_id: int) -> Access:
    """Foydalanuvchining kirish huquqi."""
    now = utcnow()
    async with session_scope() as session:
        sub = await session.scalar(
            select(Subscription).join(User).where(User.telegram_id == telegram_id)
        )
        if sub is None:
            return NO_ACCESS

        active = sub.is_active_at(now)
        plan = sub.effective_plan(now)
        deadline = sub.paid_until or sub.trial_ends_at
        days = max((deadline - now).days, 0) if deadline else 0
        on_trial = (
            sub.paid_until is None
            or (sub.trial_ends_at is not None and sub.trial_ends_at > now
                and sub.paid_until <= now)
        )
        return Access(
            is_active=active, plan=plan, days_left=days, on_trial=bool(on_trial)
        )


def price_for(plan: Plan) -> int:
    settings = get_settings()
    return settings.price_pro if plan is Plan.PRO else settings.price_basic


async def create_payment(
    telegram_id: int,
    plan: Plan,
    method: PaymentMethod,
    *,
    months: int = 1,
    external_id: str | None = None,
    note: str | None = None,
) -> int | None:
    """To'lov yozuvini yaratadi (hali tasdiqlanmagan). ID qaytaradi."""
    async with session_scope() as session:
        user = await session.scalar(
            select(User).where(User.telegram_id == telegram_id)
        )
        if user is None:
            return None

        payment = Payment(
            user_id=user.id,
            plan=plan,
            amount=price_for(plan) * months,
            months=months,
            method=method,
            status=PaymentStatus.PENDING,
            external_id=external_id,
            note=note,
        )
        session.add(payment)
        await session.flush()
        return payment.id


async def confirm_payment(payment_id: int, *, admin_id: int | None = None) -> bool:
    """To'lovni tasdiqlaydi va obunani uzaytiradi.

    Takroriy tasdiqlash muddatni ikki marta uzaytirmasligi kerak —
    shuning uchun allaqachon to'langan yozuv qaytarilmaydi.
    """
    now = utcnow()
    async with session_scope() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None or payment.status is PaymentStatus.PAID:
            return False

        sub = await session.scalar(
            select(Subscription).where(Subscription.user_id == payment.user_id)
        )
        if sub is None:
            sub = Subscription(user_id=payment.user_id)
            session.add(sub)

        # Muddat amal qilayotgan bo'lsa — ustiga qo'shamiz, aks holda bugundan
        start = sub.paid_until if (sub.paid_until and sub.paid_until > now) else now
        sub.paid_until = start + timedelta(days=30 * payment.months)
        sub.plan = payment.plan
        sub.status = SubscriptionStatus.ACTIVE

        payment.status = PaymentStatus.PAID
        payment.paid_at = now
        payment.confirmed_by = admin_id

    log.info(
        "To'lov tasdiqlandi: payment_id=%s plan=%s admin=%s",
        payment_id,
        payment.plan.value,
        admin_id,
    )
    return True


async def reject_payment(payment_id: int, *, admin_id: int | None = None) -> bool:
    async with session_scope() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None or payment.status is not PaymentStatus.PENDING:
            return False
        payment.status = PaymentStatus.REJECTED
        payment.confirmed_by = admin_id
    return True


async def pending_payments() -> list[tuple[int, int, str, int]]:
    """Tasdiq kutayotgan to'lovlar: `(payment_id, telegram_id, tarif, summa)`."""
    async with session_scope() as session:
        rows = await session.execute(
            select(Payment, User)
            .join(User, Payment.user_id == User.id)
            .where(Payment.status == PaymentStatus.PENDING)
            .order_by(Payment.id)
        )
        return [
            (p.id, u.telegram_id, p.plan.value, int(p.amount)) for p, u in rows
        ]


async def is_admin(telegram_id: int) -> bool:
    """Admin huquqi: bazadagi belgi yoki `.env` ro'yxati.

    Baza asosiy manba — birinchi foydalanuvchi avtomatik admin bo'ladi.
    `.env` esa zaxira: baza yo'qolsa ham egasi kira olsin.
    """
    if telegram_id in set(get_settings().admin_ids):
        return True
    async with session_scope() as session:
        flag = await session.scalar(
            select(User.is_admin).where(User.telegram_id == telegram_id)
        )
        return bool(flag)


async def admin_ids() -> list[int]:
    """Xabar yuborish uchun barcha adminlar (baza + `.env`)."""
    ids = set(get_settings().admin_ids)
    async with session_scope() as session:
        rows = await session.scalars(
            select(User.telegram_id).where(User.is_admin.is_(True))
        )
        ids.update(rows)
    return sorted(ids)


async def grant_admin(telegram_id: int) -> bool:
    """Foydalanuvchiga admin huquqini beradi."""
    async with session_scope() as session:
        user = await session.scalar(
            select(User).where(User.telegram_id == telegram_id)
        )
        if user is None:
            return False
        user.is_admin = True
    log.info("Admin huquqi berildi: tg_id=%s", telegram_id)
    return True


async def revoke_admin(telegram_id: int) -> bool:
    """Admin huquqini olib tashlaydi.

    Oxirgi adminni o'chirib bo'lmaydi — aks holda botni boshqarish
    imkoni yo'qoladi.
    """
    async with session_scope() as session:
        count = await session.scalar(
            select(func.count()).select_from(User).where(User.is_admin.is_(True))
        )
        if (count or 0) <= 1:
            return False
        user = await session.scalar(
            select(User).where(User.telegram_id == telegram_id)
        )
        if user is None or not user.is_admin:
            return False
        user.is_admin = False
    return True


async def user_stats() -> dict[str, int]:
    """Admin paneli uchun umumiy raqamlar."""
    now = utcnow()
    async with session_scope() as session:
        total = await session.scalar(select(func.count()).select_from(User)) or 0
        connected = (
            await session.scalar(select(func.count()).select_from(Shop)) or 0
        )
        subs = list(await session.scalars(select(Subscription)))

    active = sum(1 for s in subs if s.is_active_at(now))
    paying = sum(1 for s in subs if s.paid_until and s.paid_until > now)
    return {
        "users": total,
        "shops": connected,
        "active": active,
        "paying": paying,
        "trial": active - paying,
    }


async def recent_users(limit: int = 20) -> list[dict[str, object]]:
    """Oxirgi ro'yxatdan o'tgan foydalanuvchilar — admin paneli uchun."""
    now = utcnow()
    async with session_scope() as session:
        users = list(
            await session.scalars(
                select(User).order_by(User.id.desc()).limit(limit)
            )
        )
        result: list[dict[str, object]] = []
        for user in users:
            shops = (
                await session.scalar(
                    select(func.count())
                    .select_from(Shop)
                    .where(Shop.user_id == user.id)
                )
                or 0
            )
            sub = await session.scalar(
                select(Subscription).where(Subscription.user_id == user.id)
            )
            if sub is None:
                status = "obunasiz"
            elif sub.paid_until and sub.paid_until > now:
                status = f"{sub.plan.value} · {(sub.paid_until - now).days} kun"
            elif sub.is_active_at(now):
                status = "sinov"
            else:
                status = "tugagan"

            result.append(
                {
                    "telegram_id": user.telegram_id,
                    "name": user.full_name or user.username,
                    "is_admin": user.is_admin,
                    "shops": shops,
                    "status": status,
                }
            )
    return result


async def user_telegram_id(payment_id: int) -> int | None:
    async with session_scope() as session:
        row = await session.execute(
            select(User.telegram_id)
            .join(Payment, Payment.user_id == User.id)
            .where(Payment.id == payment_id)
        )
        return row.scalar_one_or_none()
