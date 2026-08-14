"""`/stopapi` (kalitni uzish) va yashirin `/admindad`.

Uch kafolat markazda:
  1. Uzilgach do'kon BUTUNLAY o'chadi — kalit ham, yig'ilgan ma'lumot
     ham. Qayta ulanganda kalit qaysi do'konniki bo'lsa, o'sha ulanadi.
  2. Uzilgandan keyin XABARNOMA KELMAYDI — xabar Uzumdan emas, bazadagi
     ma'lumotdan yasaladi, ya'ni manba qolmasligi kerak.
  3. `/admindad` hech qaysi menyu yoki yordam matnida KO'RINMAYDI.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select

from app.db.base import session_scope, utcnow
from app.db.models import (
    AuthType,
    Plan,
    Product,
    Shop,
    ShopCredential,
    StockSnapshot,
    Subscription,
    SubscriptionStatus,
    User,
)
from app.services import onboarding as svc

APP = Path(__file__).resolve().parents[2] / "app"
TG = 9101


def _capture_bot(monkeypatch) -> list[tuple[int, str]]:
    """Telegramga chiqmasdan yuborilgan xabarlarni yig'ib beradi."""
    import aiogram

    sent: list[tuple[int, str]] = []

    class _Session:
        async def close(self) -> None:
            return None

    class _FakeBot:
        def __init__(self, *args, **kwargs) -> None:
            self.session = _Session()

        async def send_message(self, chat_id, text, *args, **kwargs) -> None:
            sent.append((chat_id, text))

    monkeypatch.setattr(aiogram, "Bot", _FakeBot)
    return sent


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

    async def test_kalitsiz_dokon_ham_uziladi(self) -> None:
        """Kaliti o'chgan, ma'lumoti qolgan do'kon ham tozalanishi kerak.

        `/stopapi` handleri aynan shu tekshiruvga tayanadi — kalitga
        qarab turgan edi va bunday do'kon bazada abadiy qolardi.
        """
        await _seed(with_cred=False)
        assert await svc.has_connected_shop(TG) is True

        assert await svc.disconnect_api(TG) == 1
        assert await svc.has_connected_shop(TG) is False

    async def test_nothing_to_disconnect(self) -> None:
        assert await svc.has_connected_shop(999999) is False

    async def test_disconnect_removes_secret(self) -> None:
        """Kalit bazada QOLMAYDI — shifrlangan sir saqlanmasin."""
        await _seed()
        count = await svc.disconnect_api(TG)
        assert count == 1

        async with session_scope() as s:
            left = list(await s.scalars(select(ShopCredential)))
        assert left == []
        assert await svc.has_api_key(TG) is False

    async def test_shop_row_is_gone(self) -> None:
        """Do'kon qatorining o'zi o'chadi — nofaol qilib qo'yish yetmaydi."""
        shop_id = await _seed()
        await svc.disconnect_api(TG)

        async with session_scope() as s:
            shop = await s.get(Shop, shop_id)
        assert shop is None

    async def test_collected_data_is_gone(self) -> None:
        """Yig'ilgan ma'lumot ham o'chadi — xabar yasashga manba qolmasin.

        Bola jadvallar DB darajasida CASCADE bilan bog'langan, lekin
        SQLite uni bajarmaydi. Shuning uchun xizmat o'zi o'chiradi.
        """
        shop_id = await _seed()
        async with session_scope() as s:
            s.add(Product(shop_id=shop_id, sku="SKU-1", title="Tovar"))
            s.add(
                StockSnapshot(
                    shop_id=shop_id, sku="SKU-1", captured_on=date.today(), qty=5
                )
            )

        await svc.disconnect_api(TG)

        async with session_scope() as s:
            assert list(await s.scalars(select(Product))) == []
            assert list(await s.scalars(select(StockSnapshot))) == []

    async def test_active_shop_pointer_is_cleared(self) -> None:
        """`active_shop_id` o'chgan do'konga ishora qilib qolmasin."""
        shop_id = await _seed()
        async with session_scope() as s:
            user = await s.scalar(select(User).where(User.telegram_id == TG))
            user.active_shop_id = shop_id

        await svc.disconnect_api(TG)

        async with session_scope() as s:
            user = await s.scalar(select(User).where(User.telegram_id == TG))
        assert user.active_shop_id is None

    async def test_reconnect_brings_the_new_keys_shop(self) -> None:
        """Boshqa kalit yuborilsa — o'sha kalitning do'koni ulanadi.

        Eski do'kon qaytib kelmasligi kerak: kalit qaysi do'konniki
        bo'lsa, ro'yxatda faqat o'sha turadi.
        """
        from app.db.repositories import onboarding as repo

        await _seed()
        await svc.disconnect_api(TG)

        async with session_scope() as s:
            user = await s.scalar(select(User).where(User.telegram_id == TG))
            shop = await repo.upsert_shop(s, user, "25273", "AZIKO PLAST")
            await repo.save_credential(s, shop, "tok-new", AuthType.API)

        async with session_scope() as s:
            shops = list(await s.scalars(select(Shop.uzum_shop_id)))
        assert shops == ["25273"]
        assert await svc.has_api_key(TG) is True

    async def test_disconnect_twice_is_safe(self) -> None:
        await _seed()
        assert await svc.disconnect_api(TG) == 1
        assert await svc.disconnect_api(TG) == 0

    async def test_unknown_user(self) -> None:
        assert await svc.disconnect_api(999999) == 0


