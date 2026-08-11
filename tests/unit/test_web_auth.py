"""Web-kabinet kirish xavfsizligi.

Raqobatchida token URL'da ochiq yuradi va login = Telegram ID. Bizda
bir martalik token + cookie. Quyidagi testlar aynan shu kafolatlarni
ushlab turadi — buzilsa, mijoz ma'lumoti begonaga ochiladi.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.db.base import session_scope, utcnow
from app.db.models import TokenKind, User, WebToken
from app.services import web_auth

TG = 6001


async def _seed(telegram_id: int = TG, *, blocked: bool = False) -> None:
    async with session_scope() as s:
        s.add(User(telegram_id=telegram_id, is_blocked=blocked))


class TestLoginToken:
    async def test_redeem_gives_session(self) -> None:
        await _seed()
        token = await web_auth.issue_login_token(TG)

        session_token = await web_auth.redeem_login_token(token)
        assert session_token and session_token != token

        user = await web_auth.user_for_session(session_token)
        assert user is not None and user.telegram_id == TG

    async def test_single_use(self) -> None:
        """Havola nusxalansa ham ikkinchi marta ishlamaydi."""
        await _seed()
        token = await web_auth.issue_login_token(TG)

        assert await web_auth.redeem_login_token(token) is not None
        assert await web_auth.redeem_login_token(token) is None

    async def test_expired_rejected(self) -> None:
        await _seed()
        token = await web_auth.issue_login_token(TG)

        async with session_scope() as s:
            row = await s.scalar(
                select(WebToken).where(WebToken.kind == TokenKind.LOGIN)
            )
            row.expires_at = utcnow() - timedelta(minutes=1)

        assert await web_auth.redeem_login_token(token) is None

    async def test_new_link_kills_old(self) -> None:
        """Yangi havola so'ralsa — eskisi ishlamaydi."""
        await _seed()
        first = await web_auth.issue_login_token(TG)
        second = await web_auth.issue_login_token(TG)

        assert await web_auth.redeem_login_token(first) is None
        assert await web_auth.redeem_login_token(second) is not None

    async def test_garbage_rejected(self) -> None:
        await _seed()
        assert await web_auth.redeem_login_token("soxta-token") is None
        assert await web_auth.redeem_login_token("") is None


class TestSession:
    async def test_unknown_session_rejected(self) -> None:
        assert await web_auth.user_for_session("yoq") is None
        assert await web_auth.user_for_session(None) is None

    async def test_blocked_user_rejected(self) -> None:
        """Bloklangan foydalanuvchi sessiyasi ishlamaydi."""
        await _seed(6002, blocked=True)
        token = await web_auth.issue_login_token(6002)
        session_token = await web_auth.redeem_login_token(token)

        assert await web_auth.user_for_session(session_token) is None

    async def test_logout_revokes(self) -> None:
        await _seed(6003)
        token = await web_auth.issue_login_token(6003)
        session_token = await web_auth.redeem_login_token(token)

        await web_auth.revoke_session(session_token)
        assert await web_auth.user_for_session(session_token) is None


class TestStorage:
    async def test_raw_token_never_stored(self) -> None:
        """Baza o'g'irlansa ham sessiyani tiklab bo'lmasin."""
        await _seed(6004)
        token = await web_auth.issue_login_token(6004)

        async with session_scope() as s:
            hashes = [r.token_hash for r in await s.scalars(select(WebToken))]

        assert token not in hashes
        assert all(len(h) == 64 for h in hashes)  # sha256 hex

    async def test_purge_removes_expired(self) -> None:
        await _seed(6005)
        await web_auth.issue_login_token(6005)

        async with session_scope() as s:
            row = await s.scalar(select(WebToken))
            row.expires_at = utcnow() - timedelta(days=1)

        assert await web_auth.purge_expired() >= 1
