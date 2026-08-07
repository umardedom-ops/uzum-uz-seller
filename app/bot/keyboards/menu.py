"""Asosiy menyu klaviaturasi (SPEC 7).

Raqobatchidan farqimiz: birinchi tugma — "Yo'qotilgan pul". Mahsulotning
asosiy qiymati shu, hisobot emas.
"""
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.bot.texts import t


def main_menu_kb(lang: str, *, is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Asosiy menyu. Adminlarga qo'shimcha tugma ko'rinadi."""
    rows = [
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
    ]
    if is_admin:
        rows.append([KeyboardButton(text=t("menu_admin", lang))])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
