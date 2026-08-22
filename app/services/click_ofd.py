"""Click fiskalizatsiyasi — soliq cheki (OFD).

Click rasman ogohlantiradi: chek fiskalizatsiyasi **majburiy**. To'lov
o'tgani chek degani emas — chek alohida yuboriladi:

    POST https://api.click.uz/v2/merchant/payment/ofd_data/submit_items
    Auth: merchant_user_id:sha1(timestamp + secret_key):timestamp

⚠️ **Bu Shop API emas, Merchant API.** Autentifikatsiya butunlay boshqa:
Shop API — MD5 imzo (Click bizga keladi), Merchant API — SHA1 `Auth`
sarlavhasi (biz Click'ga boramiz). Chalkashtirmang.

Uchta talab, har biri buzilsa chek **rad etiladi**:

1. **`CommissionInfo` majburiy** — har pozitsiya ichida `TIN` (yuridik
   shaxs, 9 raqam) yoki `PINFL` (YaTT, 14 raqam). Ko'p qo'llanmada bu
   maydon tushib qolgan va chek hech qachon ro'yxatdan o'tmaydi.
2. **Narxlar tiyinda** — so'mni 100 ga ko'paytiring.
3. **Yig'indi aniq teng** — pozitsiyalar `Price` yig'indisi
   `received_card` ga tiyin-ba-tiyin teng bo'lishi shart.

Sozlama to'liq bo'lmasa chek yuborilmaydi, lekin **xato jim yutilmaydi**:
`OfdResult.reason` aniq sababni aytadi va log'ga yoziladi. Bu loyihada
jim yutilgan xato bir necha bo'limni o'lik qilgan.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

API_BASE = "https://api.click.uz/v2/merchant"
SUBMIT_URL = f"{API_BASE}/payment/ofd_data/submit_items"
TIMEOUT = httpx.Timeout(20.0)

# Bir so'm = 100 tiyin. OFD hamma narxni tiyinda kutadi.
TIYIN = 100


@dataclass(frozen=True, slots=True)
class OfdResult:
    """Fiskalizatsiya natijasi.

    `ok=False` bo'lganda `reason` **har doim** to'ldiriladi — chaqiruvchi
    sababni ko'rsata olsin.
    """

    ok: bool
    reason: str = ""
    qr_url: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


def auth_header(settings: Settings, *, timestamp: int | None = None) -> str:
    """`merchant_user_id:sha1(timestamp + secret_key):timestamp`.

    ⚠️ `secret_key` — Shop API dagi bilan bir xil kalit, lekin bu yerda
    MD5 emas, **SHA1** ishlatiladi va u imzo emas, sarlavha.
    """
    ts = int(time.time()) if timestamp is None else timestamp
    digest = hashlib.sha1(  # noqa: S324 — Click talabi
        f"{ts}{settings.click_secret_key}".encode()
    ).hexdigest()
    return f"{settings.click_merchant_user_id}:{digest}:{ts}"


def commission_info(settings: Settings) -> dict[str, str] | None:
    """Soliq identifikatori — YaTT uchun `PINFL`, tashkilot uchun `TIN`.

    Ikkalasi ham bo'sh bo'lsa `None` qaytadi va chek yuborilmaydi:
    busiz Click har bir chekni rad etadi, ya'ni yuborishning ma'nosi yo'q.
    """
    if settings.click_ofd_pinfl:
        return {"PINFL": settings.click_ofd_pinfl}
    if settings.click_ofd_tin:
        return {"TIN": settings.click_ofd_tin}
    return None


def vat_amount(total_tiyin: int, vat_percent: int) -> int:
    """Narx **ichidagi** QQS — ustiga qo'shilmaydi.

    `VAT = total * p / (100 + p)`. Skill'dagi `total * 12 / 112` shu
    formulaning 12% uchun ko'rinishi.

    QQS to'lovchisi bo'lmasangiz (soddalashtirilgan tartibdagi YaTT)
    `vat_percent=0` — u holda QQS ham 0.
    """
    if vat_percent <= 0:
        return 0
    return round(total_tiyin * vat_percent / (100 + vat_percent))


def build_items(
    settings: Settings,
    *,
    name: str,
    amount_soum: int,
    quantity: int = 1,
) -> list[dict[str, Any]]:
    """Chek pozitsiyalari.

    Obuna — bitta pozitsiya, shuning uchun `Price` butun summaga teng va
    yig'indi tengligi o'z-o'zidan bajariladi. Funksiya baribir ro'yxat
    qaytaradi: keyin bir nechta pozitsiya kerak bo'lsa shakl o'zgarmaydi.

    ⚠️ `Amount` — **miqdor** (dona), narx emas. Birinchi jonli chekda
    Click javobi bilan tasdiqlang.
    """
    price_tiyin = amount_soum * TIYIN
    vat = vat_amount(price_tiyin, settings.click_ofd_vat_percent)

    return [
        {
            "Name": name,
            "SPIC": settings.click_ofd_spic,
            "PackageCode": settings.click_ofd_package_code,
            "Price": price_tiyin,
            "Amount": quantity,
            "VAT": vat,
            "VATPercent": settings.click_ofd_vat_percent,
            "CommissionInfo": commission_info(settings),
        }
    ]


def check_ready(settings: Settings) -> str:
    """Sozlama to'liqmi. To'liq bo'lsa bo'sh satr, aks holda **sabab**.

    Sabab aniq bo'lishi kerak: qaysi kalit yo'q. «Fiskalizatsiya
    ishlamadi» degan xabar bilan hech kim muammoni topa olmaydi.
    """
    missing = []
    if not settings.click_merchant_user_id:
        missing.append("CLICK_MERCHANT_USER_ID")
    if not settings.click_secret_key:
        missing.append("CLICK_SECRET_KEY")
    if not settings.click_service_id:
        missing.append("CLICK_SERVICE_ID")
    if not settings.click_ofd_spic:
        missing.append("CLICK_OFD_SPIC (IKPU, tasnif.soliq.uz)")
    if not settings.click_ofd_package_code:
        missing.append("CLICK_OFD_PACKAGE_CODE")
    if commission_info(settings) is None:
        missing.append("CLICK_OFD_PINFL (YaTT) yoki CLICK_OFD_TIN (tashkilot)")

    if missing:
        return "Sozlama to'liq emas: " + ", ".join(missing)
    return ""


def totals_match(items: list[dict[str, Any]], received_tiyin: int) -> bool:
    """Pozitsiyalar yig'indisi to'langan summaga **aniq** teng bo'lsinmi.

    Bitta tiyin farq qilsa ham Click chekni rad etadi — shuning uchun
    yuborishdan oldin o'zimiz tekshiramiz va sababni aytamiz.
    """
    return sum(int(item["Price"]) for item in items) == received_tiyin


async def submit_receipt(
    *,
    payment_id: int,
    amount_soum: int,
    name: str,
    client: httpx.AsyncClient | None = None,
) -> OfdResult:
    """Chekni Click'ga yuboradi.

    To'lov javobiga **ta'sir qilmaydi**: chek yuborilmasa ham Click'ga
    «muvaffaqiyat» qaytadi, aks holda Click to'lovni xato deb hisoblaydi
    va pul qaytib ketadi. Sabab esa log'da qoladi.
    """
    settings = get_settings()

    reason = check_ready(settings)
    if reason:
        log.error("OFD chek yuborilmadi (payment_id=%s): %s", payment_id, reason)
        return OfdResult(ok=False, reason=reason)

    items = build_items(settings, name=name, amount_soum=amount_soum)
    received_tiyin = amount_soum * TIYIN

    if not totals_match(items, received_tiyin):
        total = sum(int(i["Price"]) for i in items)
        reason = (
            f"Yig'indi mos emas: pozitsiyalar={total} tiyin, "
            f"to'langan={received_tiyin} tiyin"
        )
        log.error("OFD chek yuborilmadi (payment_id=%s): %s", payment_id, reason)
        return OfdResult(ok=False, reason=reason)

    body = {
        "service_id": int(settings.click_service_id),
        "payment_id": payment_id,
        "items": items,
        "received_ecash": 0,
        "received_cash": 0,
        "received_card": received_tiyin,
    }

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT)
    try:
        resp = await client.post(
            SUBMIT_URL,
            json=body,
            headers={
                "Auth": auth_header(settings),
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        data = resp.json() if resp.content else {}
    except (httpx.HTTPError, ValueError) as exc:
        reason = f"Click'ga ulanib bo'lmadi: {exc!r}"
        log.error("OFD chek yuborilmadi (payment_id=%s): %s", payment_id, reason)
        return OfdResult(ok=False, reason=reason)
    finally:
        if owns_client:
            await client.aclose()

    # Click xatoni HTTP kodida emas, javob ichida qaytaradi
    error_code = data.get("error_code", data.get("error"))
    if error_code not in (0, "0", None):
        reason = f"Click rad etdi: error={error_code} note={data.get('error_note')!r}"
        log.error("OFD chek rad etildi (payment_id=%s): %s", payment_id, reason)
        return OfdResult(ok=False, reason=reason, payload=data)

    log.info("OFD chek yaratildi: payment_id=%s", payment_id)
    return OfdResult(ok=True, payload=data)


async def receipt_qr(
    payment_id: int, *, client: httpx.AsyncClient | None = None
) -> str:
    """Chekning soliq QR havolasi. Topilmasa bo'sh satr.

    Bu haqiqiy soliq cheki (`ofd.soliq.uz`) — mijozga ko'rsatsa bo'ladi.
    """
    settings = get_settings()
    if check_ready(settings):
        return ""

    url = f"{API_BASE}/payment/ofd_data/{settings.click_service_id}/{payment_id}"

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT)
    try:
        resp = await client.get(
            url,
            headers={"Auth": auth_header(settings), "Accept": "application/json"},
        )
        data = resp.json() if resp.content else {}
    except (httpx.HTTPError, ValueError) as exc:
        log.error("OFD QR olinmadi (payment_id=%s): %r", payment_id, exc)
        return ""
    finally:
        if owns_client:
            await client.aclose()

    return str(data.get("qrCodeURL") or "")
