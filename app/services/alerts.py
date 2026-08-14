"""Xabarnomalar — jim yo'qotishlarning oldini olish.

Raqobatchida bu funksiyalar yo'q. Uchalasi ham **o'qish** orqali
ishlaydi — sellerning do'koniga hech narsa yozilmaydi.

  * SKU bloklandi     — sotuv to'xtaydi, seller bilmaydi
  * Qoldiq tugayapti  — tugagan tovar = yo'qotilgan sotuv
  * Rank pasaydi      — qidiruvdagi o'rin tushsa, sotuv qulaydi
                        (Avtobidder o'rniga xavfsiz signal)
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import session_scope
from app.db.models import (
    AlertConfig,
    AlertType,
    Product,
    Shop,
    StockSnapshot,
    Subscription,
    User,
    shop_has_valid_key,
)

log = get_logger(__name__)

# Rank tartibi: A eng yaxshi. Pastga tushish — yomon signal.
RANK_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}

# Qoldiq shu kundan kam qolsa ogohlantiramiz
LOW_STOCK_DAYS = 7


@dataclass(frozen=True, slots=True)
class Alert:
    kind: str          # blocked | low_stock | rank_drop
    sku: str
    title: str
    message: str


def _rank_dropped(prev: str | None, current: str | None) -> bool:
    if not prev or not current or prev == current:
        return False
    return RANK_ORDER.get(current, 99) > RANK_ORDER.get(prev, 99)


async def collect_alerts(shop_id: int) -> list[Alert]:
    """Do'kon bo'yicha e'tibor talab qiladigan holatlar."""
    async with session_scope() as session:
        products = list(
            await session.scalars(select(Product).where(Product.shop_id == shop_id))
        )

        last_day = await session.scalar(
            select(StockSnapshot.captured_on)
            .where(StockSnapshot.shop_id == shop_id)
            .order_by(StockSnapshot.captured_on.desc())
            .limit(1)
        )
        stock: dict[str, int] = {}
        if last_day is not None:
            rows = await session.scalars(
                select(StockSnapshot).where(
                    StockSnapshot.shop_id == shop_id,
                    StockSnapshot.captured_on == last_day,
                )
            )
            for row in rows:
                stock[row.sku] = stock.get(row.sku, 0) + row.qty

    alerts: list[Alert] = []
    for product in products:
        title = product.title or product.sku

        if product.is_blocked:
            reason = product.block_reason or "sabab ko'rsatilmagan"
            alerts.append(
                Alert(
                    "blocked",
                    product.sku,
                    title,
                    f"🚫 <b>Tovar bloklangan — sotuv to'xtagan!</b>\n\n"
                    f"{title}\nSabab: {reason}\n\n"
                    f"Kabinetda tekshiring — har kun yo'qotilgan sotuv.",
                )
            )

        qty = stock.get(product.sku, 0)
        speed = product.avg_daily_sales or Decimal("0")
        if qty > 0 and speed > 0:
            days = int(Decimal(qty) / speed)
            if days <= LOW_STOCK_DAYS:
                alerts.append(
                    Alert(
                        "low_stock",
                        product.sku,
                        title,
                        f"⏳ <b>Qoldiq tugayapti</b>\n\n"
                        f"{title}\nQoldiq: {qty} dona — taxminan {days} kunga yetadi.\n"
                        f"Kunlik o'rtacha sotuv: {speed}",
                    )
                )

        if _rank_dropped(product.prev_rank, product.rank):
            alerts.append(
                Alert(
                    "rank_drop",
                    product.sku,
                    title,
                    f"📉 <b>Qidiruvdagi o'rin pasaydi</b>\n\n"
                    f"{title}\nRank: {product.prev_rank} → <b>{product.rank}</b>\n\n"
                    f"Sotuv kamayishi mumkin. Narx, reklama va sharhlarni "
                    f"tekshiring.",
                )
            )

    return alerts


async def send_alerts() -> int:
    """Barcha faol obunachilarga xabarnomalarni yuboradi.

    Bittasining xatosi qolganlarni to'xtatmaydi.
    """
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from app.db.base import utcnow

    settings = get_settings()

    async with session_scope() as session:
        rows = await session.execute(
            select(Shop, User, Subscription)
            .join(User, Shop.user_id == User.id)
            .outerjoin(Subscription, Subscription.user_id == User.id)
            .where(
                Shop.is_active.is_(True),
                User.is_blocked.is_(False),
                # Kalitsiz do'kon — uzilgan do'kon. Bazadagi eski ma'lumot
                # asosida xabar yubormaymiz.
                shop_has_valid_key(),
            )
        )
        targets = [
            (shop.id, user.telegram_id)
            for shop, user, sub in rows
            if sub is not None and sub.is_active_at(utcnow())
        ]

    if not targets:
        return 0

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    sent = 0
    try:
        for shop_id, telegram_id in targets:
            try:
                for alert in await collect_alerts(shop_id):
                    await bot.send_message(telegram_id, alert.message)
                    sent += 1
            except Exception:
                log.exception("Xabarnoma yuborilmadi: shop_id=%s", shop_id)
    finally:
        await bot.session.close()

    log.info("Xabarnomalar yuborildi: %s ta", sent)
    return sent


# ---------------------------------------------------------------------- #
# Sozlamalar — seller qaysi xabarnomalarni olishini tanlaydi
# ---------------------------------------------------------------------- #

#: Seller boshqara oladigan turlar. Qolganlari (masalan NEW_ORDER)
#: hozircha yuborilmaydi — ro'yxatda ko'rsatib chalg'itmaymiz.
TOGGLEABLE = (
    AlertType.DAILY_REPORT,
    AlertType.NEW_DISCREPANCY,
    AlertType.LOW_STOCK,
    AlertType.SKU_BLOCKED,
)

#: Yozuv yo'q bo'lsa xabarnoma YOQILGAN hisoblanadi — seller o'zi
#: o'chirmaguncha qiymatni ko'rsin.
_DEFAULT_ENABLED = True


async def alert_settings(shop_id: int) -> dict[AlertType, bool]:
    """Do'kon bo'yicha har bir turning holati."""
    async with session_scope() as session:
        rows = await session.scalars(
            select(AlertConfig).where(AlertConfig.shop_id == shop_id)
        )
        saved = {r.alert_type: r.enabled for r in rows}
    return {kind: saved.get(kind, _DEFAULT_ENABLED) for kind in TOGGLEABLE}


async def toggle_alert(shop_id: int, kind: AlertType) -> bool:
    """Xabarnomani yoqadi/o'chiradi va yangi holatini qaytaradi."""
    async with session_scope() as session:
        row = await session.scalar(
            select(AlertConfig).where(
                AlertConfig.shop_id == shop_id, AlertConfig.alert_type == kind
            )
        )
        if row is None:
            # Birinchi marta — standart yoqilgan edi, demak o'chiramiz
            row = AlertConfig(shop_id=shop_id, alert_type=kind, enabled=False)
            session.add(row)
            return False

        row.enabled = not row.enabled
        return row.enabled


async def is_enabled(shop_id: int, kind: AlertType) -> bool:
    """Shu turdagi xabarnoma yoqilganmi."""
    async with session_scope() as session:
        row = await session.scalar(
            select(AlertConfig).where(
                AlertConfig.shop_id == shop_id, AlertConfig.alert_type == kind
            )
        )
    return _DEFAULT_ENABLED if row is None else row.enabled
