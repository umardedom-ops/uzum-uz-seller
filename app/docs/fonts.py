"""PDF uchun shrift topish.

Muammo: reportlab'ning standart shriftlari (Helvetica) kirill va
o'zbekcha `ʻ` belgisini qo'llab-quvvatlamaydi — matn "□□□" bo'lib chiqadi.
Shuning uchun tizimda mavjud TrueType shrift topamiz.

Deploy eslatmasi: Linux serverda `fonts-dejavu-core` paketi o'rnatilgan
bo'lsin, aks holda PDF lotin harflarigina to'g'ri chiqadi.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.core.logging import get_logger

log = get_logger(__name__)

FONT_NAME = "UzumSans"
FONT_NAME_BOLD = "UzumSans-Bold"

# Tekshiriladigan joylar: loyiha ichi → Linux → Windows → macOS
_REGULAR_CANDIDATES = (
    Path(__file__).parent / "fonts" / "DejaVuSans.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/Library/Fonts/Arial.ttf"),
)
_BOLD_CANDIDATES = (
    Path(__file__).parent / "fonts" / "DejaVuSans-Bold.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    Path("C:/Windows/Fonts/arialbd.ttf"),
    Path("/Library/Fonts/Arial Bold.ttf"),
)

_registered = False


def _first_existing(candidates: tuple[Path, ...]) -> Path | None:
    return next((p for p in candidates if p.exists()), None)


def ensure_fonts() -> tuple[str, str]:
    """Shriftlarni ro'yxatdan o'tkazadi. `(oddiy, qalin)` nomlarini qaytaradi.

    Shrift topilmasa Helvetica'ga qaytadi — lotin harflari ishlaydi,
    kirill buziladi. Bu holat logga yoziladi, jim o'tilmaydi.
    """
    global _registered
    if _registered:
        return FONT_NAME, FONT_NAME_BOLD

    regular = _first_existing(_REGULAR_CANDIDATES)
    if regular is None:
        log.warning(
            "TrueType shrift topilmadi — PDF'da kirill matn buzilishi mumkin. "
            "Serverga fonts-dejavu-core o'rnating."
        )
        _registered = True
        return "Helvetica", "Helvetica-Bold"

    pdfmetrics.registerFont(TTFont(FONT_NAME, str(regular)))
    bold = _first_existing(_BOLD_CANDIDATES)
    pdfmetrics.registerFont(TTFont(FONT_NAME_BOLD, str(bold or regular)))

    _registered = True
    log.info("PDF shrifti: %s", regular.name)
    return FONT_NAME, FONT_NAME_BOLD
