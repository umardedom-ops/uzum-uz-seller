"""Rasmiy Uzum Seller API klienti — ASOSIY manba.

Barcha endpointlar Phase 0 da jonli sinalgan (docs/api-inventory.md).
Faqat GET (SPEC 9.1).

Auth: header `Authorization: <token>` — **Bearer prefiksisiz**.
Sanalar: unix epoch **millisekundda**.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

from app.core.logging import get_logger
from app.uzum.base import UzumHTTP
from app.uzum.client import AbstractUzumClient
from app.uzum.models import DateRange, PageParams, RawRecord, SessionCredentials

log = get_logger(__name__)

DEFAULT_PAGE_SIZE = 100
MAX_PAGES = 500  # cheksiz aylanishdan himoya


def to_ms(d: date, *, end_of_day: bool = False) -> int:
    """Sanani unix epoch millisekundga aylantiradi (API shuni kutadi)."""
    t = time.max if end_of_day else time.min
    return int(datetime.combine(d, t, tzinfo=UTC).timestamp() * 1000)


def extract_items(payload: Any, *keys: str) -> list[RawRecord]:
    """Turli javob konvertlaridan yozuvlar ro'yxatini ajratadi.

    Uzum javoblari bir xil emas:
      - `[...]`                              → /v1/shops, /v1/shop/{id}/invoice
      - `{"productList": [...]}`             → /v1/product/shop/{id}
      - `{"orderItems": [...]}`              → /v1/finance/orders
      - `{"payload": [...]}`                 → /v1/shop/{id}/return
      - `{"payload": {"payments": [...]}}`   → /v1/finance/expenses
      - `{"payload": {"skuAmountList": []}}` → /v3/fbs/sku/stocks
    """
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    # `payload` konverti bo'lsa ichkariga tushamiz
    inner = payload.get("payload", payload)
    if isinstance(inner, list):
        return inner
    if not isinstance(inner, dict):
        return []

    for key in keys:
        value = inner.get(key)
        if isinstance(value, list):
            return value

    # Kalit topilmasa — birinchi ro'yxat maydonini olamiz
    for value in inner.values():
        if isinstance(value, list):
            return value
    return []


class UzumApiClient(AbstractUzumClient):
    """Seller API orqali o'qish. Bitta seller kaliti = bitta klient."""

    def __init__(self, http: UzumHTTP, credentials: SessionCredentials) -> None:
        self._http = http
        self._token = credentials.secret

    # ------------------------------------------------------------------ #
    # Ichki yordamchilar
    # ------------------------------------------------------------------ #

    @property
    def _headers(self) -> dict[str, str]:
        # Bearer YO'Q — spec shunday talab qiladi
        return {"Authorization": self._token}

    async def _get(
        self, path: str, *, rate_key: str, params: dict[str, Any] | None = None
    ) -> Any:
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        return await self._http.get(
            path, rate_key=rate_key, params=clean, headers=self._headers
        )

    async def _get_all_pages(
        self,
        path: str,
        *,
        rate_key: str,
        keys: tuple[str, ...],
        params: dict[str, Any] | None = None,
        page: PageParams | None = None,
    ) -> list[RawRecord]:
        """Sahifalarni oxirigacha aylanib, hamma yozuvni yig'adi.

        `page` berilsa — faqat o'sha bitta sahifa qaytadi (nozik nazorat uchun).
        """
        size = page.limit if page else DEFAULT_PAGE_SIZE
        start = (page.offset // size) if (page and size) else 0

        items: list[RawRecord] = []
        for page_no in range(start, start + (1 if page else MAX_PAGES)):
            data = await self._get(
                path, rate_key=rate_key, params={**(params or {}), "page": page_no, "size": size}
            )
            batch = extract_items(data, *keys)
            items.extend(batch)

            if page or len(batch) < size:
                break
        else:
            log.warning("MAX_PAGES limitiga yetildi: %s (rate_key=%s)", path, rate_key)

        return items

    # ------------------------------------------------------------------ #
    # Do'konlar
    # ------------------------------------------------------------------ #

    async def get_shops(self) -> list[RawRecord]:
        """GET /v1/shops — `[{"id": 125841, "name": "..."}]`

        Do'kon ID shu yerdan keladi — sellerdan so'rash shart emas.
        """
        data = await self._get("/v1/shops", rate_key="shops")
        return extract_items(data, "shops")

    # ------------------------------------------------------------------ #
    # Katalog
    # ------------------------------------------------------------------ #

    async def get_products(
        self, shop_id: str, page: PageParams | None = None
    ) -> list[RawRecord]:
        """GET /v1/product/shop/{shopId}

        Javobda `commissionDto` bor — 5.3 komissiya auditi uchun foiz
        qo'lda kiritilmaydi. `skuList[].skuFullTitle` — shtrix kod.
        """
        return await self._get_all_pages(
            f"/v1/product/shop/{shop_id}",
            rate_key=shop_id,
            keys=("productList",),
            page=page,
        )

    # ------------------------------------------------------------------ #
    # Buyurtmalar / qaytarishlar
    # ------------------------------------------------------------------ #

    async def get_orders(
        self, shop_id: str, period: DateRange, page: PageParams | None = None
    ) -> list[RawRecord]:
        """GET /v1/finance/orders — sotuvlar (5.1 dagi `sotilgan`)."""
        return await self._get_all_pages(
            "/v1/finance/orders",
            rate_key=shop_id,
            keys=("orderItems",),
            params={
                "shopIds": shop_id,
                "dateFrom": to_ms(period.date_from),
                "dateTo": to_ms(period.date_to, end_of_day=True),
            },
            page=page,
        )

    async def get_returns(
        self, shop_id: str, period: DateRange, page: PageParams | None = None
    ) -> list[RawRecord]:
        """GET /v1/shop/{shopId}/return — qaytarish yuk xatlari.

        Diqqat: endpoint sana filtrini QO'LLAB-QUVVATLAMAYDI. Hammasi
        olinadi, davr bo'yicha filtr bizning tomonda (services) bo'ladi.
        """
        return await self._get_all_pages(
            f"/v1/shop/{shop_id}/return",
            rate_key=shop_id,
            keys=("returns", "sellerReturns"),
            page=page,
        )

    # ------------------------------------------------------------------ #
    # Ombor
    # ------------------------------------------------------------------ #

    async def get_stock_snapshot(self, shop_id: str) -> list[RawRecord]:
        """GET /v3/fbs/sku/stocks — ⚠️ FAQAT FBS qoldig'i.

        FBO ombor qoldig'i API'da YO'Q (docs/api-inventory.md §3).
        FBO uchun kabinet klienti ishlatiladi.
        """
        return await self._get_all_pages(
            "/v3/fbs/sku/stocks",
            rate_key=shop_id,
            keys=("skuAmountList",),
        )

    async def get_stock_movements(
        self, shop_id: str, period: DateRange, page: PageParams | None = None
    ) -> list[RawRecord]:
        """Ombor harakati API'da yo'q.

        Eng yaqin manba — FBO yuk xatlari (omborga qabul):
        `GET /v1/shop/{shopId}/invoice`. To'liq harakat (hisobdan chiqarish
        va h.k.) uchun kabinet kerak.
        """
        return await self.get_supply_invoices(shop_id, page=page)

    async def get_supply_invoices(
        self, shop_id: str, page: PageParams | None = None
    ) -> list[RawRecord]:
        """GET /v1/shop/{shopId}/invoice — FBO yuk xatlari (5.1 dagi `qabul`)."""
        return await self._get_all_pages(
            f"/v1/shop/{shop_id}/invoice",
            rate_key=shop_id,
            keys=("invoices",),
            page=page,
        )

    async def get_invoice_products(self, shop_id: str, invoice_id: int) -> list[RawRecord]:
        """GET /v1/shop/{shopId}/invoice/products — yuk xati tarkibi."""
        data = await self._get(
            f"/v1/shop/{shop_id}/invoice/products",
            rate_key=shop_id,
            params={"invoiceId": invoice_id},
        )
        return extract_items(data, "products", "skuList")

    # ------------------------------------------------------------------ #
    # Moliya
    # ------------------------------------------------------------------ #

    async def get_finance_ops(
        self, shop_id: str, period: DateRange, page: PageParams | None = None
    ) -> list[RawRecord]:
        """GET /v1/finance/expenses — xarajatlar (komissiya, logistika...)."""
        return await self._get_all_pages(
            "/v1/finance/expenses",
            rate_key=shop_id,
            keys=("payments",),
            params={
                "shopIds": shop_id,
                "dateFrom": to_ms(period.date_from),
                "dateTo": to_ms(period.date_to, end_of_day=True),
            },
            page=page,
        )

    # ------------------------------------------------------------------ #
    # FBS/DBS operatsion bo'lim (yorliq, akt)
    # ------------------------------------------------------------------ #

    async def get_fbs_orders(
        self,
        shop_id: str,
        *,
        status: str | None = None,
        scheme: str | None = None,
        period: DateRange | None = None,
        page: PageParams | None = None,
    ) -> list[RawRecord]:
        """GET /v2/fbs/orders — yig'ish kerak bo'lgan buyurtmalar.

        `status`: CREATED | PACKING | PENDING_DELIVERY | DELIVERING |
                  DELIVERED | COMPLETED | CANCELED | RETURNED ...
        `scheme`: FBS | DBS
        """
        params: dict[str, Any] = {"shopIds": shop_id, "status": status, "scheme": scheme}
        if period is not None:
            params["dateFrom"] = to_ms(period.date_from)
            params["dateTo"] = to_ms(period.date_to, end_of_day=True)

        return await self._get_all_pages(
            "/v2/fbs/orders",
            rate_key=shop_id,
            keys=("orders", "sellerOrders", "content"),
            params=params,
            page=page,
        )

    async def get_fbs_orders_count(
        self, shop_id: str, *, status: str | None = None
    ) -> Any:
        """GET /v2/fbs/orders/count — buyurtmalar soni (tez tekshiruv)."""
        return await self._get(
            "/v2/fbs/orders/count",
            rate_key=shop_id,
            params={"shopIds": shop_id, "status": status},
        )

    async def get_order_label(
        self, shop_id: str, order_id: int, size: str = "LARGE"
    ) -> tuple[bytes, str]:
        """GET /v1/fbs/order/{orderId}/labels/print — buyurtma yorlig'i.

        `size`: LARGE yoki BIG. Binary (PDF) qaytadi.
        """
        return await self._http.get_bytes(
            f"/v1/fbs/order/{order_id}/labels/print",
            rate_key=shop_id,
            params={"size": size},
            headers=self._headers,
        )

    async def get_invoice_document(
        self, shop_id: str, invoice_id: int
    ) -> tuple[bytes, str]:
        """GET /v1/fbs/invoice/{invoiceId}/print — ta'minlash akti."""
        return await self._http.get_bytes(
            f"/v1/fbs/invoice/{invoice_id}/print",
            rate_key=shop_id,
            headers=self._headers,
        )

    async def get_closing_documents(
        self, shop_id: str, invoice_id: int
    ) -> tuple[bytes, str]:
        """GET /v1/fbs/invoice/{invoiceId}/closing-documents — qabul akti."""
        return await self._http.get_bytes(
            f"/v1/fbs/invoice/{invoice_id}/closing-documents",
            rate_key=shop_id,
            headers=self._headers,
        )

    async def get_fbs_invoices(
        self, shop_id: str, statuses: list[str], page: PageParams | None = None
    ) -> list[RawRecord]:
        """GET /v1/fbs/invoice — FBS yuk xatlari (`statuses` majburiy)."""
        return await self._get_all_pages(
            "/v1/fbs/invoice",
            rate_key=shop_id,
            keys=("invoices", "content"),
            params={"statuses": ",".join(statuses)},
            page=page,
        )

    async def get_barcode_types(self, shop_id: str) -> list[RawRecord]:
        """GET /v1/product/barcodes/types — yorliq o'lchamlari ma'lumotnomasi."""
        data = await self._get("/v1/product/barcodes/types", rate_key=shop_id)
        return extract_items(data, "types", "barcodeTypes")

    # ------------------------------------------------------------------ #

    async def get_compensations(
        self, shop_id: str, period: DateRange, page: PageParams | None = None
    ) -> list[RawRecord]:
        """Alohida kompensatsiya endpointi API'da yo'q.

        Gipoteza: kompensatsiyalar `finance/expenses` ichida `sources`
        bo'yicha ajraladi. Haqiqiy ma'lumotli do'konda tekshirilishi kerak —
        hozircha xom xarajatlar qaytadi, filtr keyin qo'shiladi.
        """
        return await self.get_finance_ops(shop_id, period, page=page)
