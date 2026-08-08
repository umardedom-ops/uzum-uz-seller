# Audit sverkasi va tuzatishlar — AZIKO (7973), 2026-08-07

Manba: Uzum API xom javoblari (`raw-7973.json` + jonli so'rovlar) va
`uzumbot.db`. Kabinetga kirilmagan — kerak bo'lmadi, hamma dalil API'ning
o'zidan chiqdi.

## Qisqacha

**7 630 000 so'mlik "yo'qolgan tovar" soxta edi. Endi 0.**

Sverka jarayonida yana **4 ta jiddiy xato** topildi — ularning uchtasi
auditlarni butunlay ishlamas holga keltirgan edi. Hammasi tuzatildi.

| Ko'rsatkich | Oldin | Keyin |
|---|---|---|
| Soxta yo'qotish | 17 ta / 7 630 000 so'm | 0 |
| `orders` jadvali | **bo'sh** | 539 yozuv |
| `returns` jadvali | **bo'sh** | 2 yozuv |
| Ishlayotgan audit | 6 dan 1 tasi | 6 dan 6 tasi |
| Testlar | 268 | 286 |

Endi topilayotgan yagona farq — **komissiya**: 3 ta SKU bo'yicha 30 200 so'm.
Tasodifiy emas, buyurtma yozuvi bilan tasdiqlanadi (masalan buyurtma
19561422: 270 000 so'mdan 67 500 ushlangan = 25%, kartochkada 20%).

---

## 1. ❗ Qaytarish ikki marta hisoblangan → 7,63 mln soxta

`app/services/audit_runner.py` · formula: `kutilgan = qabul + qaytgan − sotilgan − chiqarilgan`

`total_returned` ga Uzumning `quantityReturned` maydoni berilardi. U
**mijoz qaytargan** miqdorni bildiradi va `quantitySold` ichida allaqachon
hisoblangan. Kutilgan qoldiqqa qo'shilgach, qaytarish ikki marta sanalgan.

**Dalil 1 — arifmetika.** 17 SKU dan 16 tasida `qabul == sotilgan`,
qoldiq 0. Ya'ni olindi → sotildi → omborda hech narsa yo'q: mukammal
izchil ombor. Farq aynan `quantityReturned` ga teng edi:

| SKU | qabul | sotilgan | qaytgan | qoldiq | bot farqi | tuzatishdan keyin |
|---|---|---|---|---|---|---|
| 708903 | 4 | 4 | 4 | 0 | **4** | 0 |
| 720773 | 6 | 6 | 4 | 0 | **4** | 0 |
| 693852 | 3 | 3 | 3 | 0 | **3** | 0 |
| 693853 | 3 | 2 | 1 | 0 | **2** | 1 → chegaradan past |
| qolgan 13 ta | n | n | 2–3 | 0 | **2–3** | 0 |

**Dalil 2 — Uzumning o'z hisobi.** Har bir SKU javobidagi
`quantityMissing` (Uzum hisoblagan yetishmovchilik) 17 tasining
hammasida **0**.

**Dalil 3 — naqsh.** 13 ta SKU da `qaytgan == sotilgan == qabul`, ya'ni
"sotilgan har bir dona qaytib kelgan". 13 xil mahsulotda 100% qaytarish
bo'lmaydi.

**Tuzatish:** `total_returned=0`. `returns` jadvalidagi yozuvlar ham bu
yerga qo'shilmaydi — `/v1/shop/{id}/return` omborga kirim emas,
sotuvchiga **chiqim** (turi `DEFECTED`), va Uzumning `quantityDefected`
maydoni ularni allaqachon sanaydi (SKU 704077: yuk xatida 1 dona,
`quantityDefected` ham 1).

## 2. ❗ `orders` jadvali bo'sh — sana millisekundda yuborilgan

`app/uzum/api_client.py` · `get_orders`

`/v1/finance/orders` ga `dateFrom`/`dateTo` millisekundda yuborilgan.
Endpoint xato bermaydi — shunchaki **bo'sh ro'yxat** qaytaradi:

| So'rov | Natija |
|---|---|
| `dateFrom`/`dateTo` ms (eski kod) | 0 |
| `dateFrom`/`dateTo` ISO | 400 |
| `dateFrom`/`dateTo` sekund | tushunarsiz (730 kun → 6, 1200 kun → 539) |
| **parametrsiz** | **539 — to'liq** |

**Tuzatish:** sana filtri yuborilmaydi, hammasi olinadi. Qaytarishlarda
allaqachon shu yondashuv ishlatilgan.

## 3. ❗ Buyurtma SKU ga bog'lanmagan — `productId` ishlatilgan

`app/services/mappers.py` · `map_order`

Buyurtmada `skuId` yo'q. Eski kod `productId` ni SKU deb yozardi. U
mahsulot darajasidagi raqam (394566), SKU esa 704077/704078/… — ya'ni
`products` va `stock_snapshots` bilan **hech qachon** mos kelmasdi.

Bog'lanish kaliti topildi: buyurtmadagi `skuTitle` = mahsulotdagi
**`skuFullTitle`** (`AZIKO-КРОС-ТЕМНСИН-44` → skuId 763221).

> ⚠️ `skuTitle` (qisqa nom, `ТЕМНСИН-40`) kalit bo'la olmaydi:
> 220 SKU da atigi 21 xil qiymat bor.

**Tuzatish:** `sku_index_by_full_title()` jadvali sync paytida quriladi
va `map_order` ga beriladi. Nom topilmasa qator yozilmaydi — noto'g'ri
kalit bilan yozgandan ko'ra yozmagan afzal.

Yo'l-yo'lakay: `sellerPrice` → **`sellPrice`** (bunday maydon hech qachon
bo'lmagan, narx doim 0 tushardi).

## 4. ❗ `returns` jadvali bo'sh — tarkib ikkinchi so'rovda

`app/services/sync.py` · `_sync_returns`

`/v1/shop/{id}/return` ro'yxati faqat sarlavhani beradi; `returnItems`
maydoni unda **yo'q**. SKU kesimidagi tarkib faqat
`/v1/shop/{id}/return/{returnId}` tafsilotida keladi — yuk xatlaridagi
(`invoice` → `invoice/products`) naqshning aynan o'zi.

**Tuzatish:** ikki qadamli sync. Yana: miqdor `amount` (reja) emas,
**`packedAmount`** (haqiqatda yig'ilgani) dan olinadi.

## 5. ❗ 365 kunlik oyna butun tarixni kesardi

`app/services/sync.py` · `_sync_orders`

539 buyurtmaning hammasi **2023-04-25 … 2024-11-21** oralig'ida.
`initial_history_days = 365` (2025-08-07 dan) ularning barchasini
tashlab yuborardi.

**Tuzatish:** sync Uzumda bor hamma narsani saqlaydi; davr filtri audit
paytida qo'llanadi. Sync — tarixiy nusxa, uni kesish ma'lumotni butunlay
yo'qotadi.

## 6. ❗ Eskirgan topilmalar hech qachon o'chmasdi

`app/services/audit_runner.py` · `_persist`

Faqat qo'shish va yangilash bor edi, o'chirish yo'q. Bir marta yozilgan
xato natija abadiy qolardi: formula tuzatilgandan keyin ham audit 0
qaytardi, lekin seller bazadagi eski 7,63 mln ni ko'raverardi.

**Tuzatish:** davr bo'yicha endi topilmaydigan yozuvlar o'chiriladi.
Da'vo yuborilgan (`CLAIMED`) va hal bo'lganlarga (`RESOLVED`) tegilmaydi
— seller yuborgan da'vo tarixi buzilmasligi kerak.

## 7. ⚠️ Bo'sh manba "yo'qotish yo'q" deb ko'rsatilardi

Eng xavfli xato: audit ishlamaganda bot **"✅ yo'qotish topilmadi"**
deb yozardi. Seller o'zini xotirjam his qiladi, aslida esa tekshiruv
umuman o'tmagan.

**Tuzatish:** `audit_runner.data_health()` qaysi manba bo'sh ekanini
aniqlaydi, bot esa ochiq aytadi: qaysi ma'lumot kelmadi, qaysi auditlar
ishlamadi, va bu "yo'qotish yo'q" degani emasligini.

---

## Tekshirilgan, lekin to'g'ri chiqqan

* Summa **tannarxda** hisoblanadi (`cost_price`), sotuv narxida emas.
* `purchasePrice` API da 0 bo'lsa ham tannarx yuk xatlaridan olinadi.
* Faqat GET so'rovlar (SPEC §9.1 buzilmagan).
* `data_is_plausible` himoyasi ishlaydi — lekin u bu holatni ushlay
  olmagan edi, chunki 13 SKU da `returned == sold` (`>` emas, teng).

## Aniqlangan, xato emas

**2024-noyabrdan keyin buyurtma yo'q.** `/v1/finance/orders` da eng yangi
yozuv 2024-11-21. Sabab tasdiqlandi: AZIKO — **sinov do'koni**, sotuv
o'sha paytda to'xtatilgan. Endpoint ham, sync ham to'g'ri ishlayapti.

Amaliy natija: yangi davrlar bo'yicha audit bo'sh chiqadi, va bu
to'g'ri. Bot endi buni "yo'qotish yo'q" deb emas, ma'lumot yo'qligi
sifatida ko'rsatadi (`data_health`).

## Ochiq qolgan

Chatga tushgan maxfiy ma'lumot hali almashtirilmagan (Uzum kaliti,
Click `SECRET_KEY`, merchant kabinet paroli). Buni faqat kabinet egasi
qila oladi — qadamlar `docs/holat.md` oxirida.

## 8. `.env` dagi begona kalit olib tashlandi

`UZUM_API_KEY` da butunlay boshqa do'konning kaliti turgan edi — `Elore
Parfume` (125841), AZIKO/AZIKO PLAST emas. U `config.py` da e'lon
qilingan, lekin kodda **hech qayerda ishlatilmagan**: har bir do'kon
kaliti `shop_credentials` dan shifrlangan holda olinadi.

Ishlatilmagani uchun botga ta'sir qilmagan, lekin tekshiruv paytida
chalg'itdi (`/v1/product/shop/7973` → 403 «Shop is not available»).
Sozlama butunlay olib tashlandi — bo'sh joyga haqiqiy kalit yozishdan
ko'ra, umumiy kalit tushunchasini yo'q qilish xavfsizroq.
