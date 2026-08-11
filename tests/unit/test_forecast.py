"""Uzumning tugash prognozi bizning o'rtachadan ustun turadi.

`forecastOutOfStock` aksiya va mavsumni hisobga oladi, shuning uchun
`qoldiq / kunlik_o'rtacha` formulasidan aniqroq.
"""
from __future__ import annotations

from decimal import Decimal

from app.docs.stock import StockRow


def _row(**kw) -> StockRow:
    base = dict(
        sku="1", barcode="b", title="T", fbo_qty=100, fbs_qty=0,
        sold_total=0, avg_daily_sales=Decimal("10"), price=None, status=None,
    )
    base.update(kw)
    return StockRow(**base)


class TestForecastWins:
    def test_uzum_forecast_preferred(self) -> None:
        """100 dona / 10 kunlik = 10 kun, lekin Uzum 3 kun deydi → 3."""
        row = _row(forecast_days=3)
        assert row.days_left == 3

    def test_falls_back_to_average(self) -> None:
        row = _row(forecast_days=None)
        assert row.days_left == 10

    def test_zero_forecast_is_respected(self) -> None:
        """0 kun — haqiqiy qiymat (bugun tugaydi), None emas."""
        row = _row(forecast_days=0)
        assert row.days_left == 0

    def test_negative_forecast_ignored(self) -> None:
        """Uzum manfiy bersa — ishonmaymiz, o'rtachaga qaytamiz."""
        row = _row(forecast_days=-5)
        assert row.days_left == 10

    def test_no_data_returns_none(self) -> None:
        """Ikkalasi ham yo'q — soxta raqam ko'rsatmaymiz."""
        row = _row(forecast_days=None, avg_daily_sales=None)
        assert row.days_left is None


class TestAttention:
    def test_forecast_triggers_attention(self) -> None:
        """Uzum «3 kun» desa — diqqat talab qiladi, o'rtacha 10 bo'lsa ham."""
        assert _row(forecast_days=3).needs_attention

    def test_healthy_stock_is_calm(self) -> None:
        assert not _row(forecast_days=30).needs_attention
