"""Onboarding oqimi (SPEC 7).

/start → til → xush kelibsiz → TARIF → oferta → telefon → yo'riqnoma
→ API kalit → asosiy menyu

Tarif til tanlangandan keyin so'raladi. Pullik tanlansa to'lov oxirida —
do'kon ulangach — taklif qilinadi.
"""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    Message,
    ReplyKeyboardRemove,
)

from app.bot.keyboards.billing import onboarding_plans_kb
from app.bot.keyboards.menu import main_menu_kb
from app.bot.keyboards.onboarding import (
    how_to_kb,
    lang_kb,
    oferta_kb,
    phone_kb,
)
from app.bot.states.onboarding import Onboarding
from app.bot.texts import DEFAULT_LANG, t
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services import billing
from app.services import onboarding as svc
from app.services.exports import find_user_shop

log = get_logger(__name__)
router = Router(name="onboarding")


def _money(amount: int) -> str:
    """149000 → «149 000»."""
    return f"{amount:,}".replace(",", " ")


# Fon vazifalariga havola: aks holda Python ularni yig'ishtirib yuborishi
# mumkin va sinxronizatsiya yarim yo'lda uziladi.
_background: set[asyncio.Task[None]] = set()


def _spawn(coro: Coroutine[object, object, None]) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _first_sync_and_notify(bot: Bot, telegram_id: int, lang: str) -> None:
    """Birinchi to'liq sync + audit, so'ng natija haqida xabar.

    Xato bo'lsa ham sellerga aniq xabar boradi — jim qolmaymiz (SPEC 9.6).
    """
    try:
        result = await svc.run_first_sync(telegram_id)
    except Exception:
        log.exception("Birinchi sync ishga tushmadi: tg_id=%s", telegram_id)
        return

    if not result.ok:
        await bot.send_message(telegram_id, t("first_sync_failed", lang))
        return

    if result.findings:
        text = t("first_sync_found", lang, count=result.findings)
    else:
        text = t(
            "first_sync_clean",
            lang,
            products=result.products,
            orders=result.orders,
        )
    await bot.send_message(telegram_id, text)


async def _lang(state: FSMContext) -> str:
    """FSM'dan tanlangan tilni oladi."""
    data = await state.get_data()
    return data.get("lang", DEFAULT_LANG)


# --- 1. /start → til tanlash ---
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """`/start` — qaytib kelgan foydalanuvchiga MENYU, yangisiga onboarding.

    ❗ Ilgari `/start` har doim onboardingni noldan boshlardi va do'koni
    ulangan seller ham qaytadan til → tarif → oferta → **API kalit**
    so'roviga tushardi (2026-08-10 da jonli uchradi). Ustiga FSM holati
    bot restartida yo'qolgani uchun bu tez-tez sodir bo'lardi: seller
    "bot meni unutdi, kalitni yana beraymi?" degan holatga tushardi.

    Endi manba — **baza**: do'kon ulangan bo'lsa, holatdan qat'i nazar
    menyuni ko'rsatamiz va tilni bazadan olamiz.
    """
    shop = await find_user_shop(message.from_user.id)

    if shop is not None:
        lang = await svc.user_lang(message.from_user.id)
        await state.clear()
        await state.set_state(Onboarding.done)
        await state.update_data(lang=lang, chosen_plan="free")

        is_admin = await billing.is_admin(message.from_user.id)
        await message.answer(
            t("main_menu_admin", lang) if is_admin else t("main_menu", lang),
            reply_markup=main_menu_kb(lang),
        )
        return

    await state.clear()
    await state.set_state(Onboarding.choosing_lang)
    await message.answer(t("choose_lang"), reply_markup=lang_kb())


# --- 2. Til tanlandi → xush kelibsiz ---
@router.callback_query(F.data.startswith("lang:"))
async def on_lang(cb: CallbackQuery, state: FSMContext) -> None:
    lang = cb.data.split(":", 1)[1]
    await state.update_data(lang=lang)
    await svc.save_user(
        cb.from_user.id,
        lang,
        full_name=cb.from_user.full_name,
        username=cb.from_user.username,
    )

    s = get_settings()

    # Xush kelibsiz — tugmasiz, chunki tarif tanlash darhol keyin keladi.
    await cb.message.edit_text(
        t("welcome", lang, trial_days=s.trial_days, price=_money(s.price_basic))
    )

    # Tarif tanlash — til tanlangandan keyingi BIRINCHI qadam, oraliq
    # "Boshlash" tugmasisiz. Tanlash majburiy: tanlanmaguncha oqim
    # davom etmaydi.
    await state.set_state(Onboarding.choosing_plan)
    await send_plans(cb.message, lang)
    await cb.answer()


