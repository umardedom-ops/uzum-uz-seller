"""Audit yadrosi testlari (SPEC 5.1–5.5).

SPEC Phase 4: "Unit testlar — bu qism xato qilsa mahsulot o'ladi."

Ikki xil xato bir xil darajada qimmat:
  * yo'qotishni topmaslik  → mijoz pul topmaydi, ketadi
  * yo'q yo'qotishni topish → seller Uzumga noto'g'ri da'vo yuboradi,
                              uyalib qoladi va bizga ishonmaydi
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.db.models import DiscrepancyKind, DiscrepancyStatus
from app.services.audit import (
    CommissionCheck,
    CompensationCheck,
    CumulativeStock,
    DimensionCheck,
    Finding,
    LogisticsCheck,
    ReturnRecord,
    StockPeriod,
    audit_commission,
    audit_compensation,
    audit_cumulative_loss,
    audit_dimension_mismatch,
    audit_logistics,
    audit_lost_return,
    audit_lost_stock,
    total_claimable,
    total_watching,
)

T1 = date(2026, 7, 1)
T2 = date(2026, 7, 31)


def stock(**kwargs: object) -> StockPeriod:
    """Sinov uchun qulay konstruktor — faqat kerakli maydonlar beriladi."""
    base = {
        "sku": "SKU-1",
        "period_from": T1,
        "period_to": T2,
        "qty_at_start": 100,
        "qty_at_end": 100,
        "unit_cost": Decimal("50000"),
    }
    base.update(kwargs)
    return StockPeriod(**base)  # type: ignore[arg-type]


class TestLostStock:
    """5.1 — kutilgan va haqiqiy qoldiq farqi."""

    def test_no_difference_returns_nothing(self) -> None:
        """Hammasi joyida — yozuv yaratilmasin (SPEC: farq==0 bo'lsa yozmaslik)."""
        assert audit_lost_stock(stock(sold=20, qty_at_end=80)) is None

    def test_full_formula(self) -> None:
        """qoldiq + qabul + qaytgan − sotilgan − chiqarilgan − haqiqiy."""
        period = stock(
            qty_at_start=100,
            received=50,
            returned=10,
            sold=30,
            written_off=5,
            qty_at_end=120,  # kutilgan 125 → 5 dona yetishmayapti
        )
        assert period.expected_qty == 125
        result = audit_lost_stock(period)

        assert result is not None
        assert result.kind == DiscrepancyKind.LOST_STOCK
        assert result.qty == 5
        assert result.amount == Decimal("250000.00")  # 5 × 50 000
        assert result.status == DiscrepancyStatus.NEW

    def test_single_unit_goes_to_watching(self) -> None:
        """1 dona farq — da'vo qilmaymiz, kuzatuvga olamiz."""
        result = audit_lost_stock(stock(qty_at_end=99))
        assert result is not None
        assert result.qty == 1
        assert result.status == DiscrepancyStatus.WATCHING
        assert not result.is_claimable

    def test_two_units_is_claimable(self) -> None:
        """2 donadan boshlab da'vo qilinadi."""
        result = audit_lost_stock(stock(qty_at_end=98))
        assert result is not None
        assert result.status == DiscrepancyStatus.NEW
        assert result.is_claimable

    def test_surplus_is_not_a_finding(self) -> None:
        """Omborda ortiqcha tovar — bu yo'qotish emas, da'vo qilmaymiz."""
        assert audit_lost_stock(stock(qty_at_end=105)) is None

    def test_inventory_day_suppresses_finding(self) -> None:
        """Inventarizatsiya kunida qoldiq qayta sanaladi — farq tabiiy."""
        period = stock(
            qty_at_end=90,
            inventory_days=frozenset({date(2026, 7, 15)}),
        )
        assert audit_lost_stock(period) is None

    def test_inventory_outside_period_does_not_suppress(self) -> None:
        """Davrdan tashqaridagi inventarizatsiya ta'sir qilmasligi kerak."""
        period = stock(
            qty_at_end=90,
            inventory_days=frozenset({date(2026, 6, 1)}),
        )
        result = audit_lost_stock(period)
        assert result is not None
        assert result.qty == 10

    def test_details_explain_the_math(self) -> None:
        """Seller hisobni tushuna olishi kerak — da'voda shu matn ishlatiladi."""
        result = audit_lost_stock(stock(sold=10, qty_at_end=85))
        assert result is not None
        assert "85" in result.details
        assert "10" in result.details


class TestCumulativeLoss:
    """5.1-bis — butun faoliyat davri bo'yicha to'plangan yetishmovchilik.

    Bu audit qoldiq tarixini talab qilmaydi, shuning uchun bot ulangan
    kuniyoq ishlaydi. Lekin tarix qirqilgan bo'lsa SOXTA yo'qotish
    ko'rsatishi mumkin — himoya sinaladi.
    """

    def _stock(self, **kwargs: object) -> CumulativeStock:
        base = {
            "sku": "SKU-1",
            "qty_now": 40,
            "total_received": 100,
            "total_returned": 0,
            "total_sold": 55,
            "total_written_off": 0,
            "unit_cost": Decimal("50000"),
            "history_complete": True,
            "first_movement": date(2025, 1, 15),
        }
        base.update(kwargs)
        return CumulativeStock(**base)  # type: ignore[arg-type]

    def test_detects_accumulated_shortage(self) -> None:
        """100 qabul − 55 sotilgan = 45 kutilgan, 40 bor → 5 yo'qolgan."""
        stock = self._stock()
        assert stock.expected_qty == 45
        result = audit_cumulative_loss(stock)

        assert result is not None
        assert result.kind == DiscrepancyKind.LOST_STOCK
        assert result.qty == 5
        assert result.amount == Decimal("250000.00")
        assert result.status == DiscrepancyStatus.NEW

    def test_balanced_stock_is_clean(self) -> None:
        assert audit_cumulative_loss(self._stock(qty_now=45)) is None

    def test_surplus_ignored(self) -> None:
        assert audit_cumulative_loss(self._stock(qty_now=50)) is None

    def test_returns_increase_expected(self) -> None:
        """Omborga qaytib tushgan tovar kutilgan qoldiqni oshiradi."""
        stock = self._stock(total_returned=10, qty_now=50)
        assert stock.expected_qty == 55
        result = audit_cumulative_loss(stock)
        assert result is not None and result.qty == 5

    def test_writeoff_reduces_expected(self) -> None:
        """Hisobdan chiqarilgan tovar yo'qotish emas."""
        stock = self._stock(total_written_off=5, qty_now=40)
        assert stock.expected_qty == 40
        assert audit_cumulative_loss(stock) is None

    def test_zero_receipts_with_activity_blocks_result(self) -> None:
        """⚠️ Haqiqiy do'konda topilgan xato (2026-08-07).

        Uzum ba'zi tovarlar uchun "qabul qilingan" ni 0 qaytaradi,
        holbuki tovar sotilgan va omborda bor. Formula bo'yicha bu
        "yo'qolgan tovar" bo'lib chiqadi — soxta natija. Sellerni
        bunday da'vo bilan Uzumga yubormaymiz.
        """
        stock = self._stock(
            total_received=0, total_returned=5, total_sold=0, qty_now=1
        )
        assert stock.diff == 4  # formula 4 dona "yo'qolgan" deydi
        assert audit_cumulative_loss(stock) is None  # lekin biz yozmaymiz

    def test_zero_receipts_with_sales_blocks_result(self) -> None:
        stock = self._stock(
            total_received=0, total_returned=6, total_sold=2, qty_now=0
        )
        assert audit_cumulative_loss(stock) is None

    def test_truly_empty_sku_is_not_flagged(self) -> None:
        """Hech qanday harakat yo'q — bu ham natija bermaydi."""
        stock = self._stock(
            total_received=0, total_returned=0, total_sold=0, qty_now=0
        )
        assert audit_cumulative_loss(stock) is None

    def test_real_receipts_still_work(self) -> None:
        """Qabul ma'lumoti bor bo'lsa — audit ishlaydi."""
        result = audit_cumulative_loss(self._stock())
        assert result is not None and result.qty == 5

    def test_returns_exceeding_sales_blocks_result(self) -> None:
        """Sotilmagan tovar qaytmaydi — bunday raqam manba xatosi.

        Haqiqiy do'konda ko'rilgan (2026-08-07): 9 sotilgan, 23 "qaytgan".
        """
        stock = self._stock(total_sold=9, total_returned=23, total_received=9, qty_now=0)
        assert audit_cumulative_loss(stock) is None

    def test_outflow_exceeding_inflow_blocks_result(self) -> None:
        """Chiqim kirimdan ko'p — qabul ma'lumoti to'liq emas."""
        stock = self._stock(
            total_received=5, total_returned=0, total_sold=40, qty_now=10
        )
        assert audit_cumulative_loss(stock) is None

    def test_incomplete_history_blocks_result(self) -> None:
        """⚠️ Eng muhim himoya: tarix qirqilgan bo'lsa hisoblamaymiz.

        Aks holda "sotilgan" kam chiqib, bot mavjud bo'lmagan yo'qotishni
        ko'rsatadi va seller Uzumga noto'g'ri da'vo yuboradi.
        """
        assert audit_cumulative_loss(self._stock(history_complete=False)) is None

    def test_single_unit_not_reported(self) -> None:
        """To'plangan hisobda 1 dona farq — shovqin."""
        assert audit_cumulative_loss(self._stock(qty_now=44)) is None

    def test_details_mention_period_start(self) -> None:
        result = audit_cumulative_loss(self._stock())
        assert result is not None
        assert "15.01.2025" in result.details
        assert "100" in result.details and "55" in result.details


class TestLostReturn:
    """5.2 — qaytdi, lekin omborga tushmadi."""

    def _rec(self, **kwargs: object) -> ReturnRecord:
        base = {
            "sku": "SKU-1",
            "return_id": "R-100",
            "qty": 2,
            "returned_at": date(2026, 7, 1),
            "received_at": None,
            "unit_cost": Decimal("40000"),
        }
        base.update(kwargs)
        return ReturnRecord(**base)  # type: ignore[arg-type]

    def test_received_is_fine(self) -> None:
        """Omborga tushgan — muammo yo'q."""
        rec = self._rec(received_at=date(2026, 7, 5))
        assert audit_lost_return(rec, today=date(2026, 8, 1)) is None

    def test_too_early_to_claim(self) -> None:
        """14 kun to'lmagan — hali yo'lda bo'lishi mumkin."""
        rec = self._rec(returned_at=date(2026, 7, 20))
        assert audit_lost_return(rec, today=date(2026, 7, 30)) is None

    def test_exactly_at_grace_boundary(self) -> None:
        """Aynan 14-kunda — da'vo qilinadi (chegarani aniq belgilaymiz)."""
        rec = self._rec(returned_at=date(2026, 7, 1))
        result = audit_lost_return(rec, today=date(2026, 7, 15))
        assert result is not None

    def test_one_day_before_boundary(self) -> None:
        """13-kunda — hali erta."""
        rec = self._rec(returned_at=date(2026, 7, 1))
        assert audit_lost_return(rec, today=date(2026, 7, 14)) is None

    def test_lost_return_detected(self) -> None:
        rec = self._rec(qty=3)
        result = audit_lost_return(rec, today=date(2026, 8, 1))

        assert result is not None
        assert result.kind == DiscrepancyKind.LOST_RETURN
        assert result.qty == 3
        assert result.amount == Decimal("120000.00")
        assert result.status == DiscrepancyStatus.NEW

    def test_wrong_status_ignored(self) -> None:
        """Uzumda "qaytarildi" statusi bo'lmasa — audit qilmaymiz."""
        rec = self._rec(is_returned_status=False)
        assert audit_lost_return(rec, today=date(2026, 8, 1)) is None


class TestCommission:
    """5.3 — ortiqcha ushlangan komissiya."""

    def test_correct_commission(self) -> None:
        check = CommissionCheck(
            sku="SKU-1",
            sales_amount=Decimal("1000000"),
            charged_commission=Decimal("200000"),
            expected_pct=Decimal("20"),
        )
        assert check.expected_commission == Decimal("200000.00")
        assert audit_commission(check) is None

    def test_overcharge_detected(self) -> None:
        check = CommissionCheck(
            sku="SKU-1",
            sales_amount=Decimal("1000000"),
            charged_commission=Decimal("250000"),  # 5% ortiqcha
            expected_pct=Decimal("20"),
        )
        result = audit_commission(check)

        assert result is not None
        assert result.kind == DiscrepancyKind.OVER_COMMISSION
        assert result.amount == Decimal("50000.00")
        assert result.status == DiscrepancyStatus.NEW

    def test_small_diff_ignored_as_rounding(self) -> None:
        """1000 so'mgacha farq — yaxlitlash, da'vo qilmaymiz."""
        check = CommissionCheck(
            sku="SKU-1",
            sales_amount=Decimal("1000000"),
            charged_commission=Decimal("200500"),
            expected_pct=Decimal("20"),
        )
        assert audit_commission(check) is None

    def test_undercharge_is_not_our_problem(self) -> None:
        """Kam ushlangan — sellerning foydasiga, da'vo qilmaymiz."""
        check = CommissionCheck(
            sku="SKU-1",
            sales_amount=Decimal("1000000"),
            charged_commission=Decimal("150000"),
            expected_pct=Decimal("20"),
        )
        assert audit_commission(check) is None

    def test_fractional_percent(self) -> None:
        """Foiz kasrli bo'lishi mumkin (API 20.5 qaytarishi mumkin)."""
        check = CommissionCheck(
            sku="SKU-1",
            sales_amount=Decimal("333333"),
            charged_commission=Decimal("100000"),
            expected_pct=Decimal("20.5"),
        )
        result = audit_commission(check)
        assert result is not None
        assert result.amount == Decimal("31666.73")


class TestLogistics:
    """5.4 — logistika tarifi farqi."""

    def test_within_tolerance(self) -> None:
        """10% farq — chidamlilik doirasida."""
        check = LogisticsCheck(
            sku="SKU-1",
            expected_fee=Decimal("10000"),
            charged_fee=Decimal("11000"),
        )
        assert audit_logistics(check) is None

    def test_above_tolerance_flagged(self) -> None:
        """20% farq — tekshirish kerak."""
        check = LogisticsCheck(
            sku="SKU-1",
            expected_fee=Decimal("10000"),
            charged_fee=Decimal("12000"),
        )
        assert check.diff_pct == Decimal("20.00")

        result = audit_logistics(check)
        assert result is not None
        assert result.kind == DiscrepancyKind.LOGISTICS
        assert result.amount == Decimal("2000.00")

    def test_exactly_at_tolerance_is_ignored(self) -> None:
        """Aynan 15% — chegara ichida, da'vo qilinmaydi."""
        check = LogisticsCheck(
            sku="SKU-1",
            expected_fee=Decimal("10000"),
            charged_fee=Decimal("11500"),
        )
        assert check.diff_pct == Decimal("15.00")
        assert audit_logistics(check) is None

    def test_always_watching_never_claim(self) -> None:
        """Logistika eng noaniq audit — avtomatik da'vo qilmaymiz."""
        check = LogisticsCheck(
            sku="SKU-1",
            expected_fee=Decimal("10000"),
            charged_fee=Decimal("50000"),
        )
        result = audit_logistics(check)
        assert result is not None
        assert result.status == DiscrepancyStatus.WATCHING
        assert not result.is_claimable

    def test_cheaper_than_expected_ignored(self) -> None:
        check = LogisticsCheck(
            sku="SKU-1",
            expected_fee=Decimal("10000"),
            charged_fee=Decimal("5000"),
        )
        assert audit_logistics(check) is None

    def test_zero_expected_fee_does_not_crash(self) -> None:
        """Kutilgan 0 bo'lsa nolga bo'linish bo'lmasin."""
        check = LogisticsCheck(
            sku="SKU-1",
            expected_fee=Decimal("0"),
            charged_fee=Decimal("5000"),
        )
        result = audit_logistics(check)
        assert result is not None
        assert result.amount == Decimal("5000.00")

    def test_zero_both_is_fine(self) -> None:
        check = LogisticsCheck(
            sku="SKU-1",
            expected_fee=Decimal("0"),
            charged_fee=Decimal("0"),
        )
        assert audit_logistics(check) is None


class TestDimensionMismatch:
    """5.4 — kartochkadagi o'lcham Uzum o'lchaganidan farq qiladi."""

    def _check(self, **kwargs: object) -> DimensionCheck:
        base = {
            "sku": "SKU-1",
            "card_group": "SMALL",
            "actual_group": "MEDIUM",
            "logistics_paid": Decimal("120000"),
            "orders_count": 8,
        }
        base.update(kwargs)
        return DimensionCheck(**base)  # type: ignore[arg-type]

    def test_mismatch_detected(self) -> None:
        result = audit_dimension_mismatch(self._check())

        assert result is not None
        assert result.kind == DiscrepancyKind.LOGISTICS
        assert result.amount == Decimal("120000.00")
        assert "SMALL" in result.details and "MEDIUM" in result.details

    def test_same_group_is_fine(self) -> None:
        assert audit_dimension_mismatch(self._check(actual_group="SMALL")) is None

    def test_case_and_spaces_ignored(self) -> None:
        """« small » va «SMALL» — bir xil guruh, soxta alert bermasin."""
        check = self._check(card_group=" small ", actual_group="SMALL")
        assert audit_dimension_mismatch(check) is None

    def test_missing_data_is_silent(self) -> None:
        """Uzum guruhni bermasa — taqqoslab bo'lmaydi, jim turamiz."""
        assert audit_dimension_mismatch(self._check(actual_group=None)) is None
        assert audit_dimension_mismatch(self._check(card_group=None)) is None

    def test_always_watching_never_auto_claim(self) -> None:
        """Aniq tarif jadvali yo'q — avtomatik da'vo qilmaymiz (SPEC 9.5)."""
        result = audit_dimension_mismatch(self._check())
        assert result is not None
        assert result.status == DiscrepancyStatus.WATCHING
        assert not result.is_claimable

    def test_zero_logistics_still_reported(self) -> None:
        """Logistika to'lanmagan bo'lsa ham nomuvofiqlik ko'rsatiladi."""
        result = audit_dimension_mismatch(
            self._check(logistics_paid=Decimal("0"), orders_count=0)
        )
        assert result is not None
        assert result.amount == Decimal("0.00")


class TestCompensation:
    """5.5 — kompensatsiya sverkasi (raqobatchida yo'q)."""

    def test_fully_paid(self) -> None:
        check = CompensationCheck(
            sku="SKU-1",
            claimed_amount=Decimal("100000"),
            paid_amount=Decimal("100000"),
        )
        assert audit_compensation(check) is None

    def test_overpaid_is_fine(self) -> None:
        check = CompensationCheck(
            sku="SKU-1",
            claimed_amount=Decimal("100000"),
            paid_amount=Decimal("120000"),
        )
        assert audit_compensation(check) is None

    def test_nothing_paid(self) -> None:
        check = CompensationCheck(
            sku="SKU-1",
            claimed_amount=Decimal("100000"),
            paid_amount=Decimal("0"),
            qty=2,
        )
        result = audit_compensation(check)

        assert result is not None
        assert result.kind == DiscrepancyKind.MISSING_COMPENSATION
        assert result.amount == Decimal("100000.00")
        assert "umuman kelmagan" in result.details

    def test_partially_paid(self) -> None:
        check = CompensationCheck(
            sku="SKU-1",
            claimed_amount=Decimal("100000"),
            paid_amount=Decimal("60000"),
        )
        result = audit_compensation(check)

        assert result is not None
        assert result.amount == Decimal("40000.00")
        assert "to'liq kelmagan" in result.details


class TestTotals:
    """Sellerga ko'rsatiladigan summalar."""

    def _finding(self, amount: str, status: DiscrepancyStatus) -> Finding:
        return Finding(
            kind=DiscrepancyKind.LOST_STOCK,
            sku="SKU-1",
            qty=1,
            amount=Decimal(amount),
            status=status,
            details="",
        )

    def test_claimable_excludes_watching(self) -> None:
        """Kuzatuvdagilar va'da qilingan summaga kirmasligi kerak."""
        findings = [
            self._finding("100000", DiscrepancyStatus.NEW),
            self._finding("50000", DiscrepancyStatus.WATCHING),
            self._finding("25000", DiscrepancyStatus.NEW),
        ]
        assert total_claimable(findings) == Decimal("125000.00")
        assert total_watching(findings) == Decimal("50000.00")

    def test_empty_list(self) -> None:
        assert total_claimable([]) == Decimal("0.00")
        assert total_watching([]) == Decimal("0.00")
