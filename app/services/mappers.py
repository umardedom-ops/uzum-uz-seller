"""Uzum JSON → bizning modellar.

Maydon nomlari rasmiy OpenAPI sxemasidan olingan (docs/api-inventory.md §5-bis).
Sinov do'koni bo'sh bo'lgani uchun jonli javob ko'rilmadi — shuning uchun
mapperlar **himoyalangan**: yo'q maydon `None` beradi, yiqilmaydi.

Muhim: Uzum vaqtni **millisekundda** beradi, pulni butun son sifatida.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.db.models import MovementType

RawRecord = dict[str, Any]


def ms_to_dt(value: Any) -> datetime | None:
    """Unix epoch millisekundni datetime'ga aylantiradi."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def iso_to_dt(value: Any) -> datetime | None:
    """ISO satrni datetime'ga aylantiradi (`dateCreated` shu ko'rinishda)."""
    if not value:
        return None
    if isinstance(value, int | float):
        return ms_to_dt(value)
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def money(value: Any) -> Decimal | None:
    """Pulni Decimal'ga aylantiradi (float orqali o'tkazmaymiz)."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return None


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


# ---------------------------------------------------------------------- #
# Mahsulotlar
# ---------------------------------------------------------------------- #


def map_products(raw: RawRecord) -> list[dict[str, Any]]:
    """Bitta mahsulot → SKU qatorlari (bir mahsulotda bir nechta SKU bo'ladi).

    Bu endpoint mahsulotning to'liq holatini beradi (docs/api-inventory.md
    §5-ter): FBO qoldiq, jami sotilgan/qaytgan, o'lchamlar, blok holati.
    Shu tufayli kabinet sessiyasi kerak emas.

    ⚠️ Shtrix kod — aynan `barcode` maydoni. `skuFullTitle` boshqa narsa
    (tarkibiy nom); uni shtrix kod deb ishlatish da'voni buzadi.
    """
    commission = raw.get("commissionDto") or {}
    pct = commission.get("maxCommission") or commission.get("minCommission")

    rows: list[dict[str, Any]] = []
    for sku in raw.get("skuList") or []:
        sku_id = as_str(sku.get("skuId"))
        if not sku_id:
            continue

        dim = sku.get("skuDimension") or {}
        status = sku.get("status") or {}
        block_reasons = sku.get("blockReasons") or []

        rows.append(
            {
                "sku": sku_id,
                "barcode": as_str(sku.get("barcode")),
                "title": as_str(sku.get("productTitle")) or as_str(raw.get("title")),
                "category": as_str(raw.get("category")),
                "size": as_str(sku.get("skuTitle")),
                "weight": money(dim.get("weight")),
                "commission_pct": money(sku.get("commission")) or money(pct),
                "sale_price": money(sku.get("price")),
                # Uzum hisoblagan jami — to'plangan audit uchun
                "qty_sold_total": _opt_int(sku.get("quantitySold")),
                "qty_returned_total": _opt_int(sku.get("quantityReturned")),
                "qty_created_total": _opt_int(sku.get("quantityCreated")),
                "qty_missing": _opt_int(sku.get("quantityMissing")),
                "qty_defected": _opt_int(sku.get("quantityDefected")),
                "qty_archived": _opt_int(sku.get("quantityArchived")),
                # O'lchamlar — 5.4 logistika auditi
                "length_mm": _opt_int(dim.get("length")),
                "width_mm": _opt_int(dim.get("width")),
                "height_mm": _opt_int(dim.get("height")),
                "dimensional_group": as_str(sku.get("dimensionalGroup")),
                "actual_dimensional_group": _dim_group(
                    sku.get("actualDimensionalGroup")
                ),
                # Holat — blok alerti
                "is_blocked": bool(sku.get("blocked")),
                "block_reason": as_str(sku.get("blockingReason"))
                or (as_str(block_reasons[0]) if block_reasons else None),
                "status": as_str(status.get("value")),
                "avg_daily_sales": money(sku.get("avgdsales")),
                # Qidiruvdagi o'rin — Avtobidder o'rniga xavfsiz signal
                "rank": as_str((sku.get("rankInfo") or {}).get("rank")),
                "returned_pct": money(sku.get("returnedPercentage")),
                "paid_storage_amount": money(sku.get("paidStorageAmount")),
            }
        )
    return rows


def _dim_group(value: Any) -> str | None:
    """Габарит guruhi satr yoki obyekt sifatida kelishi mumkin."""
    if value is None:
        return None
    if isinstance(value, dict):
        return as_str(value.get("title") or value.get("name") or value.get("value"))
    return as_str(value)


def _opt_int(value: Any) -> int | None:
    """`0` ni `None` dan ajratadi — 0 haqiqiy qiymat."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def map_product_stock(raw: RawRecord) -> list[dict[str, Any]]:
    """Mahsulot javobidan qoldiq suratlari (FBO va FBS alohida).

    `quantityActive` — Uzum omboridagi (FBO) qoldiq. Kabinetdagi
    «FBO qoldiqlar, dona» ustuni bilan bir xil.
    `quantityFbs` — sellerning o'z omboridagi (FBS) qoldiq.
    """
    rows: list[dict[str, Any]] = []
    for sku in raw.get("skuList") or []:
        sku_id = as_str(sku.get("skuId"))
        if not sku_id:
            continue

        fbo = _opt_int(sku.get("quantityActive"))
        if fbo is not None:
            rows.append({"sku": sku_id, "qty": fbo, "warehouse": "FBO"})

        fbs = _opt_int(sku.get("quantityFbs"))
        if fbs is not None:
            rows.append({"sku": sku_id, "qty": fbs, "warehouse": "FBS"})
    return rows


