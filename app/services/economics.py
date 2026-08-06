"""Yunit-iqtisodiyot, ABC tahlil va saqlash xarajati.

Ustunligimiz: tannarxni sellerdan so'ramaymiz. Uzum har buyurtma uchun
`sellerProfit`, `purchasePrice`, `commission`, `logisticDeliveryFee` ni
o'zi beradi — biz shuni yig'amiz.

ABC — daromad bo'yicha toifalash (Pareto):
  A — kumulyativ 80% gacha  (asosiy daromad)
  B — 80–95%                (o'rtacha)
  C — 95–100%               (quyruq: ko'p tovar, kam daromad)
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.base import session_scope
from app.db.models import Order, Product, StockSnapshot
from app.services.mappers import CANCELLED_STATUSES

log = get_logger(__name__)

_CENTS = Decimal("0.01")

# ABC chegaralari (kumulyativ daromad ulushi)
ABC_A_THRESHOLD = Decimal("80")
ABC_B_THRESHOLD = Decimal("95")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class SkuEconomics:
    """Bitta SKU bo'yicha davr ichidagi iqtisodiyot."""

    sku: str
    title: str
    barcode: str = ""
    qty_sold: int = 0
    revenue: Decimal = Decimal("0")        # tushum
    cost: Decimal = Decimal("0")           # tannarx (Uzum bergan)
    commission: Decimal = Decimal("0")
    logistics: Decimal = Decimal("0")
    storage: Decimal = Decimal("0")        # pullik saqlash
    reported_profit: Decimal = Decimal("0")  # Uzum hisoblagan foyda
    stock_qty: int = 0
    returned_pct: Decimal | None = None
    abc: str = "C"
    revenue_share: Decimal = Decimal("0")

    @property
    def expenses(self) -> Decimal:
        return _money(self.commission + self.logistics + self.storage)

    @property
    def profit(self) -> Decimal:
        """Sof foyda.

        Uzum bergan `sellerProfit` bor bo'lsa — o'shani ishlatamiz (u
        bizning hisobimizdan aniqroq). Bo'lmasa o'zimiz hisoblaymiz.
        """
        if self.reported_profit:
            return _money(self.reported_profit - self.storage)
        return _money(self.revenue - self.cost - self.expenses)

    @property
    def margin_pct(self) -> Decimal:
        if self.revenue == 0:
            return Decimal("0")
        return (self.profit / self.revenue * 100).quantize(Decimal("0.1"))

    @property
    def profit_per_unit(self) -> Decimal:
        if self.qty_sold == 0:
            return Decimal("0")
        return _money(self.profit / self.qty_sold)

    @property
    def is_loss_making(self) -> bool:
        """Zarar keltiryaptimi — sellerga darhol ko'rsatiladigan holat."""
        return self.qty_sold > 0 and self.profit < 0

    @property
    def is_dead_stock(self) -> bool:
        """Omborda turibdi, sotilmayapti, saqlash puli ketyapti."""
        return self.qty_sold == 0 and self.stock_qty > 0


@dataclass(frozen=True, slots=True)
class EconomicsSummary:
    rows: list[SkuEconomics]
    period_from: date
    period_to: date

    @property
    def revenue(self) -> Decimal:
        return _money(sum((r.revenue for r in self.rows), Decimal("0")))

    @property
    def profit(self) -> Decimal:
        return _money(sum((r.profit for r in self.rows), Decimal("0")))

    @property
    def storage(self) -> Decimal:
        return _money(sum((r.storage for r in self.rows), Decimal("0")))

    @property
    def commission(self) -> Decimal:
        return _money(sum((r.commission for r in self.rows), Decimal("0")))

    @property
    def logistics(self) -> Decimal:
        return _money(sum((r.logistics for r in self.rows), Decimal("0")))

    @property
    def margin_pct(self) -> Decimal:
        if self.revenue == 0:
            return Decimal("0")
        return (self.profit / self.revenue * 100).quantize(Decimal("0.1"))

    @property
    def loss_makers(self) -> list[SkuEconomics]:
        return [r for r in self.rows if r.is_loss_making]

    @property
    def dead_stock(self) -> list[SkuEconomics]:
        return [r for r in self.rows if r.is_dead_stock]

    def by_class(self, abc: str) -> list[SkuEconomics]:
        return [r for r in self.rows if r.abc == abc]


