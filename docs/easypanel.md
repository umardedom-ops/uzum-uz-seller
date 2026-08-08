# EasyPanel'ga chiqarish — qadam-baqadam

> ⚠️ **BU YO'L ISHLATILMADI.** Loyiha 2026-08-08 da boshqacha
> joylashtirildi: EasyPanel loyihasi sifatida emas, o'sha serverdagi
> **oddiy `docker compose`** bilan. Sabab: EasyPanel bepul tarifida
> 3 loyiha chegarasi bor va serverda allaqachon 2 tasi band edi
> (ERPNext, n8n) — chegara tugab qolardi.
>
> **Haqiqiy holat va buyruqlar: `docs/holat.md` → «Ishlab turgan
> server».** Bu fayl EasyPanel UI orqali qilmoqchi bo'lsangiz zaxira
> yo'riqnoma sifatida qoldirilgan.
>
> Domen esa baribir EasyPanel'niki: uning Traefik'i `*.8xspuf.easypanel.host`
> subdomenlarini va Let's Encrypt sertifikatini beradi. Bizning
> marshrut alohida faylda —
> `/etc/easypanel/traefik/config/uzumbot.yaml` — shuning uchun
> EasyPanel o'z `main.yaml` ini qayta yaratganda ham saqlanib qoladi.

Domen sotib olish shart emas: EasyPanel bepul subdomen va HTTPS beradi.

---

## 1-qadam. Kodni GitHub'ga yuklash

EasyPanel kodni Git'dan oladi. Repozitoriy allaqachon tayyor (commit
qilingan), faqat GitHub'ga yuborish qoldi.

**a)** [github.com/new](https://github.com/new) → repozitoriy yarating:
- Nomi: `uzumbot` (yoki xohlagan nom)
- **Private** tanlang
- README, .gitignore **qo'shmang** (bizda bor)

**b)** Terminalda:

```bash
cd "E:\IT loihalar\UZUMUZBOT"
git remote add origin https://github.com/<foydalanuvchi>/uzumbot.git
git branch -M main
git push -u origin main
```

> ✅ `.env` GitHub'ga **tushmaydi** — `.gitignore` da. Tekshirildi.

---

## 2-qadam. EasyPanel'da loyiha yaratish

1. EasyPanel → **Projects** → **Create Project** → nomi: `uzumbot`
2. Ichida uchta xizmat yaratamiz: `db`, `bot`, `web`

---

## 3-qadam. PostgreSQL (`db`)

**+ Service → Postgres**

| Maydon | Qiymat |
|---|---|
| Name | `db` |
| Version | `16` |
| Database | `uzumbot` |
| User | `uzumbot` |
| Password | *(quyida generatsiya qilingan parolni qo'ying)* |

**Create** → ishga tushishini kuting.

Ulanish satri ichki tarmoqda shunday bo'ladi:
```
postgresql+asyncpg://uzumbot:<PAROL>@uzumbot_db:5432/uzumbot
```

> ⚠️ EasyPanel host nomini `<loyiha>_<xizmat>` ko'rinishida beradi.
> Aniq nomni xizmat sahifasidan ko'chiring.

---

## 4-qadam. Bot (`bot`)

**+ Service → App**

**Source:**
- Type: **GitHub**
- Repository: `<foydalanuvchi>/uzumbot`
- Branch: `main`

**Build:**
- Method: **Dockerfile**
- Dockerfile path: `Dockerfile`

**Deploy:**
- Command: `bot`

**Environment** (pastdagi ro'yxatdan ko'chiring)

**Domains:** kerak emas — bot tashqaridan chaqirilmaydi.

---

## 5-qadam. Webhook serveri (`web`)

**+ Service → App** — `bot` bilan bir xil source va build.

Farqlari:
- Command: `web`
- **Domains** → **Add Domain** → EasyPanel taklif qilgan subdomenni oling,
  **Port: 8000**, HTTPS yoqilgan

Natijada quyidagilar ochiladi:
```
https://<subdomen>/health     → {"status":"ok"}
https://<subdomen>/oferta     → ommaviy oferta
https://<subdomen>/click/...  → to'lov (keyinroq)
```

---

## 6-qadam. Environment o'zgaruvchilari

Ikkala xizmatga (`bot` va `web`) bir xil qo'yiladi:

```ini
BOT_TOKEN=<BotFather tokeni>
FERNET_KEY=<generatsiya qilingan kalit>
DATABASE_URL=postgresql+asyncpg://uzumbot:<PAROL>@<db-host>:5432/uzumbot

ENV=prod
LOG_LEVEL=INFO
TZ=Asia/Tashkent

SUPPORT_USERNAME=@manejersupport
TRIAL_DAYS=3
PRICE_BASIC=149000
PRICE_PRO=299000

# Domen ma'lum bo'lgach to'ldiriladi
OFERTA_URL=https://<subdomen>/oferta
CLICK_BASE_URL=https://<subdomen>

# Click — SECRET_KEY yangilangach yoziladi
CLICK_SERVICE_ID=107646
CLICK_MERCHANT_ID=63121
CLICK_SECRET_KEY=

UZUM_API_BASE=https://api-seller.uzum.uz/api/seller-openapi
UZUM_RATE_LIMIT_PER_SEC=1
INITIAL_HISTORY_DAYS=365
```

> ⚠️ **`FERNET_KEY` ni keyinchalik o'zgartirmang.** U bilan sellerlarning
> API kalitlari shifrlangan — almashtirsangiz hamma qayta ulanishi kerak.

---

## 7-qadam. Ishga tushirish va tekshirish

1. `bot` xizmatini **Deploy** qiling → **Logs** ni oching

Ko'rinishi kerak:
```
→ Migratsiyalar qo'llanmoqda...
→ Bot ishga tushmoqda
Bot ishga tushdi: @uzumuzsellerbot (env=prod)
Rejalashtiruvchi ishga tushdi: 3 job
```

2. `web` xizmatini **Deploy** qiling

```bash
curl https://<subdomen>/health
```

3. **Botga birinchi bo'lib SIZ `/start` bosing** — avtomatik admin
   bo'lasiz. Keyin `/admin` bilan panelni oching.

> Boshqa odam oldin bossa, u admin bo'lib qoladi.

---

## 8-qadam. Zaxira nusxa (muhim)

Uzum qoldiq **tarixini bermaydi** — uni faqat biz saqlaymiz. Baza
yo'qolsa, tarix qaytmaydi.

EasyPanel → `db` xizmati → **Backups** → kunlik zaxira yoqing.

---

## Keyingi bosqichlar

| Ish | Qachon |
|---|---|
| Sotuvi bor do'konni ulash, formulani tekshirish | **birinchi navbatda** |
| Ofertadagi rekvizitlarni to'ldirish | to'lovdan oldin |
| Click SECRET_KEY yangilash + URL sozlash | to'lovdan oldin |
| Sync'ni parallel qilish | ~200 do'kondan keyin |