# ---------------------------------------------------------------------- #
# Buyurtmalar
# ---------------------------------------------------------------------- #

# Bekor qilingan buyurtmalar sotuv hisoblanmaydi (5.1 formulasida `sotilgan`)
CANCELLED_STATUSES = {"CANCELED", "CANCELLED"}


def map_order(raw: RawRecord) -> dict[str, Any] | None:
    """`SellerOrderItemDto` → `orders` qatori.

    ⚠️ Buyurtmada `skuId` yo'q — faqat `productId` va `skuTitle`.
    Vaqtincha kalit sifatida `productId` ishlatiladi, SKU ga bog'lash
    haqiqiy ma'lumotda aniqlanadi (docs/api-inventory.md §5-bis).
    """
    order_id = as_str(raw.get("orderId")) or as_str(raw.get("id"))
    sku = as_str(raw.get("productId"))
    if not order_id or not sku:
        return None

    return {
        "uzum_order_id": order_id,
        "sku": sku,
        "qty": as_int(raw.get("amount")),
        "price": money(raw.get("sellerPrice")),
        "status": as_str(raw.get("status")),
        "commission_amount": money(raw.get("commission")),
        "delivery_amount": money(raw.get("logisticDeliveryFee")),
        # Uzum hisoblagan foyda va tannarx — yunit-iqtisodiyot uchun
        "seller_profit": money(raw.get("sellerProfit")),
        "purchase_price": money(raw.get("purchasePrice")),
        "withdrawn_profit": money(raw.get("withdrawnProfit")),
        "return_cause": as_str(raw.get("returnCause")),
        "qty_returned": _opt_int(raw.get("amountReturns")),
        "created_at_uzum": ms_to_dt(raw.get("date")),
        "closed_at": ms_to_dt(raw.get("dateIssued")),
    }


def sold_qty(order_row: dict[str, Any]) -> int:
    """5.1 uchun: bekor qilingan buyurtma sotilgan hisoblanmaydi."""
    if (order_row.get("status") or "").upper() in CANCELLED_STATUSES:
        return 0
    return order_row.get("qty", 0)


# ---------------------------------------------------------------------- #
# Qaytarishlar
# ---------------------------------------------------------------------- #

# Qaytarish omborga qabul qilinganini bildiruvchi statuslar
RECEIVED_STATUSES = {"COMPLETED", "ACCEPTED", "FINISHED"}


def map_returns(raw: RawRecord) -> list[dict[str, Any]]:
    """`SellerReturnDto` → `returns` qatorlari (har SKU uchun bitta)."""
    return_id = as_str(raw.get("id"))
    if not return_id:
        return []

    status = as_str(raw.get("status"))
    is_received = (status or "").upper() in RECEIVED_STATUSES
    # Omborga tushgan sana: yakunlangan bo'lsa `completedDate`
    received_at = iso_to_dt(raw.get("completedDate")) if is_received else None

    rows: list[dict[str, Any]] = []
    for item in raw.get("returnItems") or []:
        sku = as_str(item.get("skuId"))
        if not sku:
            continue
        rows.append(
            {
                "uzum_return_id": return_id,
                "order_id": as_str(raw.get("externalNumber")),
                "sku": sku,
                # `packedAmount` — haqiqatda qabul qilingan miqdor
                "qty": as_int(item.get("amount")),
                "reason": as_str(raw.get("type")),
                "status": status,
                "returned_at": iso_to_dt(raw.get("dateCreated")),
                "received_at": received_at,
            }
        )
    return rows


