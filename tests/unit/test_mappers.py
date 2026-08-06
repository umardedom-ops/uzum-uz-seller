"""Mapper testlari.

Xavf: mapper xato maydon nomini o'qisa, sync **jim ravishda** bo'sh
ma'lumot yig'adi va audit "yo'qotish yo'q" deb aytadi. Mijoz pul
topmaydi va bizga ishonmaydi. Shuning uchun har maydon tekshiriladi.

Kirish namunalari rasmiy OpenAPI sxemasidan olingan.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.db.models import MovementType
from app.services.mappers import (
    is_compensation,
    iso_to_dt,
    map_finance_op,
    map_invoice_movement,
    map_order,
    map_product_stock,
    map_products,
    map_returns,
    map_stock,
    money,
    ms_to_dt,
    sold_qty,
)


class TestConverters:
    def test_ms_to_dt(self) -> None:
        """Uzum millisekundda beradi, sekundda emas."""
        result = ms_to_dt(1727427283895)
        assert result == datetime(2024, 9, 27, 8, 54, 43, 895000, tzinfo=UTC)

    def test_ms_to_dt_handles_garbage(self) -> None:
        assert ms_to_dt(None) is None
        assert ms_to_dt("salom") is None

    def test_iso_to_dt(self) -> None:
        result = iso_to_dt("2026-08-06T12:30:00Z")
        assert result is not None
        assert result.year == 2026 and result.hour == 12

    def test_iso_to_dt_naive_gets_utc(self) -> None:
        result = iso_to_dt("2026-08-06T12:30:00")
        assert result is not None and result.tzinfo is not None

    def test_money_is_decimal_not_float(self) -> None:
        """Float ishlatilsa da'voda tortishuv chiqadi."""
        result = money(250000)
        assert isinstance(result, Decimal)
        assert result == Decimal("250000")


def product_raw(**sku_overrides: object) -> dict:
    """Jonli API javobi shaklida namuna (Elore Parfume, 2026-08-06)."""
    sku = {
        "skuId": 11325839,
        "skuTitle": "100 ml",
        "skuFullTitle": "2620101-03303001001017001",
        "productTitle": "Elore Pure parfyum, 100 ml",
        "barcode": 1000113258397,
        "commission": 20.0,
        "price": 1500000,
        "quantityCreated": 100,
        "quantityActive": 40,
        "quantityFbs": 5,
        "quantitySold": 55,
        "quantityReturned": 3,
        "quantityMissing": 0,
        "quantityDefected": 1,
        "quantityArchived": 0,
        "blocked": False,
        "blockingReason": None,
        "blockReasons": [],
        "status": {"value": "RUN_OUT", "title": "Tugadi"},
        "skuDimension": {"length": 230, "width": 100, "height": 70, "weight": 250},
        "dimensionalGroup": "SMALL",
        "avgdsales": 1.5,
    }
    sku.update(sku_overrides)
    return {
        "productId": 3082631,
        "category": "Atirlar",
        "commissionDto": {"minCommission": 20.0, "maxCommission": 20.0},
        "skuList": [sku],
    }


