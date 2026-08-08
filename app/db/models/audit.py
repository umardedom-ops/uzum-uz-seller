"""Audit natijalari: aniqlangan farqlar va da'volar (SPEC 4, 5).

Muhim (SPEC 9.5): bu yozuvlar "aniq fakt" emas, "tekshirish kerak" degan
ma'noda taqdim etiladi. Noto'g'ri da'vo sellerni Uzum oldida noqulay
ahvolga solmasin.
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UtcDateTime

Money = Numeric(18, 2)


class DiscrepancyKind(str, enum.Enum):
    """SPEC 5.1–5.5 — pul topishning beshta yo'li."""

    LOST_STOCK = "lost_stock"          # 5.1 yo'qolgan tovar
    LOST_RETURN = "lost_return"        # 5.2 qaytdi, omborga tushmadi
    OVER_COMMISSION = "over_commission"  # 5.3 ortiqcha komissiya
    LOGISTICS = "logistics"            # 5.4 logistika farqi
    MISSING_COMPENSATION = "missing_compensation"  # 5.5 kompensatsiya kelmadi


class DiscrepancyStatus(str, enum.Enum):
    NEW = "new"
    WATCHING = "watching"    # 1 dona farq — hali da'vo qilmaymiz (SPEC 5.1)
    CLAIMED = "claimed"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class ClaimResult(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    PARTIAL = "partial"
    REJECTED = "rejected"


class Discrepancy(Base, TimestampMixin):
    __tablename__ = "discrepancies"
    __table_args__ = (
        # Bir xil davr + SKU + tur uchun takroriy yozuv bo'lmasin
        UniqueConstraint(
            "shop_id", "sku", "kind", "period_from", "period_to",
            name="uq_discrepancy_period",
        ),
        Index("ix_discrepancy_shop_status", "shop_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    sku: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[DiscrepancyKind] = mapped_column(
        Enum(DiscrepancyKind, native_enum=False, length=32)
    )
    qty: Mapped[int] = mapped_column(Integer, default=0)
    amount: Mapped[Decimal | None] = mapped_column(Money)
    period_from: Mapped[date] = mapped_column(Date)
    period_to: Mapped[date] = mapped_column(Date)
    status: Mapped[DiscrepancyStatus] = mapped_column(
        Enum(DiscrepancyStatus, native_enum=False, length=16),
        default=DiscrepancyStatus.NEW,
    )
    # Hisob qanday chiqqani — sellerga tushuntirish uchun
    details: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    claim_doc_path: Mapped[str | None] = mapped_column(String(512))
    claim_id: Mapped[int | None] = mapped_column(
        ForeignKey("claims.id", ondelete="SET NULL")
    )


class Claim(Base, TimestampMixin):
    """Tayyorlangan pretenziya (SPEC 6.2)."""

    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    doc_path: Mapped[str | None] = mapped_column(String(512))
    xlsx_path: Mapped[str | None] = mapped_column(String(512))
    total_amount: Mapped[Decimal | None] = mapped_column(Money)
    period_from: Mapped[date | None] = mapped_column(Date)
    period_to: Mapped[date | None] = mapped_column(Date)
    sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    result: Mapped[ClaimResult] = mapped_column(
        Enum(ClaimResult, native_enum=False, length=16), default=ClaimResult.PENDING
    )
