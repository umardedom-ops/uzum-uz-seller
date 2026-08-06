"""Hujjatlar uchun umumiy ma'lumot tuzilmalari (SPEC 6)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.db.models import DiscrepancyKind

# Farq turlarining o'zbekcha nomlari — hujjatlarda shu ko'rinadi
KIND_LABELS: dict[DiscrepancyKind, str] = {
    DiscrepancyKind.LOST_STOCK: "Yo'qolgan tovar",
    DiscrepancyKind.LOST_RETURN: "Qaytmagan qaytarish",
    DiscrepancyKind.OVER_COMMISSION: "Ortiqcha komissiya",
    DiscrepancyKind.LOGISTICS: "Logistika farqi",
    DiscrepancyKind.MISSING_COMPENSATION: "To'lanmagan kompensatsiya",
}


@dataclass(frozen=True, slots=True)
class ReportRow:
    """Excel hisobotining bitta qatori (SPEC 6.1 ustunlari)."""

    sku: str
    barcode: str          # MAJBURIY — usiz Uzumga isbotlab bo'lmaydi
    title: str
    period_from: date
    period_to: date
    expected_qty: int
    actual_qty: int
    diff_qty: int
    unit_cost: Decimal
    loss_amount: Decimal
    kind: DiscrepancyKind
    detected_at: date

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind.value)

    @property
    def has_barcode(self) -> bool:
        return bool(self.barcode and self.barcode.strip())


@dataclass(frozen=True, slots=True)
class ClaimContext:
    """Pretenziya uchun ma'lumot (SPEC 6.2)."""

    seller_name: str          # seller rekvizitlari
    seller_requisites: str    # INN, manzil, hisob raqam va h.k.
    shop_title: str
    shop_id: str
    period_from: date
    period_to: date
    rows: list[ReportRow] = field(default_factory=list)
    created_on: date | None = None

    @property
    def total_amount(self) -> Decimal:
        return sum((r.loss_amount for r in self.rows), Decimal("0"))

    @property
    def total_qty(self) -> int:
        return sum(r.diff_qty for r in self.rows)
