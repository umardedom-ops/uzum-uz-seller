"""Sinxronizatsiya servisi (SPEC Phase 3).

Uzumdan ma'lumot tortib, bazaga idempotent yozadi. Har yugurish
`sync_runs` ga yoziladi — xato jim yutilmaydi (SPEC 9.6).

Ish taqsimoti:
  * `sync_fast`  — soatiga bir marta: buyurtma, qaytarish, moliya
  * `sync_daily` — kuniga bir marta: qoldiq surati, mahsulot katalogi
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import session_scope
from app.db.models import AuthType, Shop, ShopCredential, SyncStatus
from app.db.repositories import sync as repo
from app.services import mappers as m
from app.uzum.api_client import UzumApiClient
from app.uzum.base import UzumHTTP
from app.uzum.models import AuthType as ClientAuthType
from app.uzum.models import DateRange, SessionCredentials

log = get_logger(__name__)

# Keyingi yugurishlarda — o'zgargan yozuvlarni ushlash uchun ustma-ust davr
INCREMENTAL_DAYS = 7


def _build_client(secret: str) -> tuple[UzumHTTP, UzumApiClient]:
    settings = get_settings()
    http = UzumHTTP(
        settings.uzum_api_base, rate_limit_per_sec=settings.uzum_rate_limit_per_sec
    )
    client = UzumApiClient(
        http, SessionCredentials(auth_type=ClientAuthType.API, secret=secret)
    )
    return http, client


async def _api_secret(shop_id: int) -> str | None:
    """Do'konning API kalitini ochib beradi (yo'q bo'lsa None)."""
    async with session_scope() as session:
        cred = await session.scalar(
            select(ShopCredential).where(
                ShopCredential.shop_id == shop_id,
                ShopCredential.auth_type == AuthType.API,
                ShopCredential.is_valid.is_(True),
            )
        )
        return cred.secret if cred else None


async def sync_shop(shop_id: int, *, full: bool = False) -> int:
    """Bitta do'konni sinxronlaydi. Yozilgan yozuvlar sonini qaytaradi.

    `full=True` — birinchi ulanish, {INITIAL_HISTORY_DAYS} kunlik tarix.
    """
    secret = await _api_secret(shop_id)
    if secret is None:
        log.warning("Do'kon %s uchun API kalit yo'q — sync o'tkazib yuborildi", shop_id)
        return 0

    async with session_scope() as session:
        shop = await session.get(Shop, shop_id)
        if shop is None or not shop.is_active:
            return 0
        uzum_shop_id = shop.uzum_shop_id
        is_first = shop.first_sync_at is None

    # Birinchi ulanishda API bergan tarixni imkon qadar chuqur tortamiz:
    # buyurtma/qaytarish/moliya tarixi bor, qoldiqniki yo'q.
    days = (
        get_settings().initial_history_days
        if (full or is_first)
        else INCREMENTAL_DAYS
    )
    today = date.today()
    period = DateRange(today - timedelta(days=days), today)

    http, client = _build_client(secret)
    kind = "full" if (full or is_first) else "incremental"
    total = 0

    async with session_scope() as session:
        run = await repo.start_run(session, shop_id, kind)
        run_id = run.id

    try:
        total += await _sync_products(shop_id, uzum_shop_id, client)
        total += await _sync_orders(shop_id, uzum_shop_id, client, period)
        total += await _sync_returns(shop_id, uzum_shop_id, client, period)
        total += await _sync_finance(shop_id, uzum_shop_id, client, period)
        total += await _sync_stocks(shop_id, uzum_shop_id, client)
        total += await _sync_invoices(shop_id, uzum_shop_id, client)
    except Exception as exc:
        # SPEC 9.6: xato jim yutilmaydi — jurnalga yoziladi va yuqoriga
        # uzatiladi (planlovchi adminga xabar beradi).
        log.exception("Sync xatosi: shop_id=%s", shop_id)
        async with session_scope() as session:
            run = await session.get(type(run), run_id)
            await repo.finish_run(
                session, run, status=SyncStatus.FAILED, error=f"{type(exc).__name__}: {exc}"
            )
        raise
    finally:
        await http.aclose()

    async with session_scope() as session:
        run = await session.get(type(run), run_id)
        await repo.finish_run(session, run, status=SyncStatus.SUCCESS, records=total)

        shop = await session.get(Shop, shop_id)
        if shop and shop.first_sync_at is None:
            from app.db.base import utcnow

            shop.first_sync_at = utcnow()

    log.info("Sync tugadi: shop_id=%s turi=%s yozuvlar=%s", shop_id, kind, total)
    return total


# ---------------------------------------------------------------------- #
# Bo'limlar
# ---------------------------------------------------------------------- #


