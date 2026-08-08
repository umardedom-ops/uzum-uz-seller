"""Audit yurituvchisi: baza → audit yadrosi → `discrepancies`.

`audit.py` sof funksiyalar to'plami. Bu modul ularni bazadagi haqiqiy
ma'lumot bilan bog'laydi va natijani saqlaydi.

Idempotent: bir davr uchun qayta ishga tushirilsa, mavjud yozuv
yangilanadi, dublikat yaratilmaydi.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.base import session_scope, utcnow
from app.db.models import (
    Compensation,
    Discrepancy,
    DiscrepancyKind,
    DiscrepancyStatus,
    MovementType,
    Order,
    Product,
    Return,
    StockMovement,
    StockSnapshot,
)
from app.services.audit import (
    CommissionCheck,
    CompensationCheck,
    CumulativeStock,
    DimensionCheck,
    Finding,
    ReturnRecord,
    StockPeriod,
    audit_commission,
    audit_compensation,
    audit_cumulative_loss,
    audit_dimension_mismatch,
    audit_lost_return,
    audit_lost_stock,
)
from app.services.mappers import CANCELLED_STATUSES

log = get_logger(__name__)


async def run_audit(
    shop_id: int,
    period_from: date,
    period_to: date,
    *,
    cumulative: bool = False,
) -> list[Finding]:
    """Do'kon bo'yicha auditlarni yuritadi va natijani saqlaydi.

    `cumulative=True` — davr bo'yicha emas, **butun faoliyat davri**
    bo'yicha to'plangan yetishmovchilikni hisoblaydi. Bu qoldiq tarixini
    talab qilmaydi, shuning uchun bot ulangan kuniyoq ishlaydi.
    """
    async with session_scope() as session:
        products = await _load_products(session, shop_id)

        findings: list[Finding] = []
        if cumulative:
            findings += await _run_cumulative_audit(session, shop_id, products)
        else:
            findings += await _run_stock_audit(
                session, shop_id, period_from, period_to, products
            )
        findings += await _run_return_audit(session, shop_id, period_to, products)
        findings += await _run_commission_audit(
            session, shop_id, period_from, period_to, products
        )
        findings += await _run_dimension_audit(
            session, shop_id, period_from, period_to, products
        )
        findings += await _run_compensation_audit(session, shop_id)

        await _persist(session, shop_id, period_from, period_to, findings)

    log.info(
        "Audit tugadi: shop_id=%s davr=%s..%s topildi=%s",
        shop_id,
        period_from,
        period_to,
        len(findings),
    )
    return findings


# ---------------------------------------------------------------------- #
# Ma'lumot to'liqligi
# ---------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class DataHealth:
    """Qaysi manba bo'sh — demak qaysi audit ishlay olmaydi.

    Buni bilmasdan "yo'qotish topilmadi" deyish — yolg'on tinchlik.
    Manba bo'sh bo'lgani "hammasi joyida" degani emas (2026-08-07:
    AZIKO do'konida `/v1/finance/orders` 365 kun uchun ham bo'sh
    qaytardi, natijada 6 auditdan 4 tasi jimgina hech narsa
    ko'rsatmasdi).
    """

    orders: int
    returns: int
    receipts: int
    stock_days: int

    #: Manba bo'sh bo'lsa — shu auditlar ishlamaydi
    _BLOCKS = {
        "orders": ("davriy yo'qotish", "komissiya"),
        "receipts": ("to'plangan yo'qotish",),
        "stock_days": ("yo'qotish (qoldiqsiz hisoblab bo'lmaydi)",),
    }

    @property
    def missing(self) -> list[str]:
        """Bo'sh manbalar nomi (o'zbekcha)."""
        names = {
            "orders": "sotuvlar tarixi",
            "receipts": "omborga qabul (yuk xatlari)",
            "stock_days": "qoldiq surati",
        }
        return [
            names[key]
            for key in ("orders", "receipts", "stock_days")
            if getattr(self, key) == 0
        ]

    @property
    def blocked_audits(self) -> list[str]:
        blocked: list[str] = []
        for key, audits in self._BLOCKS.items():
            if getattr(self, key) == 0:
                blocked.extend(audits)
        return sorted(set(blocked))

    @property
    def is_complete(self) -> bool:
        return not self.missing


async def data_health(shop_id: int) -> DataHealth:
    """Do'kon bo'yicha manbalar to'ldirilganini tekshiradi."""
    async with session_scope() as session:
        return DataHealth(
            orders=await _count(session, Order, shop_id),
            returns=await _count(session, Return, shop_id),
            receipts=await _count(session, StockMovement, shop_id),
            stock_days=await _count(session, StockSnapshot, shop_id),
        )


