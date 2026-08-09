"""Qoldiq o'zgartirish servisi — bot oqimi va Uzum yozish klienti orasida.

Vazifasi:
  - tahrirlanadigan SKU ro'yxatini berish (`list_editable_items`),
  - bitta SKU holatini olish (`get_item`),
  - o'zgarishni qo'llash va **har amalni jurnalga yozish** (`apply_change`),
  - bekor qilinganda ham iz qoldirish (`log_cancelled`).

Xavfsizlik: jonli yozish `UzumWriteClient` orqali, u esa
`settings.uzum_writes_enabled` bayrog'iga bog'liq. Bayroq o'chiq bo'lsa
amal DEMO sifatida jurnalга tushadi — foydalanuvchiga "hali jonli emas"
deb aytiladi, lekin oqim to'liq ishlaydi (CLAUDE.md qoida #1).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import session_scope
from app.db.models import AuthType, Shop, ShopCredential, StockWriteLog, StockWriteStatus
from app.services.exports import load_stock_rows
from app.uzum.base import UzumHTTP
from app.uzum.models import AuthType as ClientAuthType
from app.uzum.models import SessionCredentials
from app.uzum.writes import StockUpdate, UzumWriteClient, WritesDisabledError

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StockEditItem:
    """Tahrir uchun bitta SKU: joriy FBS qoldig'i bilan."""

    sku: str
    title: str
    current_qty: int


@dataclass(frozen=True, slots=True)
class WriteOutcome:
    """Yozish natijasi — handler shuni foydalanuvchiga aytadi."""

    status: StockWriteStatus
    applied_live: bool
    error: str | None = None


async def list_editable_items(shop_id: int) -> list[StockEditItem]:
    """Do'kondagi SKU'lar (joriy FBS qoldig'i bilan), nomi bo'yicha."""
    rows = await load_stock_rows(shop_id)
    items = [
        StockEditItem(sku=r.sku, title=r.title, current_qty=r.fbs_qty) for r in rows
    ]
    items.sort(key=lambda i: i.title.lower())
    return items


async def get_item(shop_id: int, sku: str) -> StockEditItem | None:
    """Bitta SKU holati (tasdiq ekrani uchun eski qiymatni olish)."""
    for item in await list_editable_items(shop_id):
        if item.sku == sku:
            return item
    return None


async def apply_change(
    shop_id: int,
    *,
    telegram_id: int,
    sku: str,
    old_qty: int | None,
    new_qty: int,
) -> WriteOutcome:
    """Qoldiqni yangilashga urinadi va natijani jurnalga yozadi.

    Bayroq o'chiq → DEMO (jonli yozilmaydi). Uzum xato bersa → FAILED,
    sabab jurnalда va foydalanuvchiga ko'rinadi (xato jim yutilmaydi).
    """
    outcome = await _do_write(shop_id, sku=sku, new_qty=new_qty)
    await _record(
        shop_id,
        telegram_id=telegram_id,
        sku=sku,
        old_qty=old_qty,
        new_qty=new_qty,
        status=outcome.status,
        error=outcome.error,
    )
    return outcome


async def log_cancelled(
    shop_id: int,
    *,
    telegram_id: int,
    sku: str,
    old_qty: int | None,
    new_qty: int,
) -> None:
    """Foydalanuvchi tasdiq ekranida bekor qildi — iz qoldiramiz."""
    await _record(
        shop_id,
        telegram_id=telegram_id,
        sku=sku,
        old_qty=old_qty,
        new_qty=new_qty,
        status=StockWriteStatus.CANCELLED,
        error=None,
    )


# --------------------------------------------------------------------------- #
# Ichki
# --------------------------------------------------------------------------- #


async def _do_write(shop_id: int, *, sku: str, new_qty: int) -> WriteOutcome:
    built = await _write_client_for(shop_id)
    if built is None:
        return WriteOutcome(
            status=StockWriteStatus.FAILED,
            applied_live=False,
            error="Do'kon yoki API kaliti topilmadi",
        )
    http, client, uzum_shop_id = built

    try:
        await client.set_fbs_stock(
            uzum_shop_id, [StockUpdate(sku_id=sku, amount=new_qty)]
        )
    except WritesDisabledError:
        # Himoya bayrog'i o'chiq — bu xato emas, demo
        return WriteOutcome(status=StockWriteStatus.DEMO, applied_live=False)
    except Exception as exc:  # sababni jurnalga va foydalanuvchiga qaytaramiz
        log.exception("Qoldiq yozishda xato: shop=%s sku=%s", shop_id, sku)
        return WriteOutcome(
            status=StockWriteStatus.FAILED, applied_live=False, error=str(exc)
        )
    finally:
        await http.aclose()

    return WriteOutcome(status=StockWriteStatus.APPLIED, applied_live=True)


async def _write_client_for(
    shop_id: int,
) -> tuple[UzumHTTP, UzumWriteClient, str] | None:
    """Yozish klienti quradi (kalit bazadan, shifri ochiladi)."""
    async with session_scope() as session:
        shop = await session.get(Shop, shop_id)
        if shop is None or not shop.is_active:
            return None
        cred = await session.scalar(
            select(ShopCredential).where(
                ShopCredential.shop_id == shop_id,
                ShopCredential.auth_type == AuthType.API,
                ShopCredential.is_valid.is_(True),
            )
        )
        if cred is None:
            return None
        secret = cred.secret
        uzum_shop_id = shop.uzum_shop_id

    settings = get_settings()
    http = UzumHTTP(
        settings.uzum_api_base, rate_limit_per_sec=settings.uzum_rate_limit_per_sec
    )
    client = UzumWriteClient(
        http, SessionCredentials(auth_type=ClientAuthType.API, secret=secret)
    )
    return http, client, uzum_shop_id


async def _record(
    shop_id: int,
    *,
    telegram_id: int,
    sku: str,
    old_qty: int | None,
    new_qty: int,
    status: StockWriteStatus,
    error: str | None,
) -> None:
    async with session_scope() as session:
        session.add(
            StockWriteLog(
                shop_id=shop_id,
                telegram_id=telegram_id,
                sku=sku,
                old_qty=old_qty,
                new_qty=new_qty,
                status=status,
                error=error,
            )
        )
