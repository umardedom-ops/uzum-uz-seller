"""Asosiy menyu klaviaturasi (SPEC 7).

Raqobatchidan farqimiz: birinchi tugma — "Yo'qotilgan pul". Mahsulotning
asosiy qiymati shu, hisobot emas.
"""
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.bot.texts import t


def main_menu_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t("menu_lost_money", lang))],
            [
                KeyboardButton(text=t("menu_fbs", lang)),
                KeyboardButton(text=t("menu_stock", lang)),
            ],
            [KeyboardButton(text=t("menu_reports", lang))],
            [
                KeyboardButton(text=t("menu_unit_econ", lang)),
                KeyboardButton(text=t("menu_alerts", lang)),
            ],
            [KeyboardButton(text=t("menu_settings", lang))],
        ],
        resize_keyboard=True,
    )
