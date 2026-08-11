"""Onboarding klaviaturalari."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.bot.texts import t


def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("lang_uz"), callback_data="lang:uz"),
                InlineKeyboardButton(text=t("lang_ru"), callback_data="lang:ru"),
            ]
        ]
    )


# ❗ `start_kb` OLIB TASHLANDI (2026-08-11). U «🚀 Boshlash» tugmasini
# `start:go` callback bilan chizardi, lekin bu callback uchun handler
# YO'Q edi — bosilsa bot jim qolardi. Ustiga klaviatura hech qayerda
# ishlatilmasdi: xush kelibsiz ekranidan keyin darhol tarif tanlash
# keladi, oraliq tugma kerak emas.
#
# Bunday holat qaytmasligi uchun `tests/unit/test_buttons.py` har bir
# `callback_data` ga handler borligini tekshiradi.


def oferta_kb(lang: str) -> InlineKeyboardMarkup:
    """«Oferta» tugmasi — bosilganda hujjat ochiladi.

    Server internetda bo'lsa — to'g'ridan-to'g'ri havola (URL tugma).
    Bo'lmasa — fayl yuboriladi. Ikkala holatda ham seller hujjatni
    o'qiy oladi va oqim to'xtamaydi.
    """
    url = _public_oferta_url()
    top = (
        InlineKeyboardButton(text=t("btn_oferta_full", lang), url=url)
        if url
        else InlineKeyboardButton(
            text=t("btn_oferta_full", lang), callback_data="oferta:full"
        )
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [top],
            [
                InlineKeyboardButton(
                    text=t("btn_accept", lang), callback_data="oferta:accept"
                )
            ],
        ]
    )


def _public_oferta_url() -> str | None:
    """Ochiq internetdan ochiladigan oferta havolasi (bo'lmasa None).

    `localhost`, `127.0.0.1` va namunaviy manzillar telefondan
    ochilmaydi — ular havola sifatida ishlatilmaydi.
    """
    from app.core.config import get_settings

    url = (get_settings().oferta_url or "").strip()
    if not url.startswith("https://"):
        return None
    blocked = ("localhost", "127.0.0.1", "example.com", "sizning-domeningiz")
    return None if any(bad in url for bad in blocked) else url


def phone_kb(lang: str) -> ReplyKeyboardMarkup:
    """Telegram'ning rasmiy "kontakt ulashish" tugmasi."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("btn_share_phone", lang), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def how_to_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_how_to", lang), callback_data="connect:how")]
        ]
    )
