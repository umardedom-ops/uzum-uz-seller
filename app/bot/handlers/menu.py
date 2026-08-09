"""Bildirishnomalar va Sozlamalar bo'limlari.

Ilgari ikkalasi «tayyorlanmoqda» deb javob berardi — menyuda tugma
turgani holda hech narsa qilmasdi.

Yo'qotilgan pul, FBS, Qoldiqlar, Yunit-iqtisodiyot va Hisobotlar
o'z routerlariga ega.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.texts import DEFAULT_LANG, LANGS, t
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import AlertType
from app.services import alerts, billing
from app.services.exports import find_user_shop

log = get_logger(__name__)
router = Router(name="menu")

#: Xabarnoma turi → matn kaliti
_ALERT_LABELS = {
    AlertType.DAILY_REPORT: "alert_daily_report",
    AlertType.NEW_DISCREPANCY: "alert_new_discrepancy",
    AlertType.LOW_STOCK: "alert_low_stock",
    AlertType.SKU_BLOCKED: "alert_sku_blocked",
}


async def _lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", DEFAULT_LANG)


# ---------------------------------------------------------------------- #
# 🔔 Bildirishnomalar
# ---------------------------------------------------------------------- #


def _alerts_kb(settings: dict[AlertType, bool], lang: str) -> InlineKeyboardMarkup:
    """Har bir tur uchun yoqish/o'chirish tugmasi.

    Holat tugmaning o'zida ko'rinadi (✅/⬜) — alohida ro'yxat kerak
    emas, seller bir qarashda tushunadi va bosgan zahoti o'zgaradi.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{'✅' if enabled else '⬜'} {t(_ALERT_LABELS[kind], lang)}",
                    callback_data=f"alerts:toggle:{kind.value}",
                )
            ]
            for kind, enabled in settings.items()
        ]
    )


@router.message(F.text.in_({t("menu_alerts", lg) for lg in LANGS}))
async def on_alerts(message: Message, state: FSMContext) -> None:
    lang = await _lang(state)
    shop = await find_user_shop(message.from_user.id)
    if shop is None:
        await message.answer(t("no_shop", lang))
        return

    await state.update_data(shop_id=shop.id)
    settings = await alerts.alert_settings(shop.id)

    text = t("alerts_header", lang)
    current = await alerts.collect_alerts(shop.id)
    if current:
        text += "\n\n" + t("alerts_active", lang, count=len(current))

    await message.answer(text, reply_markup=_alerts_kb(settings, lang))


@router.callback_query(F.data.startswith("alerts:toggle:"))
async def on_alert_toggle(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    shop = await find_user_shop(cb.from_user.id)
    if shop is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    kind = AlertType(cb.data.rsplit(":", 1)[1])
    enabled = await alerts.toggle_alert(shop.id, kind)

    await cb.answer(t("alert_on" if enabled else "alert_off", lang))
    settings = await alerts.alert_settings(shop.id)
    await cb.message.edit_reply_markup(reply_markup=_alerts_kb(settings, lang))


# ---------------------------------------------------------------------- #
# ⚙️ Sozlamalar
# ---------------------------------------------------------------------- #


@router.message(F.text.in_({t("menu_settings", lg) for lg in LANGS}))
async def on_settings(message: Message, state: FSMContext) -> None:
    """Do'kon, obuna va til — bir ekranda."""
    lang = await _lang(state)
    shop = await find_user_shop(message.from_user.id)
    access = await billing.get_access(message.from_user.id)

    lines = [t("settings_header", lang), ""]

    if shop is None:
        lines.append(t("settings_no_shop", lang))
    else:
        lines.append(
            t(
                "settings_shop",
                lang,
                title=shop.title or shop.uzum_shop_id,
                shop_id=shop.uzum_shop_id,
            )
        )

    if access.is_active:
        lines.append(
            t(
                "settings_plan",
                lang,
                plan=access.plan.value.upper(),
                days=access.days_left,
                kind=t("settings_trial" if access.on_trial else "settings_paid", lang),
            )
        )
    else:
        lines.append(t("settings_plan_none", lang))

    lines += ["", t("settings_support", lang, support=get_settings().support_username)]

    await message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t("settings_btn_lang", lang),
                        callback_data="settings:lang",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=t("btn_tariffs", lang), callback_data="billing:plans"
                    )
                ],
            ]
        ),
    )


@router.callback_query(F.data == "settings:lang")
async def on_change_lang(cb: CallbackQuery) -> None:
    """Til tanlash.

    ❗ `lang:` emas, `setlang:` ishlatiladi: birinchisi onboardingga
    tegishli va oqimni boshidan boshlab yuborardi.
    """
    await cb.answer()
    await cb.message.answer(
        t("choose_lang"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=t("lang_uz"), callback_data="setlang:uz"),
                    InlineKeyboardButton(text=t("lang_ru"), callback_data="setlang:ru"),
                ]
            ]
        ),
    )


@router.callback_query(F.data.startswith("setlang:"))
async def on_set_lang(cb: CallbackQuery, state: FSMContext) -> None:
    """Tilni almashtiradi va menyuni yangi tilda qayta chizadi."""
    from app.bot.keyboards.menu import main_menu_kb
    from app.services import onboarding as svc

    lang = cb.data.split(":", 1)[1]
    await state.update_data(lang=lang)
    await svc.save_user(cb.from_user.id, lang)

    await cb.answer()
    is_admin = await billing.is_admin(cb.from_user.id)
    await cb.message.answer(
        t("settings_lang_changed", lang),
        reply_markup=main_menu_kb(lang, is_admin=is_admin),
    )
