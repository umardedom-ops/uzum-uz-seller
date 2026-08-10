"""Zaxira handler — bot jim qolmasligi kafolati.

2026-08-10 da jonli xato: bot restartdan keyin FSM holati yo'qolgan,
foydalanuvchi promokod yuborgan, hech qaysi handler ushlamagan va bot
umuman javob bermagan (klaviatura ham yo'q).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.bot.handlers.fallback import _looks_like_code, on_unhandled_text
from app.db.base import session_scope
from app.db.models import User
from app.services import billing


def _message(text: str, telegram_id: int = 900) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = telegram_id
    msg.answer = AsyncMock()
    return msg


def _state(lang: str = "uz") -> MagicMock:
    st = MagicMock()
    st.get_data = AsyncMock(return_value={"lang": lang})
    return st


async def _seed_user(telegram_id: int) -> None:
    async with session_scope() as session:
        session.add(User(telegram_id=telegram_id))


class TestNeverSilent:
    async def test_random_text_gets_menu(self) -> None:
        """Tasodifiy matn — menyu qaytadi, jim qolmaydi."""
        await _seed_user(901)
        msg = _message("nima gap", 901)

        await on_unhandled_text(msg, _state())

        assert msg.answer.await_count >= 1
        # Klaviatura ham qaytarilgan bo'lishi kerak
        kwargs = msg.answer.await_args.kwargs
        assert kwargs.get("reply_markup") is not None

    async def test_codelike_text_not_called_wrong(self) -> None:
        """Kodga o'xshagan, lekin mavjud bo'lmagan matn — «kod xato»
        demaymiz (oddiy gap bo'lishi mumkin), menyu ko'rsatamiz."""
        await _seed_user(902)
        msg = _message("assalomalaykum", 902)

        await on_unhandled_text(msg, _state())

        said = " ".join(str(c) for c in msg.answer.await_args_list)
        assert "topilmadi" not in said.lower()
        assert msg.answer.await_count >= 1


class TestPromoAnyState:
    async def test_promo_works_outside_choosing_plan(self) -> None:
        """Asosiy tuzatish: kod endi istalgan holatda ishlaydi."""
        await _seed_user(903)
        code = await billing.create_promo(days=30, max_uses=1)

        msg = _message(code, 903)
        await on_unhandled_text(msg, _state())

        access = await billing.get_access(903)
        assert access.is_active
        assert access.plan.value == "pro"
        # Menyu ham ko'rsatilgan
        assert msg.answer.await_count >= 2

    async def test_already_used_is_reported(self) -> None:
        """Ikkinchi marta ishlatilsa — sabab aytiladi, jim qolinmaydi."""
        await _seed_user(904)
        code = await billing.create_promo(days=30, max_uses=5)

        await on_unhandled_text(_message(code, 904), _state())
        second = _message(code, 904)
        await on_unhandled_text(second, _state())

        assert second.answer.await_count >= 1


class TestCodeShape:
    def test_shape(self) -> None:
        assert _looks_like_code("W3G79XXF")
        assert not _looks_like_code("qisqa")       # juda kalta
        assert not _looks_like_code("bir ikki")    # bo'shliq bor
