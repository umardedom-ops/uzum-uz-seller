"""«Barcha yorliqlar bitta PDF» — birlashtirish mantig'i."""
from __future__ import annotations

import io

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app.services.fbs import _merge_pdfs


def _one_page_pdf(text: str) -> bytes:
    """Bitta sahifali soxta yorliq (reportlab)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 700, text)
    c.showPage()
    c.save()
    return buf.getvalue()


class TestMergeLabels:
    def test_merges_pages(self) -> None:
        merged = _merge_pdfs([_one_page_pdf("A"), _one_page_pdf("B")])
        assert merged is not None
        assert len(PdfReader(io.BytesIO(merged)).pages) == 2

    def test_empty_returns_none(self) -> None:
        assert _merge_pdfs([]) is None

    def test_skips_broken_part(self) -> None:
        """Buzuq bo'lak o'tkazib yuboriladi, sog'lomi qoladi."""
        merged = _merge_pdfs([b"not a pdf", _one_page_pdf("C")])
        assert merged is not None
        assert len(PdfReader(io.BytesIO(merged)).pages) == 1

    def test_all_broken_returns_none(self) -> None:
        assert _merge_pdfs([b"xxx", b"yyy"]) is None


class TestAllLabelsButton:
    def test_button_shown_only_for_multiple(self) -> None:
        """Bitta buyurtmada «hammasi» tugmasi keraksiz — faqat 2+ da."""
        from app.bot.handlers.fbs import _orders_kb
        from app.bot.texts import t
        from app.services.fbs import FbsOrder

        def order(oid: int) -> FbsOrder:
            return FbsOrder(
                order_id=oid,
                status="CREATED",
                scheme="FBS",
                created_at=None,
                items_count=1,
                title="X",
            )

        one = {
            b.text for row in _orders_kb([order(1)], "uz").inline_keyboard for b in row
        }
        many = {
            b.text
            for row in _orders_kb([order(1), order(2)], "uz").inline_keyboard
            for b in row
        }
        label = t("btn_all_labels", "uz", count=2)
        assert label not in one
        assert label in many