async def _count(session: AsyncSession, model: type, shop_id: int) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(model).where(model.shop_id == shop_id)
        )
    ) or 0


# ---------------------------------------------------------------------- #
# Ma'lumot yuklash
# ---------------------------------------------------------------------- #


async def _load_products(session: AsyncSession, shop_id: int) -> dict[str, Product]:
    rows = await session.scalars(select(Product).where(Product.shop_id == shop_id))
    return {p.sku: p for p in rows}


def _unit_cost(product: Product | None) -> Decimal:
    """Zarar hisobi uchun narx.

    Tannarx bo'lsa — o'sha. Bo'lmasa 0: noto'g'ri summa ko'rsatgandan
    ko'ra nol ko'rsatib, sellerdan tannarx so'raganimiz ma'qul.
    """
    if product is None or product.cost_price is None:
        return Decimal("0")
    return product.cost_price


# ---------------------------------------------------------------------- #
# 5.1 — Yo'qolgan tovar
# ---------------------------------------------------------------------- #


async def _run_stock_audit(
    session: AsyncSession,
    shop_id: int,
    period_from: date,
    period_to: date,
    products: dict[str, Product],
) -> list[Finding]:
    start_stock = await _snapshot_at(session, shop_id, period_from)
    end_stock = await _snapshot_at(session, shop_id, period_to)
    if not start_stock or not end_stock:
        # Tarix yetarli emas — bot ishga tushgan kundan hisob boshlanadi
        log.info("Qoldiq tarixi yetarli emas: shop_id=%s", shop_id)
        return []

    sold = await _sold_by_sku(session, shop_id, period_from, period_to)
    returned = await _returned_by_sku(session, shop_id, period_from, period_to)
    received = await _movement_by_sku(
        session, shop_id, period_from, period_to, MovementType.IN
    )
    written_off = await _movement_by_sku(
        session, shop_id, period_from, period_to, MovementType.WRITEOFF
    )

    findings: list[Finding] = []
    for sku, qty_end in end_stock.items():
        period = StockPeriod(
            sku=sku,
            period_from=period_from,
            period_to=period_to,
            qty_at_start=start_stock.get(sku, 0),
            qty_at_end=qty_end,
            received=received.get(sku, 0),
            returned=returned.get(sku, 0),
            sold=sold.get(sku, 0),
            written_off=written_off.get(sku, 0),
            unit_cost=_unit_cost(products.get(sku)),
        )
        if (finding := audit_lost_stock(period)) is not None:
            findings.append(finding)
    return findings


