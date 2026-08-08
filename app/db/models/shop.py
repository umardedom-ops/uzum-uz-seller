"""Do'kon va uning maxfiy ma'lumotlari (SPEC 4).

`ShopCredential.encrypted_secret` — Fernet bilan shifrlangan API kalit yoki
kabinet cookie. Ochiq matn bazaga ham, logga ham tushmaydi (SPEC 9.2).
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security import decrypt, encrypt
from app.db.base import Base, TimestampMixin, UtcDateTime


class AuthType(str, enum.Enum):
    """SPEC 3.1-bis: API asosiy, kabinet qo'shimcha."""

    API = "api"
    CABINET = "cabinet"


class Shop(Base, TimestampMixin):
    __tablename__ = "shops"
    __table_args__ = (
        UniqueConstraint("user_id", "uzum_shop_id", name="uq_shop_user_uzum"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Uzumdagi ID — `GET /v1/shops` dan keladi (sellerdan so'ralmaydi)
    uzum_shop_id: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    connected_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    first_sync_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    user: Mapped[User] = relationship(back_populates="shops")  # noqa: F821
    credentials: Mapped[list[ShopCredential]] = relationship(
        back_populates="shop", cascade="all, delete-orphan"
    )


class ShopCredential(Base, TimestampMixin):
    """Bitta do'kon uchun bitta ulanish turi (api yoki cabinet)."""

    __tablename__ = "shop_credentials"
    __table_args__ = (
        UniqueConstraint("shop_id", "auth_type", name="uq_cred_shop_type"),
        Index("ix_cred_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    auth_type: Mapped[AuthType] = mapped_column(
        Enum(AuthType, native_enum=False, length=16), default=AuthType.API
    )
    # Fernet bilan shifrlangan. To'g'ridan-to'g'ri o'qimang — `secret` dan foydalaning.
    encrypted_secret: Mapped[str] = mapped_column(String(1024))
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    shop: Mapped[Shop] = relationship(back_populates="credentials")

    @property
    def secret(self) -> str:
        """Shifrni ochib beradi. Natijani logga yozmang."""
        return decrypt(self.encrypted_secret)

    @secret.setter
    def secret(self, plaintext: str) -> None:
        self.encrypted_secret = encrypt(plaintext)

    def __repr__(self) -> str:  # maxfiy ma'lumot chiqmasin
        return f"<ShopCredential shop_id={self.shop_id} type={self.auth_type.value}>"
