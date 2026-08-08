"""Tarif va kirish huquqi testlari (SPEC Phase 6).

Bu pul masalasi. Ikki xato ham qimmat:
  * to'lamaganга ochiq qoldirish → daromad yo'qoladi
  * to'laganni bloklash → mijoz ketadi va yomon gapiradi
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import Plan, Subscription, SubscriptionStatus
from app.services.billing import (
    BASIC_FEATURES,
    PRO_FEATURES,
    Access,
    Feature,
    price_for,
)

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


def sub(**kwargs: object) -> Subscription:
    base = {
        "plan": Plan.TRIAL,
        "status": SubscriptionStatus.TRIAL,
        "trial_ends_at": NOW + timedelta(days=2),
        "paid_until": None,
    }
    base.update(kwargs)
    return Subscription(**base)  # type: ignore[arg-type]


class TestSubscriptionActive:
    def test_trial_is_active(self) -> None:
        assert sub().is_active_at(NOW)

    def test_expired_trial_is_not_active(self) -> None:
        assert not sub(trial_ends_at=NOW - timedelta(days=1)).is_active_at(NOW)

    def test_paid_is_active(self) -> None:
        item = sub(
            trial_ends_at=NOW - timedelta(days=10),
            paid_until=NOW + timedelta(days=20),
            plan=Plan.BASIC,
        )
        assert item.is_active_at(NOW)

    def test_cancelled_is_never_active(self) -> None:
        item = sub(
            status=SubscriptionStatus.CANCELLED, paid_until=NOW + timedelta(days=30)
        )
        assert not item.is_active_at(NOW)

    def test_no_dates_is_not_active(self) -> None:
        """Muddat yo'q — jimgina ochib qo'ymaymiz."""
        assert not sub(trial_ends_at=None, paid_until=None).is_active_at(NOW)


class TestEffectivePlan:
    def test_trial_gives_basic(self) -> None:
        """Sinov davrida Basic — Pro emas.

        Sinovda hamma narsa ochiq bo'lsa, sellerda to'lashga sabab
        qolmaydi. Basic asosiy qiymatni ko'rsatadi, Pro to'lovdan keyin.
        """
        assert sub().effective_plan(NOW) is Plan.BASIC

    def test_paid_basic(self) -> None:
        item = sub(plan=Plan.BASIC, paid_until=NOW + timedelta(days=15))
        assert item.effective_plan(NOW) is Plan.BASIC

    def test_paid_pro(self) -> None:
        item = sub(plan=Plan.PRO, paid_until=NOW + timedelta(days=15))
        assert item.effective_plan(NOW) is Plan.PRO

    def test_paid_wins_over_trial(self) -> None:
        """To'lagan mijoz sinovga qaytmasin."""
        item = sub(
            plan=Plan.BASIC,
            paid_until=NOW + timedelta(days=15),
            trial_ends_at=NOW + timedelta(days=1),
        )
        assert item.effective_plan(NOW) is Plan.BASIC

    def test_expired_everything(self) -> None:
        item = sub(
            trial_ends_at=NOW - timedelta(days=5), paid_until=NOW - timedelta(days=1)
        )
        assert item.effective_plan(NOW) is Plan.TRIAL


class TestFeatureAccess:
    def _access(self, plan: Plan, active: bool = True) -> Access:
        return Access(is_active=active, plan=plan, days_left=10, on_trial=False)

    def test_basic_has_core_features(self) -> None:
        access = self._access(Plan.BASIC)
        assert access.can(Feature.LOST_MONEY)
        assert access.can(Feature.STOCK)
        assert access.can(Feature.REPORTS)

    def test_basic_lacks_pro_features(self) -> None:
        """Sotuv imkoniyati: Basic'da yunit-iqtisodiyot yo'q."""
        access = self._access(Plan.BASIC)
        assert not access.can(Feature.ECONOMICS)
        assert not access.can(Feature.FBS_LABELS)
        assert not access.can(Feature.RETURNS_ANALYSIS)

    def test_pro_has_everything(self) -> None:
        access = self._access(Plan.PRO)
        assert all(access.can(f) for f in Feature)

    def test_inactive_blocks_everything(self) -> None:
        """Muddati tugagan — hatto Basic funksiyasi ham yopiq."""
        access = self._access(Plan.PRO, active=False)
        assert not any(access.can(f) for f in Feature)

    def test_basic_is_subset_of_pro(self) -> None:
        assert BASIC_FEATURES < PRO_FEATURES


class TestAdminIdsParsing:
    """`.env` dagi zaxira admin ro'yxati.

    Asosiy manba — baza. Bu yer noto'g'ri to'ldirilgan bo'lsa ham bot
    yiqilmasligi kerak.
    """

    def _settings(self, raw: str):
        from app.core.config import Settings

        return Settings(
            BOT_TOKEN="x",
            FERNET_KEY="x",
            ADMIN_IDS=raw,
        )

    def test_empty_is_allowed(self) -> None:
        """Bo'sh — normal holat, adminlar bazadan olinadi."""
        assert self._settings("").admin_ids == []

    def test_single_id(self) -> None:
        assert self._settings("123456").admin_ids == [123456]

    def test_multiple_with_spaces(self) -> None:
        assert self._settings("111, 222 ,333").admin_ids == [111, 222, 333]

    def test_garbage_is_skipped_not_crashing(self) -> None:
        """Noto'g'ri qiymat botni to'xtatmasin."""
        assert self._settings("111,abc,,222").admin_ids == [111, 222]

    def test_only_garbage(self) -> None:
        assert self._settings("salom").admin_ids == []


class TestPricing:
    def test_prices(self) -> None:
        assert price_for(Plan.BASIC) == 149_000
        assert price_for(Plan.PRO) == 299_000

    def test_pro_costs_more(self) -> None:
        assert price_for(Plan.PRO) > price_for(Plan.BASIC)
