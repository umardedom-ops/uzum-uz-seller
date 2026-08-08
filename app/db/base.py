"""SQLAlchemy asosi va sessiya boshqaruvi.

`DATABASE_URL` orqali SQLite (lokal) va PostgreSQL (production) o'rtasida
almashadi — model kodi o'zgarmaydi.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings


def utcnow() -> datetime:
    """Vaqt zonasi bilan hozirgi UTC (naive datetime ishlatmaymiz)."""
    return datetime.now(UTC)


class UtcDateTime(TypeDecorator):
    """Har doim vaqt zonasi bor datetime qaytaradigan ustun turi.

    ❗ Nima uchun kerak: SQLite vaqt zonasini SAQLAMAYDI. `DateTime(
    timezone=True)` deb e'lon qilinsa ham, bazadan **naive** datetime
    qaytadi. `utcnow()` esa aware. Ikkalasini taqqoslash
    `TypeError: can't compare offset-naive and offset-aware datetimes`
    beradi.

    2026-08-08 da shu xato botni **har bir xabarda** yiqitgan edi:
    obuna tekshiruvi (`Subscription.is_active_at`) middleware'da ishlaydi,
    ya'ni `/start` ham, boshqa tugma ham javob bermasdi. Xato faqat
    obunasi bor foydalanuvchida chiqqani uchun sezilmay qolgan.

    PostgreSQL da bunday muammo yo'q — shu sabab lokalda va serverda
    boshqacha xatti-harakat bo'lardi. Bu tur ikkalasini tenglashtiradi.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: object
    ) -> datetime | None:
        """Bazaga yozishdan oldin — doim UTC ga keltiramiz."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(
        self, value: datetime | None, dialect: object
    ) -> datetime | None:
        """Bazadan o'qigach — zonasi yo'q bo'lsa UTC deb belgilaymiz.

        Yozishda doim UTC ga keltirilgani uchun bu taxmin xavfsiz.
        """
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Base(DeclarativeBase):
    """Barcha modellar uchun asos."""


class TimestampMixin:
    """`created_at` / `updated_at` — deyarli har jadvalga kerak."""

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,  # uzilgan ulanishni oldindan ushlaydi
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Tranzaksiya doirasi: muvaffaqiyatda commit, xatoda rollback."""
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
