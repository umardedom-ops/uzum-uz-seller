"""Uzumdan yig'iladigan ma'lumot (SPEC 4).

Har jadvalda `shop_id` bor va u bo'yicha filtr MAJBURIY (SPEC 9.4).
Takroriy sinxronizatsiya dublikat yaratmasligi uchun tabiiy kalitlar
`UniqueConstraint` bilan himoyalangan (SPEC Phase 3 — idempotent upsert).
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UtcDateTime

# Pul — Numeric, float EMAS. Float bilan hisoblangan zarar da'voda tortishuv
# keltirib chiqaradi.
Money = Numeric(18, 2)


class MovementType(str, enum.Enum):
    IN = "in"            # omborga qabul
    SALE = "sale"        # sotildi
    RETURN = "return"    # qaytib tushdi
    WRITEOFF = "writeoff"  # hisobdan chiqarildi


class Product(Base, TimestampMixin):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("shop_id", "sku", name="uq_product_shop_sku"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    sku: Mapped[str] = mapped_column(String(64), index=True)
    # API'dagi `barcode` maydoni — Excel va pretenziya uchun MAJBURIY (SPEC 6.1).
    # DIQQAT: `skuFullTitle` bilan adashtirmang, u boshqa narsa.
    barcode: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str | None] = mapped_column(String(512))
    category: Mapped[str | None] = mapped_column(String(255))
    size: Mapped[str | None] = mapped_column(String(64))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    # Seller o'zi kiritadi (yunit-iqtisodiyot uchun)
    cost_price: Mapped[Decimal | None] = mapped_column(Money)
    # API'dan keladi — qo'lda to'ldirish shart emas (docs/api-inventory.md §4)
    commission_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    sale_price: Mapped[Decimal | None] = mapped_column(Money)

    # --- Uzum hisoblagan jami ko'rsatkichlar (butun faoliyat davri) ---
    # Shu tufayli to'plangan audit qoldiq tarixisiz ham ishlaydi.
    qty_sold_total: Mapped[int | None] = mapped_column(Integer)
    qty_returned_total: Mapped[int | None] = mapped_column(Integer)
    qty_created_total: Mapped[int | None] = mapped_column(Integer)
    qty_missing: Mapped[int | None] = mapped_column(Integer)
    qty_defected: Mapped[int | None] = mapped_column(Integer)
    qty_archived: Mapped[int | None] = mapped_column(Integer)

    # --- O'lchamlar (5.4 logistika auditi uchun) ---
    length_mm: Mapped[int | None] = mapped_column(Integer)
    width_mm: Mapped[int | None] = mapped_column(Integer)
    height_mm: Mapped[int | None] = mapped_column(Integer)
    dimensional_group: Mapped[str | None] = mapped_column(String(64))
    # Uzum omborda o'lchagan haqiqiy guruh. Kartochkadagidan farq qilsa —
    # logistika ortiqcha ushlangan bo'lishi mumkin (5.4 audit).
    actual_dimensional_group: Mapped[str | None] = mapped_column(String(64))

    # --- Holat (blok alerti uchun) ---
    is_blocked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    block_reason: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str | None] = mapped_column(String(64))
    avg_daily_sales: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    # Qidiruvdagi o'rin (A/B/C/D). Pasayishi sotuv qulashidan darak beradi —
    # Avtobidder o'rniga xavfsiz, o'qish orqali ishlaydigan signal.
    rank: Mapped[str | None] = mapped_column(String(8))
    prev_rank: Mapped[str | None] = mapped_column(String(8))
    returned_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    paid_storage_amount: Mapped[Decimal | None] = mapped_column(Money)


class Order(Base, TimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("shop_id", "uzum_order_id", "sku", name="uq_order_shop_item"),
        Index("ix_order_shop_created", "shop_id", "created_at_uzum"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    uzum_order_id: Mapped[str] = mapped_column(String(64), index=True)
    sku: Mapped[str] = mapped_column(String(64), index=True)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[Decimal | None] = mapped_column(Money)
    status: Mapped[str | None] = mapped_column(String(64))
    commission_amount: Mapped[Decimal | None] = mapped_column(Money)
    delivery_amount: Mapped[Decimal | None] = mapped_column(Money)
    # Uzum O'ZI hisoblagan sof foyda va tannarx — yunit-iqtisodiyot uchun
    # sellerdan tannarx so'rash shart emas.
    seller_profit: Mapped[Decimal | None] = mapped_column(Money)
    purchase_price: Mapped[Decimal | None] = mapped_column(Money)
    withdrawn_profit: Mapped[Decimal | None] = mapped_column(Money)
    # Qaytarish sababi — 5.2 va sabab tahlili uchun
    return_cause: Mapped[str | None] = mapped_column(String(255))
    qty_returned: Mapped[int | None] = mapped_column(Integer)
    created_at_uzum: Mapped[datetime | None] = mapped_column(UtcDateTime)
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Return(Base, TimestampMixin):
    __tablename__ = "returns"
    __table_args__ = (
        UniqueConstraint("shop_id", "uzum_return_id", "sku", name="uq_return_shop_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    uzum_return_id: Mapped[str] = mapped_column(String(64), index=True)
    order_id: Mapped[str | None] = mapped_column(String(64))
    sku: Mapped[str] = mapped_column(String(64), index=True)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str | None] = mapped_column(String(64))
    # 5.2 auditining yuragi: qaytdi, lekin omborga tushdimi?
    received_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    returned_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class StockSnapshot(Base, TimestampMixin):
    """Kunlik qoldiq surati — mahsulotning yuragi (SPEC 4).

    Uzum faqat "hozirgi holat"ni beradi, tarixni biz saqlaymiz. Shuning
    uchun kuniga 1 marta yoziladi va hech qachon o'chirilmaydi.
    """

    __tablename__ = "stock_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "shop_id", "sku", "warehouse", "captured_on", name="uq_snapshot_daily"
        ),
        Index("ix_snapshot_shop_date", "shop_id", "captured_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    sku: Mapped[str] = mapped_column(String(64), index=True)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    warehouse: Mapped[str] = mapped_column(String(64), default="FBO")
    captured_on: Mapped[date] = mapped_column(Date, index=True)
    captured_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class StockMovement(Base, TimestampMixin):
    __tablename__ = "stock_movements"
    __table_args__ = (
        UniqueConstraint(
            "shop_id", "external_id", "sku", name="uq_movement_shop_item"
        ),
        Index("ix_movement_shop_at", "shop_id", "happened_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    # Manba yozuvi ID (yuk xati va h.k.) — dublikatning oldini oladi
    external_id: Mapped[str] = mapped_column(String(64))
    sku: Mapped[str] = mapped_column(String(64), index=True)
    type: Mapped[MovementType] = mapped_column(
        Enum(MovementType, native_enum=False, length=16)
    )
    qty: Mapped[int] = mapped_column(Integer, default=0)
    happened_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class FinanceOp(Base, TimestampMixin):
    __tablename__ = "finance_ops"
    __table_args__ = (
        UniqueConstraint("shop_id", "external_id", name="uq_finance_shop_ext"),
        Index("ix_finance_shop_at", "shop_id", "happened_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(64))
    type: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str | None] = mapped_column(String(64))
    amount: Mapped[Decimal | None] = mapped_column(Money)
    description: Mapped[str | None] = mapped_column(String(512))
    sku: Mapped[str | None] = mapped_column(String(64), index=True)
    happened_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Compensation(Base, TimestampMixin):
    """Uzum to'lagan kompensatsiya — 5.5 sverkasi uchun."""

    __tablename__ = "compensations"
    __table_args__ = (
        UniqueConstraint("shop_id", "external_id", name="uq_comp_shop_ext"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(64))
    sku: Mapped[str | None] = mapped_column(String(64), index=True)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    amount: Mapped[Decimal | None] = mapped_column(Money)
    status: Mapped[str | None] = mapped_column(String(64))
    happened_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
