# Uzum Seller Bot

Uzum Market sellerlari uchun Telegram bot. Qiymat taklifi: **"hisobot" emas,
"pulingizni qaytaring"** — do'kon ma'lumotlarini kunlik tahlil qilib, Uzum
tomonidan yo'qotilgan yoki ortiqcha ushlangan pulni topadi va da'vo
(pretenziya) uchun hujjat tayyorlaydi.

To'liq texnik topshiriq: [`SPEC.md`](./SPEC.md).

## Qattiq qoidalar (SPEC 9)

1. **Uzum tomoniga faqat GET** — hech qanday yozish amali yo'q.
2. Barcha credential Fernet bilan shifrlangan, logga hech qachon tushmaydi.
3. Har bir do'kon ma'lumoti `shop_id` bo'yicha qat'iy izolyatsiya.

## Texnologiyalar

Python 3.11+ · aiogram 3.x · FastAPI · SQLAlchemy 2.0 (async) · Alembic ·
APScheduler · httpx · openpyxl · python-docx · cryptography.

## Deploy (server)

```bash
cp .env.example .env   # BOT_TOKEN, FERNET_KEY, POSTGRES_PASSWORD to'ldiring
docker compose up -d --build
```

To'liq yo'riqnoma: [`docs/deploy.md`](docs/deploy.md) — Click sozlash,
zaxira nusxa, resurs talablari.

## Boshlash (lokal dev)

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env            # keyin qiymatlarni to'ldiring
python -c "from app.core.security import generate_key; print(generate_key())"   # FERNET_KEY

pytest                            # testlar
```

Lokalda baza — SQLite (`DATABASE_URL` da). Production — PostgreSQL (faqat
`DATABASE_URL` ni almashtiring, kod o'zgarmaydi).

## Struktura

```
app/
  bot/        aiogram: handlers, keyboards, states, texts
  core/       config, security (Fernet), logging
  db/         models, migrations, repositories
  uzum/       Uzum integratsiya (client — FAQAT GET)
  services/   biznes-mantiq: sync, audit, reports
  workers/    scheduler joblari
  docs/       excel va docx generatorlar
tests/
```

## Holat (2026-08-06)

| Bosqich | Holat |
|---|---|
| Phase 0 — API inventarizatsiya | ✅ [docs/api-inventory.md](docs/api-inventory.md) |
| Phase 1 — Skelet, `uzum/` klient | ✅ jonli API'da sinalgan |
| Phase 2 — Ulanish (API kalit oqimi) | ✅ bot ishlaydi |
| DB modellar + Alembic | ✅ 15 jadval |
| Phase 4 — Audit yadrosi (5.1–5.5) | ✅ sof funksiyalar + testlar |
| Phase 5 — Excel + pretenziya | ✅ generatorlar tayyor |
| Phase 3 — Sync + scheduler | ✅ jonli sinaldi |
| Audit yurituvchisi + bot menyusi | ✅ |
| Phase 6 — Monetizatsiya | ⏳ |

**205 test o'tadi.** `pytest` bilan tekshiring.

### Bot bo'limlari

| Bo'lim | Nima qiladi |
|---|---|
| 💰 Yo'qotilgan pul | Davr tanlash (kalendar), 6 xil audit, Excel/PDF/pretenziya |
| 🏷 FBS buyurtmalar | Yig'ish kerak bo'lganlar, yorliqni bir tugma bilan (PDF) |
| 📦 Qoldiqlar | FBO/FBS qoldiq, necha kunga yetadi, blok holati, Excel/PDF |
| 🧮 Yunit-iqtisodiyot | SKU kesimida foyda, ABC, saqlash xarajati, qaytarish tahlili |

**Xabarnomalar** (har soatda): tovar bloklandi · qoldiq tugayapti · rank pasaydi.

### Pul topishning 6 yo'li (raqobatchida — 1 ta)

| # | Audit | Holat |
|---|---|---|
| 5.1 | Yo'qolgan tovar (davr + butun tarix) | ✅ |
| 5.2 | Qaytarish auditi | ✅ |
| 5.3 | Komissiya auditi | ✅ |
| 5.4 | O'lcham nomuvofiqligi → logistika | ✅ |
| 5.5 | Kompensatsiya sverkasi | ✅ |
| — | Saqlash xarajati + o'lik yuk | ✅ |

### Fon vazifalari (APScheduler, Toshkent vaqti)

| Vaqt | Vazifa |
|---|---|
| har soatda | buyurtma / qaytarish / moliya sinxronizatsiyasi |
| 06:00 | qoldiq surati + 5 ta audit |
| 09:00 | kunlik hisobot xabari |

Bot ishga tushganda rejalashtiruvchi avtomatik boshlanadi.

### Ochiq masalalar

1. **FBO ombor qoldig'i API'da yo'q** — 5.1 auditining asosiy qismi uchun
   kabinet kirishi kerak (yagona raqam + Moliya menejeri roli). Raqam
   ro'yxatdan o'tkazilishi kutilmoqda.
2. **Formula haqiqiy ma'lumotda tasdiqlanmagan** — sinov do'koni bo'sh.
   SPEC 10 talabi: sotuvi bor do'konda 3 oylik ma'lumatni qo'lda
   solishtirish. **Bu bajarilmaguncha mahsulot isbotlanmagan.**
3. **Pretenziya matni huquqiy tekshiruvdan o'tmagan** (SPEC 6.2 eslatmasi).

### Namuna hujjatlar

```bash
python -c "import app.docs.excel"   # generatorlar
```

`generated/` papkasida namunalar bor (git'ga kirmaydi).
