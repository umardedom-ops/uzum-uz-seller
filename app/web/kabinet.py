"""Web-kabinet — seller do'konini brauzerda ko'radi.

Sahifalar serverda yig'iladi (JS freymvork yo'q): kabinet asosan
o'qish uchun, murakkab holat kerak emas — sahifa tez ochiladi va
telefonda ham yaxshi ishlaydi.

Kirish: botdagi `/kabinet` havolasi orqali (`services/web_auth.py`).
"""
from __future__ import annotations

from decimal import Decimal
from html import escape

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.logging import get_logger
from app.services import web_auth
from app.services.exports import list_user_shops, load_report_rows, load_stock_rows

log = get_logger(__name__)
router = APIRouter(prefix="/kabinet", tags=["kabinet"])


def _money(value: Decimal | int | float) -> str:
    return f"{int(value):,}".replace(",", " ")


def _page(title: str, body: str, *, user: web_auth.WebUser | None = None) -> str:
    """Umumiy karkas. Tashqi resurs yo'q — hammasi ichkarida."""
    who = ""
    if user is not None:
        name = escape(user.full_name or user.username or str(user.telegram_id))
        who = (
            f'<div class="who">{name}'
            f'<a class="out" href="/kabinet/chiqish">Chiqish</a></div>'
        )

    return f"""<!doctype html>
<html lang="uz"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
  :root {{
    --bg:#F6F5FB; --card:#FFF; --text:#1A1726; --muted:#6B6580;
    --line:#E7E3F1; --accent:#6D48F0; --good:#16A34A; --bad:#DC2626;
    --warn:#C2790B;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#131019; --card:#1C1826; --text:#ECEAF3; --muted:#9E98AE;
      --line:#2E2940; --accent:#9B7BFF; --good:#4ADE80; --bad:#F87171;
      --warn:#E0A84B; }}
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--text);line-height:1.55;
    font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
  .wrap{{max-width:960px;margin:0 auto;padding:28px 18px 64px}}
  header{{display:flex;justify-content:space-between;align-items:center;
    gap:16px;flex-wrap:wrap;margin-bottom:26px}}
  .brand{{font-weight:800;font-size:19px;letter-spacing:-.01em}}
  .brand span{{color:var(--accent)}}
  .who{{font-size:14px;color:var(--muted);display:flex;gap:12px;align-items:center}}
  .out{{color:var(--accent);text-decoration:none;font-weight:600}}
  h1{{font-size:26px;margin:0 0 6px;letter-spacing:-.02em}}
  .sub{{color:var(--muted);margin:0 0 22px;font-size:14.5px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}}
  .card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:17px}}
  .card .k{{font-size:12.5px;color:var(--muted);text-transform:uppercase;
    letter-spacing:.06em;font-weight:700}}
  .card .v{{font-size:25px;font-weight:800;margin-top:6px;
    font-variant-numeric:tabular-nums}}
  .card .n{{font-size:12.5px;color:var(--muted);margin-top:3px}}
  .v.bad{{color:var(--bad)}} .v.good{{color:var(--good)}} .v.warn{{color:var(--warn)}}
  h2{{font-size:13px;text-transform:uppercase;letter-spacing:.1em;
    color:var(--muted);margin:34px 0 14px}}
  table{{width:100%;border-collapse:collapse;background:var(--card);
    border:1px solid var(--line);border-radius:12px;overflow:hidden}}
  th,td{{text-align:left;padding:11px 14px;border-bottom:1px solid var(--line);font-size:14px}}
  th{{font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}}
  tr:last-child td{{border-bottom:none}}
  td.num{{text-align:right;font-variant-numeric:tabular-nums}}
  .scroll{{overflow-x:auto}}
  .empty{{background:var(--card);border:1px solid var(--line);border-radius:12px;
    padding:22px;color:var(--muted);font-size:14.5px}}
  .note{{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);
    border-radius:10px;padding:14px 16px;font-size:14px;margin-top:26px;color:var(--muted)}}
  .center{{max-width:440px;margin:14vh auto;text-align:center}}
</style></head>
<body><div class="wrap">
<header><div class="brand">UZUM<span>UZBOT</span></div>{who}</header>
{body}
</div></body></html>"""


def _need_login(message: str = "Kirish uchun botdagi havoladan foydalaning.") -> HTMLResponse:
    body = f"""<div class="center">
      <h1>Kirish kerak</h1>
      <p class="sub">{escape(message)}</p>
      <div class="note">Telegram botda <b>/kabinet</b> deb yozing — sizga
      shaxsiy havola keladi. Havola <b>15 daqiqa</b> amal qiladi va
      <b>bir marta</b> ishlatiladi.</div>
    </div>"""
    return HTMLResponse(_page("Kirish — UZUMUZBOT", body), status_code=401)


