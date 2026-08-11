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
    """Har buyurtma uchun yorliq tugmasi + «Barcha yorliqlar bitta PDF»."""
    rows: list[list[InlineKeyboardButton]] = []
    if len(orders) > 1:
        # Bittadan ko'p bo'lsagina — bir bosishda hammasi (raqobatchi fichasi)
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("btn_all_labels", lang, count=len(orders)),
                    callback_data="fbs:all",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=t("btn_acts", lang), callback_data="fbs:invoices")]
    )
    rows += [
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


@router.callback_query(F.data == "fbs:all")
async def on_all_labels(cb: CallbackQuery, state: FSMContext) -> None:
    """Barcha buyurtma yorlig'ini bitta PDF qilib yuboradi."""
    lang = await _lang(state)

    data = await state.get_data()
    shop_id = data.get("shop_id")
    if shop_id is None:
        shop = await find_user_shop(cb.from_user.id)
        if shop is None:
            await cb.answer(t("no_shop", lang), show_alert=True)
            return
        shop_id = shop.id

    await cb.answer(t("fbs_preparing", lang))
    try:
        path = await fbs.download_all_labels(shop_id)
    except fbs.FbsUnavailableError:
        await cb.message.answer(t("fbs_unavailable", lang))
        return

    if path is None:
        await cb.message.answer(t("fbs_all_labels_failed", lang))
        return

    await cb.message.answer_document(
        FSInputFile(path), caption=t("fbs_all_labels_caption", lang)
    )


async def _shop_id(cb: CallbackQuery, state: FSMContext) -> int | None:
    """Joriy do'kon — FSM'da bo'lmasa bazadan (restartdan keyin ham ishlasin)."""
    data = await state.get_data()
    shop_id = data.get("shop_id")
    if shop_id is not None:
        return int(shop_id)
    shop = await find_user_shop(cb.from_user.id)
    return shop.id if shop else None


@router.callback_query(F.data == "fbs:invoices")
async def on_invoices(cb: CallbackQuery, state: FSMContext) -> None:
    """FBS yuk xatlari ro'yxati — har biriga ikkita akt tugmasi."""
    lang = await _lang(state)
    shop_id = await _shop_id(cb, state)
    if shop_id is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    await cb.answer()
    try:
        invoices = await fbs.list_invoices(shop_id)
    except fbs.FbsUnavailableError:
        await cb.message.answer(t("fbs_unavailable", lang))
        return

    if not invoices:
        await cb.message.answer(t("acts_empty", lang))
        return

    shown = invoices[:PAGE_SIZE]
    rows = [
        [
            InlineKeyboardButton(
                text=t("btn_act_supply", lang, invoice=inv.invoice_id),
                callback_data=f"fbs:act:{inv.invoice_id}",
            ),
            InlineKeyboardButton(
                text=t("btn_act_accept", lang),
                callback_data=f"fbs:actc:{inv.invoice_id}",
            ),
        ]
        for inv in shown
    ]

    text = t("acts_header", lang, count=len(invoices)) + "\n\n" + "\n".join(
        f"• {inv.label}" for inv in shown
    )
    await cb.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith(("fbs:act:", "fbs:actc:")))
async def on_act(cb: CallbackQuery, state: FSMContext) -> None:
    """Ta'minlash akti (`fbs:act:`) yoki qabul akti (`fbs:actc:`)."""
    lang = await _lang(state)
    closing = cb.data.startswith("fbs:actc:")
    invoice_id = int(cb.data.rsplit(":", 1)[1])

    shop_id = await _shop_id(cb, state)
    if shop_id is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    await cb.answer(t("fbs_preparing", lang))
    path = await fbs.download_invoice_document(shop_id, invoice_id, closing=closing)

    if path is None:
        await cb.message.answer(t("act_failed", lang, invoice=invoice_id))
        return

    caption = t(
        "act_caption_accept" if closing else "act_caption_supply",
        lang,
        invoice=invoice_id,
    )
    await cb.message.answer_document(FSInputFile(path), caption=caption)


async def _lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", DEFAULT_LANG)
