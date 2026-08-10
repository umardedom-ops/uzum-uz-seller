"""`/start` qaytib kelgan foydalanuvchini tanishi kerak.

2026-08-10 da jonli xato: do'koni ulangan seller `/start` bosganda
onboarding noldan boshlanib, undan **yana API kalit** so'ralardi.
FSM holati bot restartida yo'qolgani uchun bu muntazam takrorlanardi.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.bot.handlers.start import cmd_start
from app.bot.states.onboarding import Onboarding
from app.db.base import session_scope
from app.db.models import Lang, Shop, User


def _message(telegram_id: int) -> MagicMock:
    msg = MagicMock()
    msg.text = "/start"
    msg.from_user.id = telegram_id
    msg.answer = AsyncMock()
    return msg


def _state() -> MagicMock:
    st = MagicMock()
    st.clear = AsyncMock()
    st.set_state = AsyncMock()
    st.update_data = AsyncMock()
    st.get_data = AsyncMock(return_value={})
    return st


async def _seed(telegram_id: int, *, with_shop: bool, lang: Lang = Lang.UZ) -> None:
    async with session_scope() as session:
        user = User(telegram_id=telegram_id, lang=lang)
        session.add(user)
        await session.flush()
        if with_shop:
            session.add(
                Shop(user_id=user.id, uzum_shop_id="7973", title="AZIKO", is_active=True)
            )


class TestReturningUser:
    async def test_connected_user_gets_menu_not_onboarding(self) -> None:
        await _seed(801, with_shop=True)
        msg, st = _message(801), _state()

        await cmd_start(msg, st)

        text = str(msg.answer.await_args)
        # Til tanlash EMAS — menyu bo'lishi kerak
        assert "Tilni tanlang" not in text
        assert msg.answer.await_args.kwargs.get("reply_markup") is not None
        st.set_state.assert_awaited_with(Onboarding.done)

    async def test_menu_uses_saved_language(self) -> None:
        """Til bazadan olinadi — FSM bo'sh bo'lsa ham."""
        await _seed(802, with_shop=True, lang=Lang.RU)
        msg, st = _message(802), _state()

        await cmd_start(msg, st)

        kwargs = st.update_data.await_args.kwargs
        assert kwargs.get("lang") == "ru"


class TestNewUser:
    async def test_without_shop_starts_onboarding(self) -> None:
        await _seed(803, with_shop=False)
        msg, st = _message(803), _state()

        await cmd_start(msg, st)

        st.set_state.assert_awaited_with(Onboarding.choosing_lang)

    async def test_unknown_user_starts_onboarding(self) -> None:
        msg, st = _message(804), _state()

        await cmd_start(msg, st)

        st.set_state.assert_awaited_with(Onboarding.choosing_lang)
