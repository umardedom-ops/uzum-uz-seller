"""Biznes hisobotini Google Sheets'ga sinxronlash.

Har kuni (va `/sheets` buyrug'i bilan qo'lda) jadval yangilanadi:
Xulosa · Obunachilar · To'lovlar · Promokodlar.

Sozlanmagan bo'lsa — **jim yiqilmaydi**, `SheetsDisabledError` beradi va
chaqiruvchi buni foydalanuvchiga tushunarli aytadi (loyiha qoidasi:
"xato jim yutilmaydi").

Sozlash (bir marta):
  1. Google Cloud → loyiha → **Google Sheets API** ni yoqing
  2. Service account yarating → JSON kalit yuklab oling
  3. Kalitni serverga qo'ying, yo'lini `GOOGLE_CREDENTIALS_FILE` ga yozing
  4. Jadval yarating, uning ID sini `GOOGLE_SHEETS_ID` ga yozing
  5. Jadvalni service account **emailiga** ulashing (Muharrir huquqi bilan)

⚠️ JSON kalit maxfiy — git'ga ham, chatga ham tushmaydi.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services import admin_report
from app.services.admin_report import BusinessReport

log = get_logger(__name__)

# Faqat jadvalga yozish huquqi — boshqa Google xizmatlariga tegmaymiz
SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)

SHEET_SUMMARY = "Xulosa"
SHEET_SUBSCRIBERS = "Obunachilar"
SHEET_PAYMENTS = "To'lovlar"
SHEET_PROMOS = "Promokodlar"
#: Diagramma manbasi — Google grafiklari shu toza jadvalga tayanadi.
#: Xulosa varag'i odam o'qishi uchun (bo'sh qatorlar, sarlavhalar), grafik
#: uchun esa qat'iy «nom | son» ustunlari kerak.
SHEET_CHART = "Diagramma"


class SheetsDisabledError(RuntimeError):
    """Sinxronizatsiya sozlanmagan (jadval ID yoki kalit fayli yo'q)."""


class SheetsSyncError(RuntimeError):
    """Google javob bermadi yoki huquq yetmadi."""


@dataclass(frozen=True, slots=True)
class SyncResult:
    subscribers: int
    payments: int
    promos: int
    url: str


def _headers() -> dict[str, list[str]]:
    return {
        SHEET_SUBSCRIBERS: [
            "Telegram ID", "Username", "Ism", "Telefon", "Do'konlar", "Tarif",
            "Holat", "Bu oy qo'shildi", "Bu oy to'lovi", "Manba",
            "Sinov tugaydi", "To'langan muddat", "Qolgan kun",
            "Promokod", "Ro'yxatdan o'tgan",
        ],
        SHEET_PAYMENTS: [
            "№", "Telegram ID", "Tarif", "Summa", "Oy", "Usul", "Holat",
            "Tashqi ID", "Yaratilgan", "To'langan",
        ],
        SHEET_PROMOS: [
            "Kod", "Tarif", "Kun", "Ishlatilgan", "Chegara", "Faol",
            "Muddati", "Yaratgan", "Izoh",
        ],
    }


def _rows(report: BusinessReport) -> dict[str, list[list[object]]]:
    """Hisobotni jadval qatorlariga aylantiradi."""
    s = report.summary
    avg = float(s.paid_total / s.paid_count) if s.paid_count else 0.0

    summary: list[list[object]] = [
        ["Hisobot sanasi", report.generated_at.strftime("%Y-%m-%d %H:%M UTC")],
        [],
        [f"BU OY ({s.month_label})", ""],
        ["Yangi qo'shilgan", s.joined_this_month],
        ["To'lov qilgan (kishi)", s.payers_this_month],
        ["Bu oy tushum (so'm)", float(s.paid_this_month)],
        ["Promokod bilan kirgan", s.promo_this_month],
        [],
        ["KIM QAYSI TARIFDA", ""],
        ["Pro — to'lagan", s.pro_paid],
        ["Basic — to'lagan", s.basic_paid],
        ["Sinovda (hali to'lamagan)", s.on_trial],
        ["Muddati tugagan", s.expired],
        ["Obunasi yo'q", s.no_subscription],
        [],
        ["FOYDALANUVCHILAR", ""],
        ["Jami ro'yxatdan o'tgan", s.users],
        ["Do'kon ulagan", s.with_shop],
        ["Faol obuna", s.active_subs],
        ["Promokod bilan (jami)", s.promo_granted],
        [],
        ["PUL (butun davr)", ""],
        ["Tasdiqlangan tushum (so'm)", float(s.paid_total)],
        ["  to'lovlar soni", s.paid_count],
        ["  o'rtacha to'lov", round(avg)],
        ["Kutilayotgan (tasdiqlanmagan)", float(s.pending_total)],
        ["  to'lovlar soni", s.pending_count],
        ["Rad etilgan", float(s.rejected_total)],
    ]

    heads = _headers()
    return {
        SHEET_SUMMARY: summary,
        SHEET_SUBSCRIBERS: [heads[SHEET_SUBSCRIBERS]]
        + [
            [
                r.telegram_id, r.username, r.full_name, r.phone, r.shops,
                r.plan, r.status,
                "ha" if r.joined_this_month else "",
                float(r.paid_this_month) or "",
                r.source,
                r.trial_ends, r.paid_until, r.days_left,
                r.promo_codes, r.registered,
            ]
            for r in report.subscribers
        ],
        SHEET_PAYMENTS: [heads[SHEET_PAYMENTS]]
        + [
            [
                p.payment_id, p.telegram_id, p.plan, float(p.amount), p.months,
                p.method, p.status, p.external_id, p.created, p.paid_at,
            ]
            for p in report.payments
        ],
        SHEET_PROMOS: [heads[SHEET_PROMOS]]
        + [
            [
                p.code, p.plan, p.days, p.used, p.max_uses,
                "ha" if p.is_active else "yo'q", p.expires, p.created_by, p.note,
            ]
            for p in report.promos
        ],
        SHEET_CHART: _chart_rows(report),
    }


def _chart_rows(report: BusinessReport) -> list[list[object]]:
    """Diagramma uchun toza raqamlar.

    Ikki blok: tarif taqsimoti (doiraviy grafik) va to'lov holati
    (ustunli grafik). Har biri «nom | son» — Google shu shaklni kutadi.
    """
    s = report.summary

    paid_count = sum(1 for p in report.payments if p.status == "paid")
    pending_count = sum(1 for p in report.payments if p.status == "pending")
    rejected_count = len(report.payments) - paid_count - pending_count

    return [
        ["Tarif", "Kishi"],
        ["Pro (to'lagan)", s.pro_paid],
        ["Basic (to'lagan)", s.basic_paid],
        ["Sinovda", s.on_trial],
        ["Muddati tugagan", s.expired],
        ["Obunasiz", s.no_subscription],
        [],
        ["To'lov holati", "Soni"],
        ["Tasdiqlangan", paid_count],
        ["Kutilmoqda", pending_count],
        ["Rad etilgan", rejected_count],
        [],
        ["Pul", "So'm"],
        ["Bu oy tushum", float(s.paid_this_month)],
        ["Jami tushum", float(s.paid_total)],
        ["Kutilayotgan", float(s.pending_total)],
    ]


def _push(sheets_id: str, creds_file: str, data: dict[str, list[list[object]]]) -> str:
    """Bloklovchi Google chaqiruvi — `sync_now` uni alohida oqimda yuritadi."""
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_file(creds_file, scopes=list(SCOPES))
    client = gspread.authorize(creds)
    book = client.open_by_key(sheets_id)

    for title, rows in data.items():
        try:
            sheet = book.worksheet(title)
        except gspread.WorksheetNotFound:
            sheet = book.add_worksheet(
                title=title, rows=max(len(rows) + 10, 50), cols=20
            )
        # Eski ma'lumot qolib ketmasin: har safar tozalab yozamiz
        sheet.clear()
        if rows:
            sheet.update(values=rows, range_name="A1")

    _ensure_charts(book)
    return book.url


def _chart_spec(
    sheet_id: int, title: str, kind: str, header_row: int, rows: int, anchor_row: int
) -> dict:
    """Bitta diagramma tavsifi (Sheets API `addChart`).

    `header_row` — 0 dan boshlanadigan sarlavha qatori; ma'lumot undan
    keyin `rows` ta qator.
    """
    domain = {
        "sourceRange": {
            "sources": [
                {
                    "sheetId": sheet_id,
                    "startRowIndex": header_row,
                    "endRowIndex": header_row + rows + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                }
            ]
        }
    }
    series = {
        "sourceRange": {
            "sources": [
                {
                    "sheetId": sheet_id,
                    "startRowIndex": header_row,
                    "endRowIndex": header_row + rows + 1,
                    "startColumnIndex": 1,
                    "endColumnIndex": 2,
                }
            ]
        }
    }

    if kind == "PIE":
        spec = {
            "title": title,
            "pieChart": {
                "legendPosition": "RIGHT_LEGEND",
                "domain": domain,
                "series": series,
                "threeDimensional": False,
            },
        }
    else:
        spec = {
            "title": title,
            "basicChart": {
                "chartType": "COLUMN",
                "legendPosition": "NO_LEGEND",
                "domains": [{"domain": domain}],
                "series": [{"series": series, "targetAxis": "LEFT_AXIS"}],
                "headerCount": 1,
            },
        }

    return {
        "addChart": {
            "chart": {
                "spec": spec,
                "position": {
                    "overlayPosition": {
                        "anchorCell": {
                            "sheetId": sheet_id,
                            "rowIndex": anchor_row,
                            "columnIndex": 3,  # D ustuni — ma'lumotni to'smasin
                        },
                        "widthPixels": 460,
                        "heightPixels": 280,
                    }
                },
            }
        }
    }


def _ensure_charts(book: object) -> None:
    """Diagrammalarni bir marta chizadi.

    Har sinxronizatsiyada qayta chizmaymiz — aks holda grafiklar
    ko'payib ketardi. Mavjud bo'lsa tegilmaydi: ma'lumot yangilansa
    grafik o'zi yangilanadi (u diapazonga bog'langan).
    """
    import gspread

    try:
        sheet = book.worksheet(SHEET_CHART)  # type: ignore[attr-defined]
    except gspread.WorksheetNotFound:
        return

    # Allaqachon chizilganmi
    try:
        meta = book.fetch_sheet_metadata(  # type: ignore[attr-defined]
            {"fields": "sheets(properties(sheetId,title),charts(chartId))"}
        )
        for item in meta.get("sheets", []):
            if item.get("properties", {}).get("title") == SHEET_CHART:
                if item.get("charts"):
                    return  # bor — qayta chizmaymiz
    except Exception:
        log.exception("Diagramma holatini o'qib bo'lmadi — o'tkazib yuboramiz")
        return

    sheet_id = sheet.id
    requests = [
        # `_chart_rows` tartibiga mos: sarlavha qatori 0, 7, 12
        _chart_spec(sheet_id, "Kim qaysi tarifda", "PIE", 0, 5, 0),
        _chart_spec(sheet_id, "To'lov holati", "COLUMN", 7, 3, 15),
        _chart_spec(sheet_id, "Pul (so'm)", "COLUMN", 12, 3, 30),
    ]

    try:
        book.batch_update({"requests": requests})  # type: ignore[attr-defined]
        log.info("Google Sheets: %s ta diagramma chizildi", len(requests))
    except Exception:
        # Grafik chizilmasa ham ma'lumot yozilgan — sinxronizatsiya
        # muvaffaqiyatli hisoblanadi.
        log.exception("Diagrammalar chizilmadi (ma'lumot saqlandi)")


async def sync_now() -> SyncResult:
    """Jadvalni hozir yangilaydi.

    Sozlanmagan bo'lsa `SheetsDisabledError`, Google javob bermasa
    `SheetsSyncError` — ikkalasi ham foydalanuvchiga aytiladi.
    """
    settings = get_settings()
    if not settings.sheets_enabled:
        raise SheetsDisabledError(
            "GOOGLE_SHEETS_ID yoki GOOGLE_CREDENTIALS_FILE sozlanmagan"
        )

    report = await admin_report.collect()
    data = _rows(report)

    try:
        # gspread sinxron kutubxona — hodisa siklini bloklamaslik uchun
        # alohida oqimga chiqaramiz.
        url = await asyncio.to_thread(
            _push,
            settings.google_sheets_id,
            settings.google_credentials_file,
            data,
        )
    except Exception as exc:  # noqa: BLE001 — sababini yuqoriga uzatamiz
        log.exception("Google Sheets sinxronizatsiyasi yiqildi")
        raise SheetsSyncError(str(exc)) from exc

    log.info(
        "Google Sheets yangilandi: %s obunachi, %s to'lov, %s kod",
        len(report.subscribers),
        len(report.payments),
        len(report.promos),
    )
    return SyncResult(
        subscribers=len(report.subscribers),
        payments=len(report.payments),
        promos=len(report.promos),
        url=url,
    )
