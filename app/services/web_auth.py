"""Web-kabinetga kirish — parolsiz, botdagi bir martalik havola orqali.

Nima uchun parol yo'q: seller allaqachon Telegramda tanilgan. Parol
qo'shsak — yana bitta o'g'irlanadigan sir paydo bo'ladi va "parolni
unutdim" oqimi kerak bo'ladi. Bot orqali havola — xavfsizroq va soddaroq.

Oqim:
  1. Botda `/kabinet` → bir martalik havola (15 daqiqa)
  2. Havola ochiladi → token tekshiriladi va **darhol kuydiriladi**
  3. Brauzerga sessiya cookie'si beriladi (30 kun), URL toza qoladi

Token bazada **xesh** holida. O'g'irlangan bazadan sessiyani tiklab
bo'lmaydi.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, select

from app.core.logging import get_logger
from app.db.base import session_scope, utcnow
from app.db.models import TokenKind, User, WebToken

log = get_logger(__name__)

#: Kirish havolasi qancha yashaydi. Qisqa — havola chatda qolib ketsa ham
#: tez o'chadi.
LOGIN_TTL = timedelta(minutes=15)
#: Brauzer sessiyasi. Uzunroq, chunki u cookie'da va URL'ga tushmaydi.
SESSION_TTL = timedelta(days=30)

COOKIE_NAME = "uzumbot_session"


def _hash(token: str) -> str:
    """Tokenni bazaga yozishdan oldin xeshlaymiz (parol kabi)."""
    return hashlib.sha256(token.encode()).hexdigest()


def _new_token() -> str:
    """Kriptografik tasodifiy token (URL uchun xavfsiz)."""
    return secrets.token_urlsafe(32)


@dataclass(frozen=True, slots=True)
class WebUser:
    telegram_id: int
    full_name: str | None
    username: str | None
    is_admin: bool


async def issue_login_token(telegram_id: int) -> str:
    """Botdagi `/kabinet` uchun bir martalik token.

    Eski ishlatilmagan kirish tokenlari o'chiriladi — bir vaqtda bitta
    havola amal qilsin (eski xabardagi havola ishlamay qolsin).
    """
    token = _new_token()
    async with session_scope() as session:
        await session.execute(
            delete(WebToken).where(
                WebToken.telegram_id == telegram_id,
                WebToken.kind == TokenKind.LOGIN,
            )
        )
        session.add(
            WebToken(
                telegram_id=telegram_id,
                token_hash=_hash(token),
                kind=TokenKind.LOGIN,
                expires_at=utcnow() + LOGIN_TTL,
            )
        )
    return token


async def redeem_login_token(token: str) -> str | None:
    """Kirish tokenini sessiya tokeniga almashtiradi.

    Token bir martalik: ishlatilgach **darhol o'chiriladi**. Havola
    nusxalangan bo'lsa ham ikkinchi marta ishlamaydi.
    """
    if not token:
        return None

    token_hash = _hash(token)
    now = utcnow()

    async with session_scope() as session:
        row = await session.scalar(
            select(WebToken).where(
                WebToken.token_hash == token_hash,
                WebToken.kind == TokenKind.LOGIN,
            )
        )
        if row is None or row.used_at is not None or row.expires_at <= now:
            return None

        telegram_id = row.telegram_id
        # Kuydiramiz — qayta ishlatilmasin
        await session.delete(row)

        session_token = _new_token()
        session.add(
            WebToken(
                telegram_id=telegram_id,
                token_hash=_hash(session_token),
                kind=TokenKind.SESSION,
                expires_at=now + SESSION_TTL,
            )
        )

    log.info("Web-kabinetga kirildi: tg_id=%s", telegram_id)
    return session_token


async def user_for_session(token: str | None) -> WebUser | None:
    """Cookie'dagi sessiya bo'yicha foydalanuvchi. Yaroqsiz bo'lsa None."""
    if not token:
        return None

    token_hash = _hash(token)
    now = utcnow()

    async with session_scope() as session:
        row = await session.scalar(
            select(WebToken).where(
                WebToken.token_hash == token_hash,
                WebToken.kind == TokenKind.SESSION,
            )
        )
        if row is None or row.expires_at <= now:
            return None

        user = await session.scalar(
            select(User).where(User.telegram_id == row.telegram_id)
        )
        if user is None or user.is_blocked:
            return None

        return WebUser(
            telegram_id=user.telegram_id,
            full_name=user.full_name,
            username=user.username,
            is_admin=bool(user.is_admin),
        )


async def revoke_session(token: str | None) -> None:
    """Chiqish — sessiyani o'chiradi."""
    if not token:
        return
    async with session_scope() as session:
        await session.execute(
            delete(WebToken).where(
                WebToken.token_hash == _hash(token),
                WebToken.kind == TokenKind.SESSION,
            )
        )


async def purge_expired() -> int:
    """Muddati o'tgan tokenlarni tozalaydi (kunlik ish uchun)."""
    async with session_scope() as session:
        result = await session.execute(
            delete(WebToken).where(WebToken.expires_at <= utcnow())
        )
        return int(result.rowcount or 0)


def constant_time_equals(left: str, right: str) -> bool:
    """Vaqt bo'yicha hujumdan himoyalangan taqqoslash."""
    return hmac.compare_digest(left, right)
