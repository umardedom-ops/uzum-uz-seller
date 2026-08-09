"""Xabarnoma mantig'i testlari.

Ikki xato bir xil yomon:
  * alert bermaslik → seller pul yo'qotadi
  * keraksiz alert  → seller bezor bo'lib, botni o'chiradi
"""
from __future__ import annotations

import pytest

from app.services.alerts import RANK_ORDER, _rank_dropped


class TestRankDrop:
    """Rank pasayishi — Avtobidder o'rniga tanlangan xavfsiz signal."""

    @pytest.mark.parametrize(
        ("prev", "current"),
        [("A", "B"), ("B", "D"), ("A", "D"), ("C", "E")],
    )
    def test_drop_detected(self, prev: str, current: str) -> None:
        assert _rank_dropped(prev, current)

    @pytest.mark.parametrize(
        ("prev", "current"),
        [("B", "A"), ("D", "B"), ("E", "A")],
    )
    def test_improvement_is_not_alert(self, prev: str, current: str) -> None:
        """O'sish — yaxshi xabar, lekin bezovta qilmaymiz."""
        assert not _rank_dropped(prev, current)

    def test_same_rank_is_silent(self) -> None:
        assert not _rank_dropped("B", "B")

    def test_missing_values_are_silent(self) -> None:
        """Birinchi sync'da eski rank yo'q — alert bermaymiz."""
        assert not _rank_dropped(None, "D")
        assert not _rank_dropped("A", None)
        assert not _rank_dropped(None, None)

    def test_unknown_rank_does_not_crash(self) -> None:
        """Uzum yangi rank kiritsa ham yiqilmasin."""
        assert _rank_dropped("A", "Z") is True   # noma'lum — eng past deb qaraladi
        assert _rank_dropped("Z", "A") is False

    def test_rank_order_is_a_best(self) -> None:
        assert RANK_ORDER["A"] < RANK_ORDER["B"] < RANK_ORDER["D"]


class TestAlertSettings:
    """Seller qaysi xabarnomalarni olishini o'zi tanlaydi.

    Standart holat — YOQILGAN: seller qiymatni ko'rmasdan turib
    o'chirib qo'yilgan bo'lsa, mahsulot foydasiz tuyuladi.
    """

    @pytest.fixture
    async def shop_id(self) -> int:
        from app.db.base import session_scope
        from app.db.models import Shop, User

        async with session_scope() as session:
            user = User(telegram_id=777001, lang="uz")
            session.add(user)
            await session.flush()
            shop = Shop(user_id=user.id, uzum_shop_id="7973", title="AZIKO")
            session.add(shop)
            await session.flush()
            return shop.id

    async def test_all_enabled_by_default(self, shop_id: int) -> None:
        from app.services import alerts

        settings = await alerts.alert_settings(shop_id)

        assert set(settings) == set(alerts.TOGGLEABLE)
        assert all(settings.values()), "standart holatda hammasi yoqilgan bo'lishi kerak"

    async def test_toggle_turns_off_then_on(self, shop_id: int) -> None:
        from app.db.models import AlertType
        from app.services import alerts

        off = await alerts.toggle_alert(shop_id, AlertType.LOW_STOCK)
        assert off is False

        on = await alerts.toggle_alert(shop_id, AlertType.LOW_STOCK)
        assert on is True

    async def test_choice_is_saved(self, shop_id: int) -> None:
        """Qayta ochilganda tanlov saqlanib qolishi kerak."""
        from app.db.models import AlertType
        from app.services import alerts

        await alerts.toggle_alert(shop_id, AlertType.DAILY_REPORT)

        settings = await alerts.alert_settings(shop_id)
        assert settings[AlertType.DAILY_REPORT] is False
        # Qolganlariga tegilmagan
        assert settings[AlertType.LOW_STOCK] is True

    async def test_shops_are_independent(self, shop_id: int) -> None:
        """Bir do'kondagi sozlama boshqasiga ta'sir qilmasin."""
        from app.db.base import session_scope
        from app.db.models import AlertType, Shop, User
        from app.services import alerts

        async with session_scope() as session:
            user = User(telegram_id=777002, lang="uz")
            session.add(user)
            await session.flush()
            other = Shop(user_id=user.id, uzum_shop_id="25273", title="AZIKO PLAST")
            session.add(other)
            await session.flush()
            other_id = other.id

        await alerts.toggle_alert(shop_id, AlertType.SKU_BLOCKED)

        assert await alerts.is_enabled(other_id, AlertType.SKU_BLOCKED) is True
        assert await alerts.is_enabled(shop_id, AlertType.SKU_BLOCKED) is False
