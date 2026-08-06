"""Onboarding kirish ma'lumotlarini tekshirish testlari.

Seller nimani yuborishini oldindan bilmaymiz — kalit, raqam, URL yoki
tasodifiy matn. Bu funksiyalar birinchi himoya chizig'i.
"""
from __future__ import annotations

import pytest

from app.services.onboarding import looks_like_api_key, parse_shop_ids


class TestLooksLikeApiKey:
    """Uzumga bekorga so'rov yubormaslik uchun oldindan filtr."""

    @pytest.mark.parametrize(
        "key",
        [
            "TEST0000FAKE0000KEY0000NOTREAL0000EXAMPLE00=",  # haqiqiy format
            "abcdefghijklmnopqrstuvwxyz123456",
            "token_with-dashes.and_underscores123",
        ],
    )
    def test_accepts_key_shaped_input(self, key: str) -> None:
        assert looks_like_api_key(key)

    def test_accepts_with_surrounding_spaces(self) -> None:
        """Nusxalashda probel qo'shilib qolishi odatiy hol."""
        assert looks_like_api_key("  TEST0000FAKE0000KEY0000NOTREAL0000EXAMPLE00=  ")

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "salom",              # juda qisqa
            "62866",              # do'kon ID, kalit emas
            "kalitim yo'q hozir",  # probelli jumla
            "менда калит йўқ",     # kirill matn
        ],
    )
    def test_rejects_non_key(self, text: str) -> None:
        assert not looks_like_api_key(text)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Oddiy holat — videodagi namuna
        ("62866", ["62866"]),
        ("  62866  ", ["62866"]),
        # Bir nechta do'kon
        ("62866, 71024", ["62866", "71024"]),
        ("62866 71024", ["62866", "71024"]),
        ("62866\n71024", ["62866", "71024"]),
        # Dublikat tashlanadi, tartib saqlanadi
        ("62866, 62866, 71024", ["62866", "71024"]),
        # To'liq URL yuborilsa ham ishlaydi
        ("https://seller.uzum.uz/seller/62866/products/all", ["62866"]),
        ("seller.uzum.uz/seller/62866/products/all", ["62866"]),
    ],
)
def test_parse_valid(raw: str, expected: list[str]) -> None:
    assert parse_shop_ids(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "salom",
        "do'kon yo'q",
        "12",          # juda qisqa
        "12345678901",  # juda uzun
    ],
)
def test_parse_invalid(raw: str) -> None:
    assert parse_shop_ids(raw) == []
