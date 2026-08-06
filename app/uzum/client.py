"""Uzum klient interfeysi va skeleti.

MUHIM: bu yerda UYDIRMA endpoint YO'Q. Aniq manzillar `docs/api-inventory.md`
(Phase 0) to'lgach ulanadi. Hozircha:

  - `AbstractUzumClient` — kerakli metodlar shartnomasi (interfeys). Sync
    servisi va testlar shu interfeysga tayanadi, real implementatsiyaga emas.
  - `UzumCabinetClient` — "Xodim" mexanizmi (kabinet sessiyasi) orqali
    ishlaydigan skeleton. Metodlar hozircha `NotImplementedError` beradi.
  - `FakeUzumClient` (tests uchun) alohida `tests/` da bo'ladi — interfeysни
    to'ldirib, audit mantiqini Uzumsiz sinash uchun.

Barcha metodlar FAQAT o'qiydi (GET). Yozish metodi umuman yo'q (SPEC 9.1).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.uzum.base import UzumHTTP
from app.uzum.models import DateRange, PageParams, RawRecord, SessionCredentials

_NOT_READY = (
    "Endpoint hali noma'lum — avval docs/api-inventory.md ni to'ldiring "
    "(SPEC 3.2 qattiq qoidasi)."
)


class AbstractUzumClient(ABC):
    """Uzumdan ma'lumot o'qish shartnomasi.

    Har bir metod bitta do'kon (`shop_id`) doirasida ishlaydi — do'konlar
    o'rtasida qat'iy izolyatsiya (SPEC 9.4). Ro'yxat qaytaruvchi metodlar
    sahifalashni ichkarida to'liq aylanib, hamma yozuvni yig'ib beradi.
    """

    # --- Do'konlar ---
    @abstractmethod
    async def get_shops(self) -> list[RawRecord]:
        """Sessiyaga ulangan (Xodim sifatida kirilgan) do'konlar ro'yxati."""

    # --- Katalog ---
    @abstractmethod
    async def get_products(
        self, shop_id: str, page: PageParams | None = None
    ) -> list[RawRecord]:
        """Do'kon mahsulotlari: sku, barcode, nom, kategoriya, o'lcham, og'irlik."""

    # --- Buyurtmalar / qaytarishlar ---
    @abstractmethod
    async def get_orders(
        self, shop_id: str, period: DateRange, page: PageParams | None = None
    ) -> list[RawRecord]:
        """Davr bo'yicha buyurtmalar: sku, qty, narx, status, komissiya, sana."""

    @abstractmethod
    async def get_returns(
        self, shop_id: str, period: DateRange, page: PageParams | None = None
    ) -> list[RawRecord]:
        """Qaytarishlar: order_id, sku, qty, sabab, status, qabul sanasi."""

    # --- Ombor ---
    @abstractmethod
    async def get_stock_snapshot(self, shop_id: str) -> list[RawRecord]:
        """HOZIRGI qoldiq (SKU × ombor). Tarixni Uzum bermaydi — biz saqlaymiz."""

    @abstractmethod
    async def get_stock_movements(
        self, shop_id: str, period: DateRange, page: PageParams | None = None
    ) -> list[RawRecord]:
        """Ombor harakati: type(in|sale|return|writeoff), qty, sana."""

    # --- Moliya ---
    @abstractmethod
    async def get_finance_ops(
        self, shop_id: str, period: DateRange, page: PageParams | None = None
    ) -> list[RawRecord]:
        """Moliyaviy operatsiyalar: type, amount, tavsif, sana."""

    @abstractmethod
    async def get_compensations(
        self, shop_id: str, period: DateRange, page: PageParams | None = None
    ) -> list[RawRecord]:
        """Uzum to'lagan kompensatsiyalar: sku, qty, amount, status, sana."""


class UzumCabinetClient(AbstractUzumClient):
    """Kabinet sessiyasi ("Xodim" mexanizmi) orqali ishlaydigan klient.

    `credentials.secret` — Fernet bilan DB dan ochilgan cookie/token. Har
    so'rovda `UzumHTTP.get()` ga uzatiladi. Aniq manzillar va sahifalash
    mantig'i Phase 0 inventarizatsiyasidan keyin shu yerga qo'shiladi.
    """

    def __init__(self, http: UzumHTTP, credentials: SessionCredentials) -> None:
        self._http = http
        self._creds = credentials

    async def get_shops(self) -> list[RawRecord]:
        raise NotImplementedError(_NOT_READY)

    async def get_products(
        self, shop_id: str, page: PageParams | None = None
    ) -> list[RawRecord]:
        raise NotImplementedError(_NOT_READY)

    async def get_orders(
        self, shop_id: str, period: DateRange, page: PageParams | None = None
    ) -> list[RawRecord]:
        raise NotImplementedError(_NOT_READY)

    async def get_returns(
        self, shop_id: str, period: DateRange, page: PageParams | None = None
    ) -> list[RawRecord]:
        raise NotImplementedError(_NOT_READY)

    async def get_stock_snapshot(self, shop_id: str) -> list[RawRecord]:
        raise NotImplementedError(_NOT_READY)

    async def get_stock_movements(
        self, shop_id: str, period: DateRange, page: PageParams | None = None
    ) -> list[RawRecord]:
        raise NotImplementedError(_NOT_READY)

    async def get_finance_ops(
        self, shop_id: str, period: DateRange, page: PageParams | None = None
    ) -> list[RawRecord]:
        raise NotImplementedError(_NOT_READY)

    async def get_compensations(
        self, shop_id: str, period: DateRange, page: PageParams | None = None
    ) -> list[RawRecord]:
        raise NotImplementedError(_NOT_READY)
