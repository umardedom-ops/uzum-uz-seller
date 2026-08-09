"""Matnlar katalogi tekshiruvlari.

Bu fayl bitta muammoning oldini oladi: Telegram noto'g'ri HTML bo'lgan
xabarni **rad etadi** va handler xato beradi. Foydalanuvchi uchun bu
"bot ishlamayapti" degani, log esa `TelegramBadRequest` ko'rsatadi —
sababini topish qiyin. Shuning uchun teglar shu yerda tekshiriladi.
"""
from __future__ import annotations

import re

import pytest

from app.bot.texts.ru import TEXTS as RU
from app.bot.texts.uz import TEXTS as UZ

# Telegram Bot API qo'llab-quvvatlaydigan teglar (HTML uslubi)
ALLOWED_TAGS = {"b", "i", "u", "s", "code", "pre", "a", "blockquote", "tg-spoiler"}

CATALOGS = {"uz": UZ, "ru": RU}


def _iter_texts():
    for lang, catalog in CATALOGS.items():
        for key, value in catalog.items():
            if isinstance(value, str):
                yield lang, key, value


@pytest.mark.parametrize(("lang", "key", "text"), list(_iter_texts()))
def test_html_is_well_formed(lang: str, key: str, text: str) -> None:
    """Teglar tanilgan va to'g'ri yopilgan bo'lishi kerak."""
    stack: list[str] = []
    for match in re.finditer(r"<(/?)([a-z-]+)([^>]*)>", text):
        closing, tag = match.group(1), match.group(2)
        assert tag in ALLOWED_TAGS, f"{lang}.{key}: Telegram <{tag}> ni bilmaydi"
        if closing:
            assert stack and stack[-1] == tag, f"{lang}.{key}: ortiqcha </{tag}>"
            stack.pop()
        else:
            stack.append(tag)
    assert not stack, f"{lang}.{key}: yopilmagan teglar {stack}"


def test_both_languages_have_same_keys() -> None:
    """Kalit faqat bitta tilda bo'lsa, ikkinchi tilda kalit nomi ko'rinadi."""
    only_uz = sorted(set(UZ) - set(RU))
    only_ru = sorted(set(RU) - set(UZ))
    assert not only_uz, f"faqat o'zbekchada: {only_uz}"
    assert not only_ru, f"faqat ruschada: {only_ru}"
