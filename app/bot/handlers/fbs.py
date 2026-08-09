"""FBS/DBS bo'limi — buyurtmalar va yorliqlar.

Seller kabinetga kirmasdan, botdan yorliq oladi. Faqat GET — hech narsa
o'zgartirilmaydi.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.texts import DEFAULT_LANG, LANGS, t
from app.core.logging import get_logger
from app.services import fbs
from app.services.exports import find_user_shop

log = get_logger(__name__)
router = Router(name="fbs")

# Bir ekranda nechta buyurtma ko'rsatiladi
PAGE_SIZE = 10


@router.message(F.text.in_({t("menu_fbs", lg) for lg in LANGS}))
async def on_fbs(message: Message, state: FSMContext) -> None:
    lang = await _lang(state)

    shop = await find_user_shop(message.from_user.id)
    if shop is None:
        await message.answer(t("no_shop", lang))
        return

    status = await message.answer(t("fbs_loading", lang))
    try:
        orders = await fbs.list_pending_orders(shop.id)
    except fbs.FbsUnavailableError:
        # "Buyurtma yo'q" demaymiz — bu yolg'on tinchlik bo'lardi va
        # seller yig'ilmagan buyurtmalarni o'tkazib yuborardi.
        await status.edit_text(t("fbs_unavailable", lang))
        return

    if not orders:
        await status.edit_text(t("fbs_empty", lang))
        return

    await state.update_data(shop_id=shop.id)
    shown = orders[:PAGE_SIZE]
    text = t("fbs_header", lang, count=len(orders)) + "\n\n" + "\n".join(
        f"• {order.label}" for order in shown
    )
    if len(orders) > PAGE_SIZE:
        text += "\n\n" + t("fbs_more", lang, rest=len(orders) - PAGE_SIZE)

    await status.edit_text(text, reply_markup=_orders_kb(shown, lang))


def _orders_kb(orders: list[fbs.FbsOrder], lang: str) -> InlineKeyboardMarkup:
    """Har buyurtma uchun yorliq tugmasi."""
    rows = [
        [
            InlineKeyboardButton(
                text=t("btn_label_for", lang, order=order.order_id),
                callback_data=f"fbs:label:{order.order_id}",
            )
        ]
        for order in orders
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("fbs:label:"))
async def on_label(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    order_id = int(cb.data.rsplit(":", 1)[1])

    data = await state.get_data()
    shop_id = data.get("shop_id")
    if shop_id is None:
        shop = await find_user_shop(cb.from_user.id)
        if shop is None:
            await cb.answer(t("no_shop", lang), show_alert=True)
            return
        shop_id = shop.id

    await cb.answer(t("fbs_preparing", lang))
    path = await fbs.download_label(shop_id, order_id)

    if path is None:
        await cb.message.answer(t("fbs_label_failed", lang, order=order_id))
        return

    await cb.message.answer_document(
        FSInputFile(path), caption=t("fbs_label_caption", lang, order=order_id)
    )


async def _lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", DEFAULT_LANG)
