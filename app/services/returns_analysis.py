"""Qaytarish sabablari tahlili.

Qaytarish — sellerning eng og'riqli xarajati, va sababini hech kim
ko'rsatmaydi. Biz ko'rsatamiz: qaysi tovar ko'p qaytadi va nega.

Bu "yo'qolgan pul" emas, **oldini olinadigan** pul: sabab bilinsa,
kartochkani tuzatib qaytarishni kamaytirish mumkin.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.base import session_scope
from app.db.models import Order, Product, Return
from app.services.mappers import CANCELLED_STATUSES

log = get_logger(__name__)

# Shundan yuqori qaytarish foizi — muammoli tovar
HIGH_RETURN_PCT = Decimal("15")
# Kamida shuncha sotuv bo'lmasa, foiz ishonchsiz (2 tadan 1 qaytsa 50% bo'ladi)
MIN_SALES_FOR_PCT = 5


def _pct(part: int, whole: int) -> Decimal:
    if whole <= 0:
        return Decimal("0")
    return (Decimal(part) / Decimal(whole) * 100).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )


@dataclass(slots=True)
class SkuReturns:
    sku: str
    title: str
    sold: int = 0
    returned: int = 0
    lost_amount: Decimal = Decimal("0")   # omborga qaytmagan qaytarishlar
    reasons: Counter[str] = field(default_factory=Counter)

    @property
    def return_pct(self) -> Decimal:
        return _pct(self.returned, self.sold)

    @property
    def is_reliable(self) -> bool:
        """Foiz ma'noli bo'lishi uchun yetarli sotuv bormi."""
        return self.sold >= MIN_SALES_FOR_PCT

    @property
    def is_problematic(self) -> bool:
        return self.is_reliable and self.return_pct >= HIGH_RETURN_PCT

    @property
    def top_reason(self) -> str | None:
        if not self.reasons:
            return None
        return self.reasons.most_common(1)[0][0]

    @property
    def reason_summary(self) -> str:
        """Eng ko'p uchraydigan 3 ta sabab."""
        if not self.reasons:
            return "—"
        return ", ".join(
            f"{reason} ({count})" for reason, count in self.reasons.most_common(3)
        )


@dataclass(frozen=True, slots=True)
class ReturnsSummary:
    rows: list[SkuReturns]
    period_from: date
    period_to: date

    @property
    def total_sold(self) -> int:
        return sum(r.sold for r in self.rows)

    @property
    def total_returned(self) -> int:
        return sum(r.returned for r in self.rows)

    @property
    def overall_pct(self) -> Decimal:
        return _pct(self.total_returned, self.total_sold)

    @property
    def problematic(self) -> list[SkuReturns]:
        return [r for r in self.rows if r.is_problematic]

    @property
    def top_reasons(self) -> list[tuple[str, int]]:
        combined: Counter[str] = Counter()
        for row in self.rows:
            combined.update(row.reasons)
        return combined.most_common(5)


async def collect(shop_id: int, period_from: date, period_to: date) -> ReturnsSummary:
    """Davr bo'yicha qaytarish tahlili."""
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
        returns = list(
            await session.scalars(select(Return).where(Return.shop_id == shop_id))
        )

    rows: dict[str, SkuReturns] = {}

    def _row(sku: str) -> SkuReturns:
        if sku not in rows:
            product = products.get(sku)
            rows[sku] = SkuReturns(
                sku=sku, title=(product.title if product else "") or sku
            )
        return rows[sku]

    for order in orders:
        if order.created_at_uzum is None:
            continue
        if not (period_from <= order.created_at_uzum.date() <= period_to):
            continue
        if (order.status or "").upper() in CANCELLED_STATUSES:
            continue

        row = _row(order.sku)
        row.sold += order.qty
        if order.qty_returned:
            row.returned += order.qty_returned
        if order.return_cause:
            row.reasons[order.return_cause] += 1

    # Qaytarish yozuvlaridagi sabablar ham qo'shiladi
    for item in returns:
        if item.returned_at is None:
            continue
        if not (period_from <= item.returned_at.date() <= period_to):
            continue
        row = _row(item.sku)
        if item.reason:
            row.reasons[item.reason] += 1

    result = sorted(
        rows.values(), key=lambda r: (r.return_pct, r.returned), reverse=True
    )
    return ReturnsSummary(rows=result, period_from=period_from, period_to=period_to)


async def sync_reason_dictionary(shop_id: int) -> dict[str, str]:
    """Uzumdagi qaytarish sabablari ma'lumotnomasi.

    `GET /v1/fbs/order/return-reasons` — sabab kodlarini o'qishli
    matnga aylantirish uchun. Xato bo'lsa bo'sh lug'at qaytadi —
    tahlil to'xtamasin.
    """
    from app.services.fbs import _client_for

    built = await _client_for(shop_id)
    if built is None:
        return {}
    http, client, uzum_shop_id = built

    try:
        raw = await client._get(  # noqa: SLF001 — ichki yordamchi, GET
            "/v1/fbs/order/return-reasons", rate_key=uzum_shop_id
        )
    except Exception:
        log.warning("Qaytarish sabablari lug'ati olinmadi: shop_id=%s", shop_id)
        return {}
    finally:
        await http.aclose()

    mapping: dict[str, str] = {}
    items = raw if isinstance(raw, list) else (raw or {}).get("payload") or []
    if isinstance(items, dict):
        items = items.get("reasons") or []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = item.get("id") or item.get("code") or item.get("value")
        title = item.get("title") or item.get("name") or item.get("description")
        if code is not None and title:
            mapping[str(code)] = str(title)
    return mapping


def build_recommendations(summary: ReturnsSummary) -> list[str]:
    """Sellerga aniq tavsiyalar — raqam emas, qaror."""
    tips: list[str] = []
    for row in summary.problematic[:5]:
        reason = row.top_reason
        detail = f" Asosiy sabab: {reason}." if reason else ""
        tips.append(
            f"«{row.title[:40]}» — {row.return_pct}% qaytadi "
            f"({row.returned}/{row.sold}).{detail}"
        )
    return tips


def group_by_reason(summary: ReturnsSummary) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for row in summary.rows:
        for reason, count in row.reasons.items():
            totals[reason] += count
    return dict(totals)
