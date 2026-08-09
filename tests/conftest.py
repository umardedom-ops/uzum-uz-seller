"""Testlar uchun umumiy sozlash.

❗ Nima uchun kerak: testlar shu faylsiz **haqiqiy `uzumbot.db`** ga
yozardi. Ular bir-birining ma'lumotiga tegib, tasodifiy yiqilardi
(`UNIQUE constraint failed: users.telegram_id`), ishlab turgan bazani
esa keraksiz yozuvlar bilan to'ldirardi.

Endi har test sessiyasi o'zining vaqtinchalik SQLite faylida ishlaydi
va tugagach o'chiriladi.
"""
from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

# ❗ Ilova modullari import qilinishidan OLDIN qo'yiladi: `get_settings`
# lru_cache bilan keshlanadi va birinchi chaqiruvdagi qiymat qoladi.
_TMP_DB = Path(tempfile.gettempdir()) / "uzumbot-tests.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DB.as_posix()}"
os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("FERNET_KEY", "OTQnbdD9DEcVSmH1i1lPCNDGe8jsHY9htmxeK6r0nHI=")


@pytest.fixture(scope="session", autouse=True)
async def _database() -> AsyncIterator[None]:
    """Toza baza yaratadi va sessiya oxirida o'chiradi."""
    import app.db.models  # noqa: F401 — jadvallarni ro'yxatga oladi
    from app.db.base import Base, get_engine

    _TMP_DB.unlink(missing_ok=True)

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    await engine.dispose()
    _TMP_DB.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    """Har testdan keyin jadvallarni bo'shatadi.

    Testlar bir-biridan mustaqil bo'lishi kerak: biri qoldirgan
    foydalanuvchi boshqasining `UNIQUE` cheklovini buzmasin.
    """
    yield

    from sqlalchemy import delete

    from app.db.base import Base, session_scope

    async with session_scope() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(delete(table))
