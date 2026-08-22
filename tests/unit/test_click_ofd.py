"""Click fiskalizatsiyasi (OFD) testlari.

Bu soliq oqimi. Uchta talabdan bittasi buzilsa chek **rad etiladi** va
buni faqat oylar o'tib soliq masalasi chiqqanda bilib qolish mumkin:

  1. `CommissionInfo` (PINFL yoki TIN) har pozitsiyada bo'lishi
  2. narxlar **tiyinda**
  3. pozitsiyalar yig'indisi `received_card` ga **aniq** teng bo'lishi

Shuning uchun uchalasi ham alohida tekshiriladi.
"""
from __future__ import annotations

import hashlib

import pytest

from app.core.config import Settings
from app.services.click_ofd import (
    TIYIN,
    auth_header,
    build_items,
    check_ready,
    commission_info,
    totals_match,
    vat_amount,
)

SECRET = "test-secret-key"


def make_settings(**overrides: object) -> Settings:
    """To'liq sozlangan YaTT holati — testlar shundan chetlashadi."""
    base: dict[str, object] = {
        "BOT_TOKEN": "1:test",
        "CLICK_SERVICE_ID": "109666",
        "CLICK_MERCHANT_ID": "63121",
        "CLICK_SECRET_KEY": SECRET,
        "CLICK_MERCHANT_USER_ID": "12345",
        "CLICK_OFD_PINFL": "51403035960091",
        "CLICK_OFD_SPIC": "10305001001000000",
        "CLICK_OFD_PACKAGE_CODE": "1500123",
        "CLICK_OFD_VAT_PERCENT": 0,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class TestAuthHeader:
    """Merchant API — SHA1, Shop API dagi MD5 emas."""

    def test_formula(self) -> None:
        settings = make_settings()
        expected = hashlib.sha1(f"1700000000{SECRET}".encode()).hexdigest()
        assert auth_header(settings, timestamp=1700000000) == f"12345:{expected}:1700000000"

    def test_changes_with_timestamp(self) -> None:
        settings = make_settings()
        first = auth_header(settings, timestamp=1700000000)
        second = auth_header(settings, timestamp=1700000001)
        assert first != second


class TestCommissionInfo:
    """Busiz HAR BIR chek rad etiladi."""

    def test_yatt_uses_pinfl(self) -> None:
        assert commission_info(make_settings()) == {"PINFL": "51403035960091"}

    def test_company_uses_tin(self) -> None:
        settings = make_settings(CLICK_OFD_PINFL="", CLICK_OFD_TIN="123456789")
        assert commission_info(settings) == {"TIN": "123456789"}

    def test_pinfl_wins_when_both_set(self) -> None:
        """Ikkalasi ham bo'lsa — YaTT identifikatori. Bu holat sozlama
        xatosi, lekin jimgina ikkalasini yuborishdan ko'ra aniq bittasi."""
        settings = make_settings(CLICK_OFD_TIN="123456789")
        assert commission_info(settings) == {"PINFL": "51403035960091"}

    def test_none_when_missing(self) -> None:
        settings = make_settings(CLICK_OFD_PINFL="", CLICK_OFD_TIN="")
        assert commission_info(settings) is None

    def test_always_present_in_items(self) -> None:
        items = build_items(make_settings(), name="Obuna", amount_soum=149_000)
        for item in items:
            assert item["CommissionInfo"] is not None


class TestPricesInTiyin:
    """So'm × 100. Xato bo'lsa chek nol summa bilan rad etiladi."""

    def test_price_multiplied(self) -> None:
        items = build_items(make_settings(), name="Obuna", amount_soum=149_000)
        assert items[0]["Price"] == 149_000 * TIYIN == 14_900_000

    def test_price_never_zero(self) -> None:
        items = build_items(make_settings(), name="Obuna", amount_soum=1)
        assert items[0]["Price"] > 0


class TestVat:
    """QQS narx ICHIDA — ustiga qo'shilmaydi."""

    def test_zero_for_simplified_yatt(self) -> None:
        """Soddalashtirilgan tartibdagi YaTT — QQS yo'q."""
        assert vat_amount(14_900_000, 0) == 0

    def test_twelve_percent_formula(self) -> None:
        """Skill'dagi `total * 12 / 112`."""
        assert vat_amount(112_000, 12) == 12_000

    def test_vat_less_than_total(self) -> None:
        total = 14_900_000
        assert 0 < vat_amount(total, 12) < total

    def test_item_uses_configured_percent(self) -> None:
        items = build_items(
            make_settings(CLICK_OFD_VAT_PERCENT=12), name="Obuna", amount_soum=149_000
        )
        assert items[0]["VATPercent"] == 12
        assert items[0]["VAT"] == vat_amount(14_900_000, 12)


class TestTotals:
    """Bitta tiyin farq — chek rad etiladi."""

    def test_single_item_matches(self) -> None:
        items = build_items(make_settings(), name="Obuna", amount_soum=149_000)
        assert totals_match(items, 149_000 * TIYIN)

    def test_one_tiyin_off_is_rejected(self) -> None:
        items = build_items(make_settings(), name="Obuna", amount_soum=149_000)
        assert not totals_match(items, 149_000 * TIYIN + 1)


class TestCheckReady:
    """Sozlama to'liq bo'lmasa — SABAB aytiladi, jim qolinmaydi."""

    def test_complete_config_is_ready(self) -> None:
        assert check_ready(make_settings()) == ""

    @pytest.mark.parametrize(
        ("override", "expected_fragment"),
        [
            ({"CLICK_MERCHANT_USER_ID": ""}, "CLICK_MERCHANT_USER_ID"),
            ({"CLICK_OFD_SPIC": ""}, "CLICK_OFD_SPIC"),
            ({"CLICK_OFD_PACKAGE_CODE": ""}, "CLICK_OFD_PACKAGE_CODE"),
            ({"CLICK_OFD_PINFL": ""}, "CLICK_OFD_PINFL"),
        ],
    )
    def test_names_the_missing_key(
        self, override: dict[str, object], expected_fragment: str
    ) -> None:
        reason = check_ready(make_settings(**override))
        assert reason, "sabab bo'sh qolmasligi kerak"
        assert expected_fragment in reason

    def test_ofd_enabled_flag_matches(self) -> None:
        assert make_settings().ofd_enabled is True
        assert make_settings(CLICK_OFD_SPIC="").ofd_enabled is False


class TestAfterPaymentNeverRaises:
    """To'lovdan keyingi qadam yiqilsa ham webhook 500 qaytarmasligi kerak.

    Click 500 ni «to'lov o'tmadi» deb o'qiydi va muvaffaqiyatli to'lovni
    QAYTARIB YUBORADI. Ya'ni chek yoki xabar xatosi mijozni puldan ham,
    obunadan ham ayirishi mumkin edi.
    """

    @pytest.mark.asyncio
    async def test_failing_step_is_swallowed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.web import click_api

        async def boom(_: str) -> None:
            raise RuntimeError("baza yiqildi")

        monkeypatch.setattr(click_api, "_fiscalize", boom)
        monkeypatch.setattr(click_api, "_notify_client", boom)

        # Istisno chiqmasligi kerak — chiqsa test shu yerda yiqiladi
        await click_api._after_payment("42")

    @pytest.mark.asyncio
    async def test_second_step_runs_when_first_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Chek yiqilsa ham mijoz xabarni olishi kerak."""
        from app.web import click_api

        called: list[str] = []

        async def boom(_: str) -> None:
            raise RuntimeError("chek yiqildi")

        async def ok(trans_id: str) -> None:
            called.append(trans_id)

        monkeypatch.setattr(click_api, "_fiscalize", boom)
        monkeypatch.setattr(click_api, "_notify_client", ok)

        await click_api._after_payment("42")
        assert called == ["42"]