#: Tariflar banneri qidiriladigan nomlar. Bir nechta kengaytma:
#: dizayner faylni `.jpg` yoki `.png` qilib berishi mumkin va shu sabab
#: banner ko'rinmay qolmasin (2026-08-09 da aynan shunday bo'ldi —
#: fayl `tariffs.png.jpg` nomi bilan saqlangan edi).
_ASSETS = Path(__file__).resolve().parents[1] / "assets"
_BANNER_NAMES = ("tariffs.jpg", "tariffs.jpeg", "tariffs.png", "tariffs.webp")

#: Telegram rasm sarlavhasi shu uzunlikdan oshmasligi kerak
_CAPTION_LIMIT = 1024


def tariff_banner() -> Path | None:
    """Mavjud banner faylini qaytaradi, topilmasa `None`."""
    for name in _BANNER_NAMES:
        candidate = _ASSETS / name
        if candidate.exists():
            return candidate
    return None


async def send_with_banner(target: Message, text: str, kb: object) -> None:
    """Matnni tariflar banneri bilan yuboradi.

    Rasm topilmasa yoki Telegram uni rad etsa — oqim to'xtamaydi, faqat
    matn ketadi. Banner yo'qligi sababli seller tarif tanlay olmay
    qolmasligi kerak.

    Uzun matn rasm sarlavhasiga sig'maydi ({limit} belgi), shunday
    holatda ham matnga tushamiz.
    """
    banner = tariff_banner()
    if banner is not None and len(text) <= _CAPTION_LIMIT:
        try:
            await target.answer_photo(
                FSInputFile(banner), caption=text, reply_markup=kb
            )
            return
        except TelegramBadRequest:
            log.exception("Tariflar banneri yuborilmadi — matn bilan davom etamiz")

    await target.answer(text, reply_markup=kb)


def plans_text(lang: str) -> str:
    """Onboardingdagi tarif matni (narx tugmalarda bo'lgani uchun qisqa)."""
    s = get_settings()
    return t(
        "choose_plan",
        lang,
        trial_days=s.trial_days,
        price_basic=_money(s.price_basic),
        price_pro=_money(s.price_pro),
    )


async def send_plans(target: Message, lang: str) -> None:
    """Onboardingdagi tarif ekrani: banner + matn + 3 ta tugma."""
    await send_with_banner(target, plans_text(lang), onboarding_plans_kb(lang))


async def show_oferta(cb: CallbackQuery, state: FSMContext) -> None:
    """Oferta ekrani (tarif tanlangandan keyin).

    Asosiy shartlar bevosita Telegramda ko'rsatiladi — havolaga bog'liq
    emas. To'liq matnni alohida tugma bilan fayl ko'rinishida olish
    mumkin, ya'ni server ishlamasa ham seller hujjatni o'qiy oladi.
    """
    lang = await _lang(state)
    await state.set_state(Onboarding.accepting_oferta)
    await cb.message.answer(
        t("oferta", lang),
        reply_markup=oferta_kb(lang),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "oferta:full")
async def on_oferta_full(cb: CallbackQuery, state: FSMContext) -> None:
    """To'liq oferta matnini fayl sifatida yuboradi."""
    lang = await _lang(state)
    await cb.answer()

    # app/bot/handlers/start.py → parents[2] = app/
    path = Path(__file__).resolve().parents[2] / "web" / "static" / "oferta.html"
    if not path.exists():
        log.error("Oferta fayli topilmadi: %s", path)
        await cb.message.answer(t("error", lang))
        return

    await cb.message.answer_document(
        FSInputFile(path, filename="oferta.html"),
        caption=t("oferta_file_caption", lang),
    )


