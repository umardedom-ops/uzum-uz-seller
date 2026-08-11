"""«Qoldiqni o'zgartirish» — Uzumga YOZISH oqimi (tasdiq bilan).

Bu birinchi yozish fichasi. Oqim:

    Qoldiqlar ekrani → ✏️ tugma → SKU tanlash → yangi son →
    TASDIQ ekrani (eski → yangi) → yoziladi

Har amal `stock_write` servisi orqali jurnalga tushadi. Jonli yozish
`UZUM_WRITES_ENABLED` bayrog'i ortida — o'chiq bo'lsa oqim demo rejimda
to'liq ishlaydi (CLAUDE.md qoida #1, app/uzum/writes.py).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.texts import DEFAULT_LANG, t
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import StockWriteStatus
from app.services import returns_restock
from app.services.exports import find_user_shop
from app.services.stock_write import (
    apply_change,
    get_item,
    list_editable_items,
    log_cancelled,
)

log = get_logger(__name__)
router = Router(name="stock_edit")

PAGE_SIZE = 8
MAX_QTY = 1_000_000  # aql bovar qilmas sonlardan himoya


class StockEdit(StatesGroup):
    waiting_qty = State()


def _list_kb(items: list, page: int, lang: str) -> InlineKeyboardMarkup:
    """SKU tanlash klaviaturasi — sahifalash bilan."""
    total = len(items)
    start = page * PAGE_SIZE
    chunk = items[start : start + PAGE_SIZE]

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"{it.title[:36]} · {it.current_qty} dona",
                callback_data=f"stockedit:sku:{it.sku}",
            )
        ]
        for it in chunk
    ]

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="◀️", callback_data=f"stockedit:list:{page - 1}")
        )
    if start + PAGE_SIZE < total:
        nav.append(
            InlineKeyboardButton(text="▶️", callback_data=f"stockedit:list:{page + 1}")
        )
    if nav:
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_confirm_write", lang), callback_data="stockedit:confirm"
                ),
                InlineKeyboardButton(
                    text=t("btn_cancel_write", lang), callback_data="stockedit:cancel"
                ),
            ]
        ]
    )


@router.callback_query(F.data.startswith("stockedit:list:"))
async def on_list(cb: CallbackQuery, state: FSMContext) -> None:
    """SKU ro'yxatini (sahifa) ko'rsatadi."""
    lang = await _lang(state)
    shop = await find_user_shop(cb.from_user.id)
    if shop is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    items = await list_editable_items(shop.id)
    if not items:
        await cb.answer(t("stock_edit_empty", lang), show_alert=True)
        return

    page = _parse_page(cb.data)
    await state.update_data(shop_id=shop.id)
    await cb.answer()
    await cb.message.answer(
        t("stock_edit_pick", lang), reply_markup=_list_kb(items, page, lang)
    )


@router.callback_query(F.data.startswith("stockedit:sku:"))
async def on_pick(cb: CallbackQuery, state: FSMContext) -> None:
    """SKU tanlandi — yangi sonni so'raymiz."""
    lang = await _lang(state)
    shop = await find_user_shop(cb.from_user.id)
    if shop is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    sku = cb.data.split(":", 2)[2]
    item = await get_item(shop.id, sku)
    if item is None:
        await cb.answer(t("stock_edit_empty", lang), show_alert=True)
        return

    await state.update_data(
        shop_id=shop.id, sku=item.sku, old_qty=item.current_qty, title=item.title
    )
    await state.set_state(StockEdit.waiting_qty)
    await cb.answer()
    await cb.message.answer(
        t("stock_edit_ask_qty", lang, title=item.title, qty=item.current_qty)
    )


@router.message(StockEdit.waiting_qty)
async def on_qty(message: Message, state: FSMContext) -> None:
    """Yangi sonni qabul qilib, tasdiq ekranini ko'rsatadi."""
    lang = await _lang(state)
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) > MAX_QTY:
        await message.answer(t("stock_edit_bad_qty", lang))
        return

    new_qty = int(raw)
    data = await state.get_data()
    await state.update_data(new_qty=new_qty)
    await message.answer(
        t(
            "stock_edit_confirm",
            lang,
            title=data.get("title", data.get("sku", "")),
            sku=data.get("sku", ""),
            old=data.get("old_qty", "—"),
            new=new_qty,
        ),
        reply_markup=_confirm_kb(lang),
    )


