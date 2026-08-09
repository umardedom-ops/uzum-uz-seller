"""Uzumga YOZISH klienti — audit yo'lidan qat'iy ajratilgan.

Bu modul `app/uzum/api_client.py` (o'qish) dan alohida turadi va uni
audit/sync kodi **import qilmaydi**. Shunda "audit faqat GET" kafolati
kodda ko'rinib turadi (CLAUDE.md qoida #1).

Ikki qatlamli himoya:

1. **Enable-flag** (`settings.uzum_writes_enabled`, standart O'CHIQ). Yoqilmasa
   `WritesDisabledError` ko'tariladi — servis buni ushlab, demo rejimda
   davom etadi (foydalanuvchiga "hali jonli emas" deb aytiladi).
2. **Body tasdig'i.** `POST /v2/fbs/sku/stocks` so'rov TANASI hali
   Swagger'dan tasdiqlanmagan (docs/api-inventory.md §7 endpointni sanaydi,
   tanasini emas). `_build_stock_payload` dagi sxema — TAXMIN, javob
   sxemasi `SkuAmountApiResponseDto` (skuId, amount) asosida. Jonli
   yoqishdan oldin Swagger yoki bitta ehtiyot sinov bilan tekshiring.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings
from app.core.logging import get_logger
from app.uzum.base import UzumHTTP
from app.uzum.models import SessionCredentials

log = get_logger(__name__)


class WritesDisabledError(RuntimeError):
    """Yozish bayrog'i o'chiq — jonli POST yuborilmadi.

    Bu XATO emas, himoya. Servis buni ushlab demo rejimga o'tadi.
    """


@dataclass(frozen=True, slots=True)
class StockUpdate:
    """Bitta SKU uchun yangi FBS qoldig'i (mutlaq qiymat, farq emas)."""

    sku_id: str
    amount: int


def _build_stock_payload(updates: list[StockUpdate]) -> dict:
    """⚠️ TAXMINIY body. Swagger'dan tasdiqlang (writes.py yuqori izohi).

    Javob sxemasi `SkuAmountApiResponseDto` (skuId, amount) — so'rov ham
    shunga o'xshash bo'lishi kutiladi. Tasdiqlangач shu bitta funksiya
    to'g'rilanadi, qolgani o'zgarmaydi.
    """
    return {
        "skus": [{"skuId": u.sku_id, "amount": u.amount} for u in updates]
    }


class UzumWriteClient:
    """Seller API orqali yozish. Bitta seller kaliti = bitta klient."""

    def __init__(self, http: UzumHTTP, credentials: SessionCredentials) -> None:
        self._http = http
        self._token = credentials.secret

    @property
    def _headers(self) -> dict[str, str]:
        # Bearer YO'Q — o'qishdagi bilan bir xil (docs/api-inventory.md §1)
        return {"Authorization": self._token}

    async def set_fbs_stock(
        self, shop_id: str, updates: list[StockUpdate]
    ) -> object:
        """POST /v2/fbs/sku/stocks — FBS qoldig'ini yangilaydi.

        Bayroq o'chiq bo'lsa `WritesDisabledError` ko'taradi (jonli yozmaydi).
        Yoqilgan bo'lsa bitta POST yuboradi (retry yo'q — base.post izohi).
        """
        if not updates:
            return None

        settings = get_settings()
        if not settings.uzum_writes_enabled:
            log.info(
                "Qoldiq yozish DEMO: bayroq o'chiq, shop=%s, %s ta SKU",
                shop_id,
                len(updates),
            )
            raise WritesDisabledError(
                "UZUM_WRITES_ENABLED o'chiq — jonli yozish yuborilmadi"
            )

        payload = _build_stock_payload(updates)
        log.info("Qoldiq yozish JONLI: shop=%s, %s ta SKU", shop_id, len(updates))
        return await self._http.post(
            "/v2/fbs/sku/stocks",
            rate_key=shop_id,
            json=payload,
            headers=self._headers,
        )