class TestProducts:
    def test_barcode_is_the_barcode_field(self) -> None:
        """⚠️ `skuFullTitle` EMAS. Noto'g'ri kod bilan da'vo rad etiladi."""
        row = map_products(product_raw())[0]
        assert row["barcode"] == "1000113258397"
        assert row["barcode"] != "2620101-03303001001017001"

    def test_basic_fields(self) -> None:
        row = map_products(product_raw())[0]
        assert row["sku"] == "11325839"
        assert row["category"] == "Atirlar"
        assert row["commission_pct"] == Decimal("20.0")
        assert row["sale_price"] == Decimal("1500000")
        assert row["weight"] == Decimal("250")

    def test_cumulative_totals(self) -> None:
        """Uzum bergan jami raqamlar — to'plangan auditning asosi."""
        row = map_products(product_raw())[0]
        assert row["qty_created_total"] == 100
        assert row["qty_sold_total"] == 55
        assert row["qty_returned_total"] == 3
        assert row["qty_defected"] == 1

    def test_zero_is_kept_not_treated_as_missing(self) -> None:
        """0 haqiqiy qiymat — `None` ga aylanmasin."""
        row = map_products(product_raw(quantitySold=0))[0]
        assert row["qty_sold_total"] == 0

    def test_dimensions_for_logistics_audit(self) -> None:
        row = map_products(product_raw())[0]
        assert row["length_mm"] == 230
        assert row["width_mm"] == 100
        assert row["height_mm"] == 70
        assert row["dimensional_group"] == "SMALL"

    def test_block_status(self) -> None:
        row = map_products(product_raw(blocked=True, blockingReason="Sabab"))[0]
        assert row["is_blocked"] is True
        assert row["block_reason"] == "Sabab"

    def test_block_reason_from_list(self) -> None:
        """Sabab ro'yxatda kelsa ham olinsin."""
        row = map_products(product_raw(blockReasons=["Moderatsiya"]))[0]
        assert row["block_reason"] == "Moderatsiya"

    def test_not_blocked_by_default(self) -> None:
        row = map_products(product_raw())[0]
        assert row["is_blocked"] is False

    def test_status_value(self) -> None:
        row = map_products(product_raw())[0]
        assert row["status"] == "RUN_OUT"

    def test_multiple_skus_per_product(self) -> None:
        raw = {
            "productId": 1,
            "skuList": [{"skuId": 10, "barcode": 1}, {"skuId": 11, "barcode": 2}],
        }
        assert len(map_products(raw)) == 2

    def test_skips_sku_without_id(self) -> None:
        assert map_products({"productId": 1, "skuList": [{"barcode": 1}]}) == []

    def test_no_sku_list(self) -> None:
        assert map_products({"productId": 1}) == []

    def test_missing_optional_fields_do_not_crash(self) -> None:
        """Uzum maydonni bermasa ham yiqilmasin."""
        raw = {"productId": 1, "skuList": [{"skuId": 5}]}
        row = map_products(raw)[0]
        assert row["sku"] == "5"
        assert row["barcode"] is None
        assert row["length_mm"] is None


class TestProductStock:
    """FBO qoldiq mahsulot javobidan keladi — kabinet kerak emas."""

    def test_splits_fbo_and_fbs(self) -> None:
        rows = map_product_stock(product_raw())
        by_wh = {r["warehouse"]: r for r in rows}

        assert by_wh["FBO"]["qty"] == 40  # quantityActive
        assert by_wh["FBS"]["qty"] == 5   # quantityFbs
        assert by_wh["FBO"]["sku"] == "11325839"

    def test_zero_stock_is_recorded(self) -> None:
        """0 qoldiq ham yozilishi kerak — "tugadi" ham ma'lumot."""
        rows = map_product_stock(product_raw(quantityActive=0, quantityFbs=0))
        assert {r["qty"] for r in rows} == {0}
        assert len(rows) == 2

    def test_absent_field_is_skipped(self) -> None:
        raw = {"skuList": [{"skuId": 7, "quantityActive": 12}]}
        rows = map_product_stock(raw)
        assert len(rows) == 1
        assert rows[0]["warehouse"] == "FBO"

    def test_no_sku_id_skipped(self) -> None:
        assert map_product_stock({"skuList": [{"quantityActive": 5}]}) == []


class TestOrders:
    def _raw(self, **kwargs: object) -> dict:
        base = {
            "id": 999,
            "orderId": 555,
            "productId": 3082631,
            "amount": 3,
            "sellerPrice": 150000,
            "commission": 30000,
            "logisticDeliveryFee": 12000,
            "date": 1727427283895,
            "status": "TO_WITHDRAW",
        }
        base.update(kwargs)
        return base

    def test_maps_audit_critical_fields(self) -> None:
        """Komissiya va logistika — 5.3 va 5.4 auditlarining asosi."""
        row = map_order(self._raw())

        assert row is not None
        assert row["uzum_order_id"] == "555"
        assert row["qty"] == 3
        assert row["price"] == Decimal("150000")
        assert row["commission_amount"] == Decimal("30000")
        assert row["delivery_amount"] == Decimal("12000")
        assert row["created_at_uzum"] is not None

    def test_missing_order_id_is_skipped(self) -> None:
        assert map_order({"amount": 1}) is None

    def test_cancelled_order_not_counted_as_sold(self) -> None:
        """5.1 formulasida bekor qilingan buyurtma `sotilgan` emas."""
        row = map_order(self._raw(status="CANCELED"))
        assert row is not None
        assert sold_qty(row) == 0

    def test_active_order_counted_as_sold(self) -> None:
        row = map_order(self._raw(status="TO_WITHDRAW"))
        assert row is not None
        assert sold_qty(row) == 3


