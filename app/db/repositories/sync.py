"""Sinxronizatsiya uchun idempotent upsert (SPEC Phase 3).

Takroriy sync dublikat yaratmasligi kerak — aks holda audit soxta
"yo'qotish" ko'rsatadi. Har jadvalning tabiiy kaliti bo'yicha
yangilanadi.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.models import (
    Compensation,
    FinanceOp,
    Order,
    Product,
    Return,
    StockMovement,
    StockSnapshot,
    SyncRun,
    SyncStatus,
)


async def _upsert(
    session: AsyncSession,
    model: type,
    lookup: dict[str, Any],
    values: dict[str, Any],
) -> tuple[Any, bool]:
    """Topsa yangilaydi, topmasa qo'shadi. `(obyekt, yangi_mi)` qaytaradi."""
    conditions = [getattr(model, k) == v for k, v in lookup.items()]
    obj = await session.scalar(select(model).where(*conditions))

    if obj is None:
        obj = model(**lookup, **values)
        session.add(obj)
        return obj, True

    for key, value in values.items():
        if value is not None:  # yo'q ma'lumot bor ma'lumotni o'chirmasin
            setattr(obj, key, value)
    return obj, False


async def upsert_products(
    session: AsyncSession, shop_id: int, rows: list[dict[str, Any]]
) -> int:
    """Mahsulotlarni yangilaydi va o'zgarishlarni kuzatadi.

    Diqqat: `is_blocked` va `rank` maydonlari alohida ishlanadi —
    ular `None` bo'lganda ham yangilanishi kerak (blok olib tashlansa
    `False` yozilsin), va eski qiymat alert uchun saqlanadi.
    """
    count = 0
    for row in rows:
        data = dict(row)
        sku = data.pop("sku")
        blocked = data.pop("is_blocked", False)
        rank = data.pop("rank", None)

        obj, created = await _upsert(
            session, Product, {"shop_id": shop_id, "sku": sku}, data
        )

        # Blok holati — `False` ham ma'noli qiymat, `_upsert` uni tashlab yuboradi
        obj.is_blocked = bool(blocked)

        # Rank o'zgarsa eskisini saqlaymiz — alert shu farqqa qaraydi
        if rank is not None and rank != obj.rank:
            obj.prev_rank = obj.rank
            obj.rank = rank

        count += created
    await session.flush()
    return count


async def upsert_orders(
    session: AsyncSession, shop_id: int, rows: list[dict[str, Any]]
) -> int:
    count = 0
    for row in rows:
        data = dict(row)
        lookup = {
            "shop_id": shop_id,
            "uzum_order_id": data.pop("uzum_order_id"),
            "sku": data.pop("sku"),
        }
        _, created = await _upsert(session, Order, lookup, data)
        count += created
    await session.flush()
    return count


async def upsert_returns(
    session: AsyncSession, shop_id: int, rows: list[dict[str, Any]]
) -> int:
    count = 0
    for row in rows:
        data = dict(row)
        lookup = {
            "shop_id": shop_id,
            "uzum_return_id": data.pop("uzum_return_id"),
            "sku": data.pop("sku"),
        }
        _, created = await _upsert(session, Return, lookup, data)
        count += created
    await session.flush()
    return count


async def upsert_stock_snapshot(
    session: AsyncSession,
    shop_id: int,
    rows: list[dict[str, Any]],
    captured_on: date | None = None,
) -> int:
    """Kunlik qoldiq surati — kuniga bir marta, kun bo'yicha yagona.

    Kun ichida qayta ishga tushirilsa, o'sha kun yozuvi yangilanadi
    (ikkita yozuv paydo bo'lmaydi).
    """
    day = captured_on or utcnow().date()
    count = 0
    for row in rows:
        data = dict(row)
        data.pop("barcode", None)  # snapshot'da shtrix kod saqlanmaydi
        lookup = {
            "shop_id": shop_id,
            "sku": data.pop("sku"),
            "warehouse": data.pop("warehouse", "FBO"),
            "captured_on": day,
        }
        data["captured_at"] = utcnow()
        _, created = await _upsert(session, StockSnapshot, lookup, data)
        count += created
    await session.flush()
    return count


async def upsert_movements(
    session: AsyncSession, shop_id: int, rows: list[dict[str, Any]]
) -> int:
    count = 0
    for row in rows:
        data = dict(row)
        lookup = {
            "shop_id": shop_id,
            "external_id": data.pop("external_id"),
            "sku": data.pop("sku", ""),
        }
        _, created = await _upsert(session, StockMovement, lookup, data)
        count += created
    await session.flush()
    return count


async def upsert_finance_ops(
    session: AsyncSession, shop_id: int, rows: list[dict[str, Any]]
) -> int:
    count = 0
    for row in rows:
        data = dict(row)
        lookup = {"shop_id": shop_id, "external_id": data.pop("external_id")}
        data.pop("sku", None)
        _, created = await _upsert(session, FinanceOp, lookup, data)
        count += created
    await session.flush()
    return count


async def upsert_compensations(
    session: AsyncSession, shop_id: int, rows: list[dict[str, Any]]
) -> int:
    count = 0
    for row in rows:
        data = dict(row)
        lookup = {"shop_id": shop_id, "external_id": data.pop("external_id")}
        payload = {
            "sku": data.get("sku"),
            "amount": data.get("amount"),
            "status": data.get("type"),
            "happened_at": data.get("happened_at"),
        }
        _, created = await _upsert(session, Compensation, lookup, payload)
        count += created
    await session.flush()
    return count


# --- Sync jurnali (SPEC 9.6: xatolar jim yutilmaydi) -------------------- #


async def start_run(session: AsyncSession, shop_id: int, kind: str) -> SyncRun:
    run = SyncRun(
        shop_id=shop_id,
        kind=kind,
        status=SyncStatus.RUNNING,
        started_at=utcnow(),
    )
    session.add(run)
    await session.flush()
    return run


async def finish_run(
    session: AsyncSession,
    run: SyncRun,
    *,
    status: SyncStatus,
    records: int = 0,
    error: str | None = None,
) -> None:
    run.status = status
    run.finished_at = utcnow()
    run.records_synced = records
    run.error = error
