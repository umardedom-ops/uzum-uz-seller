"""FBS/DBS operatsion yordam (raqobatchining 8-xizmati).

Seller uchun qiymat: yorliq va aktlarni kabinetga kirmasdan, botdan
bitta tugma bilan olish. Ular buni "soatlab vaqtingizni tejaydi" deb
sotadi — bizda ham bo'ladi, va faqat GET orqali.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import session_scope
from app.db.models import AuthType, Shop, ShopCredential
from app.services.mappers import as_int, as_str, ms_to_dt
from app.uzum.api_client import UzumApiClient
from app.uzum.base import UzumHTTP
from app.uzum.models import AuthType as ClientAuthType
from app.uzum.models import DateRange, SessionCredentials

log = get_logger(__name__)

# Yig'ish kutilayotgan buyurtmalar — sellerga aynan shular kerak
PENDING_STATUSES = ("CREATED", "PACKING", "PENDING_DELIVERY")

LABEL_SIZES = ("LARGE", "BIG")


@dataclass(frozen=True, slots=True)
class FbsOrder:
    order_id: int
    status: str | None
    scheme: str | None
    created_at: str | None
    items_count: int
    title: str | None

    @property
    def label(self) -> str:
        parts = [f"№{self.order_id}"]
        if self.title:
            parts.append(self.title[:40])
        if self.items_count:
            parts.append(f"{self.items_count} dona")
        return " · ".join(parts)


async def _client_for(shop_id: int) -> tuple[UzumHTTP, UzumApiClient, str] | None:
    """Do'kon uchun klient quradi (kalit bazadan, shifri ochiladi)."""
    async with session_scope() as session:
        shop = await session.get(Shop, shop_id)
        if shop is None or not shop.is_active:
            return None
        cred = await session.scalar(
            select(ShopCredential).where(
                ShopCredential.shop_id == shop_id,
                ShopCredential.auth_type == AuthType.API,
                ShopCredential.is_valid.is_(True),
            )
        )
        if cred is None:
            return None
        secret = cred.secret
        uzum_shop_id = shop.uzum_shop_id

    settings = get_settings()
    http = UzumHTTP(
        settings.uzum_api_base, rate_limit_per_sec=settings.uzum_rate_limit_per_sec
    )
    client = UzumApiClient(
        http, SessionCredentials(auth_type=ClientAuthType.API, secret=secret)
    )
    return http, client, uzum_shop_id


class FbsUnavailableError(RuntimeError):
    """Uzum FBS ma'lumotini bermadi.

    ❗ "Buyurtma yo'q" va "so'rov yiqildi" — ikki boshqa narsa. Ilgari
    ikkalasi ham bo'sh ro'yxat qaytarardi va seller yig'ilishi kerak
    buyurtmalarni ko'rmay qolardi, xato esa faqat logda turardi
    (2026-08-09 da aynan shunday bo'lgan: sahifa hajmi 100 edi, Uzum
    esa FBS'da 50 dan ko'pini qabul qilmaydi).
    """


async def list_pending_orders(shop_id: int, days: int = 14) -> list[FbsOrder]:
    """Yig'ilishi kerak bo'lgan FBS/DBS buyurtmalar.

    Uzum javob bermasa `FbsUnavailableError` ko'tariladi — chaqiruvchi
    "buyurtma yo'q" deb ko'rsatmasligi uchun.
    """
    built = await _client_for(shop_id)
    if built is None:
        return []
    http, client, uzum_shop_id = built

    today = date.today()
    period = DateRange(today - timedelta(days=days), today)
    orders: list[FbsOrder] = []

    try:
        for status in PENDING_STATUSES:
            raw = await client.get_fbs_orders(
                uzum_shop_id, status=status, period=period
            )
            orders.extend(_map_order(item) for item in raw)
    except Exception as exc:
        log.exception("FBS buyurtmalarni olishda xato: shop_id=%s", shop_id)
        raise FbsUnavailableError(str(exc)) from exc
    finally:
        await http.aclose()

    # Dublikatlarni olib tashlaymiz (status bo'yicha ustma-ust kelishi mumkin)
    unique = {order.order_id: order for order in orders}
    return sorted(unique.values(), key=lambda o: o.order_id, reverse=True)


def _map_order(raw: dict) -> FbsOrder:
    items = raw.get("items") or raw.get("orderItems") or []
    first = items[0] if items else {}
    created = raw.get("dateCreated") or raw.get("date")
    moment = ms_to_dt(created) if isinstance(created, int | float) else None

    return FbsOrder(
        order_id=as_int(raw.get("id") or raw.get("orderId")),
        status=as_str(raw.get("status")),
        scheme=as_str(raw.get("scheme")),
        created_at=f"{moment:%d.%m.%Y %H:%M}" if moment else as_str(created),
        items_count=len(items) or as_int(raw.get("amount")),
        title=as_str(first.get("productTitle")) or as_str(raw.get("productTitle")),
    )


