# Deploy — EasyPanel / VPS

Ikkita jarayon ishlaydi:

| Xizmat | Nima qiladi |
|---|---|
| `bot` | Telegram bot + rejalashtiruvchi (sync, audit, kunlik hisobot, alertlar) |
| `web` | Click webhook serveri (`/click/prepare`, `/click/complete`) |
| `db` | PostgreSQL 16 |

Migratsiyalar `bot` konteynerida avtomatik qo'llanadi.

---

## 1. Serverga fayllarni yuklash

Git orqali (tavsiya etiladi) yoki arxiv bilan. Git bo'lsa:

```bash
git clone <repo> /opt/uzumbot && cd /opt/uzumbot
```

## 2. `.env` tayyorlash

```bash
cp .env.example .env
nano .env
```

**Majburiy to'ldiriladigan qatorlar:**

```ini
BOT_TOKEN=<BotFather tokeni>
FERNET_KEY=<pastdagi buyruq bilan generatsiya qiling>
POSTGRES_PASSWORD=<kuchli parol>
ENV=prod
```

Fernet kalitni generatsiya qilish:

```bash
docker compose run --rm bot python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> ⚠️ **`FERNET_KEY` ni keyinchalik o'zgartirmang.** U bilan sellerlarning
> API kalitlari shifrlangan — almashtirsangiz hammasi o'qib bo'lmaydigan
> holga keladi va barcha mijozlar qayta ulanishi kerak bo'ladi.

`ADMIN_IDS` ni to'ldirish **shart emas** — botga birinchi `/start` bosgan
odam avtomatik admin bo'ladi.

## 3. Ishga tushirish

```bash
docker compose up -d --build
docker compose logs -f bot
```

Loglarda quyidagi ko'rinishi kerak:

```
→ Migratsiyalar qo'llanmoqda...
→ Bot ishga tushmoqda
Bot ishga tushdi: @<username> (env=prod)
Rejalashtiruvchi ishga tushdi: 3 job
```

## 4. Birinchi admin

Botga **birinchi bo'lib siz** `/start` bosing — avtomatik admin bo'lasiz.
Keyin `/admin` bilan panelni oching.

> Boshqa odam oldin bossa, u admin bo'lib qoladi. Shu sababli botni
> ishga tushirgach darhol o'zingiz kiring.

---

## 5. Click integratsiyasi

### 5.1 Domen va HTTPS

EasyPanel `web` xizmatiga domenni **o'zi beradi** (masalan
`uzumbot-web.xxxxxx.easypanel.host`) va HTTPS'ni avtomatik sozlaydi.
Alohida VPS yoki hosting sotib olish shart emas.

EasyPanel'da: xizmat → **Domains** → port **8000** ni ko'rsating.

Natijada quyidagi manzillar ishlaydi:

```
https://<domen>/health            → {"status":"ok"}
https://<domen>/oferta            → ommaviy oferta hujjati
https://<domen>/click/prepare     → POST (Click uchun)
https://<domen>/click/complete    → POST (Click uchun)
```

Tekshirish:

```bash
curl https://<domen>/health
```

### 5.1-bis `.env` ni to'ldirish

Domen ma'lum bo'lgach:

```ini
CLICK_BASE_URL=https://<domen>
OFERTA_URL=https://<domen>/oferta
```

> Oferta hujjati shu serverdan beriladi — alohida sayt kerak emas.
> Matni: `app/web/static/oferta.html`. Sariq bilan belgilangan
> joylarni (tashkilot nomi, STIR, manzil) to'ldiring.

### 5.2 Click tomonidagi sozlash

1. `.env` ga yozing:
   ```ini
   CLICK_SERVICE_ID=...
   CLICK_MERCHANT_ID=...
   CLICK_SECRET_KEY=...
   CLICK_BASE_URL=https://<domen>
   ```
   Keyin: `docker compose up -d`

2. **merchant.click.uz** → *Сервисы* → ✏️ (Действие ustuni) →
   - Prepare URL: `https://<domen>/click/prepare`
   - Complete URL: `https://<domen>/click/complete`

3. Click guruhiga yozing:
   - servisni **yoqishlarini** so'rang (standart holatda o'chiq)
   - agar server **TAS-IX da bo'lmasa** — domen, **IP** va portni bering
     (oq ro'yxatga qo'shish uchun)

4. `docs.click.uz/click-api-testing` orqali testdan o'ting —
   **real to'lovdan oldin**

> **Muhim:** Click statik IP talab qiladi. IP yoki domenni
> o'zgartirishdan **oldin** Click'ka xabar bering.

---

## 6. Kundalik amallar

```bash
# Loglar
docker compose logs -f bot
docker compose logs -f web | grep Click     # to'lov so'rovlari

# Yangilash
git pull && docker compose up -d --build

# Baza zaxirasi (kuniga bir marta cron'ga qo'ying)
docker compose exec db pg_dump -U uzumbot uzumbot | gzip > backup-$(date +%F).sql.gz

# Tiklash
gunzip -c backup-2026-08-06.sql.gz | docker compose exec -T db psql -U uzumbot uzumbot
```

### Zaxira nusxa nima uchun muhim

Uzum **qoldiq tarixini bermaydi** — uni faqat biz saqlaymiz. Baza
yo'qolsa, o'sha tarix butunlay yo'qoladi va davr bo'yicha audit qaytadan
noldan boshlanadi. Kunlik `pg_dump` ni albatta sozlang.

---

## 7. Resurslar

| Obunachi | vCPU | RAM | Disk |
|---|---|---|---|
| 50 gacha | 2 | 4 GB | 40 GB |
| 200 gacha | 2 | 8 GB | 80 GB |
| 1000 | 4 | 16 GB | 200 GB |

> **Ma'lum cheklov:** hozirgi kodda `sync_all_shops` do'konlarni
> **ketma-ket** sinxronlaydi (~12 so'rov × 1 sek). ~200 do'kondan keyin
> soatlik jadval ulgurmaydi — parallel ishlashga o'tkazish kerak bo'ladi.
> Shuningdek audit yig'indilari Python'da hisoblanadi; katta hajmda
> SQL `GROUP BY` ga o'tkazish kerak.

---

## 8. Xatolarni tekshirish

| Alomat | Sabab |
|---|---|
| `TelegramConflictError` | Bot ikki joyda ishlayapti (lokal + server) |
| PDF'da `□□□` | Shrift yo'q — Dockerfile'dagi `fonts-dejavu-core` o'rnatilmagan |
| Click `-1 SIGN CHECK FAILED` | `CLICK_SECRET_KEY` noto'g'ri |
| Click so'rov kelmayapti | Servis yoqilmagan yoki IP oq ro'yxatda yo'q |
| Sync xatosi haqida xabar yo'q | Hech kim admin emas — botga `/start` bosing |
