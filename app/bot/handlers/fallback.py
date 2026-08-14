"""Zaxira handler — bot hech qachon jim qolmasin.

❗ Nima uchun kerak (2026-08-10 da jonli uchragan xato):

Promokod faqat `Onboarding.choosing_plan` holatida qabul qilinardi. Bot
qayta ishga tushsa `MemoryStorage` holatni unutadi — foydalanuvchi esa
o'sha ekranda turgandek ko'radi. Kod yuborsa, hech qaysi handler uni
ushlamasdi va **bot umuman javob bermasdi**: klaviatura ham yo'q, javob
ham yo'q. Tashqaridan "bot o'lgan" bo'lib ko'rinadi.

Bu loyihaning "xato jim yutilmaydi" qoidasiga zid edi.

Shu router **eng oxirgi** ulanadi (`main.py`) — ya'ni faqat boshqa hech
bir handler ushlamagan matn shu yerga tushadi.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.keyboards.menu import main_menu_kb
from app.bot.texts import DEFAULT_LANG, t
from app.core.logging import get_logger
from app.services import billing
from app.services import onboarding as svc

log = get_logger(__name__)
router = Router(name="fallback")

# Promokod shakli: 6–32 ta harf/raqam, bo'shliqsiz
_MIN_CODE, _MAX_CODE = 6, 32


def _looks_like_code(text: str) -> bool:
    return _MIN_CODE <= len(text) <= _MAX_CODE and text.isalnum()


@router.message(F.text)
async def on_unhandled_text(message: Message, state: FSMContext) -> None:
    """Hech kim ushlamagan matn.

    Avval promokod deb tekshiramiz (holatdan qat'i nazar — hamkor bergan
    kodni odam istalgan paytda yuborishi mumkin). Kod bo'lmasa yoki
    topilmasa — menyuni ko'rsatamiz, ya'ni foydalanuvchi hech qachon
    boshi berk ko'chada qolmaydi.
    """
    data = await state.get_data()
    lang = data.get("lang", DEFAULT_LANG)
    text = (message.text or "").strip()

    # 1) API kalitmi? `/stopapi` dan keyin qayta ulash shu yerda ishlaydi —
    #    alohida buyruq talab qilmaymiz, seller shunchaki kalitni yuboradi.
    if svc.looks_like_api_key(text):
        await _reconnect(message, lang, text)
        return

    if _looks_like_code(text):
        result, plan, days = await billing.redeem_promo(message.from_user.id, text)

        if result is billing.PromoResult.OK:
            await message.answer(
                t("promo_ok", lang, plan=_plan_name(plan, lang), days=days)
            )
            await _show_menu(message, lang)
            return

        # NOT_FOUND — bu oddiy matn bo'lishi mumkin ("assalomalaykum"),
        # shuning uchun "kod xato" demaymiz. Qolgan sabablar (muddati
        # tugagan, ishlatilgan) esa haqiqiy kodga tegishli — aytamiz.
        if result is not billing.PromoResult.NOT_FOUND:
            await message.answer(t(_PROMO_ERRORS[result], lang))
            await _show_menu(message, lang)
            return

    await _show_menu(message, lang)


_PROMO_ERRORS = {
    billing.PromoResult.NOT_FOUND: "promo_not_found",
    billing.PromoResult.EXPIRED: "promo_expired",
    billing.PromoResult.USED_UP: "promo_used_up",
    billing.PromoResult.ALREADY_USED: "promo_already_used",
    billing.PromoResult.NO_USER: "promo_no_user",
}


def _plan_name(plan: object, lang: str) -> str:
    value = getattr(plan, "value", str(plan))
    return t(f"plan_{value}", lang) if value else ""


async def _show_menu(message: Message, lang: str) -> None:
    """Menyuni qayta chizadi — klaviatura yo'qolgan bo'lsa tiklanadi."""
    is_admin = await billing.is_admin(message.from_user.id)
    await message.answer(
        t("main_menu_admin", lang) if is_admin else t("main_menu", lang),
        reply_markup=main_menu_kb(lang),
    )


async def _reconnect(message: Message, lang: str, api_key: str) -> None:
    """Kalit yuborildi — tekshirib ulaymiz.

    ❗ Xabar DARHOL o'chiriladi (SPEC 9.3): kalit chatda turgan har
    soniya xavf. O'chirish tekshiruvdan OLDIN bo'ladi.
    """
    try:
        await message.delete()
    except Exception:
        await message.answer(t("delete_failed", lang))

    status = await message.answer(t("key_checking", lang))
    result = await svc.connect_with_api_key(message.from_user.id, api_key)

    if not result.ok:
        key = "key_no_shops" if result.error == "no_shops" else "key_rejected"
        await status.edit_text(t(key, lang))
        return

    shops = ", ".join(s["title"] or s["id"] for s in result.shops)
    await status.edit_text(t("shop_connected", lang, shops=shops))
    await _show_menu(message, lang)
