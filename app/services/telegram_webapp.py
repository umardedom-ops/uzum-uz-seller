"""Telegram Mini App `initData` imzosini tekshirish.

Mini App ochilganda Telegram sahifaga `initData` beradi — ichida
foydalanuvchi ma'lumoti va **imzo**. Imzo bot tokeni bilan tekshiriladi,
shuning uchun server foydalanuvchi kimligiga ishona oladi. Web-kabinetdagi
bir martalik havola (`services/web_auth.py`) bu yerda kerak emas.

❗ **Eng muhim qoida: imzoni tekshirmasdan `user` maydoniga ishonmang.**
`initData` — oddiy matn, brauzer konsolidan istalgan `id` yozib yuborish
mumkin. Tekshirmasak har kim istalgan sellerning do'konini ko'radi.
Raqobatchining aynan shu joyda xatosi bor edi (`login = Telegram ID`).

Imzo formulasi (core.telegram.org/bots/webapps):

    secret_key = HMAC_SHA256(key="WebAppData", msg=<bot token>)
    hash       = HMAC_SHA256(key=secret_key,  msg=data_check_string)

⚠️ Kalit va xabar **teskari** tuyuladi: kalit — o'zgarmas `"WebAppData"`
satri, xabar esa bot tokeni. Odatdagidek yozilsa imzo hech qachon
to'g'ri chiqmaydi va sabab ko'rinmaydi.

`data_check_string` — `hash` dan tashqari hamma maydon `kalit=qiymat`
ko'rinishida, **kalit bo'yicha saralanib**, `\n` bilan ulanadi.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import parse_qsl

from app.core.logging import get_logger
from app.db.base import utcnow

log = get_logger(__name__)

# Eski `initData` ni qabul qilmaymiz — o'g'irlangan satr cheksiz
# ishlatilmasin. Telegram ilovasi uzoq ochiq tursa foydalanuvchi
# sahifani yangilaydi va yangi `initData` oladi.
MAX_AGE = timedelta(hours=24)


class InitDataError(Exception):
    """Imzo yoki ma'lumot yaroqsiz.

    Xabar **sabab bilan** yoziladi — «kirish rad etildi» degan quruq
    matn bilan muammoni topib bo'lmaydi.
    """


@dataclass(frozen=True, slots=True)
class WebAppUser:
    """`initData` dan olingan, **imzo bilan tasdiqlangan** foydalanuvchi."""

    telegram_id: int
    first_name: str = ""
    username: str = ""
    language_code: str = "uz"

    @property
    def display_name(self) -> str:
        return self.first_name or self.username or str(self.telegram_id)


def _data_check_string(pairs: list[tuple[str, str]]) -> str:
    """`hash` dan tashqari hamma maydon, saralangan holda, `\\n` bilan."""
    return "\n".join(
        f"{key}={value}" for key, value in sorted(pairs) if key != "hash"
    )


def _secret_key(bot_token: str) -> bytes:
    """⚠️ Kalit — `"WebAppData"` satri, xabar — bot tokeni. Teskari emas."""
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def verify_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age: timedelta = MAX_AGE,
) -> WebAppUser:
    """Imzoni tekshiradi va foydalanuvchini qaytaradi.

    Yaroqsiz bo'lsa `InitDataError` — sabab bilan. Chaqiruvchi uni
    ushlab, foydalanuvchiga tushunarli sahifa ko'rsatadi.
    """
    if not init_data:
        raise InitDataError("initData bo'sh — sahifa Telegram ichida ochilmagan")
    if not bot_token:
        raise InitDataError("BOT_TOKEN sozlanmagan — imzoni tekshirib bo'lmaydi")

    pairs = parse_qsl(init_data, keep_blank_values=True)
    received = dict(pairs).get("hash", "")
    if not received:
        raise InitDataError("initData ichida `hash` yo'q")

    expected = hmac.new(
        _secret_key(bot_token),
        _data_check_string(pairs).encode(),
        hashlib.sha256,
    ).hexdigest()

    # `compare_digest` — vaqt bo'yicha hujumdan himoya
    if not hmac.compare_digest(expected, received.lower()):
        raise InitDataError("imzo mos kelmadi")

    _check_freshness(dict(pairs).get("auth_date", ""), max_age)
    return _parse_user(dict(pairs).get("user", ""))


def _check_freshness(auth_date: str, max_age: timedelta) -> None:
    """`auth_date` juda eski bo'lmasinmi.

    Imzo to'g'ri bo'lsa ham eskisi qayta ishlatilishi mumkin: kimdir
    `initData` ni bir marta qo'lga kiritsa, muddatsiz kira olardi.
    """
    try:
        issued = int(auth_date)
    except (TypeError, ValueError):
        raise InitDataError("`auth_date` yo'q yoki raqam emas") from None

    age = utcnow().timestamp() - issued
    if age > max_age.total_seconds():
        hours = int(age // 3600)
        raise InitDataError(f"initData eskirgan ({hours} soat) — sahifani yangilang")
    # Kelajakdagi sana — soat farqi yoki soxta ma'lumot. Kichik zaxira
    # beramiz (5 daqiqa), undan kattasi shubhali.
    if age < -300:
        raise InitDataError("`auth_date` kelajakda — ma'lumot ishonchsiz")


def _parse_user(raw: str) -> WebAppUser:
    """`user` maydoni JSON. Imzo allaqachon tekshirilgan."""
    if not raw:
        raise InitDataError("initData ichida `user` yo'q")
    try:
        data = json.loads(raw)
    except ValueError:
        raise InitDataError("`user` maydoni buzuq JSON") from None

    try:
        telegram_id = int(data["id"])
    except (KeyError, TypeError, ValueError):
        raise InitDataError("`user.id` yo'q yoki raqam emas") from None

    return WebAppUser(
        telegram_id=telegram_id,
        first_name=str(data.get("first_name") or ""),
        username=str(data.get("username") or ""),
        language_code=str(data.get("language_code") or "uz"),
    )