async def _sync_products(shop_id: int, uzum_shop_id: str, client: UzumApiClient) -> int:
    """Mahsulot katalogi + qoldiq surati.

    Bitta so'rov ikkalasini ham beradi: mahsulot javobida FBO
    (`quantityActive`) va FBS (`quantityFbs`) qoldiqlari bor. Shu sabab
    ombor qoldig'i uchun kabinet sessiyasi kerak emas.
    """
    raw = await client.get_products(uzum_shop_id)
    products = [row for item in raw for row in m.map_products(item)]
    stocks = [row for item in raw for row in m.map_product_stock(item)]

    async with session_scope() as session:
        count = await repo.upsert_products(session, shop_id, products)
        await repo.upsert_stock_snapshot(session, shop_id, stocks)
    return count


async def _sync_orders(
    shop_id: int, uzum_shop_id: str, client: UzumApiClient, period: DateRange
) -> int:
    raw = await client.get_orders(uzum_shop_id, period)
    rows = [r for r in (m.map_order(item) for item in raw) if r]
    async with session_scope() as session:
        return await repo.upsert_orders(session, shop_id, rows)


async def _sync_returns(
    shop_id: int, uzum_shop_id: str, client: UzumApiClient, period: DateRange
) -> int:
    raw = await client.get_returns(uzum_shop_id, period)
    rows = [row for item in raw for row in m.map_returns(item)]
    async with session_scope() as session:
        return await repo.upsert_returns(session, shop_id, rows)


async def _sync_finance(
    shop_id: int, uzum_shop_id: str, client: UzumApiClient, period: DateRange
) -> int:
    raw = await client.get_finance_ops(uzum_shop_id, period)
    rows = [r for r in (m.map_finance_op(item) for item in raw) if r]

    # Kompensatsiyalar alohida jadvalga ham tushadi (5.5 sverkasi uchun)
    comps = [r for r in rows if m.is_compensation(r)]

    async with session_scope() as session:
        count = await repo.upsert_finance_ops(session, shop_id, rows)
        if comps:
            await repo.upsert_compensations(session, shop_id, comps)
    return count


async def _sync_stocks(shop_id: int, uzum_shop_id: str, client: UzumApiClient) -> int:
    """FBS qoldig'ining alohida manbasi (`/v3/fbs/sku/stocks`).

    Asosiy qoldiq mahsulot endpointidan keladi (`_sync_products`). Bu
    endpoint FBS uchun qo'shimcha tasdiq beradi va shtrix kodni ham
    qaytaradi — nomuvofiqlik bo'lsa shu yerdan ko'rinadi.
    """
    raw = await client.get_stock_snapshot(uzum_shop_id)
    rows = [r for r in (m.map_stock(item) for item in raw) if r]
    async with session_scope() as session:
        return await repo.upsert_stock_snapshot(session, shop_id, rows)


async def _sync_invoices(shop_id: int, uzum_shop_id: str, client: UzumApiClient) -> int:
    """FBO yuk xatlari → SKU kesimida omborga qabul (5.1 dagi `qabul`).

    Yuk xati ro'yxati faqat umumiy miqdorni beradi. SKU bo'yicha taqsimot
    va tannarx uchun har bir yuk xatining tarkibi alohida so'raladi.
    """
    invoices = await client.get_supply_invoices(uzum_shop_id)
    if not invoices:
        return 0

    movements: list[dict[str, object]] = []
    costs: dict[str, object] = {}

    for item in invoices:
        invoice_id = m.as_str(item.get("id"))
        if not invoice_id:
            continue
        try:
            products = await client.get_invoice_products(uzum_shop_id, int(invoice_id))
        except Exception:
            # Bitta yuk xati o'qilmasa qolganlari to'xtamasin
            log.warning("Yuk xati tarkibi olinmadi: shop=%s invoice=%s", shop_id, invoice_id)
            continue

        for product in products:
            for row in m.map_invoice_products(invoice_id, product):
                price = row.pop("purchase_price", None)
                if price is not None:
                    costs.setdefault(row["sku"], price)
                movements.append(row)

    async with session_scope() as session:
        count = await repo.upsert_movements(session, shop_id, movements)
        if costs:
            await repo.fill_cost_prices(session, shop_id, costs)
    return count


# ---------------------------------------------------------------------- #
# Ko'p do'kon
# ---------------------------------------------------------------------- #


async def sync_all_shops(*, full: bool = False) -> dict[int, int]:
    """Barcha faol do'konlarni navbat bilan sinxronlaydi.

    Bittasi yiqilsa qolganlari davom etadi — bitta mijozning muammosi
    hammani to'xtatmasin.
    """
    async with session_scope() as session:
        shop_ids = list(
            await session.scalars(select(Shop.id).where(Shop.is_active.is_(True)))
        )

    results: dict[int, int] = {}
    for shop_id in shop_ids:
        try:
            results[shop_id] = await sync_shop(shop_id, full=full)
        except Exception:
            results[shop_id] = -1  # xato jurnalga yozilgan
    return results
