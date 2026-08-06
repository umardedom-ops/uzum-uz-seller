# Uzum Seller API inventarizatsiya (Phase 0) — ✅ BAJARILDI

> Sana: 2026-08-05. Manba: rasmiy Swagger + jonli so'rovlar (Elore Parfume, shopId 125841).
> Barcha so'rovlar **GET**, faqat o'qish.

## 1. Asosiy ma'lumot

| | |
|---|---|
| Base URL | `https://api-seller.uzum.uz/api/seller-openapi/` |
| Swagger UI | `.../swagger/swagger-ui/webjars/swagger-ui/index.html` |
| OpenAPI spec | `.../swagger/api-docs` |
| **Auth** | Header `Authorization: <TOKEN>` — **Bearer prefiksisiz!** |
| Kalit qayerdan | Seller kabinet → Mening profilim → **API kalitlar** |

⚠️ **User-Agent majburiy.** Brauzerga o'xshamagan so'rovlarga server **403** qaytaradi
(auth to'g'ri bo'lsa ham). `app/uzum/base.py` da UA header qo'yilishi shart.

## 2. `AbstractUzumClient` metodlarini bog'lash

| Metod | Endpoint | Parametrlar | Holat |
|---|---|---|---|
| `get_shops` | `GET /v1/shops` | — | ✅ **Sinaldi** |
| `get_products` | `GET /v1/product/shop/{shopId}` | `page*`, `size*`, `searchQuery`, `sortBy`, `filter` | ✅ **Sinaldi** |
| `get_orders` | `GET /v1/finance/orders` | `shopIds*`, `dateFrom`, `dateTo` (**ms**), `page`, `size`, `statuses`, `group` | ✅ **Sinaldi** |
| `get_returns` | `GET /v1/shop/{shopId}/return` | `page`, `size` | ✅ **Sinaldi** |
| `get_finance_ops` | `GET /v1/finance/expenses` | `shopIds`, `dateFrom`, `dateTo`, `sources`, `page`, `size` | ✅ **Sinaldi** |
| `get_stock_snapshot` | `GET /v3/fbs/sku/stocks` | `page`, `size` | ⚠️ **FAQAT FBS** |
| `get_stock_movements` | — | — | ❌ **API'da yo'q** |
| `get_compensations` | — | — | ❌ **API'da yo'q** |

Qo'shimcha foydali GET'lar:
- `GET /v2/fbs/orders` — FBS buyurtmalar (`shopIds*`, `status`, `scheme`, `dateFrom/To`)
- `GET /v1/shop/{shopId}/invoice` — **FBO yuk xatlari** (omborga qabul)
- `GET /v1/shop/{shopId}/invoice/products` — yuk xati tarkibi
- `GET /v1/return` — barcha qaytarishlar
- `GET /v1/invoice` — barcha yuk xatlari

> **Sanalar millisekundda** (unix epoch ms), sekundda emas.

## 3. ⚠️ Aniqlangan bo'shliqlar — 5.1 formulasiga ta'sir

```
kutilgan = qoldiq(T1) + qabul + qaytgan − sotilgan − chiqarilgan
```

| Kerak | API beradimi | Izoh |
|---|---|---|
| qoldiq (FBS) | ✅ `/v3/fbs/sku/stocks` | |
| **qoldiq (FBO)** | ❌ **YO'Q** | Uzum omboridagi qoldiq API'da yo'q |
| qabul (FBO yuk xati) | ✅ `/v1/shop/{id}/invoice` | |
| qaytgan | ✅ `/v1/shop/{id}/return` | |
| sotilgan | ✅ `/v1/finance/orders` | |
| hisobdan chiqarilgan | ❌ yo'q | |
| kompensatsiya | ❌ yo'q | ehtimol `expenses.sources` ichida |

**Xulosa:** API FBS uchun deyarli yetarli, **FBO "yo'qolgan tovar" auditi uchun
yetmaydi**. FBO qoldig'i uchun kabinet kerak — u yerda **Moliya menejeri** roli
"ombor qoldiqlarini yuklash" huquqini beradi. Ya'ni SPEC 3.1 dagi ikki manba
rejasi **to'g'ri chiqdi**: API asosiy, kabinet — API bermagan narsa uchun.

## 4. Foydali topilma: komissiya API'dan keladi

`GET /v1/product/shop/{shopId}` javobida har mahsulot uchun:

```json
"commissionDto": { "minCommission": 20.0, "maxCommission": 20.0 }
```

Demak **5.3 komissiya auditi** uchun `commission_rates` jadvalini qo'lda
to'ldirish shart emas — foiz API'dan olinadi. SPEC 5.3 shunga moslanadi.

## 5. Mahsulot javobi — muhim maydonlar

```
productId, category, rating, status{value}, moderationStatus,
commissionDto{minCommission,maxCommission},
skuList[]: skuId, skuTitle, skuFullTitle (shtrix kod), productTitle,
           quantityCreated, quantityAvailable, quantityActive
```

`skuFullTitle` namunasi: `2620101-03303001001017001` — Excel hisobotdagi
**majburiy shtrix kod** shu bo'lishi mumkin (tasdiqlash kerak).

## 5-ter. ⭐ MAHSULOT ENDPOINTI — ENG MUHIM MANBA (2026-08-06)

`GET /v1/product/shop/{shopId}` → `skuList[]` da **hammasi bor**. Jonli
javobda tasdiqlangan.

| Maydon | Ma'nosi | Nima uchun kerak |
|---|---|---|
| **`quantityActive`** | **FBO ombor qoldig'i** | Kabinetdagi «FBO qoldiqlar, dona» ustuni bilan bir xil. **Kabinet kerak emas!** |
| `quantityFbs` | FBS qoldig'i | |
| **`quantitySold`** | **jami sotilgan** (butun tarix) | To'plangan audit (5.1-bis) |
| **`quantityReturned`** | **jami qaytgan** | To'plangan audit |
| `quantityCreated` | jami yaratilgan/ta'minlangan | To'plangan audit |
| `quantityMissing` | Uzum hisoblagan yetishmovchilik | ⚠️ sxemada "устарел" deb belgilangan |
| `quantityDefected`, `quantityArchived` | brak, arxiv | Hisobdan chiqarilgan sifatida |
| **`barcode`** | **shtrix kod** (masalan `1000113258397`) | ⚠️ `skuFullTitle` EMAS! Pretenziya uchun majburiy |
| **`skuDimension`** | `{length, width, height, weight}` | **5.4 logistika auditi** |
| `dimensionalGroup` | габарит guruhi | Tarif hisobi |
| **`blocked`, `blockReasons`, `blockingReason`** | blok holati | SKU bloklandi alerti |
| `status` | `{value: RUN_OUT, ...}` | Holat monitoringi |
| `commission` | komissiya foizi | 5.3 audit |
| `price`, `purchasePrice`, `marketPrice` | narxlar | Yunit-iqtisodiyot |
| `forecastOutOfStock` | Uzumning tugash prognozi | Qoldiq alerti |
| `avgdsales`, `avgdquantity` | kunlik o'rtacha sotuv | Sotib olish rejasi |
| `paidStorageAmount` | pullik saqlash xarajati | |
| `ikpu`, `sellerItemCode`, `article` | identifikatorlar | |

> ✅ **Katta natija:** FBO ombor qoldig'i API'da BOR. §3 dagi "FBO qoldiq
> API'da yo'q" xulosasi **noto'g'ri edi** — u faqat `/v3/fbs/sku/stocks`
> endpointiga tegishli. Mahsulot endpointi FBO ni beradi.
>
> Demak: **yagona raqam, xodim qo'shish, kabinet sessiyasi — hech biri
> kerak emas.** Ulanish faqat API kalit bilan, 1 qadam.

## 5-bis. Javob maydonlari (OpenAPI sxemasidan, 2026-08-06)

Sinov do'koni bo'sh bo'lgani uchun jonli javob ko'rilmadi — maydonlar
rasmiy sxemadan olindi.

### `SellerOrderItemDto` — `/v1/finance/orders`

```
id, orderId, productId, shopId
skuTitle, skuCharTitle, skuCharValue, productTitle
amount            — miqdor (5.1 dagi `sotilgan`)
amountReturns     — qaytarishlar soni
cancelled         — bekor qilinganlar
commission        ⭐ komissiya (5.3 audit)
logisticDeliveryFee ⭐ logistika to'lovi (5.4 audit)
purchasePrice, sellerPrice, sellerProfit, withdrawnProfit
date, dateIssued  — Unix epoch MILLISEKUND
status            — TO_WITHDRAW | PROCESSING | CANCELED | PARTIALLY_CANCELLED
returnCause, comment
```

> ⚠️ **Muhim bo'shliq:** buyurtma qatorida **`skuId` YO'Q** — faqat
> `productId` va `skuTitle` bor. Mahsulot endpointi esa `skuId` beradi.
> Ya'ni buyurtmani SKU ga bog'lash uchun `productId` + `skuCharValue`
> bo'yicha moslashtirish kerak. Haqiqiy ma'lumotda tekshirilsin.

### `SellerReturnDto` — `/v1/shop/{id}/return`

```
id, dateCreated, status, type, externalNumber
executionDate, assembledDate, completedDate, canceledDate
totalAmount, totalPackedAmount
returnItems[]: id, skuId ✅, amount, packedAmount,
               skuTitle, productTitle, purchasePrice
```

Qaytarishda `skuId` bor — buyurtmadan farqli.

### `SellerPaymentDto` — `/v1/finance/expenses`

```
id, externalId, code, name, type, source ⭐
shopId, sellerId
paymentPrice, amount, status
dateCreated, dateUpdated, dateService
```

> SKU maydoni yo'q — xarajatlar **do'kon darajasida**. Kompensatsiyalar
> ehtimol `source`/`type` bo'yicha ajraladi (5.5 uchun tekshirilsin).

### `SkuAmountApiResponseDto` — `/v3/fbs/sku/stocks`

```
skuId, skuTitle, productTitle, barcode ⭐, amount,
sellerSkuCode, fbsAllowed, dbsAllowed, fbsLinked, dbsLinked
```

### `InvoiceInList` — `/v1/shop/{id}/invoice` (FBO qabul)

```
id, invoiceNumber, externalNumber, dateCreated, dateAccepted
status, invoiceStatus, fullPrice
totalAccepted ⭐ — omborga qabul qilingan miqdor (5.1 dagi `qabul`)
totalToStock  ⭐
```

## 6. ❗ Hal qilinmagan: test ma'lumoti yo'q

Sinov do'koni (Elore Parfume) **bo'sh**: 1 ta mahsulot, 0 sotuv, 0 qoldiq,
0 qaytarish. Shu sababli:

- Javob **strukturasi** tasdiqlandi ✅
- Audit **formulasi** tasdiqlanmadi ❌

SPEC 10 talab qiladi: tarixi bor haqiqiy do'konni ulab, 3 oylik ma'lumotni
qo'lda hisoblab, bot natijasi bilan solishtirish. **Bu hali qilinmagan.**
Sotuvi bor do'kon kerak.

## 7. Xavfsizlik eslatmasi

API'da **yozish** endpointlari ham bor:
- `POST /v1/product/{shopId}/sendPriceData` — **narxlarni o'zgartirish**
- `POST /v2/fbs/sku/stocks` — qoldiqni yangilash
- `POST /v1/fbs/order/{id}/cancel` — buyurtmani bekor qilish

Ya'ni API kalit **to'liq huquq** beradi, read-only emas. Sellerga buni
ochiq ayting, va SPEC 9.1 qattiq qoidasi (`faqat GET`) — bu bizning
yagona kafolatimiz. `UzumHTTP` da yozish metodi umuman yo'q.
