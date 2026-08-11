"""Qaytgan tovarni FBS qoldig'iga qaytarish.

Eng xavfli xato — bir qaytarishni ikki marta qo'shish: qoldiq shishib
ketadi va sotuvda yo'q tovar "bor" bo'lib ko'rinadi. Shu sabab
`restocked_at` belgisi va uning testlari markazda.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from app.db.base import session_scope, utcnow
from app.db.models import (
    AuthType,
    Product,
    Return,
    Shop,
    ShopCredential,
    StockSnapshot,
    User,
)
from app.services import returns_restock

TG = 9001


async def _seed(
    *,
    returned_qty: int = 3,
    received: bool = True,
    fbs_now: int = 5,
    with_barcode: bool = True,
) -> int:
    async with session_scope() as s:
        user = User(telegram_id=TG)
        s.add(user)
        await s.flush()

        shop = Shop(user_id=user.id, uzum_shop_id="7973", is_active=True)
        s.add(shop)
        await s.flush()

        cred = ShopCredential(shop_id=shop.id, auth_type=AuthType.API, is_valid=True)
        cred.secret = "tok"
        s.add(cred)

        s.add(
            Product(
                shop_id=shop.id,
                sku="763221",
                barcode="1000113258397" if with_barcode else None,
                title="Sinov tovari",
            )
        )
        s.add(
            StockSnapshot(
                shop_id=shop.id,
                sku="763221",
                warehouse="FBS",
                qty=fbs_now,
                captured_on=date.today(),
            )
        )
        s.add(
            Return(
                shop_id=shop.id,
                uzum_return_id="R-1",
                sku="763221",
                qty=returned_qty,
                received_at=utcnow() if received else None,
            )
        )
        return shop.id


class TestCollect:
    async def test_proposes_current_plus_returned(self) -> None:
        shop_id = await _seed(returned_qty=3, fbs_now=5)
        plan = await returns_restock.collect_pending(shop_id)

        assert len(plan.items) == 1
        item = plan.items[0]
        assert item.current_qty == 5
        assert item.returned_qty == 3
        assert item.new_qty == 8  # qo'shiladi, almashtirilmaydi

    async def test_ignores_not_received(self) -> None:
        """Yo'ldagi tovar qo'shilmaydi — aks holda qoldiq soxta ko'payadi."""
        shop_id = await _seed(received=False)
        assert not await returns_restock.collect_pending(shop_id)

    async def test_skips_without_barcode(self) -> None:
        """Shtrix kodsiz — o'tkazamiz, lekin JIM emas: sonini qaytaramiz."""
        shop_id = await _seed(with_barcode=False)
        plan = await returns_restock.collect_pending(shop_id)

        assert not plan.items
        assert plan.skipped_no_barcode == 1

    async def test_merges_several_returns_of_same_sku(self) -> None:
        shop_id = await _seed(returned_qty=2, fbs_now=0)
        async with session_scope() as s:
            s.add(
                Return(
                    shop_id=shop_id,
                    uzum_return_id="R-2",
                    sku="763221",
                    qty=4,
                    received_at=utcnow(),
                )
            )

        plan = await returns_restock.collect_pending(shop_id)
        assert len(plan.items) == 1
        assert plan.items[0].returned_qty == 6
        assert plan.total_qty == 6


class TestApply:
    async def test_marks_restocked_so_it_is_not_repeated(self) -> None:
        """Eng muhim kafolat: ikkinchi marta taklif qilinmaydi."""
        shop_id = await _seed(returned_qty=3, fbs_now=5)
        plan = await returns_restock.collect_pending(shop_id)

        ok, failed = await returns_restock.apply_plan(shop_id, plan, telegram_id=TG)
        assert ok == 1 and failed == 0

        # Belgilangan
        async with session_scope() as s:
            row = await s.scalar(select(Return).where(Return.shop_id == shop_id))
            assert row.restocked_at is not None

        # Ikkinchi marta bo'sh
        assert not await returns_restock.collect_pending(shop_id)

    async def test_new_return_after_restock_is_offered(self) -> None:
        """Qo'shilgandan keyingi YANGI qaytarish yana taklif qilinadi."""
        shop_id = await _seed(returned_qty=3)
        plan = await returns_restock.collect_pending(shop_id)
        await returns_restock.apply_plan(shop_id, plan, telegram_id=TG)

        async with session_scope() as s:
            s.add(
                Return(
                    shop_id=shop_id,
                    uzum_return_id="R-9",
                    sku="763221",
                    qty=2,
                    received_at=utcnow() + timedelta(minutes=1),
                )
            )

        again = await returns_restock.collect_pending(shop_id)
        assert len(again.items) == 1 and again.items[0].returned_qty == 2
