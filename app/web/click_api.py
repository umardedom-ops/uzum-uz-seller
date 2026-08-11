"""Click webhook serveri (FastAPI).

Click bizning serverimizga POST yuboradi:

    POST /click/prepare   — to'lovni tekshirish
    POST /click/complete  — to'lovni yakunlash

Kabinetda (merchant.click.uz → Servislar → ✏️) shu manzillar
ko'rsatiladi:

    https://<domen>/click/prepare
    https://<domen>/click/complete

Talablar (Click ko'rsatmasidan):
  * HTTPS va **statik IP**
  * TAS-IX tarmog'ida bo'lmasa — IP ni oldindan Click'ka bildirish
  * Har so'rov va javob jurnalga yozilishi (nizolarni tez hal qilish uchun)
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, FastAPI, Form, Request
from fastapi.responses import HTMLResponse

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.services.click import ClickRequest, handle_complete, handle_prepare

log = get_logger(__name__)
router = APIRouter(prefix="/click", tags=["click"])


def _build(
    click_trans_id: str,
    service_id: str,
    click_paydoc_id: str,
    merchant_trans_id: str,
    amount: str,
    action: str,
    sign_time: str,
    sign_string: str,
    error: str,
    error_note: str,
    merchant_prepare_id: str,
) -> ClickRequest:
    return ClickRequest(
        click_trans_id=click_trans_id,
        service_id=service_id,
        click_paydoc_id=click_paydoc_id,
        merchant_trans_id=merchant_trans_id,
        amount=amount,
        action=action,
        sign_time=sign_time,
        sign_string=sign_string,
        error=error or "0",
        error_note=error_note or "",
        merchant_prepare_id=merchant_prepare_id or "",
    )


@router.post("/prepare")
async def click_prepare(
    request: Request,
    click_trans_id: Annotated[str, Form()] = "",
    service_id: Annotated[str, Form()] = "",
    click_paydoc_id: Annotated[str, Form()] = "",
    merchant_trans_id: Annotated[str, Form()] = "",
    amount: Annotated[str, Form()] = "",
    action: Annotated[str, Form()] = "",
    sign_time: Annotated[str, Form()] = "",
    sign_string: Annotated[str, Form()] = "",
    error: Annotated[str, Form()] = "0",
    error_note: Annotated[str, Form()] = "",
    merchant_prepare_id: Annotated[str, Form()] = "",
) -> dict[str, object]:
    req = _build(
        click_trans_id, service_id, click_paydoc_id, merchant_trans_id,
        amount, action, sign_time, sign_string, error, error_note,
        merchant_prepare_id,
    )
    # Nizolarni tez hal qilish uchun jurnal (imzo va kalit yozilmaydi)
    log.info(
        "Click PREPARE: trans=%s merchant_trans=%s amount=%s ip=%s",
        req.click_trans_id,
        req.merchant_trans_id,
        req.amount,
        request.client.host if request.client else "?",
    )
    result = await handle_prepare(req)
    log.info("Click PREPARE javob: %s", result)
    return result


@router.post("/complete")
async def click_complete(
    request: Request,
    click_trans_id: Annotated[str, Form()] = "",
    service_id: Annotated[str, Form()] = "",
    click_paydoc_id: Annotated[str, Form()] = "",
    merchant_trans_id: Annotated[str, Form()] = "",
    amount: Annotated[str, Form()] = "",
    action: Annotated[str, Form()] = "",
    sign_time: Annotated[str, Form()] = "",
    sign_string: Annotated[str, Form()] = "",
    error: Annotated[str, Form()] = "0",
    error_note: Annotated[str, Form()] = "",
    merchant_prepare_id: Annotated[str, Form()] = "",
) -> dict[str, object]:
    req = _build(
        click_trans_id, service_id, click_paydoc_id, merchant_trans_id,
        amount, action, sign_time, sign_string, error, error_note,
        merchant_prepare_id,
    )
    log.info(
        "Click COMPLETE: trans=%s merchant_trans=%s prepare=%s amount=%s ip=%s",
        req.click_trans_id,
        req.merchant_trans_id,
        req.merchant_prepare_id,
        req.amount,
        request.client.host if request.client else "?",
    )
    result = await handle_complete(req)
    log.info("Click COMPLETE javob: %s", result)

    # To'lov o'tgan bo'lsa mijozga xabar beramiz
    if result.get("error") == 0:
        await _notify_client(req.merchant_trans_id)

    return result


async def _notify_client(merchant_trans_id: str) -> None:
    """Obuna faollashgani haqida mijozga xabar.

    Xabar yuborilmasa ham to'lov javobiga ta'sir qilmasligi kerak —
    aks holda Click to'lovni xato deb hisoblaydi.
    """
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from app.services import billing

    try:
        payment_id = int(merchant_trans_id)
    except (TypeError, ValueError):
        return

    telegram_id = await billing.user_telegram_id(payment_id)
    if not telegram_id:
        return

    settings = get_settings()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        access = await billing.get_access(telegram_id)
        await bot.send_message(
            telegram_id,
            "✅ <b>To'lov qabul qilindi!</b>\n\n"
            f"Obunangiz faollashtirildi — {access.days_left} kun.\n"
            "Rahmat, ishni davom ettiramiz.",
        )
    except Exception:
        log.exception("Mijozga xabar yuborilmadi: %s", telegram_id)
    finally:
        await bot.session.close()


def create_app() -> FastAPI:
    """Webhook ilovasi.

    Ishga tushirish:
        uvicorn app.web.click_api:app --host 0.0.0.0 --port 8000
    """
    settings = get_settings()
    setup_logging(settings.log_level)

    application = FastAPI(title="Uzum Seller Bot", docs_url=None)
    application.include_router(router)

    # Web-kabinet — seller do'konini brauzerda ko'radi
    from app.web.kabinet import router as kabinet_router

    application.include_router(kabinet_router)

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "click": "on" if settings.click_enabled else "off"}

    @application.get("/oferta", response_class=HTMLResponse)
    async def oferta() -> HTMLResponse:
        """Ommaviy oferta — botdagi havola shu yerga olib keladi.

        Alohida hosting kerak emas: hujjat shu server orqali beriladi.
        """
        path = Path(__file__).parent / "static" / "oferta.html"
        if not path.exists():
            return HTMLResponse("Oferta hujjati topilmadi", status_code=404)
        return HTMLResponse(path.read_text(encoding="utf-8"))

    return application


app = create_app()
