"""Ko'p do'kon: joriy do'konni tanlash va afzal ko'rish.

Tekshiriladi: standart holatda birinchi do'kon; tanlangач o'sha qaytadi;
begona do'konni tanlash rad etiladi (egalik tekshiruvi).
"""
from __future__ import annotations

from app.db.base import session_scope
from app.db.models import Shop, User
from app.services.exports import find_user_shop, list_user_shops, set_active_shop


async def _seed_two_shops(telegram_id: int) -> tuple[int, int]:
    async with session_scope() as session:
        user = User(telegram_id=telegram_id)
        session.add(user)
        await session.flush()

        s1 = Shop(user_id=user.id, uzum_shop_id="7973", title="AZIKO", is_active=True)
        s2 = Shop(
            user_id=user.id, uzum_shop_id="25273", title="AZIKO PLAST", is_active=True
        )
        session.add_all([s1, s2])
        await session.flush()
        return s1.id, s2.id


class TestMultiShop:
    async def test_default_is_first(self) -> None:
        s1, _ = await _seed_two_shops(701)
        shop = await find_user_shop(701)
        assert shop is not None and shop.id == s1

    async def test_switch_active(self) -> None:
        _, s2 = await _seed_two_shops(702)
        chosen = await set_active_shop(702, s2)
        assert chosen is not None and chosen.id == s2
        # Endi barcha handlerlar shu do'konni oladi
        shop = await find_user_shop(702)
        assert shop is not None and shop.id == s2

    async def test_list_all(self) -> None:
        s1, s2 = await _seed_two_shops(703)
        shops = await list_user_shops(703)
        assert {s.id for s in shops} == {s1, s2}

    async def test_reject_foreign_shop(self) -> None:
        """Begona do'konni tanlab bo'lmaydi — egalik tekshiriladi."""
        s1, _ = await _seed_two_shops(704)
        other1, _ = await _seed_two_shops(705)

        rejected = await set_active_shop(704, other1)
        assert rejected is None
        # Joriy do'kon o'zgarmagan bo'lishi kerak
        shop = await find_user_shop(704)
        assert shop is not None and shop.id == s1
