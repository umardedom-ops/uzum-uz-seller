# Loyiha holati — 2026-08-09

> Yangi suhbat boshlanganda **shu faylni birinchi bo'lib o'qing**.
> Texnik topshiriq: `SPEC.md`. API ma'lumotnomasi: `docs/api-inventory.md`.

## Qisqacha

Uzum Market sellerlari uchun Telegram bot. Kod to'liq yozilgan,
**604 test o'tadi**, lint toza. Bot ishga tushadi va haqiqiy do'konlar
bilan ishlaydi.

**Audit raqamlari 2026-08-07 da tekshirildi va tuzatildi** —
`docs/sverka/xulosa.md`. Soxta 7,63 mln so'm yo'qoldi, ishlamayotgan
4 ta audit ishga tushdi.

## Ishlaydigan narsalar

| Qism | Holat |
|---|---|
| Uzum Seller API klienti (faqat GET) | ✅ jonli sinalgan |
| Onboarding: til → **tarif** → oferta → telefon → API kalit | ✅ |
| Kalit berilgach **darhol** sync + audit | ✅ |
| 6 xil audit (5.1–5.5 + saqlash xarajati) | ✅ sverka qilingan |
| Manba bo'sh bo'lsa ochiq aytiladi | ✅ |
| Excel / PDF / pretenziya + qo'shimcha kelishuv | ✅ |
| Yo'qotilgan pul · Qoldiqlar · Yunit-iqtisodiyot | ✅ |
| **Hisobotlar** (bugun/kecha/7 kun) | ✅ 2026-08-09 da yozildi |
| **FBS buyurtmalar** | ✅ 2026-08-09 da tuzatildi |
| Obuna: 3 kun sinov (Basic), Basic 149k / Pro 299k | ✅ |
| **Promokodlar** — hamkorlar orqali bepul kirish | ✅ yangi |
| Tariflar banneri + API video qo'llanma | ✅ yangi |
| Admin: birinchi `/start` bosgan avtomatik admin | ✅ |
| Serverda 24/7 (Docker + PostgreSQL) | ✅ ishlab turibdi |
| HTTPS domen + webhook | ✅ `uzumbot.8xspuf.easypanel.host` |
| 🔔 Bildirishnomalar · ⚙️ Sozlamalar | ✅ **yozildi** (`handlers/menu.py`, 2026-08-09) |
| **Qoldiq o'zgartirish (YOZISH)** | 🧪 **demo** — oqim tayyor, jonli o'chiq (pastga qarang) |
| **Click to'lovi** | ⏳ **o'chirilgan** — pastga qarang |

> ⛔ **Click hozircha O'CHIRILGAN** (`CLICK_SECRET_KEY` bo'sh).
> Sabab: `.env` da chatga tushgan eski kalit turgan, webhook manzillari
> esa Click kabinetida sozlanmagan. Bunday holatda seller pul to'lay
> olardi-yu, tasdiq kelmagani uchun obuna faollashmasdi — pul ketib,
> xizmat berilmasdi. Sozlangunicha o'chiq turadi.
>
> Hech qanday to'lov usuli yo'q bo'lsa, bot pullik tarif tanlaganга
> «onlayn to'lov ulanmagan, support'ga yozing» deb aytadi va bepul
> muddat bilan davom etadi. Tupik yo'q.

## Yozish (POST) — birinchi ficha: qoldiq o'zgartirish

Ilgari Uzumga faqat GET yuborardik (qattiq qoida). Endi **yozish
ehtiyotkorlik bilan ochildi** — birinchi ficha: FBS qoldig'ini botdan
o'zgartirish. Sabab: API kalit read-only emas, to'liq huquq beradi
(`docs/api-inventory.md §7`) — raqobatchining yozishga muhtoj fichalari
(qoldiq, narx) shu kalit orqali qilinadi, menejer roli kerak emas.

**Xavfsizlik uch qatlam:**

1. **Ajratilgan.** Yozish faqat `app/uzum/writes.py` (`UzumWriteClient`).
   Audit/sync uni import qilmaydi — "audit faqat GET" kodda ko'rinadi.
