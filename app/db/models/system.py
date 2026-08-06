"""Bildirishnoma sozlamalari va sinxronizatsiya jurnali (SPEC 4).

`SyncRun` — SPEC 9.6 talabi: sync xatolari jim yutilmaydi, jurnalga
yoziladi va adminga chiqadi.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
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

from app.db.base import Base, TimestampMixin


class AlertType(str, enum.Enum):
    DAILY_REPORT = "daily_report"        # kunlik hisobot (09:00)
    LOW_STOCK = "low_stock"              # qoldiq tugayapti
    SKU_BLOCKED = "sku_blocked"          # tovar bloklandi / moderatsiya
    NEW_DISCREPANCY = "new_discrepancy"  # yangi yo'qotish topildi
    NEW_ORDER = "new_order"
    RATING_DROP = "rating_drop"


class SyncStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class AlertConfig(Base, TimestampMixin):
    __tablename__ = "alerts_config"
    __table_args__ = (
        UniqueConstraint("shop_id", "alert_type", name="uq_alert_shop_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    alert_type: Mapped[AlertType] = mapped_column(
        Enum(AlertType, native_enum=False, length=32)
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Masalan: qoldiq necha kunga qolganda ogohlantirish
    threshold: Mapped[float | None] = mapped_column(Numeric(12, 2))


class SyncRun(Base, TimestampMixin):
    __tablename__ = "sync_runs"
    __table_args__ = (Index("ix_sync_shop_started", "shop_id", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str | None] = mapped_column(String(64))  # orders|stock|full...
    status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus, native_enum=False, length=16), default=SyncStatus.RUNNING
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_synced: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
