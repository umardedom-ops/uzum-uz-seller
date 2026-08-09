"""Tariflar va to'lov (SPEC Phase 6).

Ikki yo'l:
  * Telegram Payments — provayder tokeni bo'lsa, to'lov avtomatik
    tasdiqlanadi. Karta ma'lumoti Telegram ichida kiritiladi, bizning
    kodimizga umuman tegmaydi.
  * Qo'lda — token yo'q bo'lsa: mijoz o'tkazadi, "to'ladim" bosadi,
    admin tasdiqlaydi.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from app.bot.keyboards.billing import click_pay_kb, manual_paid_kb, plans_kb
from app.bot.keyboards.menu import main_menu_kb
from app.bot.states.onboarding import Onboarding
from app.bot.texts import DEFAULT_LANG, t
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import PaymentMethod, Plan
from app.docs.numbers import format_money
from app.services import billing, click

log = get_logger(__name__)
router = Router(name="billing")

# Telegram Payments summani eng kichik birlikda kutadi (tiyin)
_MINOR_UNITS = 100


@router.callback_query(F.data.startswith("onboarding:plan:"))
async def on_onboarding_plan(cb: CallbackQuery, state: FSMContext) -> None:
    """Onboardingdagi tarif tanlovi — 3 variantdan biri.

    Tanlov eslab qolinadi va oqim ofertaga o'tadi. Pullik tarif tanlansa
    to'lov shu yerda SO'RALMAYDI: oferta hali qabul qilinmagan va seller
    do'konini ham ulamagan. To'lov do'kon ulangandan keyin taklif
    qilinadi (`start.on_api_key`).
    """
    from app.bot.handlers.start import show_oferta

    lang = await _lang(state)
    choice = cb.data.rsplit(":", 1)[1]

    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await state.update_data(chosen_plan=choice)

    if choice == "free":
        await cb.message.answer(
            t("plan_free_started", lang, trial_days=get_settings().trial_days)
        )
    else:
        await cb.message.answer(
            t("plan_paid_later", lang, plan=_plan_name(Plan(choice), lang))
        )

    await show_oferta(cb, state)


async def offer_payment_after_connect(
    cb_message: Message, state: FSMContext, telegram_id: int
) -> bool:
    """Do'kon ulangach: pullik tarif tanlangan bo'lsa to'lovni taklif qiladi.

    `True` qaytarsa — to'lov ekrani ko'rsatildi, menyu keyinroq ochiladi.
    """
    data = await state.get_data()
    choice = data.get("chosen_plan")
    if choice in (None, "free"):
        return False

    lang = data.get("lang", DEFAULT_LANG)
    return await _send_payment_offer(cb_message, telegram_id, Plan(choice), lang)


@router.message(Onboarding.choosing_plan)
async def on_message_while_choosing(message: Message, state: FSMContext) -> None:
    """Tarif tanlash bosqichida yozilgan xabar.

    Avval promokod deb tekshiramiz: hamkor sellerga «botga kiring va
    kodni yuboring» deydi, seller esa aynan shu ekranда turadi. Buyruq
    yozishni talab qilsak ko'pchilik adashadi.

    Kod bo'lmasa — tanlash majburiyligini eslatamiz.
    """
    lang = await _lang(state)
    text = (message.text or "").strip()

    if _looks_like_code(text):
        result, plan, days = await billing.redeem_promo(message.from_user.id, text)
        if result is billing.PromoResult.OK:
            await _promo_success(message, state, lang, plan, days)
            return
        if result is not billing.PromoResult.NOT_FOUND:
            # Kod haqiqiy, lekin ishlamadi — sababini aytamiz
            await message.answer(t(_PROMO_ERRORS[result], lang))
            return

    await message.answer(t("plan_must_choose", lang))


@router.message(Command("tarif", "tariff", "pay"))
@router.callback_query(F.data == "billing:plans")
async def show_plans(event: Message | CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    settings = get_settings()

    text = t(
        "plans",
        lang,
        basic=format_money_int(settings.price_basic),
        pro=format_money_int(settings.price_pro),
        trial=settings.trial_days,
    )

    access = await billing.get_access(_user_id(event))
    if access.is_active:
        text += "\n\n" + t(
            "plan_current", lang, plan=_plan_name(access.plan, lang), days=access.days_left
        )

    from app.bot.handlers.start import send_with_banner

    target = event.message if isinstance(event, CallbackQuery) else event
    if isinstance(event, CallbackQuery):
        await event.answer()
    if target is not None:
        await send_with_banner(target, text, plans_kb(lang))


@router.callback_query(F.data.startswith("billing:buy:"))
async def on_buy(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    plan = Plan(cb.data.rsplit(":", 1)[1])
    await cb.answer()
    await _send_payment_offer(cb.message, cb.from_user.id, plan, lang)


async def _send_payment_offer(
    target: Message, telegram_id: int, plan: Plan, lang: str
) -> bool:
    """To'lov ekrani: Click → Telegram Payments → qo'lda (mavjudiga qarab).

    `False` qaytaradi — hech qanday to'lov usuli sozlanmagan. Chaqiruvchi
    shunda oqimni davom ettiradi (masalan menyuni ochadi), aks holda
    seller tupikda qolardi.

    Ikki joydan chaqiriladi: tariflar ekranidan va onboarding oxirida
    (do'kon ulangach). Shu sabab `CallbackQuery` emas, xabar oladi.
    """
    settings = get_settings()
    amount = billing.price_for(plan)

    # Hech biri sozlanmagan bo'lsa to'lov yozuvi ham yaratilmaydi: "to'lang"
    # deb rekvizitsiz ekran ko'rsatish va "To'ladim" tugmasini berish —
    # sellerni chalg'itadi va adminni soxta tasdiqqa majbur qiladi.
    if not (
        settings.click_enabled
        or settings.payment_provider_token
        or settings.payment_details
    ):
        await target.answer(
            t("payment_not_ready", lang, support=settings.support_username)
        )
        return False

    if settings.click_enabled:
        # Click Shop API — to'lov Click sahifasida, tasdiq webhook orqali
        payment_id = await billing.create_payment(
            telegram_id, plan, PaymentMethod.CLICK
        )
        if payment_id is None:
            await target.answer(t("error", lang))
            return False

        link = click.payment_link(payment_id, amount)
        await target.answer(
            t(
                "click_payment",
                lang,
                plan=_plan_name(plan, lang),
                amount=format_money_int(amount),
            ),
            reply_markup=click_pay_kb(link, lang),
            disable_web_page_preview=True,
        )
        return True

    if settings.payment_provider_token:
        # Telegram Payments — karta ma'lumoti bizga tegmaydi
        payment_id = await billing.create_payment(
            telegram_id, plan, PaymentMethod.TELEGRAM
        )
        await target.answer_invoice(
            title=_plan_name(plan, lang),
            description=t("invoice_desc", lang, plan=_plan_name(plan, lang)),
            payload=f"sub:{plan.value}:{payment_id}",
            provider_token=settings.payment_provider_token or "",
            currency=settings.payment_currency,
            prices=[
                LabeledPrice(
                    label=_plan_name(plan, lang), amount=amount * _MINOR_UNITS
                )
            ],
        )
        return True

    # Provayder tokeni yo'q — qo'lda tasdiqlash
    payment_id = await billing.create_payment(
        telegram_id, plan, PaymentMethod.MANUAL
    )
    if payment_id is None:
        await target.answer(t("error", lang))
        return False

    details = settings.payment_details
    await target.answer(
        t(
            "manual_payment",
            lang,
            plan=_plan_name(plan, lang),
            amount=format_money_int(amount),
            details=details,
        ),
        reply_markup=manual_paid_kb(payment_id, lang),
    )
    return True


@router.callback_query(F.data.startswith("billing:paid:"))
async def on_claimed_paid(cb: CallbackQuery, state: FSMContext) -> None:
    """Mijoz "to'ladim" dedi — adminga xabar ketadi."""
    lang = await _lang(state)
    payment_id = int(cb.data.rsplit(":", 1)[1])

    await cb.answer()
    await cb.message.answer(t("payment_pending", lang))
    await _notify_admins(cb, payment_id)


# --- Telegram Payments oqimi ------------------------------------------- #


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    """Telegram to'lovni tasdiqlashdan oldin so'raydi — rozilik beramiz."""
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, state: FSMContext) -> None:
    """To'lov o'tdi — obunani darhol faollashtiramiz."""
    lang = await _lang(state)
    payment = message.successful_payment

    payload_parts = (payment.invoice_payload or "").split(":")
    payment_id = int(payload_parts[2]) if len(payload_parts) > 2 else None

    if payment_id is not None:
        await billing.confirm_payment(payment_id)

    log.info(
        "Telegram to'lovi: tg_id=%s summa=%s charge=%s",
        message.from_user.id,
        payment.total_amount // _MINOR_UNITS,
        payment.telegram_payment_charge_id,
    )

    access = await billing.get_access(message.from_user.id)
    await message.answer(
        t(
            "payment_success",
            lang,
            plan=_plan_name(access.plan, lang),
            days=access.days_left,
        )
    )


# --- Yordamchilar ------------------------------------------------------- #


async def _notify_admins(cb: CallbackQuery, payment_id: int) -> None:
    from app.bot.keyboards.billing import admin_confirm_kb

    admins = await billing.admin_ids()
    if not admins:
        log.warning("Admin yo'q — to'lov tasdig'i so'ralmadi: %s", payment_id)
        return

    user = cb.from_user
    text = (
        f"💳 <b>Yangi to'lov</b> #{payment_id}\n\n"
        f"Mijoz: {user.full_name} (@{user.username or '—'})\n"
        f"ID: <code>{user.id}</code>"
    )
    for admin_id in admins:
        try:
            await cb.bot.send_message(
                admin_id, text, reply_markup=admin_confirm_kb(payment_id)
            )
        except Exception:
            log.exception("Adminga xabar yuborilmadi: %s", admin_id)


def format_money_int(value: int) -> str:
    from decimal import Decimal

    return format_money(Decimal(value)).split(",")[0]


def _plan_name(plan: Plan, lang: str) -> str:
    return t(f"plan_{plan.value}", lang)


def _user_id(event: Message | CallbackQuery) -> int:
    return event.from_user.id


async def _lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", DEFAULT_LANG)


# ---------------------------------------------------------------------- #
# Promokod — hamkorlar orqali bepul kirish
# ---------------------------------------------------------------------- #

#: Natija → matn kaliti
_PROMO_ERRORS = {
    billing.PromoResult.NOT_FOUND: "promo_not_found",
    billing.PromoResult.EXPIRED: "promo_expired",
    billing.PromoResult.USED_UP: "promo_used_up",
    billing.PromoResult.ALREADY_USED: "promo_already_used",
    billing.PromoResult.NO_USER: "promo_no_user",
}


def _looks_like_code(text: str) -> bool:
    """Promokodga o'xshaydimi — 6-32 ta harf/raqam, bo'shliqsiz."""
    return 6 <= len(text) <= 32 and text.isalnum()


@router.message(Command("promo", "kod"))
async def cmd_promo(
    message: Message, command: CommandObject, state: FSMContext
) -> None:
    """`/promo KOD` — bepul kirish kodini faollashtirish."""
    lang = await _lang(state)
    code = (command.args or "").strip()
    if not code:
        await message.answer(t("promo_ask", lang))
        return

    result, plan, days = await billing.redeem_promo(message.from_user.id, code)
    if result is billing.PromoResult.OK:
        await message.answer(
            t("promo_ok", lang, plan=_plan_name(plan, lang), days=days)
        )
        return
    await message.answer(t(_PROMO_ERRORS[result], lang))


async def _promo_success(
    message: Message, state: FSMContext, lang: str, plan: Plan, days: int
) -> None:
    """Kod ishladi: onboarding tugaydi va menyu ochiladi.

    `chosen_plan` bepulga o'rnatiladi — do'kon ulangach to'lov
    so'ralmasligi uchun (obuna allaqachon faol).
    """
    await message.answer(t("promo_ok", lang, plan=_plan_name(plan, lang), days=days))
    await state.update_data(chosen_plan="free")
    await state.set_state(Onboarding.done)

    is_admin = await billing.is_admin(message.from_user.id)
    await message.answer(
        t("main_menu_admin", lang) if is_admin else t("main_menu", lang),
        reply_markup=main_menu_kb(lang, is_admin=is_admin),
    )