class TestNoAlertsAfterDisconnect:
    """Uzilgandan keyin xabarnoma va hisobot kelmasligi kerak.

    Shikoyat aynan shundan boshlangan: `/stopapi` dan keyin ham
    "opovisheniya" kelaverardi.
    """

    async def _seed_alertable(self) -> int:
        """Bloklangan tovari bor, obunasi faol do'kon."""
        shop_id = await _seed()
        async with session_scope() as s:
            user = await s.scalar(select(User).where(User.telegram_id == TG))
            s.add(
                Subscription(
                    user_id=user.id,
                    plan=Plan.BASIC,
                    status=SubscriptionStatus.ACTIVE,
                    paid_until=utcnow() + timedelta(days=30),
                )
            )
            s.add(
                Product(
                    shop_id=shop_id,
                    sku="SKU-1",
                    title="Bloklangan tovar",
                    is_blocked=True,
                    block_reason="test",
                )
            )
        return shop_id

    async def test_alerts_sent_while_connected(self, monkeypatch) -> None:
        """Nazorat o'lchovi: kalit turganida xabarnoma ketadi."""
        from app.services import alerts

        await self._seed_alertable()
        sent = _capture_bot(monkeypatch)

        assert await alerts.send_alerts() == 1
        assert len(sent) == 1

    async def test_alerts_stop_after_disconnect(self, monkeypatch) -> None:
        from app.services import alerts

        await self._seed_alertable()
        await svc.disconnect_api(TG)
        sent = _capture_bot(monkeypatch)

        assert await alerts.send_alerts() == 0
        assert sent == []

    async def test_daily_report_stops_after_disconnect(self, monkeypatch) -> None:
        from app.services import reports

        await self._seed_alertable()
        await svc.disconnect_api(TG)
        sent = _capture_bot(monkeypatch)

        assert await reports.send_daily_reports() == 0
        assert sent == []

    async def test_alerts_stop_when_key_marked_invalid(self, monkeypatch) -> None:
        """Kalit yaroqsiz bo'lib qolsa ham xabar yuborilmaydi."""
        from app.services import alerts

        await self._seed_alertable()
        async with session_scope() as s:
            cred = await s.scalar(select(ShopCredential))
            cred.is_valid = False
        sent = _capture_bot(monkeypatch)

        assert await alerts.send_alerts() == 0
        assert sent == []


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
