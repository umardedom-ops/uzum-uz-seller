"""To'lov yozuvlari (SPEC Phase 6).

Har to'lov jurnalga tushadi — kim, qancha, qanday usulda, qaysi tarif.
Bu buxgalteriya va nizolar uchun kerak: "men to'lagandim" degan gapga
javob bo'lsin.
"""
from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UtcDateTime
from app.db.models.user import Plan


class PaymentMethod(str, enum.Enum):
    CLICK = "click"         # Click Shop API (webhook orqali tasdiqlanadi)
    TELEGRAM = "telegram"   # Telegram Payments
    MANUAL = "manual"       # qo'lda tasdiqlangan o'tkazma


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"     # mijoz "to'ladim" dedi, admin tasdiqlamagan
    PAID = "paid"
    REJECTED = "rejected"


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    plan: Mapped[Plan] = mapped_column(Enum(Plan, native_enum=False, length=16))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    months: Mapped[int] = mapped_column(default=1)
    method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, native_enum=False, length=16)
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, native_enum=False, length=16), default=PaymentStatus.PENDING
    )
    # Telegram to'lovida — `telegram_payment_charge_id`; qo'lda — chek raqami
    external_id: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(String(512))
    confirmed_by: Mapped[int | None] = mapped_column()  # admin telegram_id
    paid_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class PromoCode(Base, TimestampMixin):
    """Bepul kirish kodi.

    Nima uchun kerak: hamkorlar va adminlar sellerni to'lovsiz ulashi
    mumkin bo'lsin. Har kod jurnalga tushadi — kim yaratgan, necha marta
    ishlatilgan, qachon tugaydi. Bu «kimga bepul berdik» degan savolga
    javob beradi.

    `max_uses = 0` — cheksiz. Kod muddati (`expires_at`) yo'q bo'lsa
    muddatsiz.
    """

    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Har doim KATTA harfda saqlanadi — kiritishda registr muhim bo'lmasin
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    plan: Mapped[Plan] = mapped_column(
        Enum(Plan, native_enum=False, length=16), default=Plan.PRO
    )
    days: Mapped[int] = mapped_column(default=30)
    max_uses: Mapped[int] = mapped_column(default=1)
    used_count: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[int | None] = mapped_column()  # admin telegram_id
    note: Mapped[str | None] = mapped_column(String(255))


class PromoRedemption(Base, TimestampMixin):
    """Kim qaysi kodni ishlatgani.

    ❗ Bir foydalanuvchi bitta kodni ikki marta ishlatib muddatni
    cheksiz uzaytira olmasligi kerak — shu jadval buni to'xtatadi.
    """

    __tablename__ = "promo_redemptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    promo_id: Mapped[int] = mapped_column(
        ForeignKey("promo_codes.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
