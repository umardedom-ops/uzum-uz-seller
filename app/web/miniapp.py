"""Telegram Mini App — do'kon holati Telegram ichida.

Ikki so'rov:

    GET  /app            — qobiq (HTML + kichik JS)
    POST /app/dashboard  — ma'lumot, `Authorization: tma <initData>` bilan

Nega ikkitaga bo'lingan: Telegram `initData` ni **URL'ga qo'ymaydi**, u
faqat sahifa ichidagi `window.Telegram.WebApp.initData` da bo'ladi.
Shuning uchun avval qobiq yuklanadi, keyin JS imzoni sarlavhada yuboradi.
Sahifa mazmuni baribir **serverda** yig'iladi — kabinetdagi kabi, JS
freymvorki yo'q.

**Kirish sharti ikkita** (SPEC: mahsulot pullik):
  1. obuna faol (sinov ham hisoblanadi)
  2. do'kon ulangan

Ikkalasi ham bo'lmasa ochiq sabab va chiqish yo'li ko'rsatiladi —
bo'sh ekran qoldirilmaydi.
"""
from __future__ import annotations

from decimal import Decimal
from html import escape

from fastapi import APIRouter, Header
from fastapi.responses import HTMLResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services import billing
from app.services.exports import find_user_shop, load_report_rows, load_stock_rows
from app.services.telegram_webapp import InitDataError, WebAppUser, verify_init_data

log = get_logger(__name__)
router = APIRouter(prefix="/app", tags=["miniapp"])


def _money(value: Decimal | int | float) -> str:
    """149000 → «149 000». Ajratgich uzilmas probel — narx bo'linmaydi."""
    return f"{int(value):,}".replace(",", " ")


def _auth(header: str | None) -> WebAppUser:
    """`Authorization: tma <initData>` — Telegram'ning o'z shakli."""
    raw = (header or "").strip()
    prefix = "tma "
    if not raw.lower().startswith(prefix):
        raise InitDataError("Authorization sarlavhasi `tma <initData>` shaklida emas")
    return verify_init_data(raw[len(prefix):], get_settings().bot_token)


# ---------------------------------------------------------------------- #
# Qobiq
# ---------------------------------------------------------------------- #