# --- 4. Oferta qabul qilindi → telefon so'rash ---
@router.callback_query(F.data == "oferta:accept")
async def on_oferta_accept(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    await svc.accept_oferta(cb.from_user.id)
    await state.set_state(Onboarding.sharing_phone)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(t("ask_phone", lang), reply_markup=phone_kb(lang))
    await cb.answer()


# --- 5. Telefon keldi → ulanish taklifi ---
@router.message(Onboarding.sharing_phone, F.contact)
async def on_contact(message: Message, state: FSMContext) -> None:
    lang = await _lang(state)
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    await svc.save_user(message.from_user.id, lang, phone)

    await message.answer(
        t("phone_saved", lang, phone=phone), reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(Onboarding.reading_instruction)
    await message.answer(t("connect_intro", lang), reply_markup=how_to_kb(lang))


@router.message(Onboarding.sharing_phone)
async def on_phone_invalid(message: Message, state: FSMContext) -> None:
    """Foydalanuvchi tugma o'rniga matn yozsa."""
    lang = await _lang(state)
    await message.answer(t("phone_invalid", lang), reply_markup=phone_kb(lang))


# --- 6. Yo'riqnoma → API kalit so'rash ---
@router.callback_query(F.data == "connect:how")
async def on_how_to(cb: CallbackQuery, state: FSMContext) -> None:
    """Yozma qadamlar + video qo'llanma.

    Video matnni almashtirmaydi, to'ldiradi: seller telefonda video
    ko'ra olmasligi yoki ovozi o'chiq bo'lishi mumkin. Video yo'q
    bo'lsa ham oqim to'liq ishlaydi.
    """
    lang = await _lang(state)

    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(t("instruction", lang))
    await _send_guide_video(cb.message, lang)
    await state.set_state(Onboarding.entering_api_key)
    await cb.message.answer(t("ask_api_key", lang))
    await cb.answer()


async def _send_guide_video(target: Message, lang: str) -> None:
    """API kalit olish bo'yicha video qo'llanma."""
    video = _ASSETS / "api-guide.mp4"
    if not video.exists():
        return
    try:
        await target.answer_video(
            FSInputFile(video),
            caption=t("guide_video_caption", lang),
            supports_streaming=True,
        )
    except TelegramBadRequest:
        # Video ketmasa yozma yo'riqnoma yetarli — oqim to'xtamaydi
        log.exception("Video qo'llanma yuborilmadi")


# --- 7. API kalit → tekshirish, do'konlarni topish, saqlash ---
@router.message(Onboarding.entering_api_key, F.text)
async def on_api_key(message: Message, state: FSMContext) -> None:
    lang = await _lang(state)
    raw = message.text.strip()

    if not svc.looks_like_api_key(raw):
        await message.answer(t("key_invalid_format", lang))
        return

    # SPEC 9.3: maxfiy ma'lumot qabul qilingach xabar o'chiriladi.
    # Tekshiruvdan OLDIN o'chiramiz — kalit chatda turgan har soniya xavf.
    try:
        await message.delete()
    except TelegramBadRequest:
        # Bot xabarni o'chira olmasa (huquq yo'q) — oqim to'xtamasin,
        # lekin sellerni ogohlantiramiz.
        log.warning("Kalit xabarini o'chirib bo'lmadi: tg_id=%s", message.from_user.id)
        await message.answer(t("delete_failed", lang))

    status = await message.answer(t("key_checking", lang))
    result = await svc.connect_with_api_key(message.from_user.id, raw)

    if not result.ok:
        key = "key_no_shops" if result.error == "no_shops" else "key_rejected"
        await status.edit_text(t(key, lang))
        return

    settings = get_settings()
    # `.get()` — nomsiz do'kon uchraydi va yo'q kalit botni yiqitmasin
    shops = ", ".join(s.get("title") or s.get("id", "?") for s in result.shops)
    await status.edit_text(
        t("shop_connected", lang, shops=shops, trial_days=settings.trial_days)
    )

    await state.set_state(Onboarding.done)

    # Tarif boshida tanlangan. Pullik bo'lsa to'lov endi so'raladi —
    # seller do'koni ulanganini ko'rgandan keyin, oldin emas.
    from app.bot.handlers.billing import offer_payment_after_connect

    paid = await offer_payment_after_connect(message, state, message.from_user.id)
    if not paid:
        is_admin = await billing.is_admin(message.from_user.id)
        await message.answer(
            t("main_menu_admin", lang) if is_admin else t("main_menu", lang),
            reply_markup=main_menu_kb(lang),
        )

    # Birinchi sinxronizatsiyani darhol boshlaymiz — soatlik jadvalni
    # kutsak, seller bir soatgacha bo'sh ekranni ko'radi.
    _spawn(_first_sync_and_notify(message.bot, message.from_user.id, lang))
