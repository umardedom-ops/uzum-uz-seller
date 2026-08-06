"""«Yo'qotilgan pul» bo'limi — mahsulotning asosiy ekrani (SPEC 7).

Oqim: davr tanlash → audit yuritish → natija → Excel/pretenziya.

Davrni ikki xil tanlash mumkin: tayyor tugmalar (bugun, hafta, oy) yoki
kalendar orqali aniq oraliq.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.bot.keyboards.calendar import build_calendar, parse_calendar_callback
from app.bot.keyboards.period import period_kb, resolve_preset, results_kb
from app.bot.texts import DEFAULT_LANG, LANGS, t
from app.core.logging import get_logger
from app.db.models import Discrepancy
from app.docs.claim import build_claim
from app.docs.excel import build_report
from app.docs.models import KIND_LABELS, ClaimContext
from app.docs.numbers import format_money
from app.docs.pdf import build_report_pdf
from app.services import audit_runner
from app.services.exports import find_user_shop, history_range, load_report_rows

log = get_logger(__name__)
router = Router(name="money")

GENERATED_DIR = Path("generated")


# ---------------------------------------------------------------------- #
# 1. Bo'limga kirish → davr tanlash
# ---------------------------------------------------------------------- #


@router.message(F.text.in_({t("menu_lost_money", lg) for lg in LANGS}))
async def on_lost_money(message: Message, state: FSMContext) -> None:
    lang = await _lang(state)

    shop = await find_user_shop(message.from_user.id)
    if shop is None:
        await message.answer(t("no_shop", lang))
        return

    await state.update_data(shop_id=shop.id)
    await message.answer(await _period_prompt(shop.id, lang), reply_markup=period_kb(lang))


@router.callback_query(F.data == "money:period")
async def on_change_period(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    shop_id = await _shop_id(cb, state)
    if shop_id is None:
        return
    await cb.message.answer(await _period_prompt(shop_id, lang), reply_markup=period_kb(lang))
    await cb.answer()


async def _period_prompt(shop_id: int, lang: str) -> str:
    """Davr tanlash matni + mavjud tarix chegarasi.

    Tarix chegarasini ochiq ko'rsatamiz: seller 3 oylik davr tanlab,
    "nega bo'sh?" deb hayron bo'lmasin.
    """
    first, last = await history_range(shop_id)
    text = t("choose_period", lang)
    if first and last:
        days = (last - first).days + 1
        text += "\n\n" + t(
            "history_available",
            lang,
            start=f"{first:%d.%m.%Y}",
            end=f"{last:%d.%m.%Y}",
            days=days,
        )
    else:
        text += "\n\n" + t("history_empty", lang)
    return text


# ---------------------------------------------------------------------- #
# 2. Tayyor davr
# ---------------------------------------------------------------------- #


@router.callback_query(F.data.startswith("period:"))
async def on_period(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    key = cb.data.split(":", 1)[1]

    shop_id = await _shop_id(cb, state)
    if shop_id is None:
        return

    if key == "custom":
        first, _ = await history_range(shop_id)
        today = date.today()
        await state.update_data(cal_min=first.isoformat() if first else None)
        await cb.message.edit_text(
            t("pick_start_date", lang),
            reply_markup=build_calendar(
                today.year, today.month, "from", lang, min_date=first, max_date=today
            ),
        )
        await cb.answer()
        return

    first, _ = await history_range(shop_id)
    period_from, period_to = resolve_preset(key, date.today(), first)
    await cb.answer()
    # "Butun tarix" — qoldiq tarixiga bog'liq emas: harakatlar yig'indisi
    # bo'yicha hisoblanadi, shuning uchun ulangan kuniyoq ishlaydi.
    await _run_and_show(
        cb, state, shop_id, period_from, period_to, lang, cumulative=(key == "all")
    )


# ---------------------------------------------------------------------- #
# 3. Kalendar
# ---------------------------------------------------------------------- #


@router.callback_query(F.data == "cal:noop")
async def on_calendar_noop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(F.data.startswith("cal:"))
async def on_calendar(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    parsed = parse_calendar_callback(cb.data)
    if parsed is None:
        await cb.answer()
        return

    mode, action, value = parsed
    data = await state.get_data()
    cal_min = date.fromisoformat(data["cal_min"]) if data.get("cal_min") else None
    today = date.today()

    if action == "nav":
        year, month = (int(x) for x in value.split("-"))
        # Tugash sanasini tanlayotganda boshlanishdan oldingisi bloklanadi
        min_date = cal_min
        if mode == "to" and data.get("period_from"):
            min_date = date.fromisoformat(data["period_from"])
        await cb.message.edit_reply_markup(
            reply_markup=build_calendar(
                year, month, mode, lang, min_date=min_date, max_date=today
            )
        )
        await cb.answer()
        return

    picked = date.fromisoformat(value)

    if mode == "from":
        await state.update_data(period_from=picked.isoformat())
        await cb.message.edit_text(
            t("pick_end_date", lang, start=f"{picked:%d.%m.%Y}"),
            reply_markup=build_calendar(
                picked.year, picked.month, "to", lang, min_date=picked, max_date=today
            ),
        )
        await cb.answer()
        return

    # mode == "to"
    period_from = date.fromisoformat(data.get("period_from", picked.isoformat()))
    shop_id = await _shop_id(cb, state)
    if shop_id is None:
        return
    await cb.answer()
    await _run_and_show(cb, state, shop_id, period_from, picked, lang)


# ---------------------------------------------------------------------- #
# 4. Audit yuritish va natija
# ---------------------------------------------------------------------- #


async def _run_and_show(
    cb: CallbackQuery,
    state: FSMContext,
    shop_id: int,
    period_from: date,
    period_to: date,
    lang: str,
    *,
    cumulative: bool = False,
) -> None:
    await state.update_data(
        period_from=period_from.isoformat(), period_to=period_to.isoformat()
    )

    status = await cb.message.answer(t("analyzing", lang))
    try:
        await audit_runner.run_audit(
            shop_id, period_from, period_to, cumulative=cumulative
        )
    except Exception:
        log.exception("Audit xatosi: shop_id=%s", shop_id)
        await status.edit_text(t("error", lang))
        return

    rows = await load_report_rows(
        shop_id, period_from=period_from, period_to=period_to
    )
    header = t(
        "period_label", lang, start=f"{period_from:%d.%m.%Y}", end=f"{period_to:%d.%m.%Y}"
    )

    if not rows:
        first, _ = await history_range(shop_id)
        hint = ""
        if first and period_from < first:
            hint = "\n\n" + t("period_before_history", lang, start=f"{first:%d.%m.%Y}")
        await status.edit_text(f"{header}\n\n{t('no_losses_yet', lang)}{hint}")
        return

    findings = await audit_runner.get_findings(shop_id, only_claimable=True)
    await status.edit_text(
        f"{header}\n\n{_render_summary(findings, lang)}",
        reply_markup=results_kb(lang),
    )


def _render_summary(findings: list[Discrepancy], lang: str) -> str:
    totals: dict[str, Decimal] = {}
    for item in findings:
        label = KIND_LABELS.get(item.kind, item.kind.value)
        totals[label] = totals.get(label, Decimal("0")) + (item.amount or Decimal("0"))

    total = sum(totals.values(), Decimal("0"))
    lines = [t("losses_header_short", lang), ""]
    for label, amount in sorted(totals.items(), key=lambda x: -x[1]):
        lines.append(f"• {label}: <b>{format_money(amount)}</b> so'm")
    lines += ["", t("losses_total", lang, total=format_money(total))]
    return "\n".join(lines)


# ---------------------------------------------------------------------- #
# 5. Hujjatlar
# ---------------------------------------------------------------------- #


@router.callback_query(F.data.in_({"money:xlsx", "money:pdf"}))
async def on_export(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    shop_id = await _shop_id(cb, state)
    if shop_id is None:
        return

    period_from, period_to = await _selected_period(state)
    rows = await load_report_rows(shop_id, period_from=period_from, period_to=period_to)
    if not rows:
        await cb.answer(t("no_losses_yet", lang), show_alert=True)
        return

    await cb.answer()
    shop = await find_user_shop(cb.from_user.id)
    name = shop.uzum_shop_id if shop else str(shop_id)

    if cb.data.endswith("pdf"):
        path = build_report_pdf(
            rows,
            GENERATED_DIR / f"hisobot-{name}-{period_to}.pdf",
            shop_title=(shop.title if shop else "") or name,
            period_from=period_from,
            period_to=period_to,
        )
    else:
        path = build_report(rows, GENERATED_DIR / f"hisobot-{name}-{period_to}.xlsx")

    await cb.message.answer_document(FSInputFile(path), caption=t("excel_caption", lang))


@router.callback_query(F.data == "money:claim")
async def on_claim(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    shop = await find_user_shop(cb.from_user.id)
    if shop is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    period_from, period_to = await _selected_period(state)
    rows = await load_report_rows(shop.id, period_from=period_from, period_to=period_to)
    if not rows:
        await cb.answer(t("no_losses_yet", lang), show_alert=True)
        return

    await cb.answer()
    today = date.today()
    ctx = ClaimContext(
        seller_name=t("claim_seller_placeholder", lang),
        seller_requisites="",
        shop_title=shop.title or shop.uzum_shop_id,
        shop_id=shop.uzum_shop_id,
        period_from=period_from or min(r.period_from for r in rows),
        period_to=period_to or max(r.period_to for r in rows),
        rows=rows,
        created_on=today,
    )
    path = build_claim(
        ctx, GENERATED_DIR / f"pretenziya-{shop.uzum_shop_id}-{ctx.period_to}.docx"
    )
    await cb.message.answer_document(FSInputFile(path), caption=t("claim_caption", lang))


# ---------------------------------------------------------------------- #
# Yordamchilar
# ---------------------------------------------------------------------- #


async def _lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", DEFAULT_LANG)


async def _shop_id(cb: CallbackQuery, state: FSMContext) -> int | None:
    """Holatdagi do'kon; yo'q bo'lsa bazadan qidiradi (bot qayta yuklangan)."""
    data = await state.get_data()
    if (shop_id := data.get("shop_id")) is not None:
        return shop_id

    shop = await find_user_shop(cb.from_user.id)
    if shop is None:
        await cb.answer(t("no_shop", await _lang(state)), show_alert=True)
        return None
    await state.update_data(shop_id=shop.id)
    return shop.id


async def _selected_period(state: FSMContext) -> tuple[date | None, date | None]:
    data = await state.get_data()
    start = data.get("period_from")
    end = data.get("period_to")
    return (
        date.fromisoformat(start) if start else None,
        date.fromisoformat(end) if end else None,
    )