2. **Bayroq.** `UZUM_WRITES_ENABLED` (standart **o'chiq**). O'chiq bo'lsa
   oqim **demo** rejimda ishlaydi: amal `stock_write_log` ga `DEMO`
   sifatida tushadi, foydalanuvchiga "jonli emas" deyiladi.
3. **Tasdiq + jurnal.** Har amal foydalanuvchi tasdig'i bilan, `base.post`
   qayta urinmaydi (ikki marta yozishdan saqlanish), har amal
   `stock_write_log` ga (kim, do'kon, sku, eski→yangi, natija) yoziladi.

**Oqim:** Qoldiqlar ekrani → «✏️ Qoldiqni o'zgartirish» → SKU tanlash →
yangi son → tasdiq ekrani → yoziladi. Kod: `app/bot/handlers/stock_edit.py`,
`app/services/stock_write.py`.

> ⚠️ **Jonli yoqishdan oldin:** `POST /v2/fbs/sku/stocks` so'rov TANASI
> Swagger'dan tasdiqlanishi kerak. Hozir `writes.py:_build_stock_payload`
> da taxminiy sxema (`{"skus":[{"skuId","amount"}]}`). Tasdiqlanib,
> `.env` da `UZUM_WRITES_ENABLED=true` qo'yilganda jonli ishlaydi —
> boshqa kod o'zgarmaydi. `Product.sku` = Uzum `skuId` (tekshirilgan).

## Sverka natijasi (2026-08-07)

17 ta "yo'qolgan tovar" (7,63 mln so'm) **soxta** ekani aniqlandi va
sabab topildi: `quantityReturned` kutilgan qoldiqqa qo'shilgan, ya'ni
qaytarish ikki marta hisoblangan. Dalil: 16 tasida farq aynan shu
maydonga teng edi, Uzumning `quantityMissing` esa hammasida 0.

Yo'l-yo'lakay yana 5 ta xato topildi — uchtasi auditlarni butunlay
o'chirib qo'ygan edi (sana millisekundda yuborilgan, buyurtma SKU ga
`productId` orqali bog'langan, qaytarish tarkibi so'ralmagan).

| | Oldin | Keyin |
|---|---|---|
| Soxta yo'qotish | 17 ta / 7 630 000 | 0 |
| `orders` | bo'sh | 539 |
| `returns` | bo'sh | 2 |
| Ishlayotgan audit | 6 dan 1 | 6 dan 6 |

Hozir topilayotgan yagona farq — komissiya: 3 SKU, 30 200 so'm, har biri
buyurtma yozuvi bilan tasdiqlanadi.

Batafsil: `docs/sverka/xulosa.md`.

## 2026-08-09 da qilingan ishlar

**Bo'limlar sinovi.** Har bir menyu bo'limi serverdagi haqiqiy ma'lumot
bilan chaqirib ko'rildi. Natija: 5 tasi ishlaydi, **FBS buzuq edi**,
3 tasi umuman yozilmagan. FBS tuzatildi, Hisobotlar yozildi.

**Promokodlar.** Admin kod yaratadi (`/promo_new`), hamkor sellerga
beradi, seller botga yuboradi — tarif ochiladi. Kod amal qilayotgan
obuna ustiga qo'shiladi; bitta odam bitta kodni ikki marta ishlata
olmaydi.

**Ko'rinish.** Ekranlardagi takrorlanish olib tashlandi (narx uch marta
yozilardi), tariflar `blockquote` kartochkalariga o'tkazildi, tarif
ekraniga banner rasm va API yo'riqnomasiga video qo'llanma qo'shildi.

> ⚠️ Video qo'llanmada API kalitlari ochiq ko'rinardi (4 ta, ikkitasi
> faol). Kalitlar ustuni xiralashtirildi, login va moliya sahifasi
> kesildi. **Asl fayl va chat tarixida kalitlar qolgan — ularni
> kabinetda almashtirish tavsiya etiladi.**

## Yo'l-yo'lakay tuzatilgan xatolar (takrorlanmasin)

1. **`quantityCreated` ≠ omborga qabul.** Bir do'konda 0, boshqasida
   yetib bormagan yuk rejasini qaytardi. Qabul faqat yuk xati
   tarkibidagi `quantityAccepted` dan olinadi.
2. **Yuk xati tarkibi sinxronlanmasdi** — `/v1/shop/{id}/invoice/products`
   qo'shildi. U tannarxni ham beradi.
3. **Ishonchlilik tekshiruvi:** qaytarish > sotuv yoki chiqim > kirim
   bo'lsa — hisoblamaymiz (`CumulativeStock.data_is_plausible`).
4. **`price_monthly`** olib tashlangan sozlama `start.py` da qolib
   ketgan edi → bot yiqilardi. Endi handler testlari bor.
5. **Oferta `localhost` havolasi** telefondan ochilmasdi → matn Telegram
   ichida, "Oferta" tugmasi fayl yuboradi.
6. **`quantityReturned` kutilgan qoldiqqa qo'shilardi** → qaytarish ikki
   marta hisoblanib, 7,63 mln soxta yo'qotish chiqargan. Endi qo'shilmaydi.
7. **`/v1/finance/orders` ga sana millisekundda yuborilardi** → endpoint
   xato bermay, bo'sh ro'yxat qaytarardi. Endi sana filtri yuborilmaydi.
8. **Buyurtma SKU ga `productId` orqali bog'lanardi** → hech qachon mos
   kelmasdi. Kalit: buyurtmadagi `skuTitle` = mahsulotdagi `skuFullTitle`.
9. **Qaytarish tarkibi** ro'yxat javobida yo'q — `/return/{id}` tafsiloti
   so'raladi. Miqdor `packedAmount` dan olinadi.
10. **Eskirgan topilmalar o'chmasdi** → tuzatilgan formuladan keyin ham
    eski soxta summa ko'rinardi. Endi `_persist` ularni tozalaydi.
11. **FBS sahifa hajmi 100 yuborilardi** — Uzum `/v2/fbs/*` da 50 dan
    ko'pini qabul qilmaydi (`400 Illegal argument`). Xato yutilib, bo'lim
    jimgina o'lik turardi.
12. **Testlar haqiqiy bazaga yozardi** — izolyatsiya yo'q edi. Endi
    `tests/conftest.py` har sessiyaga vaqtinchalik baza beradi.
13. **Alembic `UtcDateTime` uchun import qo'shmasdi** → har yangi
    migratsiya `NameError` bilan yiqilardi. `env.py` da `render_item`.

## Ma'lumotlar bazasi holati

Ikki alohida baza bor — ularni adashtirmang:

**Lokal** (`uzumbot.db`, SQLite) — sverka shu yerda qilingan:

```
Foydalanuvchi: 2 (1 admin, 1 seller)
Do'kon: AZIKO (7973), AZIKO PLAST (25273)
Mahsulot: 232 · Tannarxi bor: 228
Ombor harakati: 378 · Buyurtma: 539 · Qaytarish: 2
Qoldiq surati: 464 · Farqlar: 0
```

**Server** (PostgreSQL) — **bo'sh**, noldan boshlangan. Do'konlar
qaytadan ulanadi. `FERNET_KEY` lokal bilan bir xil, ya'ni xohlasangiz
lokal bazani serverga ko'chirish mumkin (kalitlar ochiladi).

> Zaxira nusxa: `uzumbot.db.bak-20260807-220407` (sverkadan oldingi holat).

> ℹ️ AZIKO — **sinov do'koni**, sotuv 2024-noyabrda to'xtagan. Shuning
> uchun buyurtmalar 2023-04-25 … 2024-11-21 oralig'ida va yangi sotuv
> yo'q. Bu xato emas. Yangi davrlar bo'yicha audit bo'sh chiqishi
> normal — ma'lumot yo'qligi endi ochiq aytiladi (`data_health`).

## Ishlab turgan server (2026-08-08 dan)

Bot **VPS'da doimiy ishlaydi** — lokal ishga tushirish endi shart emas.

```
Server:   46.62.199.124 (Ubuntu 24.04)
Papka:    /opt/uzumbot
Loyiha:   docker compose -p uzumbot   (db · bot · web)
Baza:     PostgreSQL 16, `uzumbot_pgdata` volume ichida
Domen:    https://uzumbot.8xspuf.easypanel.host
```

Ochiq manzillar:

| Manzil | Nima |
|---|---|
| `/health` | holat tekshiruvi (Click yoqilganini ham ko'rsatadi) |
| `/oferta` | ommaviy oferta sahifasi |
| `/click/prepare`, `/click/complete` | Click webhook'lari |

> HTTPS serverdagi mavjud Traefik orqali (EasyPanel'niki). Marshrut
> **alohida faylda**: `/etc/easypanel/traefik/config/uzumbot.yaml` —
> EasyPanel o'z `main.yaml` ini qayta yozganda ham saqlanadi. `web`
> konteyneri shu sabab `easypanel` overlay tarmog'iga ham ulangan.

> ⚠️ Serverda ERPNext va n8n ham ishlaydi. Xotira tang (3.8 GB), shuning
> uchun 2 GB swap qo'shilgan. Yangi og'ir xizmat qo'shishdan oldin
> `free -m` ni tekshiring.

Foydali buyruqlar (SSH orqali):

```bash
cd /opt/uzumbot && docker compose -p uzumbot logs bot --tail 50
```

```bash
cd /opt/uzumbot && docker compose -p uzumbot restart bot
```

### Avtomatlashtirilgan

| Ish | Jadval | Skript |
|---|---|---|
| GitHub'dan avtodeploy | har 5 daqiqa | `/opt/uzumbot/deploy.sh` |
| Baza zaxirasi (14 kun) | har kuni 03:00 | `/opt/uzumbot/backup.sh` |

`master` ga push qilinsa, server 5 daqiqa ichida o'zi yangilanadi.
Qurish xato bersa **eski nusxa ishlab turaveradi** — buzuq kod botni
yiqitmaydi. Loglar: `/var/log/uzumbot-deploy.log`,
`/var/log/uzumbot-backup.log`. Zaxiralar: `/opt/uzumbot/backups/`.

### Lokal ishga tushirish (kerak bo'lsa)

```bash
cd "E:\IT loihalar\UZUMUZBOT"
.venv\Scripts\python.exe -m app.bot.main
```

> ❗ Serverdagi bot ishlab turganda lokalni yoqmang — bitta token bilan
> ikki nusxa ishlay olmaydi, Telegram `Conflict` xatosi beradi.

## Keyingi qadamlar (muhimlik tartibida)

1. **Click to'lovini yoqish** — hozir o'chiq, daromad yo'q. Ikki yo'l:
   * Bot uchun **alohida servis** yarating (tavsiya). Parfyum
     servislariga tegilmaydi.
   * Yoki mavjud `107646` (`parfumlux.uz`) servisidan foydalanish —
     ❗ ammo webhook manzili har servisga BITTA. Uni almashtirsangiz
     parfyum saytida to'lov uziladi. Almashtirishdan oldin eski
     manzillarni ko'chirib oling.

   Servis tayyor bo'lgach `.env` ga yozing:
   ```bash
   ssh root@46.62.199.124 'cd /opt/uzumbot && nano .env && docker compose -p uzumbot up -d'
   ```
   `CLICK_SERVICE_ID`, `CLICK_MERCHANT_ID`, `CLICK_SECRET_KEY`.
   Webhook manzillari: `<domen>/click/prepare` va `/click/complete`.

2. **Haqiqiy sotuvi bor do'konni ulash** — AZIKO sinov do'koni,
   sotuvi 2024-11 da to'xtagan. Formulani tirik ma'lumotda tekshirish
   kerak.

3. Ofertaga rekvizit qo'shish (hozir rekvizitsiz)

4. Zaxira nusxani serverdan tashqariga chiqarish — hozir zaxira o'sha
   serverning o'zida yotadi, server yo'qolsa u ham yo'qoladi.

5. ~200 do'kondan keyin: sync'ni parallel qilish, audit yig'indilarini
   SQL tomoniga o'tkazish

## Maxfiy ma'lumot

Do'kon kalitlari `.env` da EMAS — `shop_credentials` jadvalida
shifrlangan holda saqlanadi (`sync._api_secret()`). `.env` da faqat
bot/to'lov sozlamalari bor; git'ga ham, Docker obraziga ham tushmaydi.

> `UZUM_API_KEY` **olib tashlandi** (2026-08-07). U kodda hech qayerda
> ishlatilmagan, lekin ichida butunlay boshqa do'konning (`Elore
> Parfume`, 125841) kaliti turgan va tekshiruv paytida chalg'itgan.
> Zaxira: `.env.bak-20260807-*`.

**Sizning qo'lingizdagi ish** — chatga tushgan kalitlarni almashtirish
(buni faqat kabinet egasi qila oladi):

- **Uzum API kaliti** — Seller kabinet → API kalitlari → eskisini
  o'chirib, yangisini yarating. Keyin botda do'konni qayta ulang
  (`/start`), yangi kalit bazaga shifrlangan holda tushadi.
- **Click `SECRET_KEY`** — merchant.click.uz → sozlamalar. Yangisini
  `.env` dagi `CLICK_SECRET_KEY` ga yozing.
- **Click merchant kabinet paroli**.
