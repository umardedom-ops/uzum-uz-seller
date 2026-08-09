"""Bot kirish nuqtasi.

Ishga tushirish:
    python -m app.bot.main
"""
from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import (
    admin,
    billing,
    economics,
    fbs,
    menu,
    money,
    reports,
    start,
    stock,
    stock_edit,
    top,
)
from app.bot.middlewares.subscription import SubscriptionMiddleware
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.workers.scheduler import build_scheduler

log = get_logger(__name__)


def build_dispatcher() -> Dispatcher:
    # TODO(Task #2): MemoryStorage → doimiy storage (Redis yoki DB),
    # aks holda bot qayta ishga tushganda onboarding holati yo'qoladi.
    dp = Dispatcher(storage=MemoryStorage())

    # Obuna cheklovi — handler'lardan OLDIN ishlaydi (SPEC Phase 6)
    subscription = SubscriptionMiddleware()
    dp.message.outer_middleware(subscription)
    dp.callback_query.outer_middleware(subscription)

    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(billing.router)
    # Aniq filtrli routerlar `menu` dan OLDIN turadi
    dp.include_router(money.router)
    dp.include_router(reports.router)
    dp.include_router(fbs.router)
    dp.include_router(stock.router)
    dp.include_router(stock_edit.router)
    dp.include_router(economics.router)
    dp.include_router(top.router)
    dp.include_router(menu.router)
    return dp


async def run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    me = await bot.get_me()
    log.info("Bot ishga tushdi: @%s (env=%s)", me.username, settings.env)

    scheduler = build_scheduler()
    scheduler.start()
    log.info("Rejalashtiruvchi ishga tushdi: %s job", len(scheduler.get_jobs()))

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("To'xtatildi")
