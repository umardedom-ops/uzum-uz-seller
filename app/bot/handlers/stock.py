"""«Qoldiqlar» bo'limi — ombor holati, Excel va PDF yuklab olish.

Bu yerda seller ko'radi: qayerda nechta qoldi, qancha kunga yetadi,
nima bloklangan. Bloklangan tovar — jim yo'qotilayotgan pul.
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
from app.docs.stock import StockRow, build_stock_excel, build_stock_pdf
from app.services.exports import find_user_shop, load_stock_rows

log = get_logger(__name__)
router = Router(name="stock")

GENERATED_DIR = "generated"
PREVIEW_LIMIT = 8


def _export_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_excel_short", lang), callback_data="stock:xlsx"
                ),
                InlineKeyboardButton(
                    text=t("btn_pdf_short", lang), callback_data="stock:pdf"
                ),
            ]
        ]
    )


@router.message(F.text.in_({t("menu_stock", lg) for lg in LANGS}))
async def on_stock(message: Message, state: FSMContext) -> None:
    lang = await _lang(state)

    shop = await find_user_shop(message.from_user.id)
    if shop is None:
        await message.answer(t("no_shop", lang))
        return

    await state.update_data(shop_id=shop.id)
    rows = await load_stock_rows(shop.id)
    if not rows:
        await message.answer(t("stock_empty", lang))
        return

    await message.answer(_render(rows, lang), reply_markup=_export_kb(lang))


def _render(rows: list[StockRow], lang: str) -> str:
    attention = [r for r in rows if r.needs_attention]
    blocked = [r for r in rows if r.is_blocked]
    out_of_stock = [r for r in rows if r.total_qty == 0 and not r.is_blocked]

    lines = [
        t("stock_header", lang, total=len(rows)),
        "",
        t(
            "stock_totals",
            lang,
            fbo=sum(r.fbo_qty for r in rows),
            fbs=sum(r.fbs_qty for r in rows),
        ),
    ]

    if blocked:
        lines += ["", t("stock_blocked", lang, count=len(blocked))]
        lines += [f"  🚫 {r.title[:38]}" for r in blocked[:5]]

    if out_of_stock:
        lines += ["", t("stock_out", lang, count=len(out_of_stock))]
        lines += [f"  ⛔ {r.title[:38]}" for r in out_of_stock[:5]]

    running_low = [
        r for r in rows if r.needs_attention and not r.is_blocked and r.total_qty > 0
    ]
    if running_low:
        lines += ["", t("stock_low", lang, count=len(running_low))]
        lines += [
            f"  ⏳ {r.title[:30]} — {r.days_left_label}" for r in running_low[:5]
        ]

    if not attention:
        lines += ["", t("stock_all_ok", lang)]

    return "\n".join(lines)


@router.callback_query(F.data.in_({"stock:xlsx", "stock:pdf"}))
async def on_export(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    shop = await find_user_shop(cb.from_user.id)
    if shop is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    rows = await load_stock_rows(shop.id)
    if not rows:
        await cb.answer(t("stock_empty", lang), show_alert=True)
        return

    await cb.answer()
    name = shop.uzum_shop_id
    title = shop.title or name

    if cb.data.endswith("pdf"):
        path = build_stock_pdf(rows, f"{GENERATED_DIR}/qoldiq-{name}.pdf", shop_title=title)
    else:
        path = build_stock_excel(rows, f"{GENERATED_DIR}/qoldiq-{name}.xlsx")

    await cb.message.answer_document(
        FSInputFile(path), caption=t("stock_caption", lang)
    )


async def _lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", DEFAULT_LANG)
