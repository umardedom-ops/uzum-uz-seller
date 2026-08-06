"""Click to'lov integratsiyasi testlari (docs.click.uz/shop-api).

Bu pul oqimi. Imzo formulasi yoki xato kodi noto'g'ri bo'lsa:
  * to'lovlar o'tmaydi (daromad yo'q), yoki
  * soxta so'rov obunani bepul ochib beradi.

Formulalar hujjatdan aynan olingan.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.services.click import (
    ClickError,
    ClickRequest,
    build_sign,
    payment_link,
    response,
    verify_sign,
)

SECRET = "test-secret-key"


def make_request(**kwargs: object) -> ClickRequest:
    base = {
        "click_trans_id": "1234567",
        "service_id": "107646",
        "click_paydoc_id": "999",
        "merchant_trans_id": "42",
        "amount": "149000.00",
        "action": "0",
        "sign_time": "2026-08-06 16:45:00",
        "sign_string": "",
    }
    base.update(kwargs)
    return ClickRequest(**base)  # type: ignore[arg-type]


class TestSignature:
    def test_prepare_formula(self) -> None:
        """md5(click_trans_id + service_id + SECRET + merchant_trans_id
        + amount + action + sign_time)"""
        req = make_request(action="0")
        expected = hashlib.md5(
            f"1234567107646{SECRET}42149000.0002026-08-06 16:45:00".encode()
        ).hexdigest()
        assert build_sign(req, SECRET) == expected

    def test_complete_formula_includes_prepare_id(self) -> None:
        """Complete'da `merchant_prepare_id` ham qatnashadi."""
        req = make_request(action="1", merchant_prepare_id="42")
        expected = hashlib.md5(
            f"1234567107646{SECRET}4242149000.0012026-08-06 16:45:00".encode()
        ).hexdigest()
        assert build_sign(req, SECRET) == expected

    def test_prepare_and_complete_differ(self) -> None:
        """Ikkala bosqichda imzo boshqacha — aralashib ketmasin."""
        prepare = make_request(action="0")
        complete = make_request(action="1", merchant_prepare_id="42")
        assert build_sign(prepare, SECRET) != build_sign(complete, SECRET)

    def test_verify_accepts_valid(self) -> None:
        req = make_request()
        assert verify_sign(replace(req, sign_string=build_sign(req, SECRET)), SECRET)

    def test_verify_rejects_tampered_amount(self) -> None:
        """Summani o'zgartirgan so'rov o'tmasligi kerak."""
        req = make_request()
        sign = build_sign(req, SECRET)
        tampered = replace(req, amount="1000.00", sign_string=sign)
        assert not verify_sign(tampered, SECRET)

    def test_verify_rejects_tampered_transaction(self) -> None:
        """Boshqa odamning to'lovini o'ziga yozib olib bo'lmasin."""
        req = make_request()
        sign = build_sign(req, SECRET)
        tampered = replace(req, merchant_trans_id="99", sign_string=sign)
        assert not verify_sign(tampered, SECRET)

    def test_verify_rejects_wrong_secret(self) -> None:
        req = make_request()
        signed = replace(req, sign_string=build_sign(req, SECRET))
        assert not verify_sign(signed, "boshqa-kalit")

    def test_verify_rejects_empty_sign(self) -> None:
        assert not verify_sign(make_request(sign_string=""), SECRET)

    def test_verify_accepts_uppercase_sign(self) -> None:
        """Ba'zi tizimlar imzoni katta harfda yuboradi."""
        req = make_request()
        signed = replace(req, sign_string=build_sign(req, SECRET).upper())
        assert verify_sign(signed, SECRET)


class TestResponse:
    def test_success_prepare(self) -> None:
        payload = response(
            ClickError.SUCCESS,
            click_trans_id="123",
            merchant_trans_id="42",
            prepare_id=42,
        )
        assert payload["error"] == 0
        assert payload["error_note"] == "Success"
        assert payload["merchant_prepare_id"] == 42

    def test_success_complete(self) -> None:
        payload = response(ClickError.SUCCESS, confirm_id=42)
        assert payload["merchant_confirm_id"] == 42

    def test_error_has_note(self) -> None:
        payload = response(ClickError.SIGN_CHECK_FAILED)
        assert payload["error"] == -1
        assert payload["error_note"] == "SIGN CHECK FAILED!"

    @pytest.mark.parametrize(
        ("code", "note"),
        [
            (ClickError.INCORRECT_AMOUNT, "Incorrect parameter amount"),
            (ClickError.ALREADY_PAID, "Already paid"),
            (ClickError.USER_NOT_FOUND, "User does not exist"),
            (ClickError.TRANSACTION_NOT_FOUND, "Transaction does not exist"),
            (ClickError.TRANSACTION_CANCELLED, "Transaction cancelled"),
        ],
    )
    def test_documented_notes(self, code: ClickError, note: str) -> None:
        """Matnlar hujjatdagidek bo'lishi kerak."""
        assert response(code)["error_note"] == note


class TestPaymentLink:
    def test_contains_required_params(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core.config import Settings, get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("CLICK_SERVICE_ID", "107646")
        monkeypatch.setenv("CLICK_MERCHANT_ID", "63121")
        monkeypatch.setenv("CLICK_SECRET_KEY", SECRET)

        link = payment_link(payment_id=42, amount=149_000)

        assert "service_id=107646" in link
        assert "merchant_id=63121" in link
        assert "amount=149000" in link
        assert "transaction_param=42" in link  # bizning payments.id
        assert link.startswith("https://my.click.uz/services/pay")

        get_settings.cache_clear()
        assert Settings is not None  # import ishlatilgani uchun


class TestWebhookEndpoints:
    """Manzillar mavjudligi va imzo tekshiruvi."""

    @pytest.fixture
    def client(self) -> TestClient:
        from app.web.click_api import create_app

        return TestClient(create_app())

    def test_health(self, client: TestClient) -> None:
        assert client.get("/health").json()["status"] == "ok"

    def test_prepare_rejects_bad_signature(self, client: TestClient) -> None:
        """Imzo xato — bazaga umuman murojaat qilinmaydi."""
        resp = client.post(
            "/click/prepare",
            data={
                "click_trans_id": "1",
                "service_id": "107646",
                "merchant_trans_id": "42",
                "amount": "149000",
                "action": "0",
                "sign_time": "2026-08-06 16:45:00",
                "sign_string": "yaroqsiz",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["error"] == -1

    def test_complete_rejects_bad_signature(self, client: TestClient) -> None:
        resp = client.post(
            "/click/complete",
            data={
                "click_trans_id": "1",
                "service_id": "107646",
                "merchant_trans_id": "42",
                "merchant_prepare_id": "42",
                "amount": "149000",
                "action": "1",
                "sign_time": "2026-08-06 16:45:00",
                "sign_string": "yaroqsiz",
            },
        )
        assert resp.json()["error"] == -1
