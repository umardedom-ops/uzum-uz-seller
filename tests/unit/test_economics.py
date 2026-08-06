"""Yunit-iqtisodiyot va ABC testlari.

Noto'g'ri foyda hisobi — sellerni noto'g'ri qarorga olib keladi
(zarar keltiruvchi tovarni ko'paytiradi yoki foydalisini tashlaydi).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.economics import SkuEconomics, classify_abc


def sku(**kwargs: object) -> SkuEconomics:
    base = {
        "sku": "SKU-1",
        "title": "Tovar",
        "qty_sold": 10,
        "revenue": Decimal("1000000"),
        "cost": Decimal("400000"),
        "commission": Decimal("200000"),
        "logistics": Decimal("100000"),
        "storage": Decimal("0"),
    }
    base.update(kwargs)
    return SkuEconomics(**base)  # type: ignore[arg-type]


class TestProfit:
    def test_computed_when_uzum_profit_absent(self) -> None:
        """Uzum foyda bermasa — o'zimiz hisoblaymiz."""
        row = sku()
        # 1 000 000 − 400 000 tannarx − (200 000 + 100 000) = 300 000
        assert row.profit == Decimal("300000.00")
        assert row.margin_pct == Decimal("30.0")

    def test_uzum_profit_preferred(self) -> None:
        """Uzum bergan `sellerProfit` aniqroq — o'shani ishlatamiz."""
        row = sku(reported_profit=Decimal("250000"))
        assert row.profit == Decimal("250000.00")

    def test_storage_subtracted_from_uzum_profit(self) -> None:
        """Saqlash xarajati Uzum foydasiga kirmaydi — biz ayiramiz."""
        row = sku(reported_profit=Decimal("250000"), storage=Decimal("50000"))
        assert row.profit == Decimal("200000.00")

    def test_profit_per_unit(self) -> None:
        assert sku().profit_per_unit == Decimal("30000.00")

    def test_no_sales_no_division_error(self) -> None:
        row = sku(qty_sold=0, revenue=Decimal("0"))
        assert row.profit_per_unit == Decimal("0")
        assert row.margin_pct == Decimal("0")


class TestFlags:
    def test_loss_making(self) -> None:
        """Komissiya va logistika tushumdan oshsa — zarar."""
        row = sku(commission=Decimal("800000"), logistics=Decimal("300000"))
        assert row.is_loss_making
        assert row.profit < 0

    def test_profitable_is_not_flagged(self) -> None:
        assert not sku().is_loss_making

    def test_unsold_is_not_loss_making(self) -> None:
        """Sotilmagan tovar zarar keltirmaydi — u o'lik yuk."""
        row = sku(qty_sold=0, revenue=Decimal("0"), stock_qty=50)
        assert not row.is_loss_making
        assert row.is_dead_stock

    def test_dead_stock_needs_stock(self) -> None:
        """Sotuv ham, qoldiq ham yo'q — bu o'lik yuk emas."""
        row = sku(qty_sold=0, revenue=Decimal("0"), stock_qty=0)
        assert not row.is_dead_stock


class TestAbc:
    def test_pareto_split(self) -> None:
        """80% daromad beruvchilar — A toifasi."""
        rows = [
            sku(sku="A1", revenue=Decimal("800")),
            sku(sku="B1", revenue=Decimal("150")),
            sku(sku="C1", revenue=Decimal("40")),
            sku(sku="C2", revenue=Decimal("10")),
        ]
        classify_abc(rows)
        by_sku = {r.sku: r.abc for r in rows}

        assert by_sku["A1"] == "A"
        assert by_sku["B1"] == "B"
        assert by_sku["C1"] == "C"
        assert by_sku["C2"] == "C"

    def test_revenue_share_computed(self) -> None:
        rows = [
            sku(sku="A1", revenue=Decimal("750")),
            sku(sku="B1", revenue=Decimal("250")),
        ]
        classify_abc(rows)
        assert rows[0].revenue_share == Decimal("75.0")
        assert rows[1].revenue_share == Decimal("25.0")

    def test_zero_revenue_all_c(self) -> None:
        """Hech narsa sotilmagan bo'lsa — hammasi C, nolga bo'linish yo'q."""
        rows = [sku(sku="X", revenue=Decimal("0")), sku(sku="Y", revenue=Decimal("0"))]
        classify_abc(rows)
        assert all(r.abc == "C" for r in rows)
        assert all(r.revenue_share == Decimal("0") for r in rows)

    def test_single_product_is_a(self) -> None:
        rows = [sku(revenue=Decimal("500"))]
        classify_abc(rows)
        assert rows[0].abc == "A"

    def test_empty_list_does_not_crash(self) -> None:
        classify_abc([])


class TestSummaryTotals:
    def test_totals(self) -> None:
        from app.services.economics import EconomicsSummary

        summary = EconomicsSummary(
            rows=[
                sku(sku="A", revenue=Decimal("1000000")),
                sku(sku="B", revenue=Decimal("500000"), commission=Decimal("100000")),
            ],
            period_from=date(2026, 7, 1),
            period_to=date(2026, 7, 31),
        )
        assert summary.revenue == Decimal("1500000.00")
        assert summary.commission == Decimal("300000.00")
        assert summary.profit > 0
