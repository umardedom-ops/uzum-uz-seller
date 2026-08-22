"""Mini App tugmalari — botdagi kirish nuqtasi.

Ikki joyda ko'rinadi:

  1. **Pastdagi menyu tugmasi** — yozish maydoni yonida, har doim turadi.
     `set_chat_menu_button` bilan **har foydalanuvchiga alohida** qo'yiladi,
     shuning uchun kalitini ulamagan odam uni ko'rmaydi.
  2. **Xabar ostidagi inline tugma** — birinchi sinxronizatsiya tugagach,
     ya'ni ko'rsatadigan ma'lumot paydo bo'lganda.

Nega ikkinchisi sinxronizatsiyadan **keyin**: kalit ulangan zahoti baza
bo'sh bo'ladi. O'sha payt Mini App ochilsa seller birinchi marta bo'sh
ekran ko'radi — bu loyihaning «bo'sh ro'yxat o'rniga sababini ayting»
qoidasiga zid.

⚠️ Tugma chizishdan oldin `webapp_url` tekshiriladi. `https` bo'lmasa
Telegram tugmani rad etadi va u jimgina ishlamaydi — bu loyihada bir
marta uchragan («🚀 Boshlash» handlersiz qolgan edi).
"""
from __future__ import annotations

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    WebAppInfo,
)

from app.bot.texts import t
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


def is_available() -> bool:
    """Mini App ulanganmi (HTTPS domen sozlanganmi)."""
    return bool(get_settings().webapp_url)


def open_kb(lang: str) -> InlineKeyboardMarkup | None:
    """«📊 Kabinetni ochish» inline tugmasi. Manzil yo'q bo'lsa `None`."""
    url = get_settings().webapp_url
    if not url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("miniapp_open", lang), web_app=WebAppInfo(url=url)
                )
            ]
        ]
    )


async def enable_menu_button(bot: Bot, telegram_id: int, lang: str) -> bool:
    """Shu foydalanuvchining chatida pastdagi menyu tugmasini yoqadi.

    Do'kon ulangandan keyin chaqiriladi. Xato bo'lsa **oqim to'xtamaydi**:
    tugma qo'shimcha qulaylik, onboarding esa undan muhimroq. Lekin sabab
    log'ga tushadi — jim qolmaymiz.
    """
    url = get_settings().webapp_url
    if not url:
        log.info("Mini App manzili yo'q — menyu tugmasi qo'yilmadi")
        return False

    try:
        await bot.set_chat_menu_button(
            chat_id=telegram_id,
            menu_button=MenuButtonWebApp(
                text=t("miniapp_menu", lang), web_app=WebAppInfo(url=url)
            ),
        )
    except Exception:
        log.exception("Menyu tugmasi qo'yilmadi: tg_id=%s", telegram_id)
        return False
    return True
