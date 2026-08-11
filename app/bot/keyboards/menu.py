"""Asosiy menyu klaviaturasi (SPEC 7).

Raqobatchidan ikki farq:
  1. Birinchi tugma — "Yo'qotilgan pul". Mahsulotning asosiy qiymati shu,
     hisobot emas — shuning uchun flagman sifatida to'g'ridan-to'g'ri turadi.
  2. Qolgan bo'limlar **papkalarga** yig'ilgan. Raqobatchida 13+ tugma bir
     tekislikda yotadi va adashtiradi; bizda 3 papka, har biri o'z ichida.

Papka tugmasi bosilganda `handlers/menu.py` tegishli quyi-klaviaturani
yuboradi. Quyi-klaviaturadagi bo'lim tugmalari — aynan mavjud bo'lim
matnlari (`menu_reports`, `menu_stock` ...), shuning uchun ularning o'z
routerlari o'zgarishsiz ishlayveradi. Papka matnlari esa bo'lim
matnlaridan farqli — aks holda bosilganda bo'lim handleri chaqirilardi.
"""
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.bot.texts import t


def main_menu_kb(lang: str) -> ReplyKeyboardMarkup:
    """Bosh menyu: flagman + 3 papka.

    ❗ Admin tugmasi bu yerda YO'Q va bo'lmasligi kerak. U ilgari
    adminlarga chizilardi, lekin bot egasi mijozlar oldida ekranini
    ochganda («👑 Admin» ko'rinib turadi) keraksiz savol tug'dirardi.
    Panel `/admin` buyrug'i bilan ochiladi — funksiya saqlanadi, menyu
    esa hamma uchun bir xil va toza.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t("menu_lost_money", lang))],
            [
                KeyboardButton(text=t("folder_analytics", lang)),
                KeyboardButton(text=t("folder_warehouse", lang)),
            ],
            [KeyboardButton(text=t("folder_settings", lang))],
        ],
        resize_keyboard=True,
    )


def _sub_kb(rows_texts: list[list[str]], lang: str) -> ReplyKeyboardMarkup:
    """Papka ichidagi klaviatura — bo'lim tugmalari + «Bosh menyu» ortga."""
    rows = [[KeyboardButton(text=text) for text in row] for row in rows_texts]
    rows.append([KeyboardButton(text=t("menu_home", lang))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def folder_analytics_kb(lang: str) -> ReplyKeyboardMarkup:
    """📊 Hisobot va tahlil → Hisobotlar, Top tovarlar, Yunit-iqtisodiyot."""
    return _sub_kb(
        [
            [t("menu_reports", lang), t("menu_top", lang)],
            [t("menu_unit_econ", lang)],
        ],
        lang,
    )


def folder_warehouse_kb(lang: str) -> ReplyKeyboardMarkup:
    """📦 Ombor va buyurtma → Qoldiqlar, FBS buyurtmalar."""
    return _sub_kb(
        [
            [t("menu_stock", lang), t("menu_fbs", lang)],
        ],
        lang,
    )


def folder_settings_kb(lang: str) -> ReplyKeyboardMarkup:
    """⚙️ Sozlama va bildirishnoma → Sozlamalar, Bildirishnomalar."""
    return _sub_kb(
        [
            [t("menu_settings", lang)],
            [t("menu_alerts", lang)],
        ],
        lang,
    )
