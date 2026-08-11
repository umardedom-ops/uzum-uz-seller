"""Uzumga YOZISH klienti — audit yo'lidan qat'iy ajratilgan.

Bu modul `app/uzum/api_client.py` (o'qish) dan alohida turadi va uni
audit/sync kodi **import qilmaydi**. Shunda "audit faqat GET" kafolati
kodda ko'rinib turadi (CLAUDE.md qoida #1).

Himoya: **enable-flag** (`settings.uzum_writes_enabled`, standart O'CHIQ).
Yoqilmasa `WritesDisabledError` ko'tariladi — servis buni ushlab, demo
rejimda davom etadi (foydalanuvchiga "hali jonli emas" deb aytiladi).

✅ **So'rov tanasi tasdiqlangan** (2026-08-11, OpenAPI spetsifikatsiyasidan —
`docs/api-inventory.md` §5-quinquies):

```json
{ "skuAmountList": [ { "barcode": "...", "amount": 10 } ] }
```

⚠️ Identifikator — **`barcode`**, `skuId` EMAS. `skuId` ixtiyoriy, `barcode`
majburiy. Ilgari bu yerda taxminiy `{"skus": [{"skuId": ...}]}` turgan edi —
u ishlamasdi (`validation-failed-001`).
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


class MissingBarcodeError(ValueError):
    """Shtrix kodsiz yozib bo'lmaydi.

    Uzum yangilashni aynan `barcode` bo'yicha qiladi. Shtrix kod bo'lmasa
    so'rov jimgina rad etiladi — shuning uchun oldindan to'xtatamiz.
    """


@dataclass(frozen=True, slots=True)
class StockUpdate:
    """Bitta SKU uchun yangi FBS qoldig'i (mutlaq qiymat, farq emas).

    `barcode` — Uzum talab qiladigan majburiy identifikator.
    `sku_id` faqat jurnal va xabarlar uchun (API'da ixtiyoriy).
    """

    barcode: str
    amount: int
    sku_id: str = ""

    def __post_init__(self) -> None:
        if not self.barcode:
            raise MissingBarcodeError(
                f"SKU {self.sku_id or '?'}: shtrix kod yo'q, yozib bo'lmaydi"
            )
        if self.amount < 0:
            raise ValueError("Qoldiq manfiy bo'la olmaydi")


def _build_stock_payload(updates: list[StockUpdate]) -> dict:
    """Spetsifikatsiyadagi `SkuStockUpdateApiRequestDto`.

    Tasdiqlangan (2026-08-11): `skuAmountList` ichida `barcode` + `amount`.
    """
    return {
        "skuAmountList": [
            {"barcode": u.barcode, "amount": u.amount} for u in updates
        ]
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