async def _run_cumulative_audit(
    session: AsyncSession, shop_id: int, products: dict[str, Product]
) -> list[Finding]:
    """5.1-bis — butun faoliyat davri bo'yicha to'plangan yetishmovchilik.

    Qoldiq tarixi kerak emas: barcha harakatlar yig'indisi bugungi
    kutilgan qoldiqni beradi, uni bugungi haqiqiy qoldiq bilan
    solishtiramiz.
    """
    latest = await _latest_snapshot(session, shop_id)
    if not latest:
        log.info("Hozirgi qoldiq yo'q — to'plangan audit o'tkazib yuborildi")
        return []

    # "Qabul qilingan" miqdor uchun ikki manba bor. Uzumning
    # `quantityCreated` maydoni ba'zan 0 qaytaradi (haqiqiy do'konda
    # tekshirilgan), shuning uchun FBO yuk xatlari asosiy manba,
    # `quantityCreated` — zaxira.
    received = await _total_movements(session, shop_id, MovementType.IN)

    findings: list[Finding] = []
    for sku, qty_now in latest.items():
        product = products.get(sku)
        if product is None:
            continue

        # FAQAT yuk xatlaridagi `quantityAccepted`. `quantityCreated` ni
        # ishlatmaymiz: u haqiqiy do'konda ham 0, ham yetib bormagan
        # yukning rejasini qaytardi — ikkalasi ham soxta natija beradi.
        total_received = received.get(sku, 0)

        stock = CumulativeStock(
            sku=sku,
            qty_now=qty_now,
            total_received=total_received,
            # ❗ Qaytarish kutilgan qoldiqqa QO'SHILMAYDI (2026-08-07 sverkasi).
            #
            # `quantityReturned` — "mijoz qaytargan", u `quantitySold`
            # ichida allaqachon hisoblangan. Qo'shilsa qaytarish ikki
            # marta sanaladi va SOXTA yo'qotish chiqadi: AZIKO do'konida
            # shu had 17 ta yolg'on topilma, 7.63 mln so'm bergan
            # (16 tasida farq aynan `quantityReturned` ga teng edi,
            # Uzumning `quantityMissing` esa hammasida 0).
            #
            # `returns` jadvalidagi yozuvlar ham bu yerga tushmaydi:
            # `/v1/shop/{id}/return` — omborga KIRIM emas, sotuvchiga
            # CHIQIM (turi `DEFECTED`). Ularni chiqim sifatida qo'shish
            # ham noto'g'ri bo'lardi — Uzumning `quantityDefected` maydoni
            # ularni allaqachon sanaydi (SKU 704077: yuk xatida 1 dona,
            # `quantityDefected` ham 1).
            total_returned=0,
            total_sold=product.qty_sold_total or 0,
            total_written_off=(product.qty_defected or 0)
            + (product.qty_archived or 0),
            unit_cost=_unit_cost(product),
            history_complete=True,  # jami raqamlar manbai — Uzumning o'zi
        )
        if (finding := audit_cumulative_loss(stock)) is not None:
            findings.append(finding)

    if not findings and latest:
        log.info(
            "To'plangan audit natija bermadi: shop_id=%s — qabul ma'lumoti "
            "to'liq emas bo'lishi mumkin",
            shop_id,
        )
    return findings


def _history_is_complete(first_receipt: date | None, first_sale: date | None) -> bool:
    """Sotuv tarixi qabul tarixini qamrab oladimi.

    Qabul yozuvi yo'q bo'lsa hisoblab bo'lmaydi. Sotuv yozuvi yo'q bo'lsa
    ham — hech narsa sotilmagan bo'lishi mumkin, lekin tarix qirqilgan
    bo'lishi ham mumkin; ehtiyot bo'lib hisoblamaymiz.
    """
    if first_receipt is None or first_sale is None:
        return False
    return first_sale <= first_receipt


async def _latest_snapshot(session: AsyncSession, shop_id: int) -> dict[str, int]:
    """Eng oxirgi qoldiq surati."""
    last_day = await session.scalar(
        select(StockSnapshot.captured_on)
        .where(StockSnapshot.shop_id == shop_id)
        .order_by(StockSnapshot.captured_on.desc())
        .limit(1)
    )
    if last_day is None:
        return {}
    return await _snapshot_at(session, shop_id, last_day)


async def _total_movements(
    session: AsyncSession, shop_id: int, kind: MovementType
) -> dict[str, int]:
    rows = await session.scalars(
        select(StockMovement).where(
            StockMovement.shop_id == shop_id, StockMovement.type == kind
        )
    )
    totals: dict[str, int] = defaultdict(int)
    for row in rows:
        totals[row.sku] += row.qty
    return dict(totals)


