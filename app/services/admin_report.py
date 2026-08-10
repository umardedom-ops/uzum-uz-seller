"""Biznes hisoboti — kim obuna bo'lgan, qaysi kod orqali, to'lovi qanday.

Admin uchun yagona manzara: obunachilar, to'lovlar (tasdiqlangan yoki
yo'q), promokodlar va umumiy pul hisobi. Excel'ga chiqariladi va
xohlasa Google Sheets'ga yuklanadi.

Bu yerda faqat O'QISH — hisobot hech narsani o'zgartirmaydi.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from app.db.base import session_scope, utcnow
from app.db.models import (
    Payment,
    PaymentStatus,
    PromoCode,
    PromoRedemption,
    Shop,
    Subscription,
    User,
)


def _fmt(moment: datetime | None) -> str:
    return moment.strftime("%Y-%m-%d %H:%M") if moment else ""


@dataclass(frozen=True, slots=True)
class SubscriberRow:
    telegram_id: int
    username: str
    full_name: str
    phone: str
    shops: str
    plan: str
    status: str
    trial_ends: str
    paid_until: str
    days_left: int
    promo_codes: str
    registered: str


@dataclass(frozen=True, slots=True)
class PaymentRow:
    payment_id: int
    telegram_id: int
    plan: str
    amount: Decimal
    months: int
    method: str
    status: str
    external_id: str
    created: str
    paid_at: str


@dataclass(frozen=True, slots=True)
class PromoRow:
    code: str
    plan: str
    days: int
    used: int
    max_uses: str
    is_active: bool
    expires: str
    created_by: str
    note: str


@dataclass(slots=True)
class Summary:
    users: int = 0
    with_shop: int = 0
    active_subs: int = 0
    by_plan: dict[str, int] = field(default_factory=dict)
    paid_total: Decimal = Decimal("0")
    pending_total: Decimal = Decimal("0")
    rejected_total: Decimal = Decimal("0")
    paid_count: int = 0
    pending_count: int = 0
    promo_granted: int = 0


@dataclass(frozen=True, slots=True)
class BusinessReport:
    subscribers: list[SubscriberRow]
    payments: list[PaymentRow]
    promos: list[PromoRow]
    summary: Summary
    generated_at: datetime


async def collect() -> BusinessReport:
    """Butun biznes manzarasini bitta so'rovda yig'adi."""
    now = utcnow()

    async with session_scope() as session:
        users = list(await session.scalars(select(User).order_by(User.id)))
        subs = {
            s.user_id: s for s in await session.scalars(select(Subscription))
        }
        shops_by_user: dict[int, list[str]] = {}
        for shop in await session.scalars(select(Shop)):
            shops_by_user.setdefault(shop.user_id, []).append(
                shop.title or shop.uzum_shop_id
            )

        promos = list(await session.scalars(select(PromoCode).order_by(PromoCode.id)))
        promo_by_id = {p.id: p for p in promos}
        redemptions = list(await session.scalars(select(PromoRedemption)))
        codes_by_user: dict[int, list[str]] = {}
        for red in redemptions:
            promo = promo_by_id.get(red.promo_id)
            if promo is not None:
                codes_by_user.setdefault(red.user_id, []).append(promo.code)

        payments = list(await session.scalars(select(Payment).order_by(Payment.id)))
        user_tg = {u.id: u.telegram_id for u in users}

    # --- Obunachilar ---
    subscribers: list[SubscriberRow] = []
    summary = Summary(users=len(users))

    for user in users:
        sub = subs.get(user.id)
        shops = shops_by_user.get(user.id, [])
        if shops:
            summary.with_shop += 1

        plan_name, status, trial, paid_until, days = "—", "yo'q", "", "", 0
        if sub is not None:
            plan = sub.effective_plan(now)
            plan_name = plan.value
            status = sub.status.value
            trial = _fmt(sub.trial_ends_at)
            paid_until = _fmt(sub.paid_until)
            deadline = sub.paid_until or sub.trial_ends_at
            days = max((deadline - now).days, 0) if deadline else 0
            if sub.is_active_at(now):
                summary.active_subs += 1
                summary.by_plan[plan_name] = summary.by_plan.get(plan_name, 0) + 1

        codes = codes_by_user.get(user.id, [])
        if codes:
            summary.promo_granted += 1

        subscribers.append(
            SubscriberRow(
                telegram_id=user.telegram_id,
                username=f"@{user.username}" if user.username else "",
                full_name=user.full_name or "",
                phone=user.phone or "",
                shops=", ".join(shops),
                plan=plan_name,
                status=status,
                trial_ends=trial,
                paid_until=paid_until,
                days_left=days,
                promo_codes=", ".join(codes),
                registered=_fmt(user.created_at),
            )
        )

    # --- To'lovlar ---
    payment_rows: list[PaymentRow] = []
    for pay in payments:
        amount = Decimal(pay.amount)
        if pay.status is PaymentStatus.PAID:
            summary.paid_total += amount
            summary.paid_count += 1
        elif pay.status is PaymentStatus.PENDING:
            summary.pending_total += amount
            summary.pending_count += 1
        else:
            summary.rejected_total += amount

        payment_rows.append(
            PaymentRow(
                payment_id=pay.id,
                telegram_id=user_tg.get(pay.user_id, 0),
                plan=pay.plan.value,
                amount=amount,
                months=pay.months,
                method=pay.method.value,
                status=pay.status.value,
                external_id=pay.external_id or "",
                created=_fmt(pay.created_at),
                paid_at=_fmt(pay.paid_at),
            )
        )

    # --- Promokodlar ---
    promo_rows = [
        PromoRow(
            code=p.code,
            plan=p.plan.value,
            days=p.days,
            used=p.used_count,
            max_uses="∞" if not p.max_uses else str(p.max_uses),
            is_active=p.is_active,
            expires=_fmt(p.expires_at),
            created_by=str(p.created_by or ""),
            note=p.note or "",
        )
        for p in promos
    ]

    return BusinessReport(
        subscribers=subscribers,
        payments=payment_rows,
        promos=promo_rows,
        summary=summary,
        generated_at=now,
    )
