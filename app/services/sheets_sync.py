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
            "Holat", "Sinov tugaydi", "To'langan muddat", "Qolgan kun",
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
    summary: list[list[object]] = [
        ["Hisobot sanasi", report.generated_at.strftime("%Y-%m-%d %H:%M UTC")],
        [],
        ["FOYDALANUVCHILAR", ""],
        ["Jami ro'yxatdan o'tgan", s.users],
        ["Do'kon ulagan", s.with_shop],
        ["Faol obuna", s.active_subs],
        ["Promokod bilan kirgan", s.promo_granted],
        [],
        ["TARIF KESIMIDA (faol)", ""],
    ]
    summary += [[f"  {plan}", count] for plan, count in sorted(s.by_plan.items())]
    summary += [
        [],
        ["PUL", ""],
        ["Tasdiqlangan tushum (so'm)", float(s.paid_total)],
        ["  to'lovlar soni", s.paid_count],
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
                r.plan, r.status, r.trial_ends, r.paid_until, r.days_left,
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
    }


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

    return book.url


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
