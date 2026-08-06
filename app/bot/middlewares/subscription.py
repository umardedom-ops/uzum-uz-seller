"""Obuna cheklovi (SPEC Phase 6).

Muddati tugagan foydalanuvchi bo'limlarga kira olmaydi — tarif ekraniga
yo'naltiriladi. `/start`, tariflar va yordam har doim ochiq: odam to'lay
olmasa ham botdan chiqib keta olsin.

Tarif yetmasa (Basic'da Pro funksiyasi) — boshqacha xabar: bu sotuv
imkoniyati, "kirish yopiq" emas.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.bot.texts import DEFAULT_LANG, LANGS, t
from app.services.billing import Feature, get_access

# Qaysi tugma qaysi funksiyani talab qiladi
_FEATURE_BY_TEXT: dict[str, Feature] = {
    **{t("menu_lost_money", lg): Feature.LOST_MONEY for lg in LANGS},
    **{t("menu_stock", lg): Feature.STOCK for lg in LANGS},
    **{t("menu_reports", lg): Feature.REPORTS for lg in LANGS},
    **{t("menu_unit_econ", lg): Feature.ECONOMICS for lg in LANGS},
    **{t("menu_fbs", lg): Feature.FBS_LABELS for lg in LANGS},
}

# Callback prefikslari
_FEATURE_BY_CALLBACK: tuple[tuple[str, Feature], ...] = (
    ("money:", Feature.LOST_MONEY),
    ("period:", Feature.LOST_MONEY),
    ("cal:", Feature.LOST_MONEY),
    ("stock:", Feature.STOCK),
    ("econ:returns", Feature.RETURNS_ANALYSIS),
    ("econ:", Feature.ECONOMICS),
    ("fbs:", Feature.FBS_LABELS),
)


def _required_feature(event: TelegramObject) -> Feature | None:
    if isinstance(event, Message) and event.text:
        return _FEATURE_BY_TEXT.get(event.text)
    if isinstance(event, CallbackQuery) and event.data:
        for prefix, feature in _FEATURE_BY_CALLBACK:
            if event.data.startswith(prefix):
                return feature
    return None


class SubscriptionMiddleware(BaseMiddleware):
    """Obuna va tarif tekshiruvi."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        feature = _required_feature(event)
        if feature is None:
            return await handler(event, data)  # cheklanmaydigan amal

        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        state = data.get("state")
        lang = DEFAULT_LANG
        if state is not None:
            lang = (await state.get_data()).get("lang", DEFAULT_LANG)

        access = await get_access(user.id)

        if not access.is_active:
            await _deny(event, t("sub_expired", lang))
            return None

        if not access.can(feature):
            await _deny(event, t("sub_upgrade", lang))
            return None

        data["access"] = access
        return await handler(event, data)


async def _deny(event: TelegramObject, text: str) -> None:
    """Cheklov xabari — tariflar tugmasi bilan."""
    from app.bot.keyboards.billing import tariffs_kb

    if isinstance(event, CallbackQuery):
        await event.answer()
        if event.message is not None:
            await event.message.answer(text, reply_markup=tariffs_kb())
    elif isinstance(event, Message):
        await event.answer(text, reply_markup=tariffs_kb())
