"""Uzumga YOZISH klienti testlari.

Eng muhim xulq: bayroq o'chiq bo'lsa jonli POST **yuborilmaydi**
(WritesDisabledError), yoqilganda esa aynan bitta POST ketadi. Bu
audit'ni GET'da saqlash kafolatining bir qismi (CLAUDE.md qoida #1).
"""
from __future__ import annotations

import pytest

from app.uzum.models import AuthType, SessionCredentials
from app.uzum.writes import (
    MissingBarcodeError,
    StockUpdate,
    UzumWriteClient,
    WritesDisabledError,
    _build_stock_payload,
)


class _SpyHTTP:
    """post() chaqiruvlarini yozib boradi — jonli so'rov yubormaydi."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def post(self, path, *, rate_key, json=None, headers=None):
        self.calls.append(
            {"path": path, "rate_key": rate_key, "json": json, "headers": headers}
        )
        return {"ok": True}


def _client(http: _SpyHTTP) -> UzumWriteClient:
    return UzumWriteClient(
        http, SessionCredentials(auth_type=AuthType.API, secret="tok")
    )


class TestPayload:
    def test_shape_matches_openapi_spec(self) -> None:
        """Sxema spetsifikatsiyadan (2026-08-11) — taxmin emas.

        `SkuStockUpdateApiRequestDto`: `skuAmountList` ichida `barcode`
        (majburiy) va `amount`. `skuId` yuborilmaydi — u ixtiyoriy.
        """
        payload = _build_stock_payload(
            [
                StockUpdate(barcode="1000113258397", amount=30, sku_id="763221"),
                StockUpdate(barcode="1000113258398", amount=0),
            ]
        )
        assert payload == {
            "skuAmountList": [
                {"barcode": "1000113258397", "amount": 30},
                {"barcode": "1000113258398", "amount": 0},
            ]
        }


class TestValidation:
    def test_barcode_required(self) -> None:
        """Shtrix kodsiz — darhol to'xtaymiz (Uzum jimgina rad etardi)."""
        with pytest.raises(MissingBarcodeError):
            StockUpdate(barcode="", amount=5, sku_id="763221")

    def test_negative_amount_rejected(self) -> None:
        with pytest.raises(ValueError):
            StockUpdate(barcode="1000113258397", amount=-1)

    def test_zero_is_allowed(self) -> None:
        """0 — haqiqiy qiymat (tovar tugadi), xato emas."""
        assert StockUpdate(barcode="1000113258397", amount=0).amount == 0


class TestGuard:
    async def test_disabled_by_default_raises_and_sends_nothing(self) -> None:
        """Standart holatda bayroq o'chiq — jonli yozish bo'lmaydi."""
        http = _SpyHTTP()
        with pytest.raises(WritesDisabledError):
            await _client(http).set_fbs_stock(
                "7973", [StockUpdate(barcode="1000113258397", amount=5)]
            )
        assert http.calls == []

    async def test_empty_updates_is_noop(self) -> None:
        http = _SpyHTTP()
        result = await _client(http).set_fbs_stock("7973", [])
        assert result is None
        assert http.calls == []

    async def test_enabled_sends_exactly_one_post(self, monkeypatch) -> None:
        http = _SpyHTTP()

        class _Settings:
            uzum_writes_enabled = True

        monkeypatch.setattr("app.uzum.writes.get_settings", lambda: _Settings())

        await _client(http).set_fbs_stock(
            "7973", [StockUpdate(barcode="1000113258397", amount=30, sku_id="763221")]
        )

        assert len(http.calls) == 1
        call = http.calls[0]
        assert call["path"] == "/v2/fbs/sku/stocks"
        assert call["rate_key"] == "7973"
        assert call["json"] == {
            "skuAmountList": [{"barcode": "1000113258397", "amount": 30}]
        }
        # Bearer prefiksisiz (docs/api-inventory.md §1)
        assert call["headers"]["Authorization"] == "tok"
