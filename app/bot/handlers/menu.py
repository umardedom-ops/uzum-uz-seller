"""Asosiy menyu handler'lari.

Bo'limlar mazmuni Uzum ma'lumotiga bog'liq (Phase 3+). Hozircha menyu
ishlaydi va "tayyorlanmoqda" deb javob beradi — oqim uzilmasin.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.texts import DEFAULT_LANG, LANGS, t

router = Router(name="menu")

# Menyu tugmalari — har ikkala tilda ham tanilsin.
# `menu_lost_money` va `menu_fbs` bu yerda YO'Q: ular o'z routerlariga ega.
_MENU_KEYS = (
    "menu_reports",
    "menu_alerts",
    "menu_settings",
)
_MENU_LABELS = {t(key, lang) for key in _MENU_KEYS for lang in LANGS}


@router.message(F.text.in_(_MENU_LABELS))
async def on_menu_item(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    await message.answer(t("not_ready", lang))
