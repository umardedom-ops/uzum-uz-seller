"""Click Shop API integratsiyasi (docs.click.uz/shop-api).

Ikki bosqichli oqim — Click bizning serverimizga murojaat qiladi:

  Prepare  (action=0) — to'lovni tekshirish va zaxiralash
  Complete (action=1) — to'lovni yakunlash, obunani faollashtirish

Imzo (MD5):
  Prepare : click_trans_id + service_id + SECRET_KEY + merchant_trans_id
            + amount + action + sign_time
  Complete: click_trans_id + service_id + SECRET_KEY + merchant_trans_id
            + merchant_prepare_id + amount + action + sign_time

`merchant_trans_id` — bizning `payments.id`. Shu orqali to'lov kimniki
ekanini bilamiz.

⚠️ SECRET_KEY hech qachon logga yozilmaydi (SPEC 9.2).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from enum import IntEnum

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import session_scope
from app.db.models import Payment, PaymentStatus, Plan
from app.services import billing

log = get_logger(__name__)

PAY_URL = "https://my.click.uz/services/pay"

# Summani taqqoslashda ruxsat etilgan farq (Click float yuboradi)
AMOUNT_TOLERANCE = Decimal("0.01")


class ClickError(IntEnum):
    """Click hujjatidagi standart kodlar (docs.click.uz/shop-api/errors)."""

    SUCCESS = 0
    SIGN_CHECK_FAILED = -1
    INCORRECT_AMOUNT = -2
    ACTION_NOT_FOUND = -3
    ALREADY_PAID = -4
    USER_NOT_FOUND = -5
    TRANSACTION_NOT_FOUND = -6
    FAILED_TO_UPDATE = -7
    BAD_REQUEST = -8
    TRANSACTION_CANCELLED = -9


ERROR_NOTES: dict[int, str] = {
    ClickError.SUCCESS: "Success",
    ClickError.SIGN_CHECK_FAILED: "SIGN CHECK FAILED!",
    ClickError.INCORRECT_AMOUNT: "Incorrect parameter amount",
    ClickError.ACTION_NOT_FOUND: "Action not found",
    ClickError.ALREADY_PAID: "Already paid",
    ClickError.USER_NOT_FOUND: "User does not exist",
    ClickError.TRANSACTION_NOT_FOUND: "Transaction does not exist",
    ClickError.FAILED_TO_UPDATE: "Failed to update user",
    ClickError.BAD_REQUEST: "Error in request from click",
    ClickError.TRANSACTION_CANCELLED: "Transaction cancelled",
}


@dataclass(frozen=True, slots=True)
class ClickRequest:
    """Click yuboradigan maydonlar (form-urlencoded)."""

    click_trans_id: str
    service_id: str
    click_paydoc_id: str
    merchant_trans_id: str
    amount: str
    action: str
    sign_time: str
    sign_string: str
    error: str = "0"
    error_note: str = ""
    merchant_prepare_id: str = ""


def _md5(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()  # noqa: S324 — Click talabi


def build_sign(req: ClickRequest, secret_key: str) -> str:
    """Kutilayotgan imzoni hisoblaydi.

    Complete bosqichida `merchant_prepare_id` ham qatnashadi — Prepare'da
    qatnashmaydi. Tartib hujjatdagidek qat'iy.
    """
    parts = [req.click_trans_id, req.service_id, secret_key, req.merchant_trans_id]
    if req.action == "1":
        parts.append(req.merchant_prepare_id)
    parts += [req.amount, req.action, req.sign_time]
    return _md5("".join(parts))


def verify_sign(req: ClickRequest, secret_key: str) -> bool:
    """Imzoni tekshiradi.

    Taqqoslash `compare_digest` bilan — vaqt bo'yicha hujumdan himoya.
    """
    import hmac

    expected = build_sign(req, secret_key)
    return hmac.compare_digest(expected, (req.sign_string or "").lower())


def response(
    error: ClickError,
    *,
    click_trans_id: str = "",
    merchant_trans_id: str = "",
    prepare_id: int | None = None,
    confirm_id: int | None = None,
) -> dict[str, object]:
    """Click kutgan JSON javob."""
    payload: dict[str, object] = {
        "error": int(error),
        "error_note": ERROR_NOTES.get(error, "Error"),
    }
    if click_trans_id:
        payload["click_trans_id"] = click_trans_id
    if merchant_trans_id:
        payload["merchant_trans_id"] = merchant_trans_id
    if prepare_id is not None:
        payload["merchant_prepare_id"] = prepare_id
    if confirm_id is not None:
        payload["merchant_confirm_id"] = confirm_id
    return payload


def payment_link(payment_id: int, amount: int) -> str:
    """Mijozga beriladigan to'lov havolasi.

    ⚠️ `amount` **N.NN** formatida bo'lishi shart (`149000.00`) — hujjat
    shuni talab qiladi. Ilgari butun son yuborilardi.

    `card_type` ataylab **berilmaydi**: berilsa faqat o'sha tizim kartasi
    qabul qilinadi va, masalan, Humo egasi to'lay olmaydi.
    """
    settings = get_settings()
    return (
        f"{PAY_URL}?service_id={settings.click_service_id}"
        f"&merchant_id={settings.click_merchant_id}"
        f"&amount={amount:.2f}"
        f"&transaction_param={payment_id}"
    )


# ---------------------------------------------------------------------- #
# Bosqichlar
# ---------------------------------------------------------------------- #


async def handle_prepare(req: ClickRequest) -> dict[str, object]:
    """Prepare (action=0) — to'lovni tekshirish."""
    settings = get_settings()

    if not verify_sign(req, settings.click_secret_key):
        log.warning("Click imzo xato: trans=%s", req.click_trans_id)
        return response(ClickError.SIGN_CHECK_FAILED)

    payment = await _load_payment(req.merchant_trans_id)
    if payment is None:
        return response(ClickError.USER_NOT_FOUND)

    if payment["status"] is PaymentStatus.PAID:
        return response(ClickError.ALREADY_PAID)
    if payment["status"] is PaymentStatus.REJECTED:
        return response(ClickError.TRANSACTION_CANCELLED)

    if not _amount_matches(req.amount, payment["amount"]):
        log.warning(
            "Click summa mos emas: kutilgan=%s kelgan=%s payment_id=%s",
            payment["amount"],
            req.amount,
            payment["id"],
        )
        return response(ClickError.INCORRECT_AMOUNT)

    # Click transaksiya raqamini saqlaymiz — Complete'da solishtiriladi
    await _remember_click_trans(payment["id"], req.click_trans_id)

    return response(
        ClickError.SUCCESS,
        click_trans_id=req.click_trans_id,
        merchant_trans_id=req.merchant_trans_id,
        prepare_id=payment["id"],
    )


