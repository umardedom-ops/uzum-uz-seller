"""Onboarding biznes-mantig'i.

Asosiy oqim (SPEC 3.1-bis): seller API kalitini yuboradi → biz kalitni
tekshiramiz → `GET /v1/shops` do'konlarni O'ZI qaytaradi → shifrlab
saqlaymiz. Seller do'kon ID sini qidirmaydi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import session_scope
from app.db.repositories import onboarding as repo
from app.uzum.api_client import UzumApiClient
from app.uzum.base import UzumHTTP
from app.uzum.models import AuthType, SessionCredentials

log = get_logger(__name__)

# Do'kon ID — faqat raqam (namuna: 62866). Qo'lda kiritish uchun zaxira yo'l.
_SHOP_ID_RE = re.compile(r"^\d{3,10}$")

# API kalit: base64 ko'rinishidagi uzun satr. Aniq formatga bog'lanmaymiz —
# haqiqiy tekshiruv Uzumga so'rov yuborish orqali bo'ladi.
_MIN_KEY_LEN = 20


@dataclass(frozen=True, slots=True)
class ConnectResult:
    ok: bool
    shops: list[dict[str, str]]  # [{"id": "125841", "title": "Elore Parfume"}]
    error: str | None = None


def looks_like_api_key(text: str) -> bool:
    """Yuborilgan matn kalitga o'xshaydimi — Uzumga bekorga so'rov yubormaslik uchun."""
    candidate = text.strip()
    if len(candidate) < _MIN_KEY_LEN or " " in candidate:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9+/=_\-.]+", candidate))


def parse_shop_ids(raw: str) -> list[str]:
    """Matndan do'kon ID'larini ajratadi (zaxira yo'l, kabinet uchun).

    Vergul/probel bilan ajratilgan raqamlar yoki to'liq URL bo'lishi mumkin:
    `.../seller/62866/products/all`
    """
    url_ids = re.findall(r"/seller/(\d{3,10})(?:/|$)", raw)
    if url_ids:
        return list(dict.fromkeys(url_ids))

    parts = re.split(r"[,\s]+", raw.strip())
    ids = [p for p in parts if _SHOP_ID_RE.match(p)]
    return list(dict.fromkeys(ids))


async def connect_with_api_key(telegram_id: int, api_key: str) -> ConnectResult:
    """Kalitni tekshiradi, do'konlarni oladi va shifrlab saqlaydi.

    Kalit bazaga faqat tekshiruvdan o'tgach yoziladi — yaroqsiz kalitni
    saqlashning ma'nosi yo'q.
    """
    settings = get_settings()
    http = UzumHTTP(
        settings.uzum_api_base, rate_limit_per_sec=settings.uzum_rate_limit_per_sec
    )
    client = UzumApiClient(
        http, SessionCredentials(auth_type=AuthType.API, secret=api_key.strip())
    )

    try:
        raw_shops = await client.get_shops()
    except Exception as exc:
        # Kalit noto'g'ri, muddati o'tgan yoki Uzum javob bermayapti.
        # Kalitning O'ZI logga tushmaydi (SPEC 9.2).
        log.warning(
            "Kalit tekshiruvi muvaffaqiyatsiz: tg_id=%s xato=%s",
            telegram_id,
            type(exc).__name__,
        )
        return ConnectResult(ok=False, shops=[], error="invalid_key")
    finally:
        await http.aclose()

    if not raw_shops:
        return ConnectResult(ok=False, shops=[], error="no_shops")

    shops = [
        {"id": str(s.get("id")), "title": s.get("name") or ""} for s in raw_shops
    ]

    async with session_scope() as session:
        user = await repo.get_or_create_user(session, telegram_id)
        await repo.start_trial(session, user, settings.trial_days)
        for item in shops:
            shop = await repo.upsert_shop(session, user, item["id"], item["title"])
            await repo.save_credential(session, shop, api_key.strip(), AuthType.API)

    log.info("Ulandi: tg_id=%s do'konlar=%s", telegram_id, [s["id"] for s in shops])
    return ConnectResult(ok=True, shops=shops)


async def save_user(
    telegram_id: int,
    lang: str,
    phone: str | None = None,
    *,
    full_name: str | None = None,
    username: str | None = None,
) -> None:
    """Foydalanuvchini saqlaydi/yangilaydi.

    Birinchi foydalanuvchi avtomatik admin bo'ladi (repozitoriyda).
    """
    async with session_scope() as session:
        user = await repo.get_or_create_user(
            session, telegram_id, lang, full_name=full_name, username=username
        )
        await repo.set_lang(session, user, lang)
        if phone:
            await repo.set_phone(session, user, phone)
    log.info("User saqlandi: tg_id=%s lang=%s phone=%s", telegram_id, lang, _mask(phone))


async def accept_oferta(telegram_id: int) -> None:
    async with session_scope() as session:
        user = await repo.get_or_create_user(session, telegram_id)
        await repo.accept_oferta(session, user)


def _mask(phone: str | None) -> str:
    """Logда telefon to'liq ko'rinmasin."""
    if not phone:
        return "-"
    return f"{phone[:4]}***{phone[-2:]}" if len(phone) > 6 else "***"