async def _first_movement_date(
    session: AsyncSession, shop_id: int, kind: MovementType
) -> date | None:
    moment = await session.scalar(
        select(StockMovement.happened_at)
        .where(
            StockMovement.shop_id == shop_id,
            StockMovement.type == kind,
            StockMovement.happened_at.is_not(None),
        )
        .order_by(StockMovement.happened_at)
        .limit(1)
    )
    return moment.date() if moment else None


async def _total_sold(
    session: AsyncSession, shop_id: int
) -> tuple[dict[str, int], date | None]:
    rows = await session.scalars(select(Order).where(Order.shop_id == shop_id))
    totals: dict[str, int] = defaultdict(int)
    earliest: date | None = None
    for row in rows:
        if (row.status or "").upper() in CANCELLED_STATUSES:
            continue
        totals[row.sku] += row.qty
        if row.created_at_uzum is not None:
            day = row.created_at_uzum.date()
            earliest = day if earliest is None else min(earliest, day)
    return dict(totals), earliest


async def _total_returned(session: AsyncSession, shop_id: int) -> dict[str, int]:
    rows = await session.scalars(select(Return).where(Return.shop_id == shop_id))
    totals: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.received_at is None:
            continue  # omborga tushmagan — bu 5.2 auditига tegishli
        totals[row.sku] += row.qty
    return dict(totals)


async def _snapshot_at(
    session: AsyncSession, shop_id: int, day: date
) -> dict[str, int]:
    """Berilgan kundagi (yoki undan oldingi eng yaqin) qoldiq surati."""
    actual_day = await session.scalar(
        select(StockSnapshot.captured_on)
        .where(StockSnapshot.shop_id == shop_id, StockSnapshot.captured_on <= day)
        .order_by(StockSnapshot.captured_on.desc())
        .limit(1)
    )
    if actual_day is None:
        return {}

    rows = await session.scalars(
        select(StockSnapshot).where(
            StockSnapshot.shop_id == shop_id, StockSnapshot.captured_on == actual_day
        )
    )
    totals: dict[str, int] = defaultdict(int)
    for row in rows:
        totals[row.sku] += row.qty
    return dict(totals)


async def _sold_by_sku(
    session: AsyncSession, shop_id: int, period_from: date, period_to: date
) -> dict[str, int]:
    rows = await session.scalars(
        select(Order).where(
            Order.shop_id == shop_id,
            Order.created_at_uzum.is_not(None),
        )
    )
    totals: dict[str, int] = defaultdict(int)
    for row in rows:
        if not _in_period(row.created_at_uzum, period_from, period_to):
            continue
        if (row.status or "").upper() in CANCELLED_STATUSES:
            continue  # bekor qilingan sotuv emas
        totals[row.sku] += row.qty
    return dict(totals)


async def _returned_by_sku(
    session: AsyncSession, shop_id: int, period_from: date, period_to: date
) -> dict[str, int]:
    """Omborga QAYTIB TUSHGAN miqdor (tushmagani 5.2 auditига tegishli)."""
    rows = await session.scalars(select(Return).where(Return.shop_id == shop_id))
    totals: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.received_at is None:
            continue
        if not _in_period(row.received_at, period_from, period_to):
            continue
        totals[row.sku] += row.qty
    return dict(totals)


async def _movement_by_sku(
    session: AsyncSession,
    shop_id: int,
    period_from: date,
    period_to: date,
    kind: MovementType,
) -> dict[str, int]:
    rows = await session.scalars(
        select(StockMovement).where(
            StockMovement.shop_id == shop_id, StockMovement.type == kind
        )
    )
    totals: dict[str, int] = defaultdict(int)
    for row in rows:
        if not _in_period(row.happened_at, period_from, period_to):
            continue
        totals[row.sku] += row.qty
    return dict(totals)


def _in_period(moment: object, period_from: date, period_to: date) -> bool:
    if moment is None:
        return False
    day = moment.date() if hasattr(moment, "date") else moment
    return period_from <= day <= period_to


