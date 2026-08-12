"""Hujjatlar uchun ma'lumot tayyorlash.

`discrepancies` + `products` → `ReportRow`. Excel va pretenziya shu
qatorlardan quriladi.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.db.base import session_scope
from app.db.models import (
    Discrepancy,
    DiscrepancyKind,
    DiscrepancyStatus,
    Product,
    Shop,
    ShopStaff,
    StockSnapshot,
    User,
)
from app.docs.models import ReportRow
from app.docs.stock import StockRow


async def find_user_shop(telegram_id: int) -> Shop | None:
    """Joriy do'kon — o'ziniki yoki hodim sifatida biriktirilgani.

    Tanlangan do'kon (`User.active_shop_id`) hali kirish huquqida bo'lsa
    o'sha qaytadi; aks holda birinchi mavjud do'kon. Shu tufayli barcha
    handlerlar to'g'ri do'kon bilan avtomatik ishlaydi.
    """
    shops = await list_user_shops(telegram_id)
    if not shops:
        return None

    async with session_scope() as session:
        active_id = await session.scalar(
            select(User.active_shop_id).where(User.telegram_id == telegram_id)
        )

    if active_id is not None:
        for shop in shops:
            if shop.id == active_id:
                return shop

    return shops[0]


async def list_user_shops(telegram_id: int) -> list[Shop]:
    """Ko'ra oladigan barcha do'konlar: **o'ziniki + hodim sifatida**.

    Hodim biriktirilgan do'konni xuddi o'zinikidek tanlay oladi, lekin
    to'lov/tarif/hodim boshqaruvi unga ochilmaydi (`services/team.py`).
    """
    async with session_scope() as session:
        own = list(
            await session.scalars(
                select(Shop)
                .join(User, Shop.user_id == User.id)
                .where(User.telegram_id == telegram_id, Shop.is_active.is_(True))
                .order_by(Shop.id)
            )
        )
        staff = list(
            await session.scalars(
                select(Shop)
                .join(ShopStaff, ShopStaff.shop_id == Shop.id)
                .where(
                    ShopStaff.telegram_id == telegram_id,
                    ShopStaff.is_active.is_(True),
                    Shop.is_active.is_(True),
                )
                .order_by(Shop.id)
            )
        )

    seen = {shop.id for shop in own}
    return own + [shop for shop in staff if shop.id not in seen]


async def set_active_shop(telegram_id: int, shop_id: int) -> Shop | None:
    """Joriy do'konni o'zgartiradi.

    Kirish huquqi tekshiriladi: do'kon o'ziniki yoki hodim sifatida
    biriktirilgan bo'lishi shart. Begonasi — None (rad etiladi).
    """
    allowed = {shop.id: shop for shop in await list_user_shops(telegram_id)}
    shop = allowed.get(shop_id)
    if shop is None:
        return None

    async with session_scope() as session:
        user = await session.scalar(
            select(User).where(User.telegram_id == telegram_id)
        )
        if user is None:
            return None
        user.active_shop_id = shop.id

    return shop


async def history_range(shop_id: int) -> tuple[date | None, date | None]:
    """Qoldiq tarixi qaysi sanadan qaysi sanagacha mavjud.

    5.1 auditi ikkita nuqtani taqqoslaydi — shu oraliqdan tashqarida
    hisoblab bo'lmaydi. Foydalanuvchiga chegara ochiq ko'rsatiladi.
    """
    async with session_scope() as session:
        first = await session.scalar(
            select(StockSnapshot.captured_on)
            .where(StockSnapshot.shop_id == shop_id)
            .order_by(StockSnapshot.captured_on)
            .limit(1)
        )
        last = await session.scalar(
            select(StockSnapshot.captured_on)
            .where(StockSnapshot.shop_id == shop_id)
            .order_by(StockSnapshot.captured_on.desc())
            .limit(1)
        )
    return first, last


async def load_report_rows(
    shop_id: int,
    *,
    only_claimable: bool = True,
    period_from: date | None = None,
    period_to: date | None = None,
) -> list[ReportRow]:
    """Da'vo qilinadigan farqlarni hujjat qatorlariga aylantiradi."""
    async with session_scope() as session:
        query = select(Discrepancy).where(Discrepancy.shop_id == shop_id)
        if only_claimable:
            query = query.where(Discrepancy.status == DiscrepancyStatus.NEW)
        if period_from is not None:
            query = query.where(Discrepancy.period_to >= period_from)
        if period_to is not None:
            query = query.where(Discrepancy.period_from <= period_to)
        findings = list(
            await session.scalars(query.order_by(Discrepancy.amount.desc()))
        )
        if not findings:
            return []

        products = {
            p.sku: p
            for p in await session.scalars(
                select(Product).where(Product.shop_id == shop_id)
            )
        }

    rows: list[ReportRow] = []
    for item in findings:
        product = products.get(item.sku)
        expected, actual = _quantities(item)
        rows.append(
            ReportRow(
                sku=item.sku,
                barcode=(product.barcode if product else "") or "",
                title=(product.title if product else "") or item.sku,
                period_from=item.period_from,
                period_to=item.period_to,
                expected_qty=expected,
                actual_qty=actual,
                diff_qty=item.qty,
                unit_cost=(product.cost_price if product else None) or Decimal("0"),
                loss_amount=item.amount or Decimal("0"),
                kind=item.kind,
                detected_at=(item.detected_at.date() if item.detected_at else date.today()),
            )
        )
    return rows


