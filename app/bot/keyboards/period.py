"""Davr tanlash klaviaturasi.

Tayyor davrlar + kalendar. Ko'p seller tayyor tugmani bosadi; kalendar
aniq oraliq kerak bo'lganda ishlatiladi.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.texts import t


@dataclass(frozen=True, slots=True)
class Preset:
    key: str
    text_key: str


PRESETS: tuple[Preset, ...] = (
    Preset("today", "period_today"),
    Preset("yesterday", "period_yesterday"),
    Preset("week", "period_week"),
    Preset("month", "period_month"),
    Preset("prev_month", "period_prev_month"),
    Preset("all", "period_all"),
)


def resolve_preset(key: str, today: date, history_start: date | None) -> tuple[date, date]:
    """Tayyor davr kalitini `(dan, gacha)` sanalarga aylantiradi."""
    if key == "today":
        return today, today
    if key == "yesterday":
        day = today - timedelta(days=1)
        return day, day
    if key == "week":
        return today - timedelta(days=7), today
    if key == "month":
        return today.replace(day=1), today
    if key == "prev_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return last_prev.replace(day=1), last_prev
    if key == "all":
        return (history_start or today - timedelta(days=30)), today
    return today - timedelta(days=30), today


def period_kb(lang: str) -> InlineKeyboardMarkup:
    """Davr tugmalari.

    «Butun tarix» — butun qatorda va birinchi: u qoldiq tarixini talab
    qilmaydi, ya'ni bot ulangan kuniyoq natija beradi. Qolgan davrlar
    tarix to'planishini kutadi, shuning uchun yangi seller uchun aynan
    shu tugma qiymatli.
    """

    def btn(preset: Preset) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=t(preset.text_key, lang), callback_data=f"period:{preset.key}"
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [btn(PRESETS[5])],                    # Butun tarix
            [btn(PRESETS[0]), btn(PRESETS[1])],   # Bugun · Kecha
            [btn(PRESETS[2]), btn(PRESETS[3])],   # 7 kun · Shu oy
            [btn(PRESETS[4])],                    # O'tgan oy
            [
                InlineKeyboardButton(
                    text=t("period_custom", lang), callback_data="period:custom"
                )
            ],
        ]
    )


def results_kb(lang: str) -> InlineKeyboardMarkup:
    """Natija ekranidagi tugmalar."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_excel_short", lang), callback_data="money:xlsx"
                ),
                InlineKeyboardButton(
                    text=t("btn_pdf_short", lang), callback_data="money:pdf"
                ),
            ],
            [InlineKeyboardButton(text=t("btn_claim", lang), callback_data="money:claim")],
            [
                InlineKeyboardButton(
                    text=t("btn_change_period", lang), callback_data="money:period"
                )
            ],
        ]
    )
