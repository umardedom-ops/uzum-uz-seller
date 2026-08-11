"""Hodimlar va guruh/kanalga hisobot.

Raqobatchida bor, bizda yo'q edi — yirik seller va agentliklar uchun.

Xavfsizlik qoidalari (buzilmasin):
  1. Faqat do'kon **egasi** hodim qo'sha/o'chira oladi.
  2. Hodim to'lov, tarif va hodim boshqaruviga **hech qachon** kirmaydi.
  3. Hodim faqat o'ziga biriktirilgan do'konni ko'radi.
  4. Egasi o'zini hodim qilib qo'sha olmaydi (ma'nosiz va chalkash).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.base import session_scope
from app.db.models import ReportChannel, Shop, ShopStaff, StaffRole, User

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StaffMember:
    staff_id: int
    telegram_id: int
    role: StaffRole
    title: str | None

    @property
    def label(self) -> str:
        who = self.title or str(self.telegram_id)
        return f"{who} · {self.role.value}"


@dataclass(frozen=True, slots=True)
class Channel:
    channel_id: int
    chat_id: int
    title: str | None

    @property
    def label(self) -> str:
        return self.title or str(self.chat_id)


async def _owner_shop(telegram_id: int, shop_id: int) -> Shop | None:
    """Do'kon shu odamniki ekanini tasdiqlaydi (egalik tekshiruvi)."""
    async with session_scope() as session:
        user = await session.scalar(
            select(User).where(User.telegram_id == telegram_id)
        )
        if user is None:
            return None
        return await session.scalar(
            select(Shop).where(Shop.id == shop_id, Shop.user_id == user.id)
        )


# ---------------------------------------------------------------------- #
# Hodimlar
# ---------------------------------------------------------------------- #


async def add_staff(
    owner_telegram_id: int,
    shop_id: int,
    staff_telegram_id: int,
    *,
    role: StaffRole = StaffRole.VIEWER,
    title: str | None = None,
) -> StaffMember | None:
    """Hodim qo'shadi. Egasi bo'lmasa yoki o'zini qo'shsa — None."""
    if owner_telegram_id == staff_telegram_id:
        return None  # egasi allaqachon hamma narsani ko'radi

    shop = await _owner_shop(owner_telegram_id, shop_id)
    if shop is None:
        return None

    async with session_scope() as session:
        existing = await session.scalar(
            select(ShopStaff).where(
                ShopStaff.shop_id == shop_id,
                ShopStaff.telegram_id == staff_telegram_id,
            )
        )
        if existing is not None:
            # Qayta qo'shish — huquqni yangilash deb qaraymiz
            existing.role = role
            existing.is_active = True
            if title:
                existing.title = title
            member = StaffMember(
                existing.id, existing.telegram_id, existing.role, existing.title
            )
        else:
            staff = ShopStaff(
                shop_id=shop_id,
                telegram_id=staff_telegram_id,
                role=role,
                title=title,
                added_by=owner_telegram_id,
            )
            session.add(staff)
            await session.flush()
            member = StaffMember(staff.id, staff.telegram_id, staff.role, staff.title)

    log.info("Hodim qo'shildi: shop=%s tg=%s rol=%s", shop_id, staff_telegram_id, role.value)
    return member


async def remove_staff(owner_telegram_id: int, shop_id: int, staff_telegram_id: int) -> bool:
    """Hodimni o'chiradi (faqat egasi)."""
    shop = await _owner_shop(owner_telegram_id, shop_id)
    if shop is None:
        return False

    async with session_scope() as session:
        staff = await session.scalar(
            select(ShopStaff).where(
                ShopStaff.shop_id == shop_id,
                ShopStaff.telegram_id == staff_telegram_id,
            )
        )
        if staff is None:
            return False
        await session.delete(staff)

    log.info("Hodim o'chirildi: shop=%s tg=%s", shop_id, staff_telegram_id)
    return True


