"""`/stopapi` (kalitni uzish) va yashirin `/admindad`.

Ikki kafolat markazda:
  1. Kalit uzilgach bazada QOLMAYDI va qayta ulash ishlaydi.
  2. `/admindad` hech qaysi menyu yoki yordam matnida KO'RINMAYDI.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.db.base import session_scope
from app.db.models import AuthType, Shop, ShopCredential, User
from app.services import onboarding as svc

APP = Path(__file__).resolve().parents[2] / "app"
TG = 9101


async def _seed(*, with_cred: bool = True) -> int:
    async with session_scope() as s:
        user = User(telegram_id=TG)
        s.add(user)
        await s.flush()
        shop = Shop(user_id=user.id, uzum_shop_id="7973", is_active=True)
        s.add(shop)
        await s.flush()
        if with_cred:
            cred = ShopCredential(
                shop_id=shop.id, auth_type=AuthType.API, is_valid=True
            )
            cred.secret = "tok-xyz"
            s.add(cred)
        return shop.id


class TestStopApi:
    async def test_has_key_detection(self) -> None:
        await _seed()
        assert await svc.has_api_key(TG) is True

    async def test_without_key(self) -> None:
        await _seed(with_cred=False)
        assert await svc.has_api_key(TG) is False

    async def test_disconnect_removes_secret(self) -> None:
        """Kalit bazada QOLMAYDI — shifrlangan sir saqlanmasin."""
        await _seed()
        count = await svc.disconnect_api(TG)
        assert count == 1

        async with session_scope() as s:
            left = list(await s.scalars(select(ShopCredential)))
        assert left == []
        assert await svc.has_api_key(TG) is False

    async def test_shop_and_data_survive(self) -> None:
        """Do'kon va yig'ilgan ma'lumot o'chmaydi — faqat kalit uziladi."""
        shop_id = await _seed()
        await svc.disconnect_api(TG)

        async with session_scope() as s:
            shop = await s.get(Shop, shop_id)
        assert shop is not None and shop.is_active

    async def test_disconnect_twice_is_safe(self) -> None:
        await _seed()
        assert await svc.disconnect_api(TG) == 1
        assert await svc.disconnect_api(TG) == 0

    async def test_unknown_user(self) -> None:
        assert await svc.disconnect_api(999999) == 0


class TestReconnectDetection:
    def test_key_is_recognised(self) -> None:
        """Kalit yuborilsa fallback uni tanishi kerak."""
        assert svc.looks_like_api_key("a" * 40)

    def test_ordinary_text_is_not_a_key(self) -> None:
        assert not svc.looks_like_api_key("salom qalaysiz")
        assert not svc.looks_like_api_key("qisqa")


class TestAdmindadIsHidden:
    """Buyruq bor, lekin hech qayerda e'lon qilinmaydi."""

    def _sources(self) -> str:
        parts = []
        for folder in ("bot/handlers", "bot/keyboards", "bot/texts"):
            for path in (APP / folder).glob("*.py"):
                parts.append(path.read_text(encoding="utf-8"))
        return "\n".join(parts)

    def test_command_exists(self) -> None:
        from app.bot.handlers import admin

        names = [h.callback.__name__ for h in admin.router.message.handlers]
        assert "cmd_admindad" in names

    def test_not_advertised_anywhere(self) -> None:
        """Foydalanuvchiga ko'rinadigan matnlarda bo'lmasligi shart."""
        src = self._sources()
        # Faqat handler ta'rifida uchraydi — matnlarda emas
        assert src.count("admindad") <= 2, "buyruq matnlarda oshkor bo'lgan"

    def test_not_in_texts(self) -> None:
        from app.bot.texts.ru import TEXTS as RU
        from app.bot.texts.uz import TEXTS as UZ

        for catalog in (UZ, RU):
            joined = " ".join(catalog.values())
            assert "admindad" not in joined

    def test_not_in_admin_panel_help(self) -> None:
        """`/admin` paneli buyruqlar ro'yxatida ko'rinmasin."""
        src = (APP / "bot/handlers/admin.py").read_text(encoding="utf-8")
        panel = src[src.index("async def cmd_admin") : src.index("async def cmd_business_report")]
        assert "admindad" not in panel
