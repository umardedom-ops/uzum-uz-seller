"""`extract_items` va `to_ms` testlari.

Uzum javob konvertlari bir xil emas — har endpoint boshqacha o'raydi.
Bu funksiya xato qilsa, sync jim ravishda bo'sh ma'lumot yig'adi, va
audit "yo'qotish yo'q" deb aytadi. Shuning uchun aniq test kerak.
"""
from __future__ import annotations

from datetime import date

from app.uzum.api_client import extract_items, to_ms


class TestExtractItems:
    def test_bare_list(self) -> None:
        """/v1/shops va /v1/shop/{id}/invoice — yalang'och ro'yxat."""
        assert extract_items([{"id": 1}], "shops") == [{"id": 1}]

    def test_named_key(self) -> None:
        """/v1/product/shop/{id} — {"productList": [...]}"""
        raw = {"productList": [{"productId": 7}], "totalElements": 1}
        assert extract_items(raw, "productList") == [{"productId": 7}]

    def test_order_items(self) -> None:
        """/v1/finance/orders — {"orderItems": [...]}"""
        raw = {"orderItems": [{"id": 3}], "totalElements": 1}
        assert extract_items(raw, "orderItems") == [{"id": 3}]

    def test_payload_list(self) -> None:
        """/v1/shop/{id}/return — {"payload": [...]}"""
        raw = {"payload": [{"returnId": 5}], "timestamp": "..."}
        assert extract_items(raw, "returns") == [{"returnId": 5}]

    def test_payload_nested_key(self) -> None:
        """/v1/finance/expenses — {"payload": {"payments": [...]}}"""
        raw = {"payload": {"payments": [{"amount": 100}], "totalElements": 1}}
        assert extract_items(raw, "payments") == [{"amount": 100}]

    def test_payload_sku_amount_list(self) -> None:
        """/v3/fbs/sku/stocks — {"payload": {"skuAmountList": [...]}}"""
        raw = {"payload": {"skuAmountList": [{"skuId": 9}]}}
        assert extract_items(raw, "skuAmountList") == [{"skuId": 9}]

    def test_fallback_to_first_list(self) -> None:
        """Kalit topilmasa — birinchi ro'yxat maydoni olinadi."""
        raw = {"payload": {"unknownName": [{"x": 1}], "totalElements": 1}}
        assert extract_items(raw, "expectedKey") == [{"x": 1}]

    def test_empty_responses(self) -> None:
        """Bo'sh do'kon — hamma variant bo'sh ro'yxat berishi kerak."""
        assert extract_items([], "any") == []
        assert extract_items({"orderItems": [], "totalElements": 0}, "orderItems") == []
        assert extract_items({"payload": {"payments": []}}, "payments") == []
        assert extract_items({"payload": []}, "any") == []

    def test_garbage_input(self) -> None:
        """Kutilmagan javob bo'lsa ham yiqilmasin."""
        assert extract_items(None, "any") == []
        assert extract_items("xato", "any") == []
        assert extract_items({"totalElements": 0}, "any") == []


class TestToMs:
    def test_returns_milliseconds(self) -> None:
        """Uzum sekund emas, MILLISEKUND kutadi."""
        ms = to_ms(date(2026, 1, 1))
        assert ms == 1767225600000
        assert len(str(ms)) == 13

    def test_end_of_day_is_later(self) -> None:
        d = date(2026, 1, 1)
        assert to_ms(d, end_of_day=True) > to_ms(d)

    def test_end_of_day_same_date(self) -> None:
        """Kun oxiri keyingi kunga o'tib ketmasin."""
        d = date(2026, 1, 1)
        delta = to_ms(d, end_of_day=True) - to_ms(d)
        assert delta < 24 * 3600 * 1000
