"""Mini App `initData` imzosi testlari.

Bu **kirish nazorati**. Imzo noto'g'ri tekshirilsa har kim istalgan
sellerning do'konini, yo'qotishlarini va qoldig'ini ko'radi.
Raqobatchining (`@uzumplusbot`) aynan shu joyda xatosi bor edi —
login sifatida Telegram ID ishlatilardi, ya'ni tekshiruv yo'q edi.

Shuning uchun har bir hujum yo'li alohida sinaladi.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from urllib.parse import urlencode

import pytest

from app.db.base import utcnow
from app.services.telegram_webapp import (
    InitDataError,
    verify_init_data,
)

TOKEN = "123456:TEST-BOT-TOKEN"


def sign(fields: dict[str, str], token: str = TOKEN) -> str:
    """Telegram qanday imzolasa — shunday imzolaymiz."""
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": digest})


def make_init_data(
    *,
    telegram_id: int = 777001,
    auth_date: int | None = None,
    token: str = TOKEN,
    **extra: str,
) -> str:
    user = json.dumps(
        {"id": telegram_id, "first_name": "Elyor", "username": "elyor",
         "language_code": "uz"},
        separators=(",", ":"),
    )
    fields = {
        "user": user,
        "auth_date": str(auth_date if auth_date is not None else int(utcnow().timestamp())),
        "query_id": "AAF_test",
        **extra,
    }
    return sign(fields, token)


class TestValidSignature:
    def test_accepts_and_returns_user(self) -> None:
        user = verify_init_data(make_init_data(telegram_id=555), TOKEN)
        assert user.telegram_id == 555
        assert user.first_name == "Elyor"
        assert user.display_name == "Elyor"

    def test_extra_fields_do_not_break_it(self) -> None:
        """Telegram kelajakda yangi maydon qo'shsa ham imzo ishlashi kerak."""
        data = make_init_data(chat_type="private", start_param="qoldiq")
        assert verify_init_data(data, TOKEN).telegram_id == 777001


class TestForgery:
    """Soxta so'rovlar — hammasi rad etilishi shart."""

    def test_rejects_unsigned_data(self) -> None:
        """Imzosiz, oddiy qo'lda yozilgan satr."""
        raw = urlencode({"user": json.dumps({"id": 999}), "auth_date": "1"})
        with pytest.raises(InitDataError):
            verify_init_data(raw, TOKEN)

    def test_rejects_tampered_user_id(self) -> None:
        """❗ Asosiy hujum: imzo haqiqiy, lekin `id` boshqa odamniki."""
        data = make_init_data(telegram_id=111)
        forged = data.replace("111", "222")
        with pytest.raises(InitDataError, match="imzo"):
            verify_init_data(forged, TOKEN)

    def test_rejects_wrong_token(self) -> None:
        """Boshqa bot tokeni bilan imzolangan."""
        data = make_init_data(token="999:BOSHQA-BOT")
        with pytest.raises(InitDataError, match="imzo"):
            verify_init_data(data, TOKEN)

    def test_rejects_missing_hash(self) -> None:
        raw = urlencode({"user": json.dumps({"id": 1}), "auth_date": "1"})
        with pytest.raises(InitDataError, match="hash"):
            verify_init_data(raw, TOKEN)

    def test_rejects_empty(self) -> None:
        with pytest.raises(InitDataError):
            verify_init_data("", TOKEN)

    def test_rejects_when_bot_token_missing(self) -> None:
        """Sozlama yo'q bo'lsa hammani kiritib yubormaslik kerak."""
        with pytest.raises(InitDataError, match="BOT_TOKEN"):
            verify_init_data(make_init_data(), "")


class TestReplay:
    """Eski `initData` qayta ishlatilmasin."""

    def test_rejects_stale(self) -> None:
        old = int((utcnow() - timedelta(days=3)).timestamp())
        with pytest.raises(InitDataError, match="eskirgan"):
            verify_init_data(make_init_data(auth_date=old), TOKEN)

    def test_accepts_within_window(self) -> None:
        recent = int((utcnow() - timedelta(hours=2)).timestamp())
        assert verify_init_data(make_init_data(auth_date=recent), TOKEN)

    def test_rejects_future_date(self) -> None:
        """Kelajakdagi sana — soxta ma'lumot belgisi."""
        future = int((utcnow() + timedelta(hours=5)).timestamp())
        with pytest.raises(InitDataError, match="kelajakda"):
            verify_init_data(make_init_data(auth_date=future), TOKEN)

    def test_small_clock_skew_is_tolerated(self) -> None:
        """Telefon soati bir daqiqa oldinda bo'lishi normal."""
        skewed = int((utcnow() + timedelta(seconds=60)).timestamp())
        assert verify_init_data(make_init_data(auth_date=skewed), TOKEN)


