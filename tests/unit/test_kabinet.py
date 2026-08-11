"""Web-kabinet sahifalari — HTTP darajasida.

Eng muhimi: sessiyasiz kirish yopiq va token URL'da qolmaydi.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.base import session_scope
from app.db.models import Shop, User
from app.services import web_auth
from app.web.click_api import create_app

TG = 7001


def _client() -> TestClient:
    # Redirect'ni o'zimiz tekshiramiz (cookie va manzil muhim)
    return TestClient(create_app(), follow_redirects=False)


async def _seed(*, with_shop: bool = True) -> None:
    async with session_scope() as s:
        user = User(telegram_id=TG, full_name="Test Seller")
        s.add(user)
        await s.flush()
        if with_shop:
            s.add(
                Shop(
                    user_id=user.id, uzum_shop_id="7973",
                    title="AZIKO", is_active=True,
                )
            )


class TestGuest:
    def test_dashboard_requires_login(self) -> None:
        response = _client().get("/kabinet")
        assert response.status_code == 401
        assert "Kirish kerak" in response.text

    def test_bad_token_rejected(self) -> None:
        response = _client().get("/kabinet/kirish?token=soxta")
        assert response.status_code == 401
        assert "eskirgan" in response.text.lower()

    def test_fake_cookie_rejected(self) -> None:
        client = _client()
        client.cookies.set(web_auth.COOKIE_NAME, "soxta-sessiya")
        assert client.get("/kabinet").status_code == 401


class TestLogin:
    async def test_login_sets_cookie_and_redirects(self) -> None:
        """Token cookie'ga almashadi va URL'da qolmaydi."""
        await _seed()
        token = await web_auth.issue_login_token(TG)

        response = _client().get(f"/kabinet/kirish?token={token}")

        assert response.status_code == 303
        # URL'da token yo'q — brauzer tarixiga tushmaydi
        assert response.headers["location"] == "/kabinet"
        assert token not in response.headers["location"]

        cookie = response.headers.get("set-cookie", "")
        assert web_auth.COOKIE_NAME in cookie
        assert "HttpOnly" in cookie   # JS o'qiy olmaydi
        assert "Secure" in cookie     # faqat HTTPS
        assert "SameSite=lax" in cookie.replace("samesite", "SameSite")

    async def test_dashboard_after_login(self) -> None:
        await _seed()
        token = await web_auth.issue_login_token(TG)
        session_token = await web_auth.redeem_login_token(token)

        client = _client()
        client.cookies.set(web_auth.COOKIE_NAME, session_token)
        response = client.get("/kabinet")

        assert response.status_code == 200
        assert "AZIKO" in response.text
        assert "Chiqish" in response.text

    async def test_without_shop_shows_hint(self) -> None:
        await _seed(with_shop=False)
        token = await web_auth.issue_login_token(TG)
        session_token = await web_auth.redeem_login_token(token)

        client = _client()
        client.cookies.set(web_auth.COOKIE_NAME, session_token)
        response = client.get("/kabinet")

        assert response.status_code == 200
        assert "ulanmagan" in response.text.lower()

    async def test_logout_clears(self) -> None:
        await _seed()
        token = await web_auth.issue_login_token(TG)
        session_token = await web_auth.redeem_login_token(token)

        client = _client()
        client.cookies.set(web_auth.COOKIE_NAME, session_token)
        response = client.get("/kabinet/chiqish")

        assert response.status_code == 303
        # Sessiya bazadan ham o'chgan
        assert await web_auth.user_for_session(session_token) is None
