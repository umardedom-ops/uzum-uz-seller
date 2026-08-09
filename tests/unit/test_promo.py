"""Promokod mantiqi.

Bu pul masalasi: kod ortiqcha ishlasa daromad yo'qoladi, kam ishlasa
hamkor va seller oldida noqulay ahvolga tushamiz. Shuning uchun har
bir rad etish sababi alohida tekshiriladi.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.base import session_scope, utcnow
from app.db.models import Plan, PromoCode, Subscription, User
from app.services import billing


@pytest.fixture
async def user() -> User:
    async with session_scope() as session:
        item = User(telegram_id=999001, lang="uz")
        session.add(item)
        await session.flush()
        return item


class TestCodeGeneration:
    def test_code_has_no_confusing_characters(self) -> None:
        """0/O va 1/I/L chalkashadi — kod og'zaki ham uzatiladi."""
        for _ in range(50):
            code = billing.generate_code()
            assert not set(code) & set("01OIL")

    def test_code_length(self) -> None:
        assert len(billing.generate_code()) == 8
        assert len(billing.generate_code(12)) == 12

    def test_codes_differ(self) -> None:
        codes = {billing.generate_code() for _ in range(100)}
        assert len(codes) > 95, "kodlar takrorlanyapti"


class TestRedeem:
    async def test_activates_subscription(self, user: User) -> None:
        code = await billing.create_promo(plan=Plan.PRO, days=30)

        result, plan, days = await billing.redeem_promo(user.telegram_id, code)

        assert result is billing.PromoResult.OK
        assert plan is Plan.PRO
        assert days == 30

        access = await billing.get_access(user.telegram_id)
        assert access.is_active
        assert access.plan is Plan.PRO

    async def test_case_insensitive(self, user: User) -> None:
        """Kod og'zaki uzatiladi — registr muhim bo'lmasligi kerak."""
        code = await billing.create_promo()
        result, _, _ = await billing.redeem_promo(user.telegram_id, code.lower())
        assert result is billing.PromoResult.OK

    async def test_unknown_code(self, user: User) -> None:
        result, _, _ = await billing.redeem_promo(user.telegram_id, "YOQKOD99")
        assert result is billing.PromoResult.NOT_FOUND

    async def test_same_user_cannot_reuse(self, user: User) -> None:
        """Aks holda bitta kod bilan muddat cheksiz uzayardi."""
        code = await billing.create_promo(max_uses=10)

        first, _, _ = await billing.redeem_promo(user.telegram_id, code)
        second, _, _ = await billing.redeem_promo(user.telegram_id, code)

        assert first is billing.PromoResult.OK
        assert second is billing.PromoResult.ALREADY_USED

    async def test_usage_limit(self, user: User) -> None:
        code = await billing.create_promo(max_uses=1)
        await billing.redeem_promo(user.telegram_id, code)

        async with session_scope() as session:
            other = User(telegram_id=999002, lang="uz")
            session.add(other)

        result, _, _ = await billing.redeem_promo(999002, code)
        assert result is billing.PromoResult.USED_UP

    async def test_expired_code(self, user: User) -> None:
        code = await billing.create_promo()
        async with session_scope() as session:
            promo = await session.scalar(
                select(PromoCode).where(PromoCode.code == code)
            )
            promo.expires_at = utcnow() - timedelta(days=1)

        result, _, _ = await billing.redeem_promo(user.telegram_id, code)
        assert result is billing.PromoResult.EXPIRED

    async def test_deactivated_code(self, user: User) -> None:
        code = await billing.create_promo()
        assert await billing.deactivate_promo(code)

        result, _, _ = await billing.redeem_promo(user.telegram_id, code)
        assert result is billing.PromoResult.NOT_FOUND

    async def test_unknown_user(self) -> None:
        code = await billing.create_promo()
        result, _, _ = await billing.redeem_promo(123456789, code)
        assert result is billing.PromoResult.NO_USER

    async def test_extends_existing_paid_period(self, user: User) -> None:
        """To'lagan mijozning kunlari yo'qolmasligi kerak."""
        async with session_scope() as session:
            sub = Subscription(
                user_id=user.id,
                plan=Plan.BASIC,
                paid_until=utcnow() + timedelta(days=10),
            )
            session.add(sub)

        code = await billing.create_promo(plan=Plan.PRO, days=30)
        await billing.redeem_promo(user.telegram_id, code)

        access = await billing.get_access(user.telegram_id)
        # 10 kun qolgan + 30 kun qo'shildi
        assert access.days_left >= 39


class TestListing:
    async def test_shows_usage(self, user: User) -> None:
        code = await billing.create_promo(max_uses=5, note="hamkor")
        await billing.redeem_promo(user.telegram_id, code)

        rows = await billing.list_promos()
        row = next(r for r in rows if r["code"] == code)

        assert row["used"] == 1
        assert row["max_uses"] == 5
        assert row["note"] == "hamkor"
