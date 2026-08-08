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

    @property
    def compensation_per_unit(self) -> Decimal:
        """Bir dona uchun qoplanadigan summa (sotuv narxi − komissiya).

        `unit_cost` maydonining ma'nosi 2026-08-08 da o'zgardi: ilgari
        tannarx edi, endi Uzumning «Размер возмещения» qoidasi bo'yicha
        hisoblanadi (`audit_runner._unit_cost`). Nomi tarixiy sabab
        bilan qolgan — hujjatlarda shu xossa ishlatiladi.
        """
        return self.unit_cost

    def reason_label(self, lang: str = "uz") -> str:
        """Pretenziya jadvalidagi «Причина» ustuni."""
        ru = {
            DiscrepancyKind.LOST_STOCK: "Утеря",
            DiscrepancyKind.LOST_RETURN: "Утеря (возврат)",
            DiscrepancyKind.OVER_COMMISSION: "Излишняя комиссия",
            DiscrepancyKind.LOGISTICS: "Логистика",
            DiscrepancyKind.MISSING_COMPENSATION: "Невыплаченная компенсация",
        }
        if lang == "ru":
            return ru.get(self.kind, self.kind.value)
        return self.kind_label


@dataclass(frozen=True, slots=True)
class SellerRequisites:
    """Pretenziya sarlavhasidagi rekvizitlar.

    ❗ Bularsiz Uzum to'lov qila olmaydi — qabul qilingan haqiqiy
    pretenziyada (2026-08-08 da ko'rildi) sarlavha aynan shu maydonlardan
    iborat: ФИО, ИП, ПИНФЛ, расчетный счет, МФО.

    Bo'sh qolgan maydon hujjatda chiziqcha bo'lib chiqadi — seller qo'lda
    to'ldiradi. Xato raqam yozgandan ko'ra bo'sh joy ma'qul.
    """

    full_name: str = ""       # ФИО
    entity: str = ""          # ИП / MChJ nomi
    pinfl: str = ""           # ПИНФЛ (yoki INN)
    bank_account: str = ""    # расчетный счет
    mfo: str = ""             # МФО

    #: Vositachilik shartnomasi (Oferta) — qo'shimcha kelishuv uchun
    contract_no: str = ""
    contract_date: str = ""

    @property
    def is_complete(self) -> bool:
        return all((self.full_name, self.pinfl, self.bank_account, self.mfo))

    @property
    def missing(self) -> list[str]:
        names = {
            "full_name": "F.I.Sh.",
            "pinfl": "PINFL",
            "bank_account": "hisob raqam",
            "mfo": "MFO",
        }
        return [label for key, label in names.items() if not getattr(self, key)]


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
    #: Hujjat tili — "uz" yoki "ru". Uzum bilan huquqiy yozishma odatda
    #: rus tilida, lekin seller o'z tilini tanlashi mumkin.
    lang: str = "uz"
    requisites: SellerRequisites = field(default_factory=SellerRequisites)

    @property
    def total_amount(self) -> Decimal:
        return sum((r.loss_amount for r in self.rows), Decimal("0"))

    @property
    def total_qty(self) -> int:
        return sum(r.diff_qty for r in self.rows)