@router.callback_query(F.data == "stockedit:confirm")
async def on_confirm(cb: CallbackQuery, state: FSMContext) -> None:
    """Tasdiqlandi — yozishga urinamiz (yoki demo)."""
    lang = await _lang(state)
    data = await state.get_data()
    shop_id = data.get("shop_id")
    sku = data.get("sku")
    new_qty = data.get("new_qty")
    if shop_id is None or sku is None or new_qty is None:
        await cb.answer(t("stock_edit_empty", lang), show_alert=True)
        await state.set_state(None)
        return

    await cb.answer()
    outcome = await apply_change(
        shop_id,
        telegram_id=cb.from_user.id,
        sku=sku,
        old_qty=data.get("old_qty"),
        new_qty=new_qty,
    )
    title = data.get("title", sku)
    old = data.get("old_qty", "—")

    if outcome.status is StockWriteStatus.APPLIED:
        text = t("stock_edit_applied", lang, title=title, new=new_qty)
    elif outcome.status is StockWriteStatus.DEMO:
        text = t("stock_edit_demo", lang, title=title, old=old, new=new_qty)
    else:
        text = t("stock_edit_failed", lang, error=outcome.error or "—")

    await state.set_state(None)
    await cb.message.answer(text)


@router.callback_query(F.data == "stockedit:cancel")
async def on_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    """Bekor qilindi — iz qoldiramiz, hech narsa yozilmaydi."""
    lang = await _lang(state)
    data = await state.get_data()
    shop_id = data.get("shop_id")
    sku = data.get("sku")
    if shop_id is not None and sku is not None and data.get("new_qty") is not None:
        await log_cancelled(
            shop_id,
            telegram_id=cb.from_user.id,
            sku=sku,
            old_qty=data.get("old_qty"),
            new_qty=data.get("new_qty"),
        )
    await state.set_state(None)
    await cb.answer()
    await cb.message.answer(t("stock_edit_cancelled", lang))


# ---------------------------------------------------------------------- #
# ↩️ Qaytgan tovarni qoldiqqa qaytarish
# ---------------------------------------------------------------------- #


@router.callback_query(F.data == "restock:show")
async def on_restock_show(cb: CallbackQuery, state: FSMContext) -> None:
    """Qaytgan, lekin qoldiqqa qo'shilmagan tovarlarni ko'rsatadi."""
    lang = await _lang(state)
    shop = await find_user_shop(cb.from_user.id)
    if shop is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    await cb.answer()
    plan = await returns_restock.collect_pending(shop.id)

    if not plan:
        text = t("restock_empty", lang)
        if plan.skipped_no_barcode:
            text += "\n\n" + t(
                "restock_skipped", lang, count=plan.skipped_no_barcode
            )
        await cb.message.answer(text)
        return

    await state.update_data(shop_id=shop.id)
    lines = [
        t("restock_header", lang, count=len(plan.items), total=plan.total_qty),
        "",
    ]
    lines += [f"• {item.label}" for item in plan.items[:15]]
    if len(plan.items) > 15:
        lines.append(t("restock_more", lang, rest=len(plan.items) - 15))
    if plan.skipped_no_barcode:
        lines += ["", t("restock_skipped", lang, count=plan.skipped_no_barcode)]

    await cb.message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t("btn_restock_apply", lang),
                        callback_data="restock:apply",
                    ),
                    InlineKeyboardButton(
                        text=t("btn_cancel_write", lang),
                        callback_data="restock:cancel",
                    ),
                ]
            ]
        ),
    )


@router.callback_query(F.data == "restock:apply")
async def on_restock_apply(cb: CallbackQuery, state: FSMContext) -> None:
    """Tasdiqlandi — qoldiqqa qo'shamiz."""
    lang = await _lang(state)
    shop = await find_user_shop(cb.from_user.id)
    if shop is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    await cb.answer(t("stock_edit_writing", lang))

    # Rejani QAYTA yig'amiz: ekran ochilgandan beri sync o'tган bo'lishi
    # mumkin, eski ro'yxat bilan yozsak noto'g'ri son chiqadi.
    plan = await returns_restock.collect_pending(shop.id)
    if not plan:
        await cb.message.answer(t("restock_empty", lang))
        return

    ok, failed = await returns_restock.apply_plan(
        shop.id, plan, telegram_id=cb.from_user.id
    )

    text = t("restock_done", lang, ok=ok)
    if failed:
        text += "\n\n" + t("restock_failed", lang, count=failed)
    if not get_settings().uzum_writes_enabled:
        text += "\n\n" + t("stock_edit_demo_note", lang)

    await cb.message.answer(text)


@router.callback_query(F.data == "restock:cancel")
async def on_restock_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    await cb.answer()
    await cb.message.answer(t("stock_edit_cancelled", lang))


def _parse_page(data: str) -> int:
    try:
        return max(0, int(data.rsplit(":", 1)[1]))
    except (ValueError, IndexError):
        return 0


async def _lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", DEFAULT_LANG)
