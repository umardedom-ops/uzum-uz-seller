"""Xabarnoma mantig'i testlari.

Ikki xato bir xil yomon:
  * alert bermaslik → seller pul yo'qotadi
  * keraksiz alert  → seller bezor bo'lib, botni o'chiradi
"""
from __future__ import annotations

import pytest

from app.services.alerts import RANK_ORDER, _rank_dropped


class TestRankDrop:
    """Rank pasayishi — Avtobidder o'rniga tanlangan xavfsiz signal."""

    @pytest.mark.parametrize(
        ("prev", "current"),
        [("A", "B"), ("B", "D"), ("A", "D"), ("C", "E")],
    )
    def test_drop_detected(self, prev: str, current: str) -> None:
        assert _rank_dropped(prev, current)

    @pytest.mark.parametrize(
        ("prev", "current"),
        [("B", "A"), ("D", "B"), ("E", "A")],
    )
    def test_improvement_is_not_alert(self, prev: str, current: str) -> None:
        """O'sish — yaxshi xabar, lekin bezovta qilmaymiz."""
        assert not _rank_dropped(prev, current)

    def test_same_rank_is_silent(self) -> None:
        assert not _rank_dropped("B", "B")

    def test_missing_values_are_silent(self) -> None:
        """Birinchi sync'da eski rank yo'q — alert bermaymiz."""
        assert not _rank_dropped(None, "D")
        assert not _rank_dropped("A", None)
        assert not _rank_dropped(None, None)

    def test_unknown_rank_does_not_crash(self) -> None:
        """Uzum yangi rank kiritsa ham yiqilmasin."""
        assert _rank_dropped("A", "Z") is True   # noma'lum — eng past deb qaraladi
        assert _rank_dropped("Z", "A") is False

    def test_rank_order_is_a_best(self) -> None:
        assert RANK_ORDER["A"] < RANK_ORDER["B"] < RANK_ORDER["D"]
