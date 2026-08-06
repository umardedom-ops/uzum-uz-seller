"""Davr tanlash va kalendar testlari.

Noto'g'ri davr — noto'g'ri hisobot. Chegara sanalari (oy boshi/oxiri,
yil chegarasi) eng xatoga moyil joylar.
"""
from __future__ import annotations

from datetime import date

from app.bot.keyboards.calendar import build_calendar, parse_calendar_callback
from app.bot.keyboards.period import resolve_preset

TODAY = date(2026, 8, 6)
HISTORY_START = date(2026, 7, 20)


class TestPresets:
    def test_today(self) -> None:
        assert resolve_preset("today", TODAY, HISTORY_START) == (TODAY, TODAY)

    def test_yesterday(self) -> None:
        day = date(2026, 8, 5)
        assert resolve_preset("yesterday", TODAY, HISTORY_START) == (day, day)

    def test_week(self) -> None:
        assert resolve_preset("week", TODAY, HISTORY_START) == (
            date(2026, 7, 30),
            TODAY,
        )

    def test_this_month_starts_at_first(self) -> None:
        assert resolve_preset("month", TODAY, HISTORY_START) == (
            date(2026, 8, 1),
            TODAY,
        )

    def test_prev_month_full_range(self) -> None:
        """O'tgan oy — 1-sanadan oxirgi kunigacha."""
        assert resolve_preset("prev_month", TODAY, HISTORY_START) == (
            date(2026, 7, 1),
            date(2026, 7, 31),
        )

    def test_prev_month_across_year_boundary(self) -> None:
        """Yanvarda "o'tgan oy" — o'tgan yilning dekabri."""
        jan = date(2026, 1, 15)
        assert resolve_preset("prev_month", jan, None) == (
            date(2025, 12, 1),
            date(2025, 12, 31),
        )

    def test_prev_month_february(self) -> None:
        """Fevral 28/29 kun — oxirgi kun to'g'ri topilsin."""
        march = date(2026, 3, 10)
        start, end = resolve_preset("prev_month", march, None)
        assert start == date(2026, 2, 1)
        assert end == date(2026, 2, 28)  # 2026 kabisa yil emas

    def test_all_uses_history_start(self) -> None:
        assert resolve_preset("all", TODAY, HISTORY_START) == (HISTORY_START, TODAY)

    def test_all_without_history_falls_back(self) -> None:
        """Tarix yo'q bo'lsa ham yiqilmasin."""
        start, end = resolve_preset("all", TODAY, None)
        assert start < end == TODAY

    def test_unknown_key_is_safe(self) -> None:
        start, end = resolve_preset("nomalum", TODAY, HISTORY_START)
        assert start < end


class TestCalendar:
    def test_structure(self) -> None:
        """Sarlavha + hafta kunlari + haftalar."""
        kb = build_calendar(2026, 8, "from", "uz")
        assert len(kb.inline_keyboard) >= 3
        assert kb.inline_keyboard[0][1].text == "Avgust 2026"
        assert len(kb.inline_keyboard[1]) == 7

    def test_month_navigation_wraps_year(self) -> None:
        """Yanvardan orqaga — o'tgan yil dekabri."""
        kb = build_calendar(2026, 1, "from", "uz")
        prev_button = kb.inline_keyboard[0][0]
        assert prev_button.callback_data == "cal:from:nav:2025-12"

        kb = build_calendar(2026, 12, "from", "uz")
        next_button = kb.inline_keyboard[0][2]
        assert next_button.callback_data == "cal:from:nav:2027-01"

    def test_future_dates_are_disabled(self) -> None:
        """Kelajakni tanlab bo'lmaydi."""
        kb = build_calendar(2026, 8, "from", "uz", max_date=date(2026, 8, 6))
        day_buttons = [b for row in kb.inline_keyboard[2:] for b in row]
        selectable = {
            b.callback_data.split(":")[-1]
            for b in day_buttons
            if b.callback_data.startswith("cal:")
        }
        assert "2026-08-06" in selectable
        assert "2026-08-07" not in selectable

    def test_before_history_is_disabled(self) -> None:
        kb = build_calendar(2026, 8, "from", "uz", min_date=date(2026, 8, 10))
        selectable = {
            b.callback_data.split(":")[-1]
            for row in kb.inline_keyboard[2:]
            for b in row
            if b.callback_data.startswith("cal:") and "day" in b.callback_data
        }
        assert "2026-08-05" not in selectable
        assert "2026-08-15" in selectable

    def test_russian_labels(self) -> None:
        kb = build_calendar(2026, 8, "from", "ru")
        assert kb.inline_keyboard[0][1].text == "Август 2026"
        assert kb.inline_keyboard[1][0].text == "Пн"

    def test_mode_is_preserved_in_callbacks(self) -> None:
        """`to` rejimida tugmalar `to` ni saqlashi kerak."""
        kb = build_calendar(2026, 8, "to", "uz")
        assert kb.inline_keyboard[0][0].callback_data.startswith("cal:to:nav:")


class TestCallbackParsing:
    def test_day_callback(self) -> None:
        assert parse_calendar_callback("cal:from:day:2026-08-06") == (
            "from",
            "day",
            "2026-08-06",
        )

    def test_nav_callback(self) -> None:
        assert parse_calendar_callback("cal:to:nav:2026-09") == ("to", "nav", "2026-09")

    def test_noop_returns_none(self) -> None:
        assert parse_calendar_callback("cal:noop") is None

    def test_foreign_callback_returns_none(self) -> None:
        assert parse_calendar_callback("money:xlsx") is None
