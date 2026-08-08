# Loyiha holati — 2026-08-07

> Yangi suhbat boshlanganda **shu faylni birinchi bo'lib o'qing**.
> Texnik topshiriq: `SPEC.md`. API ma'lumotnomasi: `docs/api-inventory.md`.

## Qisqacha

Uzum Market sellerlari uchun Telegram bot. Kod to'liq yozilgan,
**286 test o'tadi**, lint toza. Bot ishga tushadi va haqiqiy do'konlar
bilan ishlaydi.

**Audit raqamlari 2026-08-07 da tekshirildi va tuzatildi** —
`docs/sverka/xulosa.md`. Soxta 7,63 mln so'm yo'qoldi, ishlamayotgan
4 ta audit ishga tushdi.

## Ishlaydigan narsalar

| Qism | Holat |
|---|---|
| Uzum Seller API klienti (faqat GET) | ✅ jonli sinalgan |
| Onboarding: til → oferta → telefon → API kalit | ✅ |
| Kalit berilgach **darhol** sync + audit | ✅ |
| 6 xil audit (5.1–5.5 + saqlash xarajati) | ✅ sverka qilingan |
| Manba bo'sh bo'lsa ochiq aytiladi | ✅ yangi |
| Excel / PDF / pretenziya | ✅ |
| FBS yorliqlar, qoldiq, yunit-iqtisodiyot | ✅ |
| Obuna: 3 kun sinov, Basic 149k / Pro 299k | ✅ |
| Click to'lovi (Shop API webhook) | ✅ kod tayyor, sozlanmagan |
| Admin: birinchi `/start` bosgan avtomatik admin | ✅ |
| Docker Compose + PostgreSQL | ✅ qurilmagan (Docker yo'q) |

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

## Ma'lumotlar bazasi holati

```
Foydalanuvchi: 2 (1 admin, 1 seller)
Do'kon: AZIKO (7973), AZIKO PLAST (25273)
Mahsulot: 232 · Tannarxi bor: 228
Ombor harakati: 378 · Buyurtma: 539 · Qaytarish: 2
Qoldiq surati: 464 · Farqlar: 0
```

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
```

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

1. GitHub'ga push + EasyPanel'ga deploy (`docs/easypanel.md`)
3. Click: yangi `CLICK_SECRET_KEY`, domen, webhook URL sozlash
4. Ofertaga rekvizit kerak bo'lsa qo'shish (hozir rekvizitsiz)
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
