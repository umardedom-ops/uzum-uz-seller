"""Sonni so'zga aylantirish testlari.

Pretenziyada summa noto'g'ri yozilsa — hujjat rad etiladi yoki
tortishuvga sabab bo'ladi.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.docs.numbers import amount_in_words, format_money, number_to_words


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, "nol"),
        (1, "bir"),
        (9, "to'qqiz"),
        (10, "o'n"),
        (11, "o'n bir"),
        (20, "yigirma"),
        (45, "qirq besh"),
        (99, "to'qson to'qqiz"),
        (100, "yuz"),               # "bir yuz" emas
        (101, "yuz bir"),
        (250, "ikki yuz ellik"),
        (999, "to'qqiz yuz to'qson to'qqiz"),
        (1000, "ming"),             # "bir ming" emas
        (1001, "ming bir"),
        (2000, "ikki ming"),
        (50000, "ellik ming"),
        (100000, "yuz ming"),
        (250000, "ikki yuz ellik ming"),
        (1000000, "bir million"),   # million'da "bir" saqlanadi
        (1234567, "bir million ikki yuz o'ttiz to'rt ming besh yuz oltmish yetti"),
        (1000000000, "bir milliard"),
    ],
)
def test_number_to_words(n: int, expected: str) -> None:
    assert number_to_words(n) == expected


def test_negative() -> None:
    assert number_to_words(-5) == "minus besh"


class TestAmountInWords:
    def test_whole_amount(self) -> None:
        assert amount_in_words(Decimal("250000.00")) == "ikki yuz ellik ming so'm"

    def test_with_tiyin(self) -> None:
        result = amount_in_words(Decimal("1500.50"))
        assert result == "ming besh yuz so'm ellik tiyin"

    def test_zero(self) -> None:
        assert amount_in_words(Decimal("0")) == "nol so'm"

    def test_realistic_loss(self) -> None:
        """Haqiqiy zarar summasi — 5 dona × 50 000."""
        assert amount_in_words(Decimal("250000.00")) == "ikki yuz ellik ming so'm"


class TestFormatMoney:
    def test_grouping(self) -> None:
        assert format_money(Decimal("1234567.89")) == "1 234 567,89"

    def test_small(self) -> None:
        assert format_money(Decimal("500.00")) == "500,00"

    def test_zero(self) -> None:
        assert format_money(Decimal("0")) == "0,00"
