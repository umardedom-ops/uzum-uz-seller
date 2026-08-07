"""Onboarding oqimi (SPEC 7).

/start → til → xush kelibsiz → oferta → telefon → yo'riqnoma → do'kon ID
→ asosiy menyu
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.bot.keyboards.menu import main_menu_kb
from app.bot.keyboards.onboarding import (
    how_to_kb,
    lang_kb,
    oferta_kb,
    phone_kb,
    start_kb,
)
from app.bot.states.onboarding import Onboarding
from app.bot.texts import DEFAULT_LANG, t
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services import onboarding as svc

log = get_logger(__name__)
router = Router(name="onboarding")


def _money(amount: int) -> str:
    """149000 → «149 000»."""
    return f"{amount:,}".replace(",", " ")


async def _lang(state: FSMContext) -> str:
    """FSM'dan tanlangan tilni oladi."""
    data = await state.get_data()
    return data.get("lang", DEFAULT_LANG)


# --- 1. /start → til tanlash ---
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Onboarding.choosing_lang)
    await message.answer(t("choose_lang"), reply_markup=lang_kb())


# --- 2. Til tanlandi → xush kelibsiz ---
@router.callback_query(F.data.startswith("lang:"))
async def on_lang(cb: CallbackQuery, state: FSMContext) -> None:
    lang = cb.data.split(":", 1)[1]
    await state.update_data(lang=lang)
    await svc.save_user(
        cb.from_user.id,
        lang,
        full_name=cb.from_user.full_name,
        username=cb.from_user.username,
    )

    s = get_settings()
    await cb.message.edit_text(
        t(
            "welcome",
            lang,
            trial_days=s.trial_days,
            price=_money(s.price_basic),
        ),
        reply_markup=start_kb(lang),
    )
    await state.set_state(Onboarding.accepting_oferta)
    await cb.answer()


# --- 3. Boshlash → oferta ---
@router.callback_query(F.data == "start:go")
async def on_start(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    await cb.message.edit_text(
        t("oferta", lang, url=get_settings().oferta_url),
        reply_markup=oferta_kb(lang),
        disable_web_page_preview=True,
    )
    await cb.answer()


# --- 4. Oferta qabul qilindi → telefon so'rash ---
@router.callback_query(F.data == "oferta:accept")
async def on_oferta_accept(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    await svc.accept_oferta(cb.from_user.id)
    await state.set_state(Onboarding.sharing_phone)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(t("ask_phone", lang), reply_markup=phone_kb(lang))
    await cb.answer()


# --- 5. Telefon keldi → ulanish taklifi ---
@router.message(Onboarding.sharing_phone, F.contact)
async def on_contact(message: Message, state: FSMContext) -> None:
    lang = await _lang(state)
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    await svc.save_user(message.from_user.id, lang, phone)

    await message.answer(
        t("phone_saved", lang, phone=phone), reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(Onboarding.reading_instruction)
    await message.answer(t("connect_intro", lang), reply_markup=how_to_kb(lang))


@router.message(Onboarding.sharing_phone)
async def on_phone_invalid(message: Message, state: FSMContext) -> None:
    """Foydalanuvchi tugma o'rniga matn yozsa."""
    lang = await _lang(state)
    await message.answer(t("phone_invalid", lang), reply_markup=phone_kb(lang))


# --- 6. Yo'riqnoma → API kalit so'rash ---
@router.callback_query(F.data == "connect:how")
async def on_how_to(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)

    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(t("instruction", lang))
    await state.set_state(Onboarding.entering_api_key)
    await cb.message.answer(t("ask_api_key", lang))
    await cb.answer()


# --- 7. API kalit → tekshirish, do'konlarni topish, saqlash ---
@router.message(Onboarding.entering_api_key, F.text)
async def on_api_key(message: Message, state: FSMContext) -> None:
    lang = await _lang(state)
    raw = message.text.strip()

    if not svc.looks_like_api_key(raw):
        await message.answer(t("key_invalid_format", lang))
        return

    # SPEC 9.3: maxfiy ma'lumot qabul qilingach xabar o'chiriladi.
    # Tekshiruvdan OLDIN o'chiramiz — kalit chatda turgan har soniya xavf.
    try:
        await message.delete()
    except TelegramBadRequest:
        # Bot xabarni o'chira olmasa (huquq yo'q) — oqim to'xtamasin,
        # lekin sellerni ogohlantiramiz.
        log.warning("Kalit xabarini o'chirib bo'lmadi: tg_id=%s", message.from_user.id)
        await message.answer(t("delete_failed", lang))

    status = await message.answer(t("key_checking", lang))
    result = await svc.connect_with_api_key(message.from_user.id, raw)

    if not result.ok:
        key = "key_no_shops" if result.error == "no_shops" else "key_rejected"
        await status.edit_text(t(key, lang))
        return

    await state.set_state(Onboarding.done)
    shops = ", ".join(s["title"] or s["id"] for s in result.shops)
    await status.edit_text(
        t("shop_connected", lang, shops=shops, trial_days=get_settings().trial_days)
    )
    await message.answer(t("main_menu", lang), reply_markup=main_menu_kb(lang))
