"""«Top tovarlar» hisoboti — eng ko'p sotilgan / eng ko'p foyda bergan.

Raqobatchida bu statik ro'yxat. Bizda ikki saralash: soni bo'yicha va
foyda bo'yicha — bir bosishda almashadi. Ma'lumot `economics.collect`
dan olinadi (tannarx Uzumniki, sellerdan so'ralmaydi).
"""
from __future__ import annotations

from datetime import date, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.texts import DEFAULT_LANG, LANGS, t
from app.core.logging import get_logger
from app.docs.numbers import format_money
from app.services import economics
from app.services.exports import find_user_shop

log = get_logger(__name__)
router = Router(name="top")

DAYS = 30
LIMIT = 10


def _kb(lang: str, *, active: str) -> InlineKeyboardMarkup:
    """Saralash tugmalari — faol bo'lgani belgilanadi."""
    def label(key: str, text_key: str) -> str:
        mark = "🔘 " if key == active else ""
        return mark + t(text_key, lang)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label("qty", "top_by_qty"), callback_data="top:qty"
                ),
                InlineKeyboardButton(
                    text=label("profit", "top_by_profit"), callback_data="top:profit"
                ),
            ]
        ]
    )


def _render(rows: list[economics.SkuEconomics], lang: str, *, by: str) -> str:
    """Top ro'yxatini matnga aylantiradi."""
    ranked = sorted(
        rows,
        key=lambda r: (r.profit if by == "profit" else r.qty_sold),
        reverse=True,
    )[:LIMIT]

    header = t("top_header_profit" if by == "profit" else "top_header_qty", lang)
    lines = [header, ""]
    for i, r in enumerate(ranked, 1):
        lines.append(
            t(
                "top_row",
                lang,
                n=i,
                title=(r.title or r.sku)[:34],
                qty=r.qty_sold,
                revenue=format_money(r.revenue),
                profit=format_money(r.profit),
            )
        )
    return "\n".join(lines)


async def _load(shop_id: int) -> list[economics.SkuEconomics]:
    today = date.today()
    summary = await economics.collect(shop_id, today - timedelta(days=DAYS), today)
    return [r for r in summary.rows if r.qty_sold > 0]


@router.message(F.text.in_({t("menu_top", lg) for lg in LANGS}))
async def on_top(message: Message, state: FSMContext) -> None:
    lang = await _lang(state)

    shop = await find_user_shop(message.from_user.id)
    if shop is None:
        await message.answer(t("no_shop", lang))
        return

    await state.update_data(shop_id=shop.id)
    rows = await _load(shop.id)
    if not rows:
        await message.answer(t("top_empty", lang))
        return

    await message.answer(_render(rows, lang, by="qty"), reply_markup=_kb(lang, active="qty"))


@router.callback_query(F.data.in_({"top:qty", "top:profit"}))
async def on_top_sort(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    by = cb.data.split(":", 1)[1]

    data = await state.get_data()
    shop_id = data.get("shop_id")
    if shop_id is None:
        shop = await find_user_shop(cb.from_user.id)
        if shop is None:
            await cb.answer(t("no_shop", lang), show_alert=True)
            return
        shop_id = shop.id

    rows = await _load(shop_id)
    if not rows:
        await cb.answer(t("top_empty", lang), show_alert=True)
        return

    await cb.answer()
    await cb.message.edit_text(
        _render(rows, lang, by=by), reply_markup=_kb(lang, active=by)
    )


async def _lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", DEFAULT_LANG)