# ---------------------------------------------------------------------- #
# Qoldiq (FBS)
# ---------------------------------------------------------------------- #


def map_stock(raw: RawRecord) -> dict[str, Any] | None:
    """`SkuAmountApiResponseDto` → `stock_snapshots` qatori."""
    sku = as_str(raw.get("skuId"))
    if not sku:
        return None
    return {
        "sku": sku,
        "qty": as_int(raw.get("amount")),
        "warehouse": "FBS",  # API faqat FBS beradi
        "barcode": as_str(raw.get("barcode")),
    }


# ---------------------------------------------------------------------- #
# Yuk xatlari (FBO qabul)
# ---------------------------------------------------------------------- #


def map_invoice_products(invoice_id: str, raw: RawRecord) -> list[dict[str, Any]]:
    """Yuk xati tarkibi → SKU kesimida omborga QABUL QILINGAN miqdor.

    Muhim farq (2026-08-07 da haqiqiy do'konda aniqlangan):
      * `quantityToStock`  — yuborilgan/rejalashtirilgan miqdor
      * `quantityAccepted` — ombor **haqiqatda qabul qilgan** miqdor

    5.1 formulasidagi «qabul» — aynan `quantityAccepted`. Rejani hisobga
    olsak, yetib bormagan yuk xati «yo'qolgan tovar» bo'lib ko'rinadi.

    `purchasePrice` — tannarx, zarar summasini hisoblash uchun.
    """
    rows: list[dict[str, Any]] = []
    for sku in raw.get("skuForInvoiceDtoList") or []:
        sku_id = as_str(sku.get("id"))
        if not sku_id:
            continue
        rows.append(
            {
                "external_id": f"{invoice_id}:{sku_id}",
                "sku": sku_id,
                "type": MovementType.IN,
                "qty": as_int(sku.get("quantityAccepted")),
                "purchase_price": money(sku.get("purchasePrice")),
            }
        )
    return rows


def map_invoice_movement(raw: RawRecord) -> dict[str, Any] | None:
    """`InvoiceInList` → `stock_movements` (tur: IN).

    Yuk xati darajasidagi umumiy miqdor. SKU bo'yicha taqsimlash uchun
    `/v1/shop/{id}/invoice/products` alohida so'raladi.
    """
    invoice_id = as_str(raw.get("id"))
    if not invoice_id:
        return None
    return {
        "external_id": invoice_id,
        "type": MovementType.IN,
        "qty": as_int(raw.get("totalAccepted")),
        "happened_at": iso_to_dt(raw.get("dateAccepted"))
        or iso_to_dt(raw.get("dateCreated")),
    }


# ---------------------------------------------------------------------- #
# Moliya
# ---------------------------------------------------------------------- #

# Kompensatsiyani ajratish uchun kalit so'zlar (5.5).
# ⚠️ Haqiqiy ma'lumotda tekshirilishi kerak — gipoteza.
COMPENSATION_HINTS = ("compens", "компенс", "возмещ")


def map_finance_op(raw: RawRecord) -> dict[str, Any] | None:
    """`SellerPaymentDto` → `finance_ops` qatori."""
    external_id = as_str(raw.get("externalId")) or as_str(raw.get("id"))
    if not external_id:
        return None
    return {
        "external_id": external_id,
        "type": as_str(raw.get("type")),
        "source": as_str(raw.get("source")),
        "amount": money(raw.get("amount")) or money(raw.get("paymentPrice")),
        "description": as_str(raw.get("name")),
        "happened_at": iso_to_dt(raw.get("dateService"))
        or iso_to_dt(raw.get("dateCreated")),
    }


def is_compensation(row: dict[str, Any]) -> bool:
    """Moliyaviy operatsiya kompensatsiyami (5.5 uchun)."""
    haystack = " ".join(
        str(row.get(k) or "") for k in ("type", "source", "description")
    ).lower()
    return any(hint in haystack for hint in COMPENSATION_HINTS)
