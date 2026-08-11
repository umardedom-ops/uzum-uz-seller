"""Qaytgan tovarni FBS qoldig'iga qaytarish.

Muammo: mijoz tovarni qaytardi, u omboringizga keldi — lekin Uzumdagi
FBS qoldig'i o'zi ko'paymaydi. Seller qo'lda kiritishi kerak, ko'pincha
unutiladi va tovar sotuvda ko'rinmay qoladi.

Bu modul qaytarishlarni topib, qancha qo'shish kerakligini hisoblaydi va
tasdiqdan keyin yozadi.

Qat'iy qoidalar:
  1. **Faqat qabul qilingan** qaytarish hisobga olinadi (`received_at`).
     Yo'ldagi tovarni qo'shsak, qoldiq soxta ko'payadi.
  2. Har qaytarish **bir marta** qo'shiladi (`restocked_at` belgisi).
  3. Yozish har doim **tasdiq bilan** — avtomatik emas.
  4. Shtrix kodsiz SKU o'tkazib yuboriladi (Uzum uni qabul qilmaydi).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.base import session_scope, utcnow
from app.db.models import Product, Return, StockSnapshot, StockWriteStatus
from app.services.stock_write import apply_change

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RestockItem:
    """Bitta SKU bo'yicha taklif."""

    sku: str
    title: str
    barcode: str
    returned_qty: int
    current_qty: int
    return_ids: tuple[str, ...]

    @property
    def new_qty(self) -> int:
        return self.current_qty + self.returned_qty

    @property
    def label(self) -> str:
        return (
            f"{self.title[:32]} — {self.current_qty} → {self.new_qty} "
            f"(+{self.returned_qty})"
        )


@dataclass(frozen=True, slots=True)
class RestockPlan:
    items: list[RestockItem]
    skipped_no_barcode: int = 0

    @property
    def total_qty(self) -> int:
        return sum(item.returned_qty for item in self.items)

    def __bool__(self) -> bool:
        return bool(self.items)


async def collect_pending(shop_id: int) -> RestockPlan:
    """Qoldiqqa qo'shilmagan qaytarishlarni yig'adi.

    Bir SKU bo'yicha bir nechta qaytarish bo'lsa — birlashtiriladi.
    """
    async with session_scope() as session:
        rows = list(
            await session.scalars(
                select(Return).where(
                    Return.shop_id == shop_id,
                    Return.received_at.is_not(None),   # omborga tushgan
                    Return.restocked_at.is_(None),     # hali qo'shilmagan
                    Return.qty > 0,
                )
            )
        )
        if not rows:
            return RestockPlan(items=[])

        products = {
            p.sku: p
            for p in await session.scalars(
                select(Product).where(Product.shop_id == shop_id)
            )
        }

        # Hozirgi FBS qoldig'i — eng oxirgi suratdan. Product'da bunday
        # maydon yo'q: qoldiq `stock_snapshots` da ombor kesimida turadi.
        last_day = await session.scalar(
            select(StockSnapshot.captured_on)
            .where(StockSnapshot.shop_id == shop_id)
            .order_by(StockSnapshot.captured_on.desc())
            .limit(1)
        )
        fbs_now: dict[str, int] = {}
        if last_day is not None:
            for snap in await session.scalars(
                select(StockSnapshot).where(
                    StockSnapshot.shop_id == shop_id,
                    StockSnapshot.captured_on == last_day,
                    StockSnapshot.warehouse == "FBS",
                )
            ):
                fbs_now[snap.sku] = snap.qty

    # SKU bo'yicha yig'amiz
    by_sku: dict[str, list[Return]] = {}
    for row in rows:
        by_sku.setdefault(row.sku, []).append(row)

    items: list[RestockItem] = []
    skipped = 0
    for sku, returns in sorted(by_sku.items()):
        product = products.get(sku)
        barcode = (product.barcode if product else "") or ""
        if not barcode:
            # Uzum shtrix kodsiz yangilamaydi — jim o'tkazib yubormaymiz,
            # sonini chaqiruvchiga qaytaramiz
            skipped += 1
            continue

        items.append(
            RestockItem(
                sku=sku,
                title=(product.title if product else "") or sku,
                barcode=barcode,
                returned_qty=sum(r.qty for r in returns),
                current_qty=fbs_now.get(sku, 0),
                return_ids=tuple(r.uzum_return_id for r in returns),
            )
        )

    return RestockPlan(items=items, skipped_no_barcode=skipped)


async def apply_plan(
    shop_id: int, plan: RestockPlan, *, telegram_id: int
) -> tuple[int, int]:
    """Rejani qo'llaydi. `(muvaffaqiyatli, xato)` qaytaradi.

    Har SKU alohida yoziladi — bittasining xatosi qolganini to'xtatmaydi.
    Faqat muvaffaqiyatli yozilgan qaytarishlar belgilanadi, ya'ni xato
    bo'lsa keyingi safar qayta taklif qilinadi.
    """
    ok = failed = 0

    for item in plan.items:
        outcome = await apply_change(
            shop_id,
            telegram_id=telegram_id,
            sku=item.sku,
            old_qty=item.current_qty,
            new_qty=item.new_qty,
        )

        if outcome.status in (StockWriteStatus.APPLIED, StockWriteStatus.DEMO):
            ok += 1
            await _mark_restocked(shop_id, item.return_ids)
        else:
            failed += 1
            log.warning(
                "Qaytarishdan qoldiq qo'shilmadi: shop=%s sku=%s sabab=%s",
                shop_id,
                item.sku,
                outcome.error,
            )

    log.info(
        "Qaytarishdan qoldiq: shop=%s muvaffaqiyatli=%s xato=%s",
        shop_id,
        ok,
        failed,
    )
    return ok, failed


async def _mark_restocked(shop_id: int, return_ids: tuple[str, ...]) -> None:
    """Qayta qo'shilmasligi uchun belgilaymiz."""
    if not return_ids:
        return
    now = utcnow()
    async with session_scope() as session:
        rows = await session.scalars(
            select(Return).where(
                Return.shop_id == shop_id,
                Return.uzum_return_id.in_(return_ids),
                Return.restocked_at.is_(None),
            )
        )
        for row in rows:
            row.restocked_at = now
