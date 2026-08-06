"""Fon vazifalari rejalashtiruvchisi (SPEC Phase 3, APScheduler).

Jadval (Toshkent vaqti):
  * har soatda      — buyurtma/qaytarish/moliya sinxronizatsiyasi
  * 06:00           — kunlik qoldiq surati + audit
  * 09:00           — kunlik hisobot xabari (SPEC 7)

SPEC 9.6: sync xatolari jim yutilmaydi — adminga Telegram orqali chiqadi.
"""
from __future__ import annotations

from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import session_scope
from app.db.models import Shop
from app.services import alerts, audit_runner, sync

log = get_logger(__name__)

# Audit qancha kunlik davrni tekshiradi
AUDIT_WINDOW_DAYS = 30


async def job_sync_hourly() -> None:
    """Tez sinxronizatsiya + xabarnomalar.

    Blok va qoldiq holati aynan shu yerda ushlanadi: sync yangi holatni
    olib keladi, keyin darhol tekshiriladi. Kechikish qancha kam bo'lsa,
    seller shuncha kam pul yo'qotadi.
    """
    results = await sync.sync_all_shops()
    failed = [shop_id for shop_id, count in results.items() if count < 0]
    log.info("Soatlik sync: %s do'kon, %s xato", len(results), len(failed))
    if failed:
        await _alert_admin(f"⚠️ Sync xatosi: do'konlar {failed}")

    try:
        await alerts.send_alerts()
    except Exception:
        log.exception("Xabarnomalarni yuborishda xato")


async def job_daily_snapshot_and_audit() -> None:
    """Kunlik qoldiq surati va audit.

    Suratni sync oladi; keyin audit yuritiladi. Tartib muhim — audit
    yangi suratdan keyin ishlashi kerak.
    """
    await sync.sync_all_shops()

    today = date.today()
    period_from = today - timedelta(days=AUDIT_WINDOW_DAYS)

    async with session_scope() as session:
        shop_ids = list(
            await session.scalars(select(Shop.id).where(Shop.is_active.is_(True)))
        )

    for shop_id in shop_ids:
        try:
            await audit_runner.run_audit(shop_id, period_from, today)
        except Exception:
            log.exception("Audit xatosi: shop_id=%s", shop_id)
            await _alert_admin(f"⚠️ Audit xatosi: do'kon {shop_id}")


async def job_daily_report() -> None:
    """Kunlik hisobot xabari (SPEC 7).

    TODO: xabar yuborish `app/services/reports.py` da amalga oshiriladi.
    """
    from app.services import reports

    await reports.send_daily_reports()


def build_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone=settings.tz)

    scheduler.add_job(
        job_sync_hourly,
        IntervalTrigger(hours=1),
        id="sync_hourly",
        max_instances=1,       # oldingisi tugamagan bo'lsa yangisi boshlanmasin
        coalesce=True,         # o'tkazib yuborilganlar to'planib ketmasin
        misfire_grace_time=600,
    )
    scheduler.add_job(
        job_daily_snapshot_and_audit,
        CronTrigger(hour=6, minute=0),
        id="daily_snapshot_audit",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        job_daily_report,
        CronTrigger(hour=9, minute=0),
        id="daily_report",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    return scheduler


async def _alert_admin(text: str) -> None:
    """Adminlarga Telegram orqali xabar (SPEC 9.6).

    Adminlar bazadan olinadi — `.env` ni qo'lda to'ldirish shart emas.
    """
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from app.services.billing import admin_ids

    settings = get_settings()
    admins = await admin_ids()
    if not admins:
        log.warning("Admin yo'q, alert yuborilmadi: %s", text)
        return

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        for admin_id in admins:
            try:
                await bot.send_message(admin_id, text)
            except Exception:
                log.exception("Adminga xabar yuborilmadi: %s", admin_id)
    finally:
        await bot.session.close()
