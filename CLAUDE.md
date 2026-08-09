# Uzum Seller Bot — ishlash qoidalari

> **Birinchi ish:** `docs/holat.md` ni o'qing. U loyihaning hozirgi
> holati, ishlayotgan server va ochiq masalalar haqida.
> Texnik topshiriq: `SPEC.md`. Uzum API ma'lumotnomasi:
> `docs/api-inventory.md`.

## Til

Kod izohlari, docstring'lar, commit xabarlari va bot matnlari —
**o'zbek tilida**. Bot foydalanuvchilari uchun `uz` va `ru` katalogi bor
(`app/bot/texts/`), ikkalasi bir xil kalitlarga ega bo'lishi shart.

## Qattiq qoidalar

1. **Uzumga faqat GET.** Hech qanday POST/PUT/DELETE yo'q. `UzumHTTP`
   da yozish metodi qasddan mavjud emas — uni qo'shmang.
2. **Maxfiy ma'lumot logga tushmaydi.** API kalitlari `shop_credentials`
   da shifrlangan holda. `.env` git'ga tushmaydi.
3. **Audit natijasi "aniq fakt" emas, "tekshirish kerak".** Noto'g'ri
   da'vo sellerni Uzum oldida noqulay ahvolga soladi.
4. **Xato jim yutilmaydi.** Bo'sh ro'yxat qaytarish o'rniga sababini
   ayting. Bu loyihada shu naqsh bir necha bo'limni o'lik qilgan:
   so'rov yiqilardi, foydalanuvchi esa "ma'lumot yo'q" deb ko'rardi.

## Buyruqlar

```bash
.venv\Scripts\python.exe -m pytest -q
```

```bash
.venv\Scripts\python.exe -m ruff check app tests
```

Commitdan oldin ikkalasi ham toza bo'lishi kerak.

## Server va deploy

Bot **46.62.199.124** da doimiy ishlaydi (`/opt/uzumbot`). SSH kalit
sozlangan, parol kerak emas.

`master` ga push qilinsa server **5 daqiqada o'zi yangilanadi**
(`/opt/uzumbot/deploy.sh`, cron). Qurish xato bersa eski nusxa ishlab
turaveradi. Qo'lda deploy qilish shart emas.

Loglar: `docker compose -p uzumbot logs bot --tail 50`

> Serverda ERPNext va n8n ham ishlaydi — ular boshqa loyihalar,
> ularga tegmang. Xotira tang (3.8 GB + 2 GB swap).

## Tuzoqlar (bir marta yiqilib o'rganilgan)

* **Sahifa hajmi endpointга qarab farq qiladi.** `/v2/fbs/*` maksimum
  50 ta, qolganlari 100. Kattaроq so'rasangiz `400 Illegal argument`.
* **`/v1/finance/orders` ga sana filtri yubormang** — u xato bermay
  bo'sh ro'yxat qaytaradi. Filtr audit paytida qo'llanadi.
* **Buyurtma SKU ga `skuTitle` orqali bog'lanadi** (= mahsulotdagi
  `skuFullTitle`), `productId` orqali emas.
* **`quantityReturned` kutilgan qoldiqqa qo'shilmaydi** — u
  `quantitySold` ichida allaqachon bor. Qo'shilsa soxta yo'qotish
  chiqadi (7,63 mln so'mlik voqea shundan bo'lgan).
* **Migratsiya yozganda** `UtcDateTime` avtomatik to'g'ri chiqadi
  (`env.py` dagi `render_item`). Qo'lda `app.db.base.` deb yozmang —
  import qo'shilmaydi va migratsiya yiqiladi.
* **Testlar o'z vaqtinchalik bazasida ishlaydi** (`tests/conftest.py`).
  Haqiqiy `uzumbot.db` ga yozmang.
* **Telegram HTML**: faqat `b, i, u, s, code, pre, a, blockquote,
  tg-spoiler`. Noto'g'ri teg — xabar rad etiladi va bot "ishlamayapti"
  bo'lib ko'rinadi. `tests/unit/test_texts.py` buni tekshiradi.

## Hujjat yangilash

Sezilarli o'zgarishdan keyin `docs/holat.md` ni yangilang — keyingi
suhbat aynan shuni o'qiydi. Eskirgan hujjat yo'q hujjatdan yomonroq.
