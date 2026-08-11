"""Qoldiq o'zgartirish servisi testlari.

Tekshiriladi: bayroq o'chiq bo'lsa amal DEMO sifatida jurnalga tushadi
(jonli yozilmaydi), kalit yo'q bo'lsa FAILED, bekor qilinsa CANCELLED.
Har holatda `stock_write_log` ga bitta qator yoziladi — yozish amali
hech qachon izsiz qolmaydi.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.base import session_scope
from app.db.models import (
    AuthType,
    Product,
    Shop,
    ShopCredential,
    StockWriteLog,
    StockWriteStatus,
    User,
)
from app.services.stock_write import apply_change, log_cancelled

#: Sinovdagi SKU va uning shtrix kodi. Uzum qoldiqni aynan shtrix kod
#: bo'yicha yangilaydi, shuning uchun mahsulot ham yaratiladi.
SKU = "763221"
BARCODE = "1000113258397"


async def _seed_shop(
    *,
    telegram_id: int = 555,
    uzum_shop_id: str = "7973",
    with_cred: bool = True,
    with_barcode: bool = True,
) -> int:
    async with session_scope() as session:
        user = User(telegram_id=telegram_id)
        session.add(user)
        await session.flush()

        shop = Shop(user_id=user.id, uzum_shop_id=uzum_shop_id, is_active=True)
        session.add(shop)
        await session.flush()

        session.add(
            Product(
                shop_id=shop.id,
                sku=SKU,
                barcode=BARCODE if with_barcode else None,
                title="Sinov tovari",
            )
        )

        if with_cred:
            cred = ShopCredential(
                shop_id=shop.id, auth_type=AuthType.API, is_valid=True
            )
            cred.secret = "token-xyz"  # setter shifrlaydi
            session.add(cred)

        return shop.id


async def _logs() -> list[StockWriteLog]:
    async with session_scope() as session:
        return list(await session.scalars(select(StockWriteLog)))


class TestApplyChange:
    async def test_demo_when_flag_off(self) -> None:
        """Bayroq o'chiq (standart) — DEMO, jonli yozilmaydi, jurnalga tushadi."""
        shop_id = await _seed_shop(telegram_id=555)

        outcome = await apply_change(
            shop_id, telegram_id=555, sku=SKU, old_qty=12, new_qty=30
        )

        assert outcome.status is StockWriteStatus.DEMO
        assert outcome.applied_live is False

        logs = await _logs()
        assert len(logs) == 1
        row = logs[0]
        assert row.status is StockWriteStatus.DEMO
        assert row.sku == "763221"
        assert row.old_qty == 12
        assert row.new_qty == 30
        assert row.telegram_id == 555

    async def test_failed_when_no_credential(self) -> None:
        """API kaliti bo'lmasa — FAILED, sabab jurnalда."""
        shop_id = await _seed_shop(telegram_id=556, with_cred=False)

        outcome = await apply_change(
            shop_id, telegram_id=556, sku="9", old_qty=None, new_qty=5
        )

        assert outcome.status is StockWriteStatus.FAILED
        assert outcome.error
        logs = await _logs()
        assert len(logs) == 1
        assert logs[0].status is StockWriteStatus.FAILED

    async def test_log_cancelled(self) -> None:
        """Bekor qilinganда ham iz qoladi — CANCELLED."""
        shop_id = await _seed_shop(telegram_id=777)

        await log_cancelled(
            shop_id, telegram_id=777, sku="9", old_qty=3, new_qty=10
        )

        logs = await _logs()
        assert len(logs) == 1
        assert logs[0].status is StockWriteStatus.CANCELLED
        assert logs[0].new_qty == 10

    async def test_without_barcode_fails_with_reason(self) -> None:
        """Shtrix kodsiz yozib bo'lmaydi — Uzum aynan shu bo'yicha yangilaydi.

        Sababi ochiq aytiladi: jim yutilsa, seller nega ishlamaganini
        bilmasdi (CLAUDE.md qoida #4).
        """
        shop_id = await _seed_shop(telegram_id=888, with_barcode=False)

        outcome = await apply_change(
            shop_id, telegram_id=888, sku=SKU, old_qty=1, new_qty=7
        )

        assert outcome.status is StockWriteStatus.FAILED
        assert "shtrix kod" in (outcome.error or "").lower()

        logs = await _logs()
        assert len(logs) == 1 and logs[0].status is StockWriteStatus.FAILED
