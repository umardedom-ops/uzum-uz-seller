# Loyiha holati — 2026-08-07

> Yangi suhbat boshlanganda **shu faylni birinchi bo'lib o'qing**.
> Texnik topshiriq: `SPEC.md`. API ma'lumotnomasi: `docs/api-inventory.md`.

## Qisqacha

Uzum Market sellerlari uchun Telegram bot. Kod to'liq yozilgan,
**268 test o'tadi**, lint toza. Bot ishga tushadi va haqiqiy do'konlar
bilan ishlaydi.

**Asosiy savol hali ochiq:** audit raqamlari to'g'rimi — kabinet bilan
solishtirilmagan.

## Ishlaydigan narsalar

| Qism | Holat |
|---|---|
| Uzum Seller API klienti (faqat GET) | ✅ jonli sinalgan |
| Onboarding: til → oferta → telefon → API kalit | ✅ |
| Kalit berilgach **darhol** sync + audit | ✅ |
| 6 xil audit (5.1–5.5 + saqlash xarajati) | ⚠️ hisoblaydi, tasdiqlanmagan |
| Excel / PDF / pretenziya | ✅ |
| FBS yorliqlar, qoldiq, yunit-iqtisodiyot | ✅ |
| Obuna: 3 kun sinov, Basic 149k / Pro 299k | ✅ |
| Click to'lovi (Shop API webhook) | ✅ kod tayyor, sozlanmagan |
| Admin: birinchi `/start` bosgan avtomatik admin | ✅ |
| Docker Compose + PostgreSQL | ✅ qurilmagan (Docker yo'q) |

## ❗ Eng muhim ochiq masala

Bot AZIKO do'konida **17 ta yo'qotish (7.6 mln so'm)** ko'rsatyapti.
Raqamlar ichki jihatdan izchil, lekin **kabinet bilan solishtirilmagan**.

Shubha: Uzumning `quantityReturned` maydoni "omborga qaytib tushgan"ni
anglatadimi yoki "mijoz qaytargan, hali yo'lda"ni? Ikkinchisi bo'lsa,
qaytarishlar ikki marta hisoblanayapti.

**Qilinishi kerak (SPEC 10):** bitta SKU olib (masalan `693852`, 3 dona),
Uzum kabinetida qo'lda solishtirish. Natijaga qarab formulani tuzatish.

Tekshirilmaguncha sellerlar Uzumga da'vo yubormasligi kerak.

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

## Ma'lumotlar bazasi holati

```
Foydalanuvchi: 2 (8266195913 — admin, 7889583510 — seller)
Do'kon: AZIKO (7973), AZIKO PLAST (25273)
Mahsulot: 232 · Tannarxi bor: 228
Ombor harakati: 378 · Farqlar: 17
```

## Ishga tushirish

```bash
cd "E:\IT loihalar\UZUMUZBOT"
.venv\Scripts\python.exe -m app.bot.main                                    # bot
.venv\Scripts\python.exe -m uvicorn app.web.click_api:app --port 8000       # webhook
```

> Suhbat tugaganda bu jarayonlar to'xtaydi — qayta ishga tushirish kerak.

## Keyingi qadamlar (muhimlik tartibida)

1. **Audit raqamlarini kabinet bilan solishtirish** ← hammasidan muhim
2. GitHub'ga push + EasyPanel'ga deploy (`docs/easypanel.md`)
3. Click: yangi `CLICK_SECRET_KEY`, domen, webhook URL sozlash
4. Ofertaga rekvizit kerak bo'lsa qo'shish (hozir rekvizitsiz)
5. ~200 do'kondan keyin: sync'ni parallel qilish, audit yig'indilarini
   SQL tomoniga o'tkazish

## Maxfiy ma'lumot

Barchasi `.env` da (git'ga ham, Docker obraziga ham tushmaydi).
Chat tarixiga tushgan va **almashtirilishi kerak**:
- Uzum API kaliti
- Click `SECRET_KEY`, merchant kabinet paroli