class TestReturns:
    def _raw(self, **kwargs: object) -> dict:
        base = {
            "id": 77,
            "dateCreated": "2026-07-01T10:00:00Z",
            "status": "PROCESSING",
            "type": "CLIENT_RETURN",
            "externalNumber": "ORD-1",
            "returnItems": [
                {"skuId": 11325839, "amount": 2, "packedAmount": 2}
            ],
        }
        base.update(kwargs)
        return base

    def test_not_received_leaves_received_at_empty(self) -> None:
        """5.2 auditining yuragi: omborga tushmagan qaytarish."""
        rows = map_returns(self._raw())

        assert len(rows) == 1
        assert rows[0]["sku"] == "11325839"
        assert rows[0]["qty"] == 2
        assert rows[0]["received_at"] is None
        assert rows[0]["returned_at"] is not None

    def test_completed_return_has_received_at(self) -> None:
        rows = map_returns(
            self._raw(status="COMPLETED", completedDate="2026-07-05T10:00:00Z")
        )
        assert rows[0]["received_at"] is not None

    def test_multiple_items(self) -> None:
        raw = self._raw(
            returnItems=[
                {"skuId": 1, "amount": 1},
                {"skuId": 2, "amount": 3},
            ]
        )
        assert len(map_returns(raw)) == 2

    def test_no_id_is_skipped(self) -> None:
        assert map_returns({"returnItems": [{"skuId": 1}]}) == []


class TestStock:
    def test_maps_fbs_stock(self) -> None:
        raw = {
            "skuId": 11325839,
            "barcode": "2620101-033",
            "amount": 42,
            "skuTitle": "100 ml",
        }
        row = map_stock(raw)

        assert row is not None
        assert row["sku"] == "11325839"
        assert row["qty"] == 42
        assert row["warehouse"] == "FBS"  # API faqat FBS beradi

    def test_no_sku_id(self) -> None:
        assert map_stock({"amount": 5}) is None


class TestInvoices:
    def test_maps_accepted_qty_as_incoming(self) -> None:
        """5.1 dagi `qabul` — yuk xatidagi `totalAccepted`."""
        raw = {
            "id": 3001,
            "totalAccepted": 50,
            "dateAccepted": "2026-07-10T08:00:00Z",
            "dateCreated": "2026-07-08T08:00:00Z",
        }
        row = map_invoice_movement(raw)

        assert row is not None
        assert row["type"] == MovementType.IN
        assert row["qty"] == 50
        assert row["happened_at"] is not None

    def test_falls_back_to_created_date(self) -> None:
        raw = {"id": 1, "totalAccepted": 5, "dateCreated": "2026-07-08T08:00:00Z"}
        row = map_invoice_movement(raw)
        assert row is not None and row["happened_at"] is not None


class TestFinance:
    def test_maps_payment(self) -> None:
        raw = {
            "id": 900,
            "externalId": "EXT-900",
            "type": "COMMISSION",
            "source": "ORDER",
            "amount": 30000,
            "name": "Komissiya",
            "dateService": "2026-07-15T00:00:00Z",
        }
        row = map_finance_op(raw)

        assert row is not None
        assert row["external_id"] == "EXT-900"
        assert row["amount"] == Decimal("30000")

    def test_falls_back_to_id(self) -> None:
        row = map_finance_op({"id": 5, "amount": 100})
        assert row is not None and row["external_id"] == "5"

    def test_compensation_detected_by_keyword(self) -> None:
        """5.5 uchun kompensatsiyalarni ajratish (gipoteza — tekshirilsin)."""
        assert is_compensation({"type": "COMPENSATION", "source": "", "description": ""})
        assert is_compensation({"type": "", "source": "", "description": "Компенсация"})

    def test_regular_payment_is_not_compensation(self) -> None:
        assert not is_compensation(
            {"type": "COMMISSION", "source": "ORDER", "description": "Komissiya"}
        )
