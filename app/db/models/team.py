"""Jamoa bilan ishlash: hodimlar va guruh/kanalga hisobot.

Raqobatchida bor edi, bizda yo'q edi — yirik seller va agentliklar uchun
muhim. Ikkalasi ham do'kon **egasi** tomonidan boshqariladi.

⚠️ Xavfsizlik: hodim faqat o'ziga berilgan do'konni ko'radi va hech
qachon to'lov/obuna sozlamalariga tega olmaydi (`StaffRole` ga qarang).
"""
from __future__ import annotations

import enum

from sqlalchemy import BigInteger, Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class StaffRole(str, enum.Enum):
    """Hodim huquqi.

    Ataylab ikkitagina: ko'proq daraja chalkashtiradi va xato beradi.
    To'lov, tarif va hodim boshqaruvi **hech qaysi rolda ochilmaydi** —
    ular faqat egasiniki.
    """

    VIEWER = "viewer"    # faqat ko'radi: hisobot, qoldiq, analitika
    MANAGER = "manager"  # + operatsion ish: FBS yorliq, aktlar


class ShopStaff(Base, TimestampMixin):
    """Do'konga biriktirilgan hodim."""

    __tablename__ = "shop_staff"
    __table_args__ = (
        UniqueConstraint("shop_id", "telegram_id", name="uq_staff_shop_tg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    #: Hodimning Telegram ID si. U hali botga kirmagan bo'lishi mumkin —
    #: shuning uchun `users` ga FK qo'yilmagan.
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    role: Mapped[StaffRole] = mapped_column(
        Enum(StaffRole, native_enum=False, length=16), default=StaffRole.VIEWER
    )
    title: Mapped[str | None] = mapped_column(String(128))  # ism/izoh
    added_by: Mapped[int | None] = mapped_column(BigInteger)  # ega telegram_id
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ReportChannel(Base, TimestampMixin):
    """Kunlik hisobot yuboriladigan guruh yoki kanal.

    Bot o'sha guruhga qo'shilgan bo'lishi va yozish huquqi bo'lishi kerak.
    Bitta do'konga bir nechta manzil bo'lishi mumkin (masalan ombor
    guruhi + rahbariyat kanali).
    """

    __tablename__ = "report_channels"
    __table_args__ = (
        UniqueConstraint("shop_id", "chat_id", name="uq_channel_shop_chat"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    #: Guruh/kanal ID si — manfiy son bo'ladi (Telegram shunday beradi)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    added_by: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
