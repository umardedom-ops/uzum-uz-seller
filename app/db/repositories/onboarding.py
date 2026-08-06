"""Onboarding uchun bazaga yozish amallari.

Barcha amallar **idempotent**: takroriy chaqirilsa dublikat yaratmaydi.
Foydalanuvchi botni qayta ishga tushirsa yoki xabarni ikki marta yuborsa
ham baza toza qoladi.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.models import (
    AuthType,
    Lang,
    Plan,
    Shop,
    ShopCredential,
    Subscription,
    SubscriptionStatus,
    User,
)

log = get_logger(__name__)


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    lang: str = "uz",
    *,
    full_name: str | None = None,
    username: str | None = None,
) -> User:
    """Foydalanuvchini topadi yoki yaratadi.

    **Birinchi foydalanuvchi avtomatik admin bo'ladi.** Bot egasi uni
    birinchi ishga tushiradi — shu tarzda `.env` ni qo'lda tahrirlash
    shart emas.

    Xavfsizlik: bu faqat baza butunlay bo'sh bo'lgandagina ishlaydi.
    """
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is not None:
        if full_name and user.full_name != full_name:
            user.full_name = full_name
        if username and user.username != username:
            user.username = username
        return user

    is_first = (await session.scalar(select(func.count()).select_from(User))) == 0

    user = User(
        telegram_id=telegram_id,
        lang=Lang(lang),
        full_name=full_name,
        username=username,
        is_admin=is_first,
    )
    session.add(user)
    await session.flush()  # id kerak

    if is_first:
        log.warning(
            "Birinchi foydalanuvchi ADMIN qilib belgilandi: tg_id=%s", telegram_id
        )
    return user


async def set_lang(session: AsyncSession, user: User, lang: str) -> None:
    user.lang = Lang(lang)


async def set_phone(session: AsyncSession, user: User, phone: str) -> None:
    user.phone = phone


async def accept_oferta(session: AsyncSession, user: User) -> None:
    user.oferta_accepted = True


async def start_trial(
    session: AsyncSession, user: User, trial_days: int
) -> Subscription:
    """Sinov muddatini boshlaydi. Allaqachon boshlangan bo'lsa — tegmaydi.

    Bu muhim: aks holda seller do'konni qayta ulab, sinovni cheksiz
    uzaytira olardi.
    """
    sub = await session.scalar(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    if sub is not None:
        return sub

    sub = Subscription(
        user_id=user.id,
        plan=Plan.TRIAL,
        status=SubscriptionStatus.TRIAL,
        trial_ends_at=utcnow() + timedelta(days=trial_days),
    )
    session.add(sub)
    await session.flush()
    return sub


async def upsert_shop(
    session: AsyncSession, user: User, uzum_shop_id: str, title: str | None = None
) -> Shop:
    """Do'konni qo'shadi yoki mavjudini yangilaydi."""
    shop = await session.scalar(
        select(Shop).where(Shop.user_id == user.id, Shop.uzum_shop_id == uzum_shop_id)
    )
    if shop is None:
        shop = Shop(
            user_id=user.id,
            uzum_shop_id=uzum_shop_id,
            title=title,
            connected_at=utcnow(),
        )
        session.add(shop)
        await session.flush()
    elif title and shop.title != title:
        shop.title = title  # do'kon nomi o'zgargan bo'lsa

    shop.is_active = True
    return shop


async def save_credential(
    session: AsyncSession,
    shop: Shop,
    secret: str,
    auth_type: AuthType = AuthType.API,
) -> ShopCredential:
    """Kalitni SHIFRLAB saqlaydi (SPEC 9.2).

    Bir do'kon uchun bir tur bitta bo'ladi — yangisi eskisini almashtiradi.
    """
    cred = await session.scalar(
        select(ShopCredential).where(
            ShopCredential.shop_id == shop.id, ShopCredential.auth_type == auth_type
        )
    )
    if cred is None:
        cred = ShopCredential(shop_id=shop.id, auth_type=auth_type)
        session.add(cred)

    cred.secret = secret  # setter shifrlaydi
    cred.is_valid = True
    cred.last_checked_at = utcnow()
    await session.flush()
    return cred


async def get_active_shops(session: AsyncSession, telegram_id: int) -> list[Shop]:
    result = await session.scalars(
        select(Shop)
        .join(User)
        .where(User.telegram_id == telegram_id, Shop.is_active.is_(True))
    )
    return list(result)
