"""Foydalanuvchi va obuna (SPEC 4)."""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UtcDateTime


class Lang(str, enum.Enum):
    UZ = "uz"
    RU = "ru"


class SubscriptionStatus(str, enum.Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Plan(str, enum.Enum):
    """Tariflar funksiya bo'yicha farqlanadi (SPEC Phase 6).

    Sinov davrida PRO ochiladi — seller to'liq qiymatni ko'rsin, keyin
    o'zi tanlasin.
    """

    TRIAL = "trial"
    BASIC = "basic"   # yo'qotilgan pul + qoldiqlar
    PRO = "pro"       # + yunit-iqtisodiyot, FBS yorliq, qaytarish tahlili


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    lang: Mapped[Lang] = mapped_column(
        Enum(Lang, native_enum=False, length=8), default=Lang.UZ
    )
    oferta_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    # Admin huquqi bazada saqlanadi — `.env` ni qo'lda tahrirlash shart emas.
    # Birinchi ro'yxatdan o'tgan foydalanuvchi avtomatik admin bo'ladi.
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    full_name: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(64))
    # Foydalanuvchi tanlagan joriy do'kon (ko'p do'konli akkaunt uchun).
    # DB-darajali FK qo'yilmagan (SQLite migratsiyasi sodda qolsin) — egalik
    # `exports.set_active_shop` da tekshiriladi. None bo'lsa birinchi do'kon.
    active_shop_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    subscription: Mapped[Subscription | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    shops: Mapped[list[Shop]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    plan: Mapped[Plan] = mapped_column(
        Enum(Plan, native_enum=False, length=16), default=Plan.TRIAL
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, native_enum=False, length=16),
        default=SubscriptionStatus.TRIAL,
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    paid_until: Mapped[datetime | None] = mapped_column(UtcDateTime)

    user: Mapped[User] = relationship(back_populates="subscription")

    def is_active_at(self, moment: datetime) -> bool:
        """Shu paytda xizmatdan foydalana oladimi?

        Sinov yoki to'lov muddati amal qilsa — ha. Muddatlar yo'q bo'lsa —
        yo'q (jim ravishda ochib qo'ymaymiz).
        """
        if self.status == SubscriptionStatus.CANCELLED:
            return False
        for deadline in (self.paid_until, self.trial_ends_at):
            if deadline is not None and deadline > moment:
                return True
        return False

    def effective_plan(self, moment: datetime) -> Plan:
        """Shu paytda qaysi tarif amal qilyapti.

        Sinov davrida **BASIC** beriladi: seller mahsulotning asosiy
        qiymatini ko'radi, lekin Pro imkoniyatlari to'lovdan keyin ochiladi.
        (2026-08-08 gacha sinovda PRO berilardi — bunda sellerning to'lashga
        sababi qolmasdi.)

        To'lov muddati o'tgan bo'lsa, sinov hali tugamagan bo'lishi ham
        mumkin; shu sabab ikkalasi alohida tekshiriladi.
        """
        if self.paid_until is not None and self.paid_until > moment:
            return self.plan if self.plan in (Plan.BASIC, Plan.PRO) else Plan.BASIC
        if self.trial_ends_at is not None and self.trial_ends_at > moment:
            return Plan.BASIC
        return Plan.TRIAL  # muddati tugagan — kirish yopiq