_SHELL = """<!doctype html>
<html lang="uz"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Kabinet</title>
<!-- Telegram SDK. `integrity` ATAYLAB qo'yilmagan: Telegram bu faylni
     ogohlantirmasdan yangilaydi va qat'iy xesh qo'yilsa ilova o'sha
     kuni jimgina ochilmay qoladi. Boshqa tashqi manba yo'q. -->
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root{
    --bg:var(--tg-theme-bg-color,#F6F5FB);
    --card:var(--tg-theme-secondary-bg-color,#FFFFFF);
    --text:var(--tg-theme-text-color,#1A1726);
    --muted:var(--tg-theme-hint-color,#6B6580);
    --accent:var(--tg-theme-link-color,#6D48F0);
    --line:rgba(128,128,128,.22);
    --bad:#DC2626; --warn:#C2790B; --ok:#16A34A;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    line-height:1.5;padding:14px 14px calc(14px + env(safe-area-inset-bottom))}
  .tnum{font-variant-numeric:tabular-nums}
  .chip{display:inline-flex;gap:6px;align-items:center;background:var(--card);
    border:1px solid var(--line);color:var(--accent);border-radius:999px;
    padding:6px 12px;font-size:13px;font-weight:600;margin-bottom:12px}
  .tiles{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px}
  .tile{background:var(--card);border:1px solid var(--line);
    border-radius:13px;padding:12px}
  .tile.wide{grid-column:1/-1}
  .k{font-size:10px;font-weight:700;text-transform:uppercase;
    letter-spacing:.07em;color:var(--muted)}
  .v{font-size:22px;font-weight:800;margin-top:3px;line-height:1.15}
  .tile.wide .v{font-size:28px}
  .n{font-size:11px;color:var(--muted);margin-top:2px}
  .bad{color:var(--bad)} .warn{color:var(--warn)} .ok{color:var(--ok)}
  h2{font-size:11px;font-weight:700;text-transform:uppercase;
    letter-spacing:.09em;color:var(--muted);margin:18px 0 9px}
  .row{display:flex;align-items:center;gap:10px;padding:10px 12px;
    background:var(--card);border:1px solid var(--line);border-radius:11px;
    border-left:3px solid var(--line);margin-bottom:7px}
  .row.crit{border-left-color:var(--bad)} .row.low{border-left-color:var(--warn)}
  .row .t{flex:1;min-width:0}
  .row .t strong{display:block;font-size:13px;font-weight:600;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .row .t span{font-size:11px;color:var(--muted)}
  .pill{font-size:10px;font-weight:700;padding:3px 8px;border-radius:6px;
    white-space:nowrap;border:1px solid var(--line);color:var(--muted)}
  .pill.crit{color:var(--bad)} .pill.low{color:var(--warn)}
  .note{background:var(--card);border:1px solid var(--line);
    border-left:3px solid var(--accent);border-radius:10px;padding:13px 15px;
    font-size:13px;color:var(--muted);margin-top:20px}
  .center{text-align:center;padding:16vh 8px}
  .center h1{font-size:20px;margin:0 0 8px}
  .center p{color:var(--muted);font-size:14.5px;margin:0 auto;max-width:32ch}
  .skel{background:var(--card);border:1px solid var(--line);border-radius:13px;
    height:74px;margin-bottom:8px;opacity:.55}
  @media (prefers-reduced-motion:no-preference){
    .skel{animation:pulse 1.4s ease-in-out infinite}
    @keyframes pulse{50%{opacity:.28}}
  }
</style></head>
<body>
<div id="root">
  <div class="skel" style="height:26px;width:45%"></div>
  <div class="skel"></div><div class="skel"></div>
</div>
<script>
(function () {
  var tg = window.Telegram && window.Telegram.WebApp;
  var root = document.getElementById('root');

  function fail(title, text) {
    root.innerHTML = '<div class="center"><h1></h1><p></p></div>';
    root.querySelector('h1').textContent = title;
    root.querySelector('p').textContent = text;
  }

  if (!tg || !tg.initData) {
    fail('Telegram ichida oching',
         'Bu sahifa botdagi «Kabinet» tugmasi orqali ochiladi.');
    return;
  }

  tg.ready();
  tg.expand();
  if (tg.disableVerticalSwipes) { tg.disableVerticalSwipes(); }

  fetch('/app/dashboard', {
    method: 'POST',
    headers: { 'Authorization': 'tma ' + tg.initData }
  })
  .then(function (r) { return r.text().then(function (t) { return [r.ok, t]; }); })
  .then(function (p) {
    // `innerHTML` — mazmun O'Z serverimizdan keladi va u yerda hamma
    // matn `html.escape()` dan o'tadi (tovar nomlari Uzum'dan kelgani
    // uchun bu majburiy). Foydalanuvchi kiritgan matn bu yerga tushmaydi.
    root.innerHTML = p[1];
    if (!p[0] && tg.HapticFeedback) {
      tg.HapticFeedback.notificationOccurred('error');
    }
  })
  .catch(function () {
    fail('Ulanib bo\\'lmadi', 'Internet aloqasini tekshiring va qayta oching.');
  });
})();
</script>
</body></html>"""


@router.get("", response_class=HTMLResponse)
async def shell() -> HTMLResponse:
    """Qobiq. Ma'lumot yo'q — u ikkinchi so'rovda keladi."""
    return HTMLResponse(_SHELL)


# ---------------------------------------------------------------------- #
# Ma'lumot
# ---------------------------------------------------------------------- #


def _gate(title: str, text: str) -> HTMLResponse:
    """Kirish yopiq — sabab va chiqish yo'li bilan."""
    return HTMLResponse(
        f'<div class="center"><h1>{escape(title)}</h1>'
        f"<p>{escape(text)}</p></div>",
        status_code=200,  # Telegram ichida xato kodi foyda bermaydi
    )