# ---------------------------------------------------------------------- #
# 5.2 — Yo'qolgan qaytarish
# ---------------------------------------------------------------------- #


async def _run_return_audit(
    session: AsyncSession,
    shop_id: int,
    today: date,
    products: dict[str, Product],
) -> list[Finding]:
    rows = await session.scalars(
        select(Return).where(Return.shop_id == shop_id, Return.received_at.is_(None))
    )
    findings: list[Finding] = []
    for row in rows:
        if row.returned_at is None:
            continue
        record = ReturnRecord(
            sku=row.sku,
            return_id=row.uzum_return_id,
            qty=row.qty,
            returned_at=row.returned_at.date(),
            received_at=None,
            unit_cost=_unit_cost(products.get(row.sku)),
        )
        if (finding := audit_lost_return(record, today=today)) is not None:
            findings.append(finding)
    return findings


# ---------------------------------------------------------------------- #
# 5.3 — Ortiqcha komissiya
# ---------------------------------------------------------------------- #


async def _run_commission_audit(
    session: AsyncSession,
    shop_id: int,
    period_from: date,
    period_to: date,
    products: dict[str, Product],
) -> list[Finding]:
    rows = await session.scalars(select(Order).where(Order.shop_id == shop_id))

    sales: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    charged: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in rows:
        if not _in_period(row.created_at_uzum, period_from, period_to):
            continue
        if (row.status or "").upper() in CANCELLED_STATUSES:
            continue
        if row.price is not None:
            sales[row.sku] += row.price * row.qty
        if row.commission_amount is not None:
            charged[row.sku] += row.commission_amount

    findings: list[Finding] = []
    for sku, amount in sales.items():
        product = products.get(sku)
        if product is None or product.commission_pct is None:
            continue  # foizni bilmasak, taqqoslab bo'lmaydi
        check = CommissionCheck(
            sku=sku,
            sales_amount=amount,
            charged_commission=charged.get(sku, Decimal("0")),
            expected_pct=product.commission_pct,
        )
        if (finding := audit_commission(check)) is not None:
            findings.append(finding)
    return findings


# ---------------------------------------------------------------------- #
# 5.4 — O'lcham nomuvofiqligi (logistika)
# ---------------------------------------------------------------------- #


async def _run_dimension_audit(
    session: AsyncSession,
    shop_id: int,
    period_from: date,
    period_to: date,
    products: dict[str, Product],
) -> list[Finding]:
    """Kartochkadagi габарит guruhi Uzum o'lchaganidan farq qiladimi."""
    candidates = [
        product
        for product in products.values()
        if product.dimensional_group and product.actual_dimensional_group
    ]
    if not candidates:
        return []

    paid: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    counts: dict[str, int] = defaultdict(int)
    rows = await session.scalars(select(Order).where(Order.shop_id == shop_id))
    for row in rows:
        if not _in_period(row.created_at_uzum, period_from, period_to):
            continue
        if (row.status or "").upper() in CANCELLED_STATUSES:
            continue
        paid[row.sku] += row.delivery_amount or Decimal("0")
        counts[row.sku] += 1

    findings: list[Finding] = []
    for product in candidates:
        check = DimensionCheck(
            sku=product.sku,
            card_group=product.dimensional_group,
            actual_group=product.actual_dimensional_group,
            logistics_paid=paid.get(product.sku, Decimal("0")),
            orders_count=counts.get(product.sku, 0),
        )
        if (finding := audit_dimension_mismatch(check)) is not None:
            findings.append(finding)
    return findings


# ---------------------------------------------------------------------- #
# 5.5 — Kompensatsiya sverkasi
# ---------------------------------------------------------------------- #


