"""API kalitni uzish va qayta ulash.

`/stopapi` — kalit o'chadi, sinxronizatsiya to'xtaydi. Seller istalgan
payt ulanishni uza olishi kerak: "kalitni bermay turay" degan huquq
ishonchning bir qismi. Kabinetga kirish shart emas.

Qayta ulash: shunchaki yangi kalitni botga yuboring — `fallback` uni
tanib, o'zi ulaydi (alohida buyruq kerak emas).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.texts import DEFAULT_LANG, t
from app.core.logging import get_logger
from app.services import onboarding as svc

log = get_logger(__name__)
router = Router(name="apikey")


async def _lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", DEFAULT_LANG)


@router.message(Command("stopapi"))
async def cmd_stop_api(message: Message, state: FSMContext) -> None:
    """Kalitni uzish — avval tasdiq so'raymiz.

    Tasdiqsiz o'chirsak, tasodifan bosilganda seller ma'lumotsiz qolib,
    sababini tushunmasdi.
    """
    lang = await _lang(state)

    # Kalit emas, DO'KON borligi tekshiriladi: kaliti allaqachon o'chgan,
    # lekin ma'lumoti qolgan do'konni ham seller tozalay olsin.
    if not await svc.has_connected_shop(message.from_user.id):
        await message.answer(t("stopapi_none", lang))
        return

    await message.answer(
        t("stopapi_confirm", lang),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t("stopapi_yes", lang), callback_data="apikey:stop"
                    ),
                    InlineKeyboardButton(
                        text=t("btn_cancel_write", lang), callback_data="apikey:keep"
                    ),
                ]
            ]
        ),
    )


@router.callback_query(F.data == "apikey:stop")
async def on_stop_confirm(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    count = await svc.disconnect_api(cb.from_user.id)
    await cb.answer()
    await cb.message.answer(
        t("stopapi_done", lang, count=count) if count else t("stopapi_none", lang)
    )


@router.callback_query(F.data == "apikey:keep")
async def on_stop_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    await cb.answer()
    await cb.message.answer(t("stopapi_kept", lang))
