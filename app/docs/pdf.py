"""PDF hisobot generatori.

Excel — ishlash uchun (filtrlash, hisoblash). PDF — ko'rish va chop etish
uchun: telefonda ochiladi, buxgalterga yuboriladi, da'voga ilova qilinadi.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.docs.fonts import ensure_fonts
from app.docs.models import ReportRow
from app.docs.numbers import format_money

HEADER_BG = colors.HexColor("#1F3864")
WARN_BG = colors.HexColor("#FFF2CC")
GRID = colors.HexColor("#BFBFBF")


def _styles() -> dict[str, ParagraphStyle]:
    regular, bold = ensure_fonts()
    return {
        "title": ParagraphStyle(
            "title", fontName=bold, fontSize=15, spaceAfter=4, leading=19
        ),
        "sub": ParagraphStyle(
            "sub", fontName=regular, fontSize=9.5, textColor=colors.grey, spaceAfter=10
        ),
        "cell": ParagraphStyle("cell", fontName=regular, fontSize=8, leading=10),
        "cellHead": ParagraphStyle(
            "cellHead", fontName=bold, fontSize=8, leading=10, textColor=colors.white
        ),
        "total": ParagraphStyle(
            "total", fontName=bold, fontSize=11, alignment=TA_RIGHT, spaceBefore=8
        ),
        "note": ParagraphStyle(
            "note",
            fontName=regular,
            fontSize=8.5,
            textColor=colors.HexColor("#9C5700"),
            spaceBefore=8,
        ),
    }


def _table(
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
    widths: Sequence[float],
    styles: dict[str, ParagraphStyle],
    highlight_rows: set[int],
) -> Table:
    data = [[Paragraph(h, styles["cellHead"]) for h in header]]
    data += [[Paragraph(c, styles["cell"]) for c in row] for row in rows]

    table = Table(data, colWidths=list(widths), repeatRows=1)
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    # Shtrix kodsiz qatorlar — Excel'dagidek sariq bilan
    commands += [
        ("BACKGROUND", (0, i + 1), (-1, i + 1), WARN_BG) for i in highlight_rows
    ]
    table.setStyle(TableStyle(commands))
    return table


def build_report_pdf(
    rows: list[ReportRow],
    output_path: str | Path,
    *,
    shop_title: str = "",
    period_from: date | None = None,
    period_to: date | None = None,
) -> Path:
    """Yo'qotishlar hisoboti — PDF (SPEC 6.1 ustunlari)."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()

    doc = SimpleDocTemplate(
        str(path),
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title="Yo'qotishlar hisoboti",
    )

    story: list[object] = [Paragraph("Yo'qotishlar hisoboti", styles["title"])]

    subtitle = shop_title
    if period_from and period_to:
        subtitle += f" · {period_from:%d.%m.%Y} — {period_to:%d.%m.%Y}"
    if subtitle:
        story.append(Paragraph(subtitle, styles["sub"]))

    header = (
        "SKU", "Shtrix kod", "Tovar nomi", "Davr", "Kutilgan",
        "Haqiqiy", "Farq", "Tannarx", "Zarar (so'm)", "Turi",
    )
    widths = (
        22 * mm, 30 * mm, 62 * mm, 30 * mm, 16 * mm,
        16 * mm, 14 * mm, 22 * mm, 26 * mm, 30 * mm,
    )

    body: list[list[str]] = []
    highlight: set[int] = set()
    for index, row in enumerate(rows):
        if not row.has_barcode:
            highlight.add(index)
        body.append(
            [
                row.sku,
                row.barcode or "⚠ YO'Q",
                row.title,
                f"{row.period_from:%d.%m.%y}—{row.period_to:%d.%m.%y}",
                str(row.expected_qty),
                str(row.actual_qty),
                str(row.diff_qty),
                format_money(row.unit_cost),
                format_money(row.loss_amount),
                row.kind_label,
            ]
        )

    story.append(_table(header, body, widths, styles, highlight))

    total = sum((r.loss_amount for r in rows), start=rows[0].loss_amount * 0) if rows else 0
    story.append(
        Paragraph(f"JAMI: {format_money(total)} so'm", styles["total"])
    )

    missing = sum(1 for r in rows if not r.has_barcode)
    if missing:
        story.append(
            Paragraph(
                f"⚠ {missing} ta tovarda shtrix kod yo'q (sariq bilan belgilangan). "
                "Bunday tovarlar bo'yicha Uzumga da'vo qilish qiyin.",
                styles["note"],
            )
        )

    story.append(Spacer(1, 6 * mm))
    doc.build(story)
    return path