async def _run_compensation_audit(
    session: AsyncSession, shop_id: int
) -> list[Finding]:
    """Tan olingan zararlar bo'yicha to'lov keldimi."""
    claimed = await session.scalars(
        select(Discrepancy).where(
            Discrepancy.shop_id == shop_id,
            Discrepancy.status == DiscrepancyStatus.CLAIMED,
        )
    )
    comps = await session.scalars(
        select(Compensation).where(Compensation.shop_id == shop_id)
    )
    paid: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for comp in comps:
        if comp.sku and comp.amount:
            paid[comp.sku] += comp.amount

    findings: list[Finding] = []
    for item in claimed:
        check = CompensationCheck(
            sku=item.sku,
            claimed_amount=item.amount or Decimal("0"),
            paid_amount=paid.get(item.sku, Decimal("0")),
            qty=item.qty,
        )
        if (finding := audit_compensation(check)) is not None:
            findings.append(finding)
    return findings


# ---------------------------------------------------------------------- #
# Saqlash
# ---------------------------------------------------------------------- #


async def _persist(
    session: AsyncSession,
    shop_id: int,
    period_from: date,
    period_to: date,
    findings: list[Finding],
) -> None:
    """Natijani `discrepancies` ga yozadi (idempotent).

    Mavjud yozuv yangilanadi — lekin da'vo qilingan yoki hal bo'lganlarga
    tegilmaydi, aks holda seller yuborgan da'vo holati yo'qoladi.

    Endi topilmaydigan farqlar **o'chiriladi**. Busiz bir marta yozilgan
    xato natija abadiy qolardi: formula tuzatilsa ham seller eski soxta
    summani ko'raverardi (2026-08-07 da aniqlandi — audit 0 qaytardi,
    lekin bazadagi 17 ta eski yozuv joyida turdi).
    """
    protected = {DiscrepancyStatus.CLAIMED, DiscrepancyStatus.RESOLVED}

    # Bu davr uchun endi o'rinli bo'lmagan yozuvlarni olib tashlaymiz
    current = {(f.sku, f.kind) for f in findings}
    stale = await session.scalars(
        select(Discrepancy).where(
            Discrepancy.shop_id == shop_id,
            Discrepancy.period_from == period_from,
            Discrepancy.period_to == period_to,
        )
    )
    for row in stale:
        if row.status in protected:
            continue  # seller da'vo yuborgan — tarixni buzmaymiz
        if (row.sku, row.kind) not in current:
            await session.delete(row)

    for finding in findings:
        existing = await session.scalar(
            select(Discrepancy).where(
                Discrepancy.shop_id == shop_id,
                Discrepancy.sku == finding.sku,
                Discrepancy.kind == finding.kind,
                Discrepancy.period_from == period_from,
                Discrepancy.period_to == period_to,
            )
        )
        if existing is not None:
            if existing.status in protected:
                continue
            existing.qty = finding.qty
            existing.amount = finding.amount
            existing.status = finding.status
            existing.details = finding.details
            existing.detected_at = utcnow()
            continue

        session.add(
            Discrepancy(
                shop_id=shop_id,
                sku=finding.sku,
                kind=finding.kind,
                qty=finding.qty,
                amount=finding.amount,
                period_from=period_from,
                period_to=period_to,
                status=finding.status,
                details=finding.details,
                detected_at=utcnow(),
            )
        )


# ---------------------------------------------------------------------- #
# Hisobot uchun o'qish
# ---------------------------------------------------------------------- #


async def get_findings(
    shop_id: int, *, only_claimable: bool = False
) -> list[Discrepancy]:
    """Do'kon bo'yicha aniqlangan farqlar (bot menyusi uchun)."""
    async with session_scope() as session:
        query = select(Discrepancy).where(Discrepancy.shop_id == shop_id)
        if only_claimable:
            query = query.where(Discrepancy.status == DiscrepancyStatus.NEW)
        rows = await session.scalars(query.order_by(Discrepancy.amount.desc()))
        return list(rows)


async def summarize(shop_id: int) -> dict[DiscrepancyKind, Decimal]:
    """Tur bo'yicha jami summa — "Yo'qotilgan pul" ekranida ko'rsatiladi."""
    findings = await get_findings(shop_id, only_claimable=True)
    totals: dict[DiscrepancyKind, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in findings:
        totals[item.kind] += item.amount or Decimal("0")
    return dict(totals)
