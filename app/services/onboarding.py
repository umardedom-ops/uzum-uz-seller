"""Onboarding biznes-mantig'i.

Asosiy oqim (SPEC 3.1-bis): seller API kalitini yuboradi → biz kalitni
tekshiramiz → `GET /v1/shops` do'konlarni O'ZI qaytaradi → shifrlab
saqlaymiz. Seller do'kon ID sini qidirmaydi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import session_scope
from app.db.models import (
    AlertConfig,
    Claim,
    Compensation,
    Discrepancy,
    FinanceOp,
    Order,
    Product,
    ReportChannel,
    Return,
    Shop,
    ShopCredential,
    ShopStaff,
    StockMovement,
    StockSnapshot,
    StockWriteLog,
    SyncRun,
    User,
)
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


@dataclass(frozen=True, slots=True)
class FirstSyncResult:
    ok: bool
    products: int = 0
    orders: int = 0
    findings: int = 0
    error: str | None = None


async def run_first_sync(telegram_id: int) -> FirstSyncResult:
    """Ulangandan keyingi birinchi to'liq sinxronizatsiya va audit.

    Soatlik jadvalni kutmaymiz — seller kalitni bergan zahoti ma'lumot
    tortila boshlaydi. Aks holda u bir soatgacha bo'sh ekranni ko'radi.
    """
    from sqlalchemy import select

    from app.db.models import Order, Product, Shop, User
    from app.services import audit_runner, sync

    async with session_scope() as session:
        shop_ids = list(
            await session.scalars(
                select(Shop.id)
                .join(User, Shop.user_id == User.id)
                .where(User.telegram_id == telegram_id, Shop.is_active.is_(True))
            )
        )

    if not shop_ids:
        return FirstSyncResult(ok=False, error="no_shops")

    findings = 0
    try:
        for shop_id in shop_ids:
            await sync.sync_shop(shop_id, full=True)
            # Butun faoliyat davri bo'yicha — qoldiq tarixi kerak emas
            today = date.today()
            result = await audit_runner.run_audit(
                shop_id, today - timedelta(days=365), today, cumulative=True
            )
            findings += len(result)
    except Exception as exc:
        log.exception("Birinchi sync xatosi: tg_id=%s", telegram_id)
        return FirstSyncResult(ok=False, error=type(exc).__name__)

    async with session_scope() as session:
        products = 0
        orders = 0
        for shop_id in shop_ids:
            products += len(
                list(
                    await session.scalars(
                        select(Product.id).where(Product.shop_id == shop_id)
                    )
                )
            )
            orders += len(
                list(
                    await session.scalars(
                        select(Order.id).where(Order.shop_id == shop_id)
                    )
                )
            )

    log.info(
        "Birinchi sync tugadi: tg_id=%s mahsulot=%s buyurtma=%s farq=%s",
        telegram_id,
        products,
        orders,
        findings,
    )
    return FirstSyncResult(
        ok=True, products=products, orders=orders, findings=findings
    )


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


async def user_lang(telegram_id: int, default: str = "uz") -> str:
    """Saqlangan tilni qaytaradi.

    Kerak, chunki FSM holati vaqtinchalik (bot restartida yo'qoladi) —
    qaytib kelgan foydalanuvchiga menyuni **o'z tilida** ko'rsatish uchun
    manba baza bo'lishi kerak.
    """
    async with session_scope() as session:
        lang = await session.scalar(
            select(User.lang).where(User.telegram_id == telegram_id)
        )
    return lang.value if lang is not None else default


async def accept_oferta(telegram_id: int) -> None:
    async with session_scope() as session:
        user = await repo.get_or_create_user(session, telegram_id)
        await repo.accept_oferta(session, user)


def _mask(phone: str | None) -> str:
    """Logда telefon to'liq ko'rinmasin."""
    if not phone:
        return "-"
    return f"{phone[:4]}***{phone[-2:]}" if len(phone) > 6 else "***"


#: `/stopapi` da do'kon bilan birga o'chadigan jadvallar — hammasida
#: `shop_id` bor. Tartib bola → ota: `Discrepancy` `Claim` ga ishora
#: qiladi, shuning uchun u avval o'chadi.
#:
#: DB darajasida `ondelete="CASCADE"` qo'yilgan, lekin SQLite uni faqat
#: `PRAGMA foreign_keys=ON` bilan bajaradi — biz uni yoqmaymiz. Shuning
#: uchun bolalarni O'ZIMIZ o'chiramiz: aks holda lokal bazada yetim
#: qatorlar qolib, keyingi ulanishda eski ma'lumot aralashadi.
_SHOP_OWNED_TABLES = (
    Discrepancy,
    Claim,
    AlertConfig,
    SyncRun,
    StockWriteLog,
    ShopStaff,
    ReportChannel,
    Product,
    Order,
    Return,
    StockSnapshot,
    StockMovement,
    FinanceOp,
    Compensation,
    ShopCredential,
)


async def disconnect_api(telegram_id: int) -> int:
    """Do'konni butunlay uzadi: kalit ham, yig'ilgan ma'lumot ham o'chadi.

    Nima uchun kerak: seller istalgan payt ulanishni uza olishi kerak.
    "Kalitni bermay turay" degan huquq — ishonchning bir qismi va uni
    kabinetga kirmasdan, botning o'zidan qilish mumkin bo'lsin.

    Nega faqat kalitni o'chirish yetmaydi (2026-08-14 dagi jonli xato):
    xabarnoma, kunlik hisobot va audit Uzumdan emas, **bazadagi**
    ma'lumotdan yasaladi. Kalit yo'q bo'lsa ham eski `Product` va
    `StockSnapshot` qatorlari joyida turar, bot esa "tovar bloklangan"
    deb xabar yuboraverardi — do'kon allaqachon uzilgan bo'lsa ham.
    Do'kon o'chgach, xabar yasashga manba qolmaydi.

    Qayta ulash: yangi kalit yuboriladi va **kalit qaysi do'konniki
    bo'lsa, o'sha do'kon** ulanadi (`GET /v1/shops` javobi bo'yicha) —
    eski do'kon qaytib kelmaydi.

    Obuna va to'lov tarixi o'chmaydi — ular foydalanuvchiga bog'langan,
    do'konga emas.

    Nechta do'kon uzilganini qaytaradi.
    """
    async with session_scope() as session:
        user = await session.scalar(
            select(User).where(User.telegram_id == telegram_id)
        )
        if user is None:
            return 0

        shops = list(
            await session.execute(
                select(Shop.id, Shop.uzum_shop_id).where(Shop.user_id == user.id)
            )
        )
        if not shops:
            return 0

        shop_ids = [row.id for row in shops]

        # Yozish tarixi ham o'chadi — hech bo'lmasa server logida iz
        # qolsin (CLAUDE.md: har bir yozish qayd etiladi).
        writes = await session.scalar(
            select(func.count())
            .select_from(StockWriteLog)
            .where(StockWriteLog.shop_id.in_(shop_ids))
        )

        for model in _SHOP_OWNED_TABLES:
            await session.execute(delete(model).where(model.shop_id.in_(shop_ids)))
        await session.execute(delete(Shop).where(Shop.id.in_(shop_ids)))

        # Tanlangan do'kon o'chgan bo'lsa ko'rsatkich osilib qolmasin
        # (bu ustunda FK yo'q — o'zimiz tozalaymiz).
        if user.active_shop_id in shop_ids:
            user.active_shop_id = None

    log.info(
        "Do'kon uzildi: tg_id=%s do'konlar=%s yozish_jurnalidan %s qator o'chdi",
        telegram_id,
        [row.uzum_shop_id for row in shops],
        writes or 0,
    )
    return len(shops)


async def has_connected_shop(telegram_id: int) -> bool:
    """Uziladigan narsa bormi — kalit yoki bazada qolgan do'kon.

    Faqat kalitni tekshirish yetmaydi: kalit boshqa yo'l bilan o'chgan
    (yaroqsiz bo'lib qolgan, eski `/stopapi` dan qolgan) bo'lsa ham
    do'kon va uning ma'lumoti bazada turadi. Seller uni `/stopapi`
    orqali tozalay olishi kerak, aks holda "uzilgan, lekin qolgan"
    do'kon abadiy qoladi.
    """
    async with session_scope() as session:
        row = await session.scalar(
            select(Shop.id)
            .join(User, User.id == Shop.user_id)
            .where(User.telegram_id == telegram_id)
            .limit(1)
        )
        return row is not None


async def has_api_key(telegram_id: int) -> bool:
    """Foydalanuvchida faol API kalit bormi."""
    async with session_scope() as session:
        row = await session.scalar(
            select(ShopCredential.id)
            .join(Shop, Shop.id == ShopCredential.shop_id)
            .join(User, User.id == Shop.user_id)
            .where(
                User.telegram_id == telegram_id,
                ShopCredential.is_valid.is_(True),
            )
            .limit(1)
        )
        return row is not None
