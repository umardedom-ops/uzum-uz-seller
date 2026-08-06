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
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from app.bot.keyboards.billing import click_pay_kb, manual_paid_kb, plans_kb
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

    if isinstance(event, CallbackQuery):
        await event.answer()
        if event.message is not None:
            await event.message.answer(text, reply_markup=plans_kb(lang))
    else:
        await event.answer(text, reply_markup=plans_kb(lang))


@router.callback_query(F.data.startswith("billing:buy:"))
async def on_buy(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    settings = get_settings()
    plan = Plan(cb.data.rsplit(":", 1)[1])
    amount = billing.price_for(plan)

    await cb.answer()

    if settings.click_enabled:
        # Click Shop API — to'lov Click sahifasida, tasdiq webhook orqali
        payment_id = await billing.create_payment(
            cb.from_user.id, plan, PaymentMethod.CLICK
        )
        if payment_id is None:
            await cb.message.answer(t("error", lang))
            return

        link = click.payment_link(payment_id, amount)
        await cb.message.answer(
            t(
                "click_payment",
                lang,
                plan=_plan_name(plan, lang),
                amount=format_money_int(amount),
            ),
            reply_markup=click_pay_kb(link, lang),
            disable_web_page_preview=True,
        )
        return

    if settings.payment_provider_token:
        # Telegram Payments — karta ma'lumoti bizga tegmaydi
        payment_id = await billing.create_payment(
            cb.from_user.id, plan, PaymentMethod.TELEGRAM
        )
        await cb.message.answer_invoice(
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
        return

    # Provayder tokeni yo'q — qo'lda tasdiqlash
    payment_id = await billing.create_payment(
        cb.from_user.id, plan, PaymentMethod.MANUAL
    )
    if payment_id is None:
        await cb.message.answer(t("error", lang))
        return

    details = settings.payment_details or t("payment_details_missing", lang)
    await cb.message.answer(
        t(
            "manual_payment",
            lang,
            plan=_plan_name(plan, lang),
            amount=format_money_int(amount),
            details=details,
        ),
        reply_markup=manual_paid_kb(payment_id, lang),
    )


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
