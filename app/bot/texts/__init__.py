"""Ikki tilli matnlar katalogi (uz / ru).

Foydalanish:
    from app.bot.texts import t
    t("welcome", lang, name="Ali")

Matn topilmasa xato emas, kalitning o'zi qaytadi — bot yiqilmasin.
"""
from __future__ import annotations

from app.bot.texts.ru import TEXTS as RU
from app.bot.texts.uz import TEXTS as UZ

_CATALOG: dict[str, dict[str, str]] = {"uz": UZ, "ru": RU}

DEFAULT_LANG = "uz"
LANGS = ("uz", "ru")


def t(key: str, lang: str = DEFAULT_LANG, /, **kwargs: object) -> str:
    """Kalit bo'yicha matn, `{...}` o'rinlarini `kwargs` bilan to'ldiradi."""
    catalog = _CATALOG.get(lang, _CATALOG[DEFAULT_LANG])
    template = catalog.get(key) or _CATALOG[DEFAULT_LANG].get(key, key)
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template