def classify_abc(rows: list[SkuEconomics]) -> None:
    """Daromad bo'yicha A/B/C toifasini belgilaydi (joyida o'zgartiradi).

    Daromadi nol bo'lganlar avtomatik C — ular quyruqning eng oxiri.
    """
    total = sum((r.revenue for r in rows), Decimal("0"))
    if total <= 0:
        for row in rows:
            row.abc = "C"
            row.revenue_share = Decimal("0")
        return

    ordered = sorted(rows, key=lambda r: r.revenue, reverse=True)
    cumulative = Decimal("0")
    for row in ordered:
        share = row.revenue / total * 100
        row.revenue_share = share.quantize(Decimal("0.1"))

        # Toifa chegaradan OLDINGI kumulyativ ulushga qarab beriladi.
        # Shu sabab chegarani kesib o'tuvchi tovar yuqori toifada qoladi —
        # aks holda yagona tovar 100% daromad berib turib C ga tushardi.
        if cumulative < ABC_A_THRESHOLD:
            row.abc = "A"
        elif cumulative < ABC_B_THRESHOLD:
            row.abc = "B"
        else:
            row.abc = "C"

        cumulative += share


async def collect(shop_id: int, period_from: date, period_to: date) -> EconomicsSummary:
    """Davr bo'yicha SKU kesimida iqtisodiyot."""
    async with session_scope() as session:
        products = {
            p.sku: p
            for p in await session.scalars(
                select(Product).where(Product.shop_id == shop_id)
            )
        }
        orders = list(
            await session.scalars(select(Order).where(Order.shop_id == shop_id))
        )

        last_day = await session.scalar(
            select(StockSnapshot.captured_on)
            .where(StockSnapshot.shop_id == shop_id)
            .order_by(StockSnapshot.captured_on.desc())
            .limit(1)
        )
        stock: dict[str, int] = defaultdict(int)
        if last_day is not None:
            for snap in await session.scalars(
                select(StockSnapshot).where(
                    StockSnapshot.shop_id == shop_id,
                    StockSnapshot.captured_on == last_day,
                )
            ):
                stock[snap.sku] += snap.qty

    rows: dict[str, SkuEconomics] = {}

    def _row(sku: str) -> SkuEconomics:
        if sku not in rows:
            product = products.get(sku)
            rows[sku] = SkuEconomics(
                sku=sku,
                title=(product.title if product else "") or sku,
                barcode=(product.barcode if product else "") or "",
                stock_qty=stock.get(sku, 0),
                storage=(product.paid_storage_amount if product else None)
                or Decimal("0"),
                returned_pct=product.returned_pct if product else None,
            )
        return rows[sku]

    for order in orders:
        if order.created_at_uzum is None:
            continue
        day = order.created_at_uzum.date()
        if not (period_from <= day <= period_to):
            continue
        if (order.status or "").upper() in CANCELLED_STATUSES:
            continue

        row = _row(order.sku)
        row.qty_sold += order.qty
        if order.price is not None:
            row.revenue += order.price * order.qty
        if order.purchase_price is not None:
            row.cost += order.purchase_price * order.qty
        row.commission += order.commission_amount or Decimal("0")
        row.logistics += order.delivery_amount or Decimal("0")
        row.reported_profit += order.seller_profit or Decimal("0")

    # Sotuvsiz, lekin omborda turgan tovarlar ham ko'rinsin (o'lik yuk)
    for sku, qty in stock.items():
        if qty > 0:
            _row(sku)

    result = list(rows.values())
    classify_abc(result)
    result.sort(key=lambda r: r.revenue, reverse=True)

    return EconomicsSummary(
        rows=result, period_from=period_from, period_to=period_to
    )
