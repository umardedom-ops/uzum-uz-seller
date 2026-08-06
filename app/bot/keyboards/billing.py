"""Tarif va to'lov klaviaturalari."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.texts import t
from app.db.models import Plan


def tariffs_kb(lang: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_tariffs", lang), callback_data="billing:plans"
                )
            ]
        ]
    )


def plans_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_buy_basic", lang),
                    callback_data=f"billing:buy:{Plan.BASIC.value}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_buy_pro", lang),
                    callback_data=f"billing:buy:{Plan.PRO.value}",
                )
            ],
        ]
    )


def click_pay_kb(link: str, lang: str) -> InlineKeyboardMarkup:
    """Click to'lov sahifasiga havola.

    Tasdiqni Click webhook orqali o'zi yuboradi — mijoz "to'ladim"
    tugmasini bosishi shart emas.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_pay_click", lang), url=link)]
        ]
    )


def manual_paid_kb(payment_id: int, lang: str) -> InlineKeyboardMarkup:
    """Qo'lda to'lov: mijoz "to'ladim" deydi."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_i_paid", lang),
                    callback_data=f"billing:paid:{payment_id}",
                )
            ]
        ]
    )


def admin_confirm_kb(payment_id: int) -> InlineKeyboardMarkup:
    """Admin uchun: tasdiqlash yoki rad etish."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Tasdiqlash", callback_data=f"admin:pay_ok:{payment_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Rad etish", callback_data=f"admin:pay_no:{payment_id}"
                ),
            ]
        ]
    )
