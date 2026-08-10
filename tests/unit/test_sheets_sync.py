"""Google Sheets sinxronizatsiyasi — tarmoqqa chiqmasdan tekshiriladi.

Muhim: sozlanmagan bo'lsa jim yiqilmasligi va qatorlar to'g'ri
tuzilishi. Haqiqiy Google chaqiruvi mock qilinadi.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from app.db.base import session_scope, utcnow
from app.db.models import (
    Payment,
    PaymentMethod,
    PaymentStatus,
    Plan,
    PromoCode,
    User,
)
from app.services import sheets_sync
from app.services.sheets_sync import (
    SHEET_PAYMENTS,
    SHEET_PROMOS,
    SHEET_SUBSCRIBERS,
    SHEET_SUMMARY,
    SheetsDisabledError,
    SheetsSyncError,
)


async def _seed() -> None:
    async with session_scope() as s:
        user = User(telegram_id=2001, username="test_seller")
        s.add(user)
        await s.flush()
        s.add(
            Payment(
                user_id=user.id, plan=Plan.PRO, amount=Decimal("299000"), months=1,
                method=PaymentMethod.CLICK, status=PaymentStatus.PAID,
                paid_at=utcnow(),
            )
        )
        s.add(PromoCode(code="SHEETKOD", plan=Plan.PRO, days=30, max_uses=5))


class TestDisabled:
    async def test_raises_when_not_configured(self) -> None:
        """Sozlanmagan — aniq xato beradi, jim qolmaydi."""
        with pytest.raises(SheetsDisabledError):
            await sheets_sync.sync_now()


class TestRows:
    async def test_four_sheets_built(self) -> None:
        from app.services import admin_report

        await _seed()
        report = await admin_report.collect()
        data = sheets_sync._rows(report)

        assert set(data) == {
            SHEET_SUMMARY, SHEET_SUBSCRIBERS, SHEET_PAYMENTS, SHEET_PROMOS
        }
        # Sarlavha + kamida bitta qator
        assert len(data[SHEET_SUBSCRIBERS]) >= 2
        assert data[SHEET_SUBSCRIBERS][0][0] == "Telegram ID"
        assert data[SHEET_PAYMENTS][0][0] == "№"
        assert data[SHEET_PROMOS][0][0] == "Kod"

    async def test_payment_status_included(self) -> None:
        """To'lov tasdiqlanganmi — jadvalda ko'rinishi shart."""
        from app.services import admin_report

        await _seed()
        report = await admin_report.collect()
        rows = sheets_sync._rows(report)[SHEET_PAYMENTS]

        statuses = [r[6] for r in rows[1:]]
        assert "paid" in statuses


class TestSyncFlow:
    async def test_success_path(self) -> None:
        """Sozlangan bo'lsa — jadvalga yozadi va natija qaytaradi."""
        await _seed()

        with patch.object(
            type(sheets_sync.get_settings()), "sheets_enabled", property(lambda _: True)
        ), patch.object(
            sheets_sync, "_push", return_value="https://docs.google.com/x"
        ) as push:
            result = await sheets_sync.sync_now()

        assert result.url.startswith("https://")
        assert result.subscribers >= 1
        push.assert_called_once()

    async def test_google_failure_is_reported(self) -> None:
        """Google yiqilsa — sabab yuqoriga uzatiladi, yutilmaydi."""
        await _seed()

        with patch.object(
            type(sheets_sync.get_settings()), "sheets_enabled", property(lambda _: True)
        ), patch.object(sheets_sync, "_push", side_effect=RuntimeError("403 ruxsat yo'q")):
            with pytest.raises(SheetsSyncError, match="403"):
                await sheets_sync.sync_now()