async def list_staff(shop_id: int) -> list[StaffMember]:
    async with session_scope() as session:
        rows = await session.scalars(
            select(ShopStaff)
            .where(ShopStaff.shop_id == shop_id, ShopStaff.is_active.is_(True))
            .order_by(ShopStaff.id)
        )
        return [StaffMember(s.id, s.telegram_id, s.role, s.title) for s in rows]


async def staff_shops(telegram_id: int) -> list[Shop]:
    """Shu odam **hodim sifatida** kira oladigan do'konlar.

    Egalik bilan aralashtirmaymiz: bu faqat biriktirilganlar.
    """
    async with session_scope() as session:
        return list(
            await session.scalars(
                select(Shop)
                .join(ShopStaff, ShopStaff.shop_id == Shop.id)
                .where(
                    ShopStaff.telegram_id == telegram_id,
                    ShopStaff.is_active.is_(True),
                    Shop.is_active.is_(True),
                )
                .order_by(Shop.id)
            )
        )


async def staff_role_for(telegram_id: int, shop_id: int) -> StaffRole | None:
    """Shu do'konda qanday rol bilan turibdi (hodim bo'lmasa None)."""
    async with session_scope() as session:
        return await session.scalar(
            select(ShopStaff.role).where(
                ShopStaff.shop_id == shop_id,
                ShopStaff.telegram_id == telegram_id,
                ShopStaff.is_active.is_(True),
            )
        )


# ---------------------------------------------------------------------- #
# Guruh / kanal
# ---------------------------------------------------------------------- #


async def link_channel(
    owner_telegram_id: int, shop_id: int, chat_id: int, title: str | None = None
) -> Channel | None:
    """Guruh/kanalni do'konga ulaydi (faqat egasi)."""
    shop = await _owner_shop(owner_telegram_id, shop_id)
    if shop is None:
        return None

    async with session_scope() as session:
        existing = await session.scalar(
            select(ReportChannel).where(
                ReportChannel.shop_id == shop_id, ReportChannel.chat_id == chat_id
            )
        )
        if existing is not None:
            existing.is_active = True
            if title:
                existing.title = title
            channel = Channel(existing.id, existing.chat_id, existing.title)
        else:
            row = ReportChannel(
                shop_id=shop_id,
                chat_id=chat_id,
                title=title,
                added_by=owner_telegram_id,
            )
            session.add(row)
            await session.flush()
            channel = Channel(row.id, row.chat_id, row.title)

    log.info("Kanal ulandi: shop=%s chat=%s", shop_id, chat_id)
    return channel


async def unlink_channel(owner_telegram_id: int, shop_id: int, chat_id: int) -> bool:
    shop = await _owner_shop(owner_telegram_id, shop_id)
    if shop is None:
        return False

    async with session_scope() as session:
        row = await session.scalar(
            select(ReportChannel).where(
                ReportChannel.shop_id == shop_id, ReportChannel.chat_id == chat_id
            )
        )
        if row is None:
            return False
        await session.delete(row)

    log.info("Kanal uzildi: shop=%s chat=%s", shop_id, chat_id)
    return True


async def list_channels(shop_id: int) -> list[Channel]:
    async with session_scope() as session:
        rows = await session.scalars(
            select(ReportChannel)
            .where(ReportChannel.shop_id == shop_id, ReportChannel.is_active.is_(True))
            .order_by(ReportChannel.id)
        )
        return [Channel(c.id, c.chat_id, c.title) for c in rows]


async def channels_for_shops(shop_ids: list[int]) -> dict[int, list[int]]:
    """Kunlik hisobot uchun: do'kon → chat ID lar."""
    if not shop_ids:
        return {}
    async with session_scope() as session:
        rows = await session.scalars(
            select(ReportChannel).where(
                ReportChannel.shop_id.in_(shop_ids),
                ReportChannel.is_active.is_(True),
            )
        )
        result: dict[int, list[int]] = {}
        for row in rows:
            result.setdefault(row.shop_id, []).append(row.chat_id)
        return result
