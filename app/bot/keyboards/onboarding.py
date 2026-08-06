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


def start_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_start", lang), callback_data="start:go")]
        ]
    )


def oferta_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_accept", lang), callback_data="oferta:accept")]
        ]
    )


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
