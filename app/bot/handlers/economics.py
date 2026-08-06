"""«Yunit-iqtisodiyot» bo'limi.

Ustunligimiz: tannarxni sellerdan so'ramaymiz — Uzum `sellerProfit` va
`purchasePrice` ni o'zi beradi. Raqobatchida bu qo'lda kiritiladi.

Ekranda uch narsa: umumiy foyda, zarar keltiruvchi tovarlar, va
omborda pul yeyayotgan o'lik yuk.
"""
from __future__ import annotations

from datetime import date, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.texts import DEFAULT_LANG, LANGS, t
from app.core.logging import get_logger
from app.docs.economics_report import build_economics_excel, build_economics_pdf
from app.docs.numbers import format_money
from app.services import economics, returns_analysis
from app.services.exports import find_user_shop

log = get_logger(__name__)
router = Router(name="economics")

GENERATED_DIR = "generated"
DEFAULT_DAYS = 30


def _kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_excel_short", lang), callback_data="econ:xlsx"
                ),
                InlineKeyboardButton(
                    text=t("btn_pdf_short", lang), callback_data="econ:pdf"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_returns", lang), callback_data="econ:returns"
                )
            ],
        ]
    )


@router.message(F.text.in_({t("menu_unit_econ", lg) for lg in LANGS}))
async def on_economics(message: Message, state: FSMContext) -> None:
    lang = await _lang(state)

    shop = await find_user_shop(message.from_user.id)
    if shop is None:
        await message.answer(t("no_shop", lang))
        return

    await state.update_data(shop_id=shop.id)
    status = await message.answer(t("analyzing", lang))

    today = date.today()
    summary = await economics.collect(
        shop.id, today - timedelta(days=DEFAULT_DAYS), today
    )

    if not summary.rows:
        await status.edit_text(t("econ_empty", lang))
        return

    await status.edit_text(_render(summary, lang), reply_markup=_kb(lang))


def _render(summary: economics.EconomicsSummary, lang: str) -> str:
    lines = [
        t(
            "econ_header",
            lang,
            start=f"{summary.period_from:%d.%m}",
            end=f"{summary.period_to:%d.%m.%Y}",
        ),
        "",
        t("econ_revenue", lang, value=format_money(summary.revenue)),
        t("econ_commission", lang, value=format_money(summary.commission)),
        t("econ_logistics", lang, value=format_money(summary.logistics)),
    ]

    if summary.storage > 0:
        lines.append(t("econ_storage", lang, value=format_money(summary.storage)))

    lines += [
        "",
        t(
            "econ_profit",
            lang,
            value=format_money(summary.profit),
            margin=summary.margin_pct,
        ),
    ]

    # ABC — qaysi tovarlar daromad beradi
    a_class = summary.by_class("A")
    if a_class:
        lines += [
            "",
            t("econ_abc", lang, a=len(a_class), b=len(summary.by_class("B")),
              c=len(summary.by_class("C"))),
        ]

    # Zarar keltiruvchilar — darhol ko'rinadigan muammo
    losers = summary.loss_makers
    if losers:
        lines += ["", t("econ_losers", lang, count=len(losers))]
        for row in losers[:5]:
            lines.append(
                f"  📉 {row.title[:32]} — {format_money(row.profit)} so'm"
            )

    # O'lik yuk — omborda pul yeyayotganlar
    dead = summary.dead_stock
    if dead:
        dead_storage = sum((r.storage for r in dead), start=summary.storage * 0)
        lines += ["", t("econ_dead", lang, count=len(dead))]
        if dead_storage > 0:
            lines.append(t("econ_dead_cost", lang, value=format_money(dead_storage)))

    return "\n".join(lines)


@router.callback_query(F.data.in_({"econ:xlsx", "econ:pdf"}))
async def on_export(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    shop = await find_user_shop(cb.from_user.id)
    if shop is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    today = date.today()
    summary = await economics.collect(
        shop.id, today - timedelta(days=DEFAULT_DAYS), today
    )
    if not summary.rows:
        await cb.answer(t("econ_empty", lang), show_alert=True)
        return

    await cb.answer()
    name = shop.uzum_shop_id
    title = shop.title or name

    if cb.data.endswith("pdf"):
        path = build_economics_pdf(
            summary, f"{GENERATED_DIR}/iqtisodiyot-{name}.pdf", shop_title=title
        )
    else:
        path = build_economics_excel(
            summary, f"{GENERATED_DIR}/iqtisodiyot-{name}.xlsx"
        )

    await cb.message.answer_document(FSInputFile(path), caption=t("econ_caption", lang))


@router.callback_query(F.data == "econ:returns")
async def on_returns(cb: CallbackQuery, state: FSMContext) -> None:
    lang = await _lang(state)
    shop = await find_user_shop(cb.from_user.id)
    if shop is None:
        await cb.answer(t("no_shop", lang), show_alert=True)
        return

    await cb.answer()
    today = date.today()
    summary = await returns_analysis.collect(
        shop.id, today - timedelta(days=DEFAULT_DAYS), today
    )

    if summary.total_sold == 0:
        await cb.message.answer(t("returns_empty", lang))
        return

    lines = [
        t("returns_header", lang),
        "",
        t(
            "returns_overall",
            lang,
            returned=summary.total_returned,
            sold=summary.total_sold,
            pct=summary.overall_pct,
        ),
    ]

    if summary.top_reasons:
        lines += ["", t("returns_reasons", lang)]
        lines += [f"  • {reason} — {count} ta" for reason, count in summary.top_reasons]

    tips = returns_analysis.build_recommendations(summary)
    if tips:
        lines += ["", t("returns_problem", lang)]
        lines += [f"  ⚠️ {tip}" for tip in tips]
    else:
        lines += ["", t("returns_ok", lang)]

    await cb.message.answer("\n".join(lines))


async def _lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", DEFAULT_LANG)