async def load_stock_rows(shop_id: int) -> list[StockRow]:
    """Qoldiq hisoboti qatorlari.

    Eng oxirgi surat + mahsulot kartochkasidagi ma'lumot. Diqqat talab
    qiladiganlar (bloklangan, tugagan, tugayotgan) yuqorida turadi.
    """
    async with session_scope() as session:
        last_day = await session.scalar(
            select(StockSnapshot.captured_on)
            .where(StockSnapshot.shop_id == shop_id)
            .order_by(StockSnapshot.captured_on.desc())
            .limit(1)
        )
        snapshots = (
            list(
                await session.scalars(
                    select(StockSnapshot).where(
                        StockSnapshot.shop_id == shop_id,
                        StockSnapshot.captured_on == last_day,
                    )
                )
            )
            if last_day
            else []
        )
        products = {
            p.sku: p
            for p in await session.scalars(
                select(Product).where(Product.shop_id == shop_id)
            )
        }

    by_sku: dict[str, dict[str, int]] = defaultdict(lambda: {"FBO": 0, "FBS": 0})
    for snap in snapshots:
        by_sku[snap.sku][snap.warehouse] = snap.qty

    # Suratsiz mahsulotlar ham ko'rinsin (qoldiq 0 deb)
    for sku in products:
        by_sku.setdefault(sku, {"FBO": 0, "FBS": 0})

    rows = [
        StockRow(
            sku=sku,
            barcode=(products[sku].barcode if sku in products else "") or "",
            title=(products[sku].title if sku in products else "") or sku,
            fbo_qty=qty.get("FBO", 0),
            fbs_qty=qty.get("FBS", 0),
            sold_total=(products[sku].qty_sold_total if sku in products else 0) or 0,
            avg_daily_sales=products[sku].avg_daily_sales if sku in products else None,
            price=products[sku].sale_price if sku in products else None,
            status=products[sku].status if sku in products else None,
            is_blocked=bool(products[sku].is_blocked) if sku in products else False,
            block_reason=products[sku].block_reason if sku in products else None,
            forecast_days=(
                products[sku].forecast_out_of_stock if sku in products else None
            ),
            # Ombor xodimi Uzum SKU sini emas, o'z artikulini biladi.
            # `sellerItemCode` afzal; bo'lmasa `article`.
            article=(
                (products[sku].seller_item_code or products[sku].article or "")
                if sku in products
                else ""
            ),
            market_price=(
                products[sku].market_price if sku in products else None
            ),
        )
        for sku, qty in by_sku.items()
    ]
    # Diqqat talab qiladiganlar birinchi, keyin qoldig'i kamlari
    rows.sort(key=lambda r: (not r.needs_attention, r.total_qty))
    return rows


def _quantities(item: Discrepancy) -> tuple[int, int]:
    """Excel ustunlari uchun kutilgan/haqiqiy miqdor.

    Faqat 5.1 (yo'qolgan tovar) auditida qoldiq tushunchasi bor; qolgan
    turlarda 0 qo'yiladi — soxta raqam ko'rsatmaymiz.
    """
    if item.kind is DiscrepancyKind.LOST_STOCK:
        return item.qty, 0
    return 0, 0
