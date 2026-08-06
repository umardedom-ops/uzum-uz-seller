"""Pretenziya (da'vo xati) generatori — python-docx (SPEC 6.2).

Tuzilishi: sarlavha, seller rekvizitlari, do'kon nomi va ID, davr,
yo'qolgan tovarlar jadvali, umumiy zarar (raqam va so'z bilan), talab
matni, sana, imzo joyi.

> ⚠️ SPEC 6.2 talabi: **shablon matnini yuristdan yoki haqiqiy sellerdan
> oling** — Uzum qabul qiladigan shakl bo'lishi kerak. Quyidagi matn
> ishchi variant, huquqiy jihatdan tasdiqlanmagan.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from app.docs.models import ClaimContext
from app.docs.numbers import amount_in_words, format_money

TABLE_HEADERS = (
    "№",
    "SKU",
    "Shtrix kod",
    "Tovar nomi",
    "Miqdori",
    "Tannarx",
    "Zarar (so'm)",
)


def build_claim(ctx: ClaimContext, output_path: str | Path) -> Path:
    """Pretenziya hujjatini yaratadi va yo'lini qaytaradi."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    created = ctx.created_on or date.today()

    doc = Document()
    _set_base_style(doc)

    # --- Sarlavha ---
    title = doc.add_paragraph("PRETENZIYA")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.runs[0].bold = True
    title.runs[0].font.size = Pt(16)

    subtitle = doc.add_paragraph(
        "omborda yo'qolgan tovarlar bo'yicha zararni qoplash to'g'risida"
    )
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.runs[0].italic = True

    doc.add_paragraph()

    # --- Kimga / kimdan ---
    doc.add_paragraph("Kimga: «Uzum Market» MChJ")
    doc.add_paragraph(f"Kimdan: {ctx.seller_name}")
    if ctx.seller_requisites:
        doc.add_paragraph(f"Rekvizitlar: {ctx.seller_requisites}")

    doc.add_paragraph()

    # --- Do'kon va davr ---
    doc.add_paragraph(f"Do'kon: {ctx.shop_title} (ID: {ctx.shop_id})")
    doc.add_paragraph(
        f"Tekshiruv davri: {ctx.period_from:%d.%m.%Y} — {ctx.period_to:%d.%m.%Y}"
    )

    doc.add_paragraph()

    # --- Bayon ---
    doc.add_paragraph(
        "Yuqorida ko'rsatilgan davrda do'konimizning ombor harakati "
        "tahlil qilindi. Tahlil natijasida quyidagi tovarlar bo'yicha "
        "hisob-kitobdagi qoldiq bilan haqiqiy qoldiq o'rtasida farq "
        "aniqlandi:"
    )

    # --- Jadval ---
    _add_table(doc, ctx)

    # --- Jami ---
    doc.add_paragraph()
    total = doc.add_paragraph()
    total.add_run("Umumiy zarar: ").bold = True
    total.add_run(f"{format_money(ctx.total_amount)} so'm ")
    total.add_run(f"({amount_in_words(ctx.total_amount)})").italic = True

    doc.add_paragraph(f"Jami miqdor: {ctx.total_qty} dona")

    doc.add_paragraph()

    # --- Talab ---
    demand = doc.add_paragraph()
    demand.add_run("Talab: ").bold = True
    demand.add_run(
        "yuqorida ko'rsatilgan farqlar bo'yicha tekshiruv o'tkazishingizni "
        "va aniqlangan zararni qoplashingizni so'rayman."
    )

    doc.add_paragraph(
        "Ilova: aniqlangan farqlarning batafsil hisoboti (Excel fayl)."
    )

    doc.add_paragraph()
    doc.add_paragraph()

    # --- Sana va imzo ---
    footer = doc.add_paragraph(f"Sana: {created:%d.%m.%Y}")
    footer.alignment = WD_ALIGN_PARAGRAPH.LEFT

    sign = doc.add_paragraph("Imzo: ______________________")
    sign.alignment = WD_ALIGN_PARAGRAPH.LEFT

    doc.save(path)
    return path


def _set_base_style(doc: Document) -> None:
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)


def _add_table(doc: Document, ctx: ClaimContext) -> None:
    table = doc.add_table(rows=1, cols=len(TABLE_HEADERS))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    header = table.rows[0].cells
    for i, name in enumerate(TABLE_HEADERS):
        header[i].text = name
        for paragraph in header[i].paragraphs:
            for run in paragraph.runs:
                run.bold = True

    for idx, row in enumerate(ctx.rows, start=1):
        cells = table.add_row().cells
        cells[0].text = str(idx)
        cells[1].text = row.sku
        # Shtrix kodsiz tovarга da'vo qilib bo'lmaydi — ochiq belgilaymiz
        cells[2].text = row.barcode if row.has_barcode else "—"
        cells[3].text = row.title
        cells[4].text = str(row.diff_qty)
        cells[5].text = format_money(row.unit_cost)
        cells[6].text = format_money(row.loss_amount)