class TestMalformed:
    """Buzuq ma'lumot — sabab bilan rad etilsin, yiqilmasin."""

    def test_rejects_bad_auth_date(self) -> None:
        data = make_init_data()
        with pytest.raises(InitDataError, match="auth_date"):
            verify_init_data(sign({"user": json.dumps({"id": 1}), "auth_date": "xxx"}), TOKEN)
        assert data  # ishlatilgani uchun

    def test_rejects_broken_user_json(self) -> None:
        with pytest.raises(InitDataError, match="JSON"):
            verify_init_data(
                sign({"user": "{buzuq", "auth_date": str(int(utcnow().timestamp()))}),
                TOKEN,
            )

    def test_rejects_missing_user(self) -> None:
        with pytest.raises(InitDataError, match="user"):
            verify_init_data(
                sign({"auth_date": str(int(utcnow().timestamp()))}), TOKEN
            )

    def test_rejects_user_without_id(self) -> None:
        with pytest.raises(InitDataError, match="user.id"):
            verify_init_data(
                sign({
                    "user": json.dumps({"first_name": "Elyor"}),
                    "auth_date": str(int(utcnow().timestamp())),
                }),
                TOKEN,
            )

    def test_error_always_says_why(self) -> None:
        """Har bir rad etishda sabab bo'lishi kerak — jim qolmaymiz."""
        with pytest.raises(InitDataError) as exc:
            verify_init_data("hash=abc", TOKEN)
        assert str(exc.value)


class TestMiniAppRoutes:
    """Marshrutlar darajasida kirish nazorati.

    Imzo moduli to'g'ri bo'lsa ham, marshrut uni chaqirmasa foyda yo'q.
    Shuning uchun oxirigacha tekshiriladi.
    """

    @pytest.fixture
    def client(self, monkeypatch: pytest.MonkeyPatch):
        from fastapi.testclient import TestClient

        from app.core.config import get_settings
        from app.web.click_api import create_app

        get_settings.cache_clear()
        monkeypatch.setenv("BOT_TOKEN", TOKEN)
        yield TestClient(create_app())
        get_settings.cache_clear()

    def test_shell_loads_without_auth(self, client) -> None:
        """Qobiq imzosiz ham ochiladi — u bo'sh, ma'lumot yo'q."""
        resp = client.get("/app")
        assert resp.status_code == 200
        assert "telegram-web-app.js" in resp.text
        # ❗ Qobiqda hech qanday do'kon ma'lumoti bo'lmasligi kerak
        assert "yo'qotish" not in resp.text.lower()

    def test_dashboard_without_header_is_refused(self, client) -> None:
        resp = client.post("/app/dashboard")
        assert "Kirish tasdiqlanmadi" in resp.text

    def test_dashboard_with_forged_signature_is_refused(self, client) -> None:
        """Boshqa token bilan imzolangan — do'kon ma'lumoti chiqmasligi shart."""
        forged = make_init_data(telegram_id=42, token="999:SOXTA")
        resp = client.post(
            "/app/dashboard", headers={"Authorization": "tma " + forged}
        )
        assert "Kirish tasdiqlanmadi" in resp.text
        assert "SKU" not in resp.text

    def test_refusal_does_not_leak_reason(self, client) -> None:
        """Soxta so'rov yuborayotgan odamga yo'l ko'rsatmaymiz.

        Sabab log'da qoladi, javobda emas.
        """
        resp = client.post("/app/dashboard", headers={"Authorization": "tma buzuq"})
        assert "imzo" not in resp.text.lower()
        assert "hash" not in resp.text.lower()

    def test_valid_signature_unknown_user_gets_gate(self, client) -> None:
        """Imzo haqiqiy, lekin obuna yo'q — ma'lumot berilmaydi."""
        resp = client.post(
            "/app/dashboard",
            headers={"Authorization": "tma " + make_init_data(telegram_id=987654)},
        )
        assert "Obuna" in resp.text
        assert "SKU" not in resp.text
