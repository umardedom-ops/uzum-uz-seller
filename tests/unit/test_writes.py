"""Uzumga YOZISH klienti testlari.

Eng muhim xulq: bayroq o'chiq bo'lsa jonli POST **yuborilmaydi**
(WritesDisabledError), yoqilganda esa aynan bitta POST ketadi. Bu
audit'ni GET'da saqlash kafolatining bir qismi (CLAUDE.md qoida #1).
"""
from __future__ import annotations

import pytest

from app.uzum.models import AuthType, SessionCredentials
from app.uzum.writes import (
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
    def test_shape_matches_response_schema(self) -> None:
        payload = _build_stock_payload(
            [StockUpdate("763221", 30), StockUpdate("9", 0)]
        )
        assert payload == {
            "skus": [
                {"skuId": "763221", "amount": 30},
                {"skuId": "9", "amount": 0},
            ]
        }


class TestGuard:
    async def test_disabled_by_default_raises_and_sends_nothing(self) -> None:
        """Standart holatda bayroq o'chiq — jonli yozish bo'lmaydi."""
        http = _SpyHTTP()
        with pytest.raises(WritesDisabledError):
            await _client(http).set_fbs_stock("7973", [StockUpdate("1", 5)])
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

        await _client(http).set_fbs_stock("7973", [StockUpdate("763221", 30)])

        assert len(http.calls) == 1
        call = http.calls[0]
        assert call["path"] == "/v2/fbs/sku/stocks"
        assert call["rate_key"] == "7973"
        assert call["json"] == {"skus": [{"skuId": "763221", "amount": 30}]}
        # Bearer prefiksisiz (docs/api-inventory.md §1)
        assert call["headers"]["Authorization"] == "tok"