async def download_label(
    shop_id: int, order_id: int, size: str = "LARGE", out_dir: Path | None = None
) -> Path | None:
    """Buyurtma yorlig'ini yuklab, faylga yozadi.

    Uzum PDF qaytaradi; boshqa format kelsa kengaytma javobdan olinadi.
    """
    if size not in LABEL_SIZES:
        size = "LARGE"

    built = await _client_for(shop_id)
    if built is None:
        return None
    http, client, uzum_shop_id = built

    try:
        content, content_type = await client.get_order_label(
            uzum_shop_id, order_id, size=size
        )
    except Exception:
        log.exception("Yorliq yuklanmadi: shop_id=%s order=%s", shop_id, order_id)
        return None
    finally:
        await http.aclose()

    if not content:
        return None

    directory = out_dir or Path("generated")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"yorliq-{order_id}{_extension(content_type)}"
    path.write_bytes(content)
    return path


async def download_invoice_document(
    shop_id: int, invoice_id: int, *, closing: bool = False, out_dir: Path | None = None
) -> Path | None:
    """Ta'minlash akti (`closing=False`) yoki qabul akti (`closing=True`)."""
    built = await _client_for(shop_id)
    if built is None:
        return None
    http, client, uzum_shop_id = built

    try:
        if closing:
            content, content_type = await client.get_closing_documents(
                uzum_shop_id, invoice_id
            )
        else:
            content, content_type = await client.get_invoice_document(
                uzum_shop_id, invoice_id
            )
    except Exception:
        log.exception("Akt yuklanmadi: shop_id=%s invoice=%s", shop_id, invoice_id)
        return None
    finally:
        await http.aclose()

    if not content:
        return None

    directory = out_dir or Path("generated")
    directory.mkdir(parents=True, exist_ok=True)
    name = "qabul-akti" if closing else "taminlash-akti"
    path = directory / f"{name}-{invoice_id}{_extension(content_type)}"
    path.write_bytes(content)
    return path


def _merge_pdfs(parts: list[bytes]) -> bytes | None:
    """Bir nechta PDF baytini bitta PDF ga birlashtiradi.

    Buzuq bo'lak o'tkazib yuboriladi (jim yutmaymiz — logga yozamiz).
    Hech bo'lak qo'shilmasa None qaytadi.
    """
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    added = 0
    for part in parts:
        try:
            reader = PdfReader(io.BytesIO(part))
            for page in reader.pages:
                writer.add_page(page)
            added += 1
        except Exception:
            log.exception("Yorliq PDF birlashtirishda buzuq bo'lak o'tkazildi")

    if added == 0:
        return None

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


async def download_all_labels(
    shop_id: int, days: int = 14, out_dir: Path | None = None
) -> Path | None:
    """Yig'ilishi kerak barcha buyurtma yorlig'ini BITTA PDF ga yig'adi.

    Raqobatchining "bitta tugma bilan" fichasi — faqat GET (yorliqlar
    tayyor, biz yaratmaymiz, faqat olamiz va birlashtiramiz).

    Buyurtma yo'q bo'lsa None. Uzum yorliq bermasa o'sha buyurtma
    o'tkazib yuboriladi; hech biri kelmasa None.
    """
    orders = await list_pending_orders(shop_id, days=days)
    if not orders:
        return None

    built = await _client_for(shop_id)
    if built is None:
        return None
    http, client, uzum_shop_id = built

    pdf_parts: list[bytes] = []
    try:
        for order in orders:
            try:
                content, content_type = await client.get_order_label(
                    uzum_shop_id, order.order_id
                )
            except Exception:
                log.exception(
                    "Yorliq yuklanmadi (o'tkazildi): shop=%s order=%s",
                    shop_id,
                    order.order_id,
                )
                continue
            if content and "pdf" in (content_type or "").lower():
                pdf_parts.append(content)

    finally:
        await http.aclose()

    merged = _merge_pdfs(pdf_parts)
    if merged is None:
        return None

    directory = out_dir or Path("generated")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"yorliqlar-{shop_id}.pdf"
    path.write_bytes(merged)
    return path


def _extension(content_type: str) -> str:
    """Javob turiga qarab fayl kengaytmasi."""
    lowered = (content_type or "").lower()
    if "pdf" in lowered:
        return ".pdf"
    if "zip" in lowered:
        return ".zip"
    if "png" in lowered:
        return ".png"
    if "jpeg" in lowered or "jpg" in lowered:
        return ".jpg"
    if "html" in lowered:
        return ".html"
    return ".pdf"  # Uzum odatda PDF beradi