async def handle_complete(req: ClickRequest) -> dict[str, object]:
    """Complete (action=1) — to'lovni yakunlash va obunani faollashtirish."""
    settings = get_settings()

    if not verify_sign(req, settings.click_secret_key):
        log.warning("Click imzo xato (complete): trans=%s", req.click_trans_id)
        return response(ClickError.SIGN_CHECK_FAILED)

    payment = await _load_payment(req.merchant_trans_id)
    if payment is None:
        return response(ClickError.USER_NOT_FOUND)

    # ❗ Holat tekshiruvi `error` dan OLDIN turadi. Teskari tartibda
    # to'langan yozuvga kelgan reversal avval `reject_payment` ga tushardi
    # va javob «bekor qilindi» bo'lardi — Click tomonda bekor, bizda esa
    # to'langan. Obuna zarar ko'rmasdi (`reject_payment` faqat PENDING ni
    # o'zgartiradi), lekin himoya tasodifiy edi va javob noto'g'ri.
    if payment["status"] is PaymentStatus.PAID:
        return response(ClickError.ALREADY_PAID)
    if payment["status"] is PaymentStatus.REJECTED:
        return response(ClickError.TRANSACTION_CANCELLED)

    # Click o'z tomonida xato yuborsa — to'lovni bekor qilamiz.
    # `payment["id"]` ishlatiladi: `merchant_trans_id` raqam bo'lmasa
    # `int()` yiqilib, webhook 500 qaytarardi.
    if _click_failed(req.error):
        await billing.reject_payment(int(payment["id"]))
        return response(ClickError.TRANSACTION_CANCELLED)

    if str(payment["id"]) != str(req.merchant_prepare_id):
        return response(ClickError.TRANSACTION_NOT_FOUND)

    if not _amount_matches(req.amount, payment["amount"]):
        return response(ClickError.INCORRECT_AMOUNT)

    ok = await billing.confirm_payment(payment["id"])
    if not ok:
        return response(ClickError.FAILED_TO_UPDATE)

    log.info(
        "Click to'lovi tasdiqlandi: payment_id=%s click_trans=%s",
        payment["id"],
        req.click_trans_id,
    )
    return response(
        ClickError.SUCCESS,
        click_trans_id=req.click_trans_id,
        merchant_trans_id=req.merchant_trans_id,
        confirm_id=payment["id"],
    )


# ---------------------------------------------------------------------- #
# Yordamchilar
# ---------------------------------------------------------------------- #


def _click_failed(error: str) -> bool:
    """Click o'z tomonida xato yubordimi.

    Raqam bo'lmagan qiymat kelsa `int()` yiqilib, webhook **500** qaytarardi.
    Click 500 ni «javob yo'q» deb hisoblab so'rovni takrorlayveradi, biz esa
    sababni ko'rmasdik. Endi noaniq qiymat «xato emas» deb o'qiladi va
    keyingi tekshiruvlar ishlaydi.
    """
    try:
        return int(error) < 0
    except (TypeError, ValueError):
        log.warning("Click `error` maydoni raqam emas: %r", error)
        return False


def _amount_matches(incoming: str, expected: Decimal) -> bool:
    try:
        value = Decimal(str(incoming))
    except (TypeError, ArithmeticError):
        return False
    return abs(value - expected) <= AMOUNT_TOLERANCE


async def _load_payment(merchant_trans_id: str) -> dict[str, object] | None:
    """`merchant_trans_id` — bizning `payments.id`."""
    try:
        payment_id = int(merchant_trans_id)
    except (TypeError, ValueError):
        return None

    async with session_scope() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            return None
        return {
            "id": payment.id,
            "amount": Decimal(payment.amount),
            "status": payment.status,
            "plan": payment.plan,
        }


async def _remember_click_trans(payment_id: int, click_trans_id: str) -> None:
    async with session_scope() as session:
        payment = await session.get(Payment, payment_id)
        if payment is not None:
            payment.external_id = click_trans_id


async def pending_payment_owner(payment_id: int) -> tuple[int, Plan] | None:
    """To'lov egasining Telegram ID si va tarifi — xabar yuborish uchun."""
    async with session_scope() as session:
        row = await session.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        payment = row.scalar_one_or_none()
        if payment is None:
            return None
    telegram_id = await billing.user_telegram_id(payment_id)
    return (telegram_id, payment.plan) if telegram_id else None
