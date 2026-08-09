"""«Hisobotlar» bo'limi.

Kunlik ko'rsatkichlar: buyurtma, tushum, sof foyda, qaytarish. Xuddi
shu raqamlar har kuni avtomatik xabar sifatida ham keladi
(`workers/scheduler.py`), bu yerda seller ularni istalgan payt va
istalgan kun uchun ko'ra oladi.

⚠️ Bo'lim 2026-08-09 gacha YOZILMAGAN edi — menyuda tugma bor edi-yu,
u «tayyorlanmoqda» deb javob berardi. Xizmat qatlami (`services/reports`)
allaqachon tayyor bo'lgan, faqat ekran yo'q edi.
"""
from __future__ import annotations

from datetime import date, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.texts import DEFAULT_LANG, LANGS, t
from app.core.logging import get_logger
from app.services import reports
from app.services.exports import find_user_shop

log = get_logger(__name__)
router = Router(name="reports")

#: Tugma kaliti → o'sha kunni hisoblovchi funksiya
_DAYS = {
    "today": lambda today: today,
    "yesterday": lambda today: today - timedelta(days=1),
}


def _kb(lang: str, active: str) -> InlineKeyboardMarkup:
    """Kun almashtirish tugmalari. Faol kun belgilanadi."""
    def label(key: str) -> str:
        text = t(f"report_{key}", lang)
        return f"• {text} •" if key == active else text

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label("today"), callback_data="report:today"
                ),
                InlineKeyboardButton(
                    text=label("yesterday"), callback_data="report:yesterday"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=label("week"), callback_data="report:week"
                )
            ],
        ]
    )


async def _render(shop_id: int, shop_title: str, key: str) -> str:
    """Tanlangan davr uchun hisobot matni."""
    today = date.today()

    if key == "week":
        return await _render_week(shop_id, shop_title, today)

    day = _DAYS[key](today)
    stats = await reports.collect_daily_stats(shop_id, day)
    prev = await reports.collect_daily_stats(shop_id, day - timedelta(days=1))
    losses = await reports.month_losses(shop_id, today)
    return reports.render_daily_report(
        shop_title, day, stats, losses, prev_orders=prev.orders
    )


async def _render_week(shop_id: int, shop_title: str, today: date) -> str:
    """7 kunlik yig'indi — kunlik hisobotlar ustiga qo'shiladi."""
    from decimal import Decimal

    from app.docs.numbers import format_money

    orders = returns = 0
    revenue = profit = Decimal("0")
    for offset in range(7):
        stats = await reports.collect_daily_stats(shop_id, today - timedelta(days=offset))
        orders += stats.orders
        returns += stats.returns
        revenue += stats.revenue
        profit += stats.net_profit

    losses = await reports.month_losses(shop_id, today)
    lines = [
        f"📊 <b>7 kun</b> — {shop_title}",
        "",
        f"<blockquote>Buyurtmalar: <b>{orders}</b> ta\n"
        f"Tushum: <b>{format_money(revenue)}</b> so'm\n"
        f"Sof foyda: <b>{format_money(profit)}</b> so'm\n"
        f"Qaytarishlar: <b>{returns}</b> ta</blockquote>",
    ]
    if losses > 0:
        lines += ["", f"💰 Bu oy topilgan yo'qotish: <b>{format_money(losses)}</b> so'm"]
    return "\n".join(lines)


@router.message(F.text.in_({t("menu_reports", lg) for lg in LANGS}))
async def on_reports(message: Message, state: FSMContext) -> None:
    lang = await _lang(state)

    shop = await find_user_shop(message.from_user.id)
    if shop is None:
        await message.answer(t("no_shop", lang))
        return

    await state.update_data(shop_id=shop.id)
    title = shop.title or shop.uzum_shop_id
    await message.answer(
        await _render(shop.id, title, "today"), reply_markup=_kb(lang, "today")
    )


@router.callback_query(F.data.startswith("report:"))
async def on_switch_day(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    key = cb.data.split(":", 1)[1]

    shop = await find_user_shop(cb.from_user.id)
    if shop is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    await cb.answer()
    title = shop.title or shop.uzum_shop_id
    text = await _render(shop.id, title, key)

    # Bir xil matnni qayta yuborish Telegram xatosi beradi — tekshiramiz
    if cb.message is not None and (cb.message.text or "") != text:
        await cb.message.edit_text(text, reply_markup=_kb(lang, key))


async def _lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", DEFAULT_LANG)
