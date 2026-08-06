"""Sonni o'zbekcha so'z bilan yozish.

Pretenziyada summa raqam va so'z bilan ko'rsatilishi kerak (SPEC 6.2) —
bu rasmiy hujjatlarda standart talab va summani keyin o'zgartirishga
yo'l qo'ymaydi.
"""
from __future__ import annotations

from decimal import Decimal

_ONES = (
    "", "bir", "ikki", "uch", "to'rt", "besh",
    "olti", "yetti", "sakkiz", "to'qqiz",
)
_TENS = (
    "", "o'n", "yigirma", "o'ttiz", "qirq", "ellik",
    "oltmish", "yetmish", "sakson", "to'qson",
)

# (bo'luvchi, nomi, birlikda "bir" yozilsinmi)
_SCALES: tuple[tuple[int, str, bool], ...] = (
    (10**12, "trillion", True),
    (10**9, "milliard", True),
    (10**6, "million", True),
    (1000, "ming", False),   # 1000 → "ming", "bir ming" emas
    (100, "yuz", False),     # 100 → "yuz", "bir yuz" emas
)


def _under_hundred(n: int) -> list[str]:
    parts: list[str] = []
    if n >= 10:
        parts.append(_TENS[n // 10])
    if n % 10:
        parts.append(_ONES[n % 10])
    return parts


def number_to_words(n: int) -> str:
    """Butun sonni o'zbekcha so'z bilan qaytaradi.

    >>> number_to_words(1_234_567)
    "bir million ikki yuz o'ttiz to'rt ming besh yuz oltmish yetti"
    """
    if n == 0:
        return "nol"
    if n < 0:
        return f"minus {number_to_words(-n)}"

    parts: list[str] = []
    remainder = n

    for divisor, name, keep_one in _SCALES:
        count, remainder = divmod(remainder, divisor)
        if not count:
            continue
        prefix = number_to_words(count)
        if count == 1 and not keep_one:
            parts.append(name)
        else:
            parts.append(f"{prefix} {name}")

    parts.extend(_under_hundred(remainder))
    return " ".join(p for p in parts if p)


def amount_in_words(amount: Decimal, currency: str = "so'm") -> str:
    """Pul summasini so'z bilan: butun qismi + tiyin (bo'lsa).

    >>> amount_in_words(Decimal("250000.00"))
    "ikki yuz ellik ming so'm"
    """
    whole = int(amount)
    fraction = int((abs(amount) - abs(whole)) * 100 + Decimal("0.5"))

    words = f"{number_to_words(whole)} {currency}"
    if fraction:
        words += f" {number_to_words(fraction)} tiyin"
    return words


def format_money(amount: Decimal) -> str:
    """Raqamni o'qishli qiladi: 1234567.89 → "1 234 567,89"."""
    whole = int(abs(amount))
    fraction = int((abs(amount) - whole) * 100 + Decimal("0.5"))
    grouped = f"{whole:,}".replace(",", " ")
    sign = "-" if amount < 0 else ""
    return f"{sign}{grouped},{fraction:02d}"
