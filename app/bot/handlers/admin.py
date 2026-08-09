"""Admin buyruqlari.

Admin huquqi **bazada** saqlanadi — `.env` ni qo'lda tahrirlash shart
emas. Birinchi `/start` bosgan foydalanuvchi avtomatik admin bo'ladi
(bot egasi uni birinchi ishga tushiradi).

`.env` dagi `ADMIN_IDS` zaxira bo'lib qoladi: baza yo'qolsa ham egasi
kira olsin.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from app.bot.texts import LANGS, t
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Plan
from app.services import billing

log = get_logger(__name__)
router = Router(name="admin")


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    """Telegram ID ni ko'rsatadi.

    Admin bazadan aniqlanadi, shuning uchun bu buyruq faqat ma'lumot
    uchun — hech narsani qo'lda ko'chirish shart emas.
    """
    user = message.from_user
    is_admin = await billing.is_admin(user.id)
    role = "👑 Admin" if is_admin else "Foydalanuvchi"

    await message.answer(
        f"🆔 Telegram ID: <code>{user.id}</code>\n"
        f"Holat: {role}\n\n"
        f"Admin buyruqlari: /admin"
    )


@router.message(Command("admin"))
@router.message(F.text.in_({t("menu_admin", lg) for lg in LANGS}))
async def cmd_admin(message: Message) -> None:
    """Admin paneli: statistika va tasdiq kutayotgan to'lovlar.

    `/admin` buyrug'i yoki menyudagi tugma orqali ochiladi.
    """
    if not await billing.is_admin(message.from_user.id):
        return  # jim — bu buyruq borligini bildirmaymiz

    stats = await billing.user_stats()
    pending = await billing.pending_payments()

    lines = [
        "👑 <b>Admin panel</b>",
        "",
        f"👥 Foydalanuvchilar: <b>{stats['users']}</b>",
        f"🏪 Ulangan do'konlar: <b>{stats['shops']}</b>",
        f"✅ Faol obuna: <b>{stats['active']}</b> "
        f"(to'lagan: {stats['paying']}, sinovda: {stats['trial']})",
    ]

    if pending:
        lines += ["", f"💳 <b>Tasdiq kutmoqda: {len(pending)} ta</b>"]
        for payment_id, telegram_id, plan, amount in pending[:10]:
            money = f"{amount:,}".replace(",", " ")
            lines.append(f"  #{payment_id} · <code>{telegram_id}</code> · {plan} · {money}")
        lines.append("")
        lines.append("Tasdiqlash: <code>/pay_ok 12</code> · Rad: <code>/pay_no 12</code>")
    else:
        lines += ["", "💳 Tasdiq kutayotgan to'lov yo'q."]

    lines += [
        "",
        "<b>Buyruqlar:</b>",
        "<code>/users</code> — oxirgi foydalanuvchilar",
        "<code>/makeadmin 123456</code> — admin qilish",
        "<code>/unadmin 123456</code> — huquqni olib tashlash",
        "",
        "<b>Bepul kirish:</b>",
        "<code>/promo_new</code> — Pro, 30 kun, 1 martalik kod",
        "<code>/promo_new pro 90 10</code> — tarif, kun, necha kishiga",
        "<code>/promos</code> — kodlar ro'yxati",
        "<code>/promo_off KOD</code> — kodni to'xtatish",
    ]

    await message.answer("\n".join(lines))


@router.message(Command("users"))
async def cmd_users(message: Message) -> None:
    if not await billing.is_admin(message.from_user.id):
        return

    rows = await billing.recent_users(limit=20)
    if not rows:
        await message.answer("Foydalanuvchi yo'q.")
        return

    lines = ["👥 <b>Oxirgi foydalanuvchilar</b>", ""]
    for item in rows:
        mark = "👑" if item["is_admin"] else ("🏪" if item["shops"] else "·")
        name = item["name"] or "—"
        lines.append(
            f"{mark} <code>{item['telegram_id']}</code> {name[:24]} "
            f"· {item['status']}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("makeadmin"))
async def cmd_make_admin(message: Message, command: CommandObject) -> None:
    if not await billing.is_admin(message.from_user.id):
        return

    target = _parse_id(command.args)
    if target is None:
        await message.answer("Foydalanish: <code>/makeadmin 123456789</code>")
        return

    ok = await billing.grant_admin(target)
    await message.answer(
        f"✅ <code>{target}</code> admin qilindi."
        if ok
        else f"❌ <code>{target}</code> topilmadi. U avval botga /start yozishi kerak."
    )


@router.message(Command("unadmin"))
async def cmd_revoke_admin(message: Message, command: CommandObject) -> None:
    if not await billing.is_admin(message.from_user.id):
        return

    target = _parse_id(command.args)
    if target is None:
        await message.answer("Foydalanish: <code>/unadmin 123456789</code>")
        return

    ok = await billing.revoke_admin(target)
    await message.answer(
        f"✅ <code>{target}</code> huquqi olib tashlandi."
        if ok
        else "❌ Bajarilmadi. Oxirgi adminni o'chirib bo'lmaydi."
    )


# --- To'lovni tasdiqlash ------------------------------------------------ #


@router.message(Command("pay_ok"))
async def cmd_pay_ok(message: Message, command: CommandObject) -> None:
    if not await billing.is_admin(message.from_user.id):
        return

    payment_id = _parse_id(command.args)
    if payment_id is None:
        await message.answer("Foydalanish: <code>/pay_ok 12</code>")
        return

    await _confirm(message, payment_id, message.from_user.id)


@router.message(Command("pay_no"))
async def cmd_pay_no(message: Message, command: CommandObject) -> None:
    if not await billing.is_admin(message.from_user.id):
        return

    payment_id = _parse_id(command.args)
    if payment_id is None:
        await message.answer("Foydalanish: <code>/pay_no 12</code>")
        return

    await billing.reject_payment(payment_id, admin_id=message.from_user.id)
    await message.answer(f"❌ To'lov #{payment_id} rad etildi")
    await _notify_client(message, payment_id, approved=False)


@router.callback_query(F.data.startswith("admin:pay_ok:"))
async def on_confirm(cb: CallbackQuery) -> None:
    if not await billing.is_admin(cb.from_user.id):
        await cb.answer("Ruxsat yo'q", show_alert=True)
        return

    payment_id = int(cb.data.rsplit(":", 1)[1])
    ok = await billing.confirm_payment(payment_id, admin_id=cb.from_user.id)
    if not ok:
        await cb.answer("Bu to'lov allaqachon ishlangan", show_alert=True)
        return

    await cb.answer("Tasdiqlandi")
    await cb.message.edit_text(f"✅ To'lov #{payment_id} tasdiqlandi")
    await _notify_client(cb, payment_id, approved=True)


@router.callback_query(F.data.startswith("admin:pay_no:"))
async def on_reject(cb: CallbackQuery) -> None:
    if not await billing.is_admin(cb.from_user.id):
        await cb.answer("Ruxsat yo'q", show_alert=True)
        return

    payment_id = int(cb.data.rsplit(":", 1)[1])
    await billing.reject_payment(payment_id, admin_id=cb.from_user.id)
    await cb.answer("Rad etildi")
    await cb.message.edit_text(f"❌ To'lov #{payment_id} rad etildi")
    await _notify_client(cb, payment_id, approved=False)


# --- Yordamchilar ------------------------------------------------------- #


async def _confirm(message: Message, payment_id: int, admin_id: int) -> None:
    ok = await billing.confirm_payment(payment_id, admin_id=admin_id)
    if not ok:
        await message.answer(f"To'lov #{payment_id} topilmadi yoki allaqachon ishlangan.")
        return
    await message.answer(f"✅ To'lov #{payment_id} tasdiqlandi")
    await _notify_client(message, payment_id, approved=True)


async def _notify_client(
    event: Message | CallbackQuery, payment_id: int, *, approved: bool
) -> None:
    telegram_id = await billing.user_telegram_id(payment_id)
    if not telegram_id:
        return

    text = (
        "✅ <b>To'lovingiz tasdiqlandi!</b>\n\nObunangiz faollashtirildi."
        if approved
        else f"❌ To'lov tasdiqlanmadi.\n\nSavol bo'lsa: {get_settings().support_username}"
    )
    try:
        await event.bot.send_message(telegram_id, text)
    except Exception:
        log.exception("Mijozga xabar yuborilmadi: %s", telegram_id)


def _parse_id(args: str | None) -> int | None:
    if not args:
        return None
    try:
        return int(args.strip().split()[0])
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------- #
# Promokodlar — hamkorlar orqali bepul ulash
# ---------------------------------------------------------------------- #


@router.message(Command("promo_new"))
async def cmd_promo_new(message: Message, command: CommandObject) -> None:
    """Yangi bepul kirish kodi.

    `/promo_new` — Pro, 30 kun, 1 kishiga
    `/promo_new pro 90 10` — Pro, 90 kun, 10 kishiga
    """
    if not await billing.is_admin(message.from_user.id):
        return

    parts = (command.args or "").split()
    plan = Plan.PRO
    days, uses = 30, 1
    try:
        if len(parts) >= 1:
            plan = Plan(parts[0].lower())
        if len(parts) >= 2:
            days = int(parts[1])
        if len(parts) >= 3:
            uses = int(parts[2])
    except (ValueError, KeyError):
        await message.answer(
            "❌ Format: <code>/promo_new pro 90 10</code>\n"
            "(tarif: basic yoki pro · kun · necha kishiga)"
        )
        return

    code = await billing.create_promo(
        plan=plan, days=days, max_uses=uses, created_by=message.from_user.id
    )
    limit = "cheksiz" if uses == 0 else f"{uses} kishiga"
    await message.answer(
        f"✅ <b>Kod tayyor</b>\n\n"
        f"<code>{code}</code>\n\n"
        f"Tarif: <b>{plan.value.upper()}</b> · {days} kun · {limit}\n\n"
        f"Sellerga shu xabarni yuboring:\n"
        f"<blockquote>Botga kiring va shu kodni yuboring: {code}</blockquote>"
    )


@router.message(Command("promos"))
async def cmd_promos(message: Message) -> None:
    """Yaratilgan kodlar ro'yxati."""
    if not await billing.is_admin(message.from_user.id):
        return

    rows = await billing.list_promos()
    if not rows:
        await message.answer("Hozircha kod yaratilmagan.")
        return

    lines = ["🎟 <b>Promokodlar</b>", ""]
    for r in rows:
        limit = "∞" if r["max_uses"] == 0 else r["max_uses"]
        mark = "" if r["active"] else " ⛔"
        lines.append(
            f"<code>{r['code']}</code> · {r['plan'].upper()} · {r['days']} kun · "
            f"{r['used']}/{limit}{mark}"
        )
    lines += ["", "To'xtatish: <code>/promo_off KOD</code>"]
    await message.answer("\n".join(lines))


@router.message(Command("promo_off"))
async def cmd_promo_off(message: Message, command: CommandObject) -> None:
    """Kodni to'xtatish — tarqalib ketgan bo'lsa."""
    if not await billing.is_admin(message.from_user.id):
        return

    code = (command.args or "").strip()
    if not code:
        await message.answer("Format: <code>/promo_off KOD</code>")
        return

    ok = await billing.deactivate_promo(code)
    await message.answer("⛔ Kod to'xtatildi." if ok else "❌ Bunday kod topilmadi.")