@router.post("/dashboard", response_class=HTMLResponse)
async def dashboard(authorization: str | None = Header(default=None)) -> HTMLResponse:
    """Bosh ekran. Kirish sharti: faol obuna **va** ulangan do'kon."""
    try:
        user = _auth(authorization)
    except InitDataError as exc:
        # Sabab log'da qoladi, foydalanuvchiga esa umumiy xabar —
        # soxta so'rov yuborayotgan odamga yo'l ko'rsatmaymiz.
        log.warning("Mini App kirish rad etildi: %s", exc)
        return _gate("Kirish tasdiqlanmadi", "Botga qayting va «Kabinet» tugmasini qayta bosing.")

    access = await billing.get_access(user.telegram_id)
    if not access.is_active:
        return _gate(
            "Obuna tugagan",
            "Kabinet obuna bilan ishlaydi. Botda «Tarif» bo'limidan uzaytiring.",
        )

    shop = await find_user_shop(user.telegram_id)
    if shop is None:
        return _gate(
            "Do'kon ulanmagan",
            "Botda /start orqali Uzum API kalitingizni yuboring — "
            "ma'lumot shundan keyin ko'rinadi.",
        )

    return HTMLResponse(await _render(shop))


async def _render(shop: object) -> str:
    """Kartochkalar va diqqat talab qiladigan tovarlar.

    Manba — kabinet bilan bir xil (`services/exports`), shuning uchun
    veb-kabinet va Mini App hech qachon boshqa raqam ko'rsatmaydi.
    """
    shop_id = shop.id  # type: ignore[attr-defined]
    losses = await load_report_rows(shop_id, only_claimable=True)
    stock = await load_stock_rows(shop_id)

    total_loss = sum((row.loss_amount for row in losses), Decimal("0"))
    blocked = [r for r in stock if r.is_blocked]
    out = [r for r in stock if r.total_qty == 0 and not r.is_blocked]
    low = [r for r in stock if r.needs_attention and not r.is_blocked and r.total_qty > 0]

    title = escape(str(getattr(shop, "title", None) or getattr(shop, "uzum_shop_id", "")))
    parts = [
        f'<div class="chip">{title}</div>',
        '<div class="tiles">',
        '<div class="tile wide"><div class="k">Topilgan yo\'qotish</div>'
        f'<div class="v tnum {"bad" if total_loss else "ok"}">{_money(total_loss)}</div>'
        f'<div class="n">so\'m · {len(losses)} ta holat · tekshirilishi kerak</div></div>',
        f'<div class="tile"><div class="k">Mahsulot</div>'
        f'<div class="v tnum">{len(stock)}</div><div class="n">SKU</div></div>',
        f'<div class="tile"><div class="k">Bloklangan</div>'
        f'<div class="v tnum {"bad" if blocked else ""}">{len(blocked)}</div>'
        f'<div class="n">sotuv to\'xtagan</div></div>',
        f'<div class="tile"><div class="k">Tugagan</div>'
        f'<div class="v tnum {"warn" if out else ""}">{len(out)}</div>'
        f'<div class="n">qoldiq 0</div></div>',
        f'<div class="tile"><div class="k">Tugayapti</div>'
        f'<div class="v tnum {"warn" if low else ""}">{len(low)}</div>'
        f'<div class="n">7 kundan kam</div></div>',
        "</div>",
    ]

    attention = blocked + low
    if attention:
        parts.append("<h2>Diqqat talab qiladi</h2>")
        for row in attention[:20]:
            crit = row in blocked
            parts.append(
                f'<div class="row {"crit" if crit else "low"}"><div class="t">'
                f"<strong>{escape(row.title[:52])}</strong>"
                f'<span>FBO {row.fbo_qty} · FBS {row.fbs_qty}</span></div>'
                f'<span class="pill {"crit" if crit else "low"}">'
                f'{escape(row.status_label[:18] if crit else row.days_left_label)}'
                "</span></div>"
            )
    else:
        parts.append(
            '<h2>Ombor</h2><div class="note">Diqqat talab qiladigan tovar yo\'q.</div>'
        )

    parts.append(
        '<div class="note">Hisobot — tahliliy taxmin, yuridik dalil emas. '
        "Da'vo qilishdan oldin tekshiring. Excel va pretenziya botda.</div>"
    )
    return "".join(parts)
