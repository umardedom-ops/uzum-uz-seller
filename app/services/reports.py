"""Kunlik hisobot va xabarnomalar (SPEC 7).

Namuna (SPEC 7):

    📊 Kecha, 4-avgust — Royal Home
    Buyurtmalar: 42 ta (+12%)
    Tushum: 6 240 000 so'm
    ...
    💰 Bu oy topilgan yo'qotish: 1 840 000 so'm
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import session_scope
from app.db.models import (
    Discrepancy,
    DiscrepancyStatus,
    Order,
    Return,
    Shop,
    Subscription,
    User,
)
from app.docs.numbers import format_money
from app.services.mappers import CANCELLED_STATUSES

log = get_logger(__name__)

UZ_MONTHS = (
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
)


class DailyStats:
    """Bitta do'konning bir kunlik ko'rsatkichlari."""

    def __init__(self) -> None:
        self.orders = 0
        self.revenue = Decimal("0")
        self.commission = Decimal("0")
        self.delivery = Decimal("0")
        self.returns = 0

    @property
    def net_profit(self) -> Decimal:
        """Sof foyda — tannarxsiz taxminiy (komissiya va logistika chegirilgan)."""
        return self.revenue - self.commission - self.delivery

    @property
    def margin_pct(self) -> Decimal:
        if self.revenue == 0:
            return Decimal("0")
        return (self.net_profit / self.revenue * 100).quantize(Decimal("1"))


async def collect_daily_stats(shop_id: int, day: date) -> DailyStats:
    stats = DailyStats()
    async with session_scope() as session:
        orders = await session.scalars(
            select(Order).where(Order.shop_id == shop_id)
        )
        for row in orders:
            if row.created_at_uzum is None or row.created_at_uzum.date() != day:
                continue
            if (row.status or "").upper() in CANCELLED_STATUSES:
                continue
            stats.orders += 1
            if row.price is not None:
                stats.revenue += row.price * row.qty
            stats.commission += row.commission_amount or Decimal("0")
            stats.delivery += row.delivery_amount or Decimal("0")

        returns = await session.scalars(
            select(Return).where(Return.shop_id == shop_id)
        )
        for row in returns:
            if row.returned_at is not None and row.returned_at.date() == day:
                stats.returns += 1

    return stats


async def month_losses(shop_id: int, today: date) -> Decimal:
    """Shu oyda topilgan, da'vo qilish mumkin bo'lgan yo'qotish."""
    month_start = today.replace(day=1)
    async with session_scope() as session:
        rows = await session.scalars(
            select(Discrepancy).where(
                Discrepancy.shop_id == shop_id,
                Discrepancy.status == DiscrepancyStatus.NEW,
            )
        )
        total = Decimal("0")
        for row in rows:
            if row.detected_at and row.detected_at.date() >= month_start:
                total += row.amount or Decimal("0")
    return total


def render_daily_report(
    shop_title: str,
    day: date,
    stats: DailyStats,
    losses: Decimal,
    prev_orders: int = 0,
) -> str:
    """Kunlik xabar matni (SPEC 7 namunasi bo'yicha)."""
    month = UZ_MONTHS[day.month - 1]
    lines = [
        f"📊 <b>{day.day}-{month}</b> — {shop_title}",
        "",
        f"Buyurtmalar: {stats.orders} ta{_delta(stats.orders, prev_orders)}",
        f"Tushum: {format_money(stats.revenue)} so'm",
        f"Sof foyda: {format_money(stats.net_profit)} so'm "
        f"(marja {stats.margin_pct}%)",
        f"Qaytarishlar: {stats.returns} ta",
    ]
    if losses > 0:
        lines += ["", f"💰 Bu oy topilgan yo'qotish: {format_money(losses)} so'm"]
    return "\n".join(lines)


def _delta(current: int, previous: int) -> str:
    """O'sish/pasayish foizi. Oldingi kun 0 bo'lsa ko'rsatilmaydi."""
    if previous <= 0:
        return ""
    change = round((current - previous) / previous * 100)
    if change == 0:
        return ""
    return f" ({change:+d}%)"


async def send_daily_reports() -> int:
    """Barcha faol obunachilarga kunlik hisobot yuboradi.

    Obunasi tugaganlarga yuborilmaydi — bu to'lovga undovchi omil.
    Bittasining xatosi qolganlarni to'xtatmaydi.
    """
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    settings = get_settings()
    yesterday = date.today() - timedelta(days=1)
    day_before = yesterday - timedelta(days=1)

    async with session_scope() as session:
        rows = await session.execute(
            select(Shop, User, Subscription)
            .join(User, Shop.user_id == User.id)
            .outerjoin(Subscription, Subscription.user_id == User.id)
            .where(Shop.is_active.is_(True), User.is_blocked.is_(False))
        )
        targets = [
            (shop.id, shop.title or shop.uzum_shop_id, user.telegram_id)
            for shop, user, sub in rows
            if sub is not None and sub.is_active_at(_now())
        ]

    if not targets:
        return 0

    # Guruh/kanalga ham yuboriladi — jamoa bilan ishlaydigan seller uchun
    from app.services import team

    channels = await team.channels_for_shops([shop_id for shop_id, _, _ in targets])

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    sent = 0
    try:
        for shop_id, title, telegram_id in targets:
            try:
                stats = await collect_daily_stats(shop_id, yesterday)
                prev = await collect_daily_stats(shop_id, day_before)
                losses = await month_losses(shop_id, yesterday)
                text = render_daily_report(title, yesterday, stats, losses, prev.orders)
                await bot.send_message(telegram_id, text)
                sent += 1
            except Exception:
                log.exception("Kunlik hisobot yuborilmadi: shop_id=%s", shop_id)
                continue

            # Kanalning xatosi (bot chiqarilgan, huquq yo'q) egaga
            # yuborilgan hisobotni bekor qilmasin — alohida try.
            for chat_id in channels.get(shop_id, []):
                try:
                    await bot.send_message(chat_id, text)
                    sent += 1
                except Exception:
                    log.exception(
                        "Kanalga hisobot yuborilmadi: shop=%s chat=%s",
                        shop_id,
                        chat_id,
                    )
    finally:
        await bot.session.close()

    log.info("Kunlik hisobot yuborildi: %s ta", sent)
    return sent


def _now():  # noqa: ANN202
    from app.db.base import utcnow

    return utcnow()


async def losses_by_kind(shop_id: int) -> dict[str, Decimal]:
    """Tur bo'yicha yo'qotishlar — "Yo'qotilgan pul" menyusi uchun."""
    from app.docs.models import KIND_LABELS

    async with session_scope() as session:
        rows = await session.scalars(
            select(Discrepancy).where(
                Discrepancy.shop_id == shop_id,
                Discrepancy.status == DiscrepancyStatus.NEW,
            )
        )
        totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for row in rows:
            label = KIND_LABELS.get(row.kind, row.kind.value)
            totals[label] += row.amount or Decimal("0")
    return dict(totals)
