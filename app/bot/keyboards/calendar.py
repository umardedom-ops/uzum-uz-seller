"""Inline kalendar — davr tanlash uchun.

aiogram'da tayyor kalendar yo'q, shuning uchun o'zimiz quramiz.
Callback formati:
    cal:<rejim>:nav:<YYYY-MM>   — oyni almashtirish
    cal:<rejim>:day:<YYYY-MM-DD> — kunni tanlash
    cal:noop                     — bo'sh katak (javob bermaydi)

`rejim` — `from` yoki `to`: boshlanish yoki tugash sanasi tanlanyapti.
"""
from __future__ import annotations

import calendar
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

MONTHS = {
    "uz": (
        "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
        "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
    ),
    "ru": (
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
    ),
}

WEEKDAYS = {
    "uz": ("Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"),
    "ru": ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"),
}

NOOP = "cal:noop"


def month_name(month: int, lang: str) -> str:
    names = MONTHS.get(lang, MONTHS["uz"])
    return names[month - 1]


def build_calendar(
    year: int,
    month: int,
    mode: str,
    lang: str = "uz",
    *,
    min_date: date | None = None,
    max_date: date | None = None,
) -> InlineKeyboardMarkup:
    """Bir oylik kalendar. Ruxsat etilmagan kunlar bosilmaydi.

    `min_date` — tarix qachondan boshlanadi (undan oldini tanlab bo'lmaydi).
    `max_date` — odatda bugun (kelajakni tanlab bo'lmaydi).
    """
    rows: list[list[InlineKeyboardButton]] = []

    # --- sarlavha: < Oy Yil > ---
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)

    rows.append(
        [
            InlineKeyboardButton(
                text="‹", callback_data=f"cal:{mode}:nav:{prev_year:04d}-{prev_month:02d}"
            ),
            InlineKeyboardButton(
                text=f"{month_name(month, lang)} {year}", callback_data=NOOP
            ),
            InlineKeyboardButton(
                text="›", callback_data=f"cal:{mode}:nav:{next_year:04d}-{next_month:02d}"
            ),
        ]
    )

    # --- hafta kunlari ---
    rows.append(
        [
            InlineKeyboardButton(text=day, callback_data=NOOP)
            for day in WEEKDAYS.get(lang, WEEKDAYS["uz"])
        ]
    )

    # --- kunlar ---
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
        row: list[InlineKeyboardButton] = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data=NOOP))
                continue

            current = date(year, month, day)
            allowed = (min_date is None or current >= min_date) and (
                max_date is None or current <= max_date
            )
            if allowed:
                row.append(
                    InlineKeyboardButton(
                        text=str(day),
                        callback_data=f"cal:{mode}:day:{current.isoformat()}",
                    )
                )
            else:
                # Ruxsat etilmagan kun — ko'rinadi, lekin ishlamaydi
                row.append(InlineKeyboardButton(text="·", callback_data=NOOP))
        rows.append(row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_calendar_callback(data: str) -> tuple[str, str, str] | None:
    """`cal:from:day:2026-08-06` → `("from", "day", "2026-08-06")`."""
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "cal":
        return None
    return parts[1], parts[2], parts[3]
