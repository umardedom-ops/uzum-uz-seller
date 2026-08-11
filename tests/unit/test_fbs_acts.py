"""FBS aktlari — o'lik ficha tiriltirildi.

Kod aktni yuklay olardi, lekin botda unga yo'l yo'q edi: FBS ekranida
faqat yorliq tugmalari bor edi. Endi «📑 Aktlar» tugmasi bor.
"""
from __future__ import annotations

from app.bot.handlers.fbs import _orders_kb
from app.bot.texts import t
from app.services.fbs import INVOICE_STATUSES, FbsOrder, _map_invoice


def _order(oid: int) -> FbsOrder:
    return FbsOrder(
        order_id=oid, status="CREATED", scheme="FBS",
        created_at=None, items_count=1, title="X",
    )


class TestStatuses:
    def test_only_verified_statuses(self) -> None:
        """2026-08-11 da jonli aniqlangan — boshqasi Uzumda 400 beradi."""
        assert INVOICE_STATUSES == ("CREATED", "ACCEPTED", "CANCELLED")

    def test_cancelled_double_l(self) -> None:
        """Buyurtmada bitta L, aktda ikkita — adashtirmaslik uchun test."""
        assert "CANCELLED" in INVOICE_STATUSES
        assert "CANCELED" not in INVOICE_STATUSES


class TestActsButton:
    def test_button_present_even_with_one_order(self) -> None:
        labels = {
            b.text for row in _orders_kb([_order(1)], "uz").inline_keyboard for b in row
        }
        assert t("btn_acts", "uz") in labels

    def test_callback_is_wired(self) -> None:
        buttons = [
            b
            for row in _orders_kb([_order(1)], "uz").inline_keyboard
            for b in row
            if b.text == t("btn_acts", "uz")
        ]
        assert buttons and buttons[0].callback_data == "fbs:invoices"


class TestInvoiceMapping:
    def test_maps_fields(self) -> None:
        inv = _map_invoice(
            {"id": 55, "invoiceNumber": "INV-9", "status": "ACCEPTED"}
        )
        assert inv.invoice_id == 55
        assert inv.number == "INV-9"
        assert "INV-9" in inv.label

    def test_falls_back_to_alternate_names(self) -> None:
        inv = _map_invoice({"invoiceId": 77, "invoiceStatus": "CREATED"})
        assert inv.invoice_id == 77
        assert inv.status == "CREATED"

    def test_empty_raw_does_not_crash(self) -> None:
        inv = _map_invoice({})
        assert inv.invoice_id == 0