@router.get("/kirish", response_class=HTMLResponse, response_model=None)
async def login(token: str = "") -> HTMLResponse | RedirectResponse:
    """Bir martalik havola: tokenni cookie'ga almashtiradi.

    Muvaffaqiyatda **redirect** qilamiz — shunda token URL'da qolmaydi
    (brauzer tarixiga tushmaydi). Raqobatchining asosiy xatosi shu edi.
    """
    session_token = await web_auth.redeem_login_token(token)
    if session_token is None:
        return _need_login("Havola eskirgan yoki allaqachon ishlatilgan.")

    response = RedirectResponse(url="/kabinet", status_code=303)
    response.set_cookie(
        web_auth.COOKIE_NAME,
        session_token,
        max_age=int(web_auth.SESSION_TTL.total_seconds()),
        httponly=True,   # JS o'qiy olmaydi (XSS himoyasi)
        secure=True,     # faqat HTTPS
        samesite="lax",  # CSRF himoyasi
        path="/",
    )
    return response


@router.get("/chiqish")
async def logout(request: Request) -> RedirectResponse:
    await web_auth.revoke_session(request.cookies.get(web_auth.COOKIE_NAME))
    response = RedirectResponse(url="/kabinet", status_code=303)
    response.delete_cookie(web_auth.COOKIE_NAME, path="/")
    return response


@router.get("", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Asosiy ekran: do'kon holati bir qarashda."""
    user = await web_auth.user_for_session(request.cookies.get(web_auth.COOKIE_NAME))
    if user is None:
        return _need_login()

    shops = await list_user_shops(user.telegram_id)
    if not shops:
        body = """<h1>Do'kon ulanmagan</h1>
        <p class="sub">Botda <b>/start</b> orqali do'koningizni ulang.</p>"""
        return HTMLResponse(_page("Kabinet — UZUMUZBOT", body, user=user))

    shop = shops[0]
    losses = await load_report_rows(shop.id, only_claimable=True)
    stock = await load_stock_rows(shop.id)

    total_loss = sum((row.loss_amount for row in losses), Decimal("0"))
    blocked = [r for r in stock if r.is_blocked]
    out = [r for r in stock if r.total_qty == 0 and not r.is_blocked]
    low = [r for r in stock if r.needs_attention and not r.is_blocked and r.total_qty > 0]

    cards = f"""<div class="grid">
      <div class="card"><div class="k">Topilgan yo'qotish</div>
        <div class="v {'bad' if total_loss else 'good'}">{_money(total_loss)}</div>
        <div class="n">so'm · {len(losses)} ta holat</div></div>
      <div class="card"><div class="k">Mahsulot</div>
        <div class="v">{len(stock)}</div><div class="n">SKU</div></div>
      <div class="card"><div class="k">Bloklangan</div>
        <div class="v {'bad' if blocked else ''}">{len(blocked)}</div>
        <div class="n">sotuv to'xtagan</div></div>
      <div class="card"><div class="k">Tugagan</div>
        <div class="v {'warn' if out else ''}">{len(out)}</div>
        <div class="n">qoldiq 0</div></div>
      <div class="card"><div class="k">Tugayapti</div>
        <div class="v {'warn' if low else ''}">{len(low)}</div>
        <div class="n">7 kundan kam</div></div>
    </div>"""

    if losses:
        rows = "".join(
            f"<tr><td>{escape(r.title[:52])}</td>"
            f"<td>{escape(r.barcode or '—')}</td>"
            f"<td class='num'>{r.diff_qty}</td>"
            f"<td class='num'>{_money(r.loss_amount)}</td></tr>"
            for r in losses[:15]
        )
        losses_html = f"""<h2>Topilgan yo'qotishlar</h2><div class="scroll"><table>
          <tr><th>Tovar</th><th>Shtrix kod</th><th>Dona</th><th>Summa</th></tr>
          {rows}</table></div>"""
    else:
        losses_html = (
            '<h2>Topilgan yo\'qotishlar</h2>'
            '<div class="empty">Hozircha yo\'qotish topilmadi. '
            'Har kuni tekshirib boramiz.</div>'
        )

    attention = blocked + low
    if attention:
        rows = "".join(
            f"<tr><td>{escape(r.title[:52])}</td>"
            f"<td class='num'>{r.fbo_qty}</td><td class='num'>{r.fbs_qty}</td>"
            f"<td>{escape(r.days_left_label)}</td>"
            f"<td>{escape(r.status_label[:40])}</td></tr>"
            for r in attention[:15]
        )
        stock_html = f"""<h2>Diqqat talab qiladi</h2><div class="scroll"><table>
          <tr><th>Tovar</th><th>FBO</th><th>FBS</th><th>Yetadi</th><th>Holat</th></tr>
          {rows}</table></div>"""
    else:
        stock_html = (
            '<h2>Ombor</h2><div class="empty">Diqqat talab qiladigan tovar yo\'q.</div>'
        )

    more = f" · yana {len(shops) - 1} ta do'kon" if len(shops) > 1 else ""
    title = escape(shop.title or shop.uzum_shop_id)
    shop_line = escape(shop.uzum_shop_id) + escape(more)

    body = (
        f"<h1>{title}</h1>"
        f'<p class="sub">Do\'kon ID: {shop_line}</p>'
        f"{cards}{losses_html}{stock_html}"
        '<div class="note">Hisobot — tahliliy taxmin, yuridik dalil emas. '
        "Da'vo qilishdan oldin tekshiring. Excel va pretenziya botda.</div>"
    )
    return HTMLResponse(_page("Kabinet — UZUMUZBOT", body, user=user))
