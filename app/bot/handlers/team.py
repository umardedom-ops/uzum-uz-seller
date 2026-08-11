"""Hodimlar va guruh/kanalga hisobot — bot interfeysi.

Hodim qo'shish oqimi ataylab sodda: egasi hodimning Telegram ID sini
yuboradi. Username orqali qidirish Telegram API'da ishonchli emas
(maxfiylik sozlamasi yopiq bo'lsa topilmaydi) va "topilmadi" xatosi
foydalanuvchini chalg'itadi.

Guruh ulash: bot guruhga qo'shiladi va o'sha guruhda `/ulash` yoziladi —
shunda chat ID ni o'zimiz bilamiz, foydalanuvchi uni qidirmaydi.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.texts import DEFAULT_LANG, t
from app.core.logging import get_logger
from app.db.models import StaffRole
from app.services import team
from app.services.exports import find_user_shop

log = get_logger(__name__)
router = Router(name="team")


class Team(StatesGroup):
    adding_staff = State()


async def _lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", DEFAULT_LANG)


# ---------------------------------------------------------------------- #
# 👤 Hodimlar
# ---------------------------------------------------------------------- #


def _staff_kb(members: list[team.StaffMember], lang: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=t("staff_remove_btn", lang, who=m.title or m.telegram_id),
                callback_data=f"team:rm:{m.telegram_id}",
            )
        ]
        for m in members
    ]
    rows.append(
        [InlineKeyboardButton(text=t("staff_add_btn", lang), callback_data="team:add")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "team:staff")
async def on_staff(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    shop = await find_user_shop(cb.from_user.id)
    if shop is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    await cb.answer()
    await state.update_data(shop_id=shop.id)
    members = await team.list_staff(shop.id)

    text = t("staff_header", lang, shop=shop.title or shop.uzum_shop_id)
    if members:
        text += "\n\n" + "\n".join(f"• {m.label}" for m in members)
    else:
        text += "\n\n" + t("staff_empty", lang)

    await cb.message.answer(text, reply_markup=_staff_kb(members, lang))


@router.callback_query(F.data == "team:add")
async def on_staff_add(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    await cb.answer()
    await state.set_state(Team.adding_staff)
    await cb.message.answer(t("staff_ask_id", lang))


@router.message(Team.adding_staff)
async def on_staff_id(message: Message, state: FSMContext) -> None:
    """Hodim ID sini qabul qiladi."""
    lang = await _lang(state)
    raw = (message.text or "").strip()

    if not raw.lstrip("-").isdigit():
        await message.answer(t("staff_bad_id", lang))
        return

    data = await state.get_data()
    shop_id = data.get("shop_id")
    if shop_id is None:
        shop = await find_user_shop(message.from_user.id)
        if shop is None:
            await state.clear()
            await message.answer(t("no_shop", lang))
            return
        shop_id = shop.id

    member = await team.add_staff(
        message.from_user.id, int(shop_id), int(raw), role=StaffRole.VIEWER
    )
    await state.set_state(None)

    if member is None:
        await message.answer(t("staff_add_failed", lang))
        return

    await message.answer(t("staff_added", lang, who=member.telegram_id))


@router.callback_query(F.data.startswith("team:rm:"))
async def on_staff_remove(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    staff_tg = int(cb.data.rsplit(":", 1)[1])

    shop = await find_user_shop(cb.from_user.id)
    if shop is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    ok = await team.remove_staff(cb.from_user.id, shop.id, staff_tg)
    await cb.answer(t("staff_removed" if ok else "staff_add_failed", lang))

    members = await team.list_staff(shop.id)
    await cb.message.edit_reply_markup(reply_markup=_staff_kb(members, lang))


# ---------------------------------------------------------------------- #
# 📢 Guruh / kanal
# ---------------------------------------------------------------------- #


@router.callback_query(F.data == "team:channels")
async def on_channels(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    shop = await find_user_shop(cb.from_user.id)
    if shop is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    await cb.answer()
    channels = await team.list_channels(shop.id)

    text = t("channels_header", lang)
    if channels:
        text += "\n\n" + "\n".join(f"• {c.label}" for c in channels)
    else:
        text += "\n\n" + t("channels_empty", lang)
    text += "\n\n" + t("channels_howto", lang)

    rows = [
        [
            InlineKeyboardButton(
                text=t("channel_unlink_btn", lang, who=c.label[:24]),
                callback_data=f"team:unlink:{c.chat_id}",
            )
        ]
        for c in channels
    ]
    await cb.message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
    )


@router.callback_query(F.data.startswith("team:unlink:"))
async def on_channel_unlink(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    chat_id = int(cb.data.rsplit(":", 1)[1])

    shop = await find_user_shop(cb.from_user.id)
    if shop is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    ok = await team.unlink_channel(cb.from_user.id, shop.id, chat_id)
    await cb.answer(t("channel_unlinked" if ok else "staff_add_failed", lang))
    if ok and cb.message is not None:
        await cb.message.edit_reply_markup(reply_markup=None)


@router.message(Command("ulash", "link"))
async def cmd_link_channel(message: Message, state: FSMContext) -> None:
    """Guruh/kanalda yoziladi — o'sha chatni do'konga ulaydi.

    Shaxsiy chatda yozilsa ma'nosi yo'q: hisobot allaqachon shu yerga
    keladi. Shuning uchun ochiq aytamiz.
    """
    lang = await _lang(state)

    if message.chat.type == "private":
        await message.answer(t("channel_private", lang))
        return

    shop = await find_user_shop(message.from_user.id)
    if shop is None:
        await message.answer(t("no_shop", lang))
        return

    channel = await team.link_channel(
        message.from_user.id,
        shop.id,
        message.chat.id,
        title=message.chat.title,
    )
    if channel is None:
        await message.answer(t("channel_not_owner", lang))
        return

    await message.answer(
        t("channel_linked", lang, shop=shop.title or shop.uzum_shop_id)
    )
