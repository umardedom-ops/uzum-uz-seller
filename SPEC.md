# Uzum Seller Bot — MVP Texnik Topshiriq (Claude Code uchun)

> Bu faylni Claude Code'ga to'liq nusxalab bering yoki loyiha papkasiga
> `SPEC.md` nomi bilan qo'ying va "read SPEC.md and start with Phase 1" deng.

---

## 1. Loyiha haqida

Uzum Market sellerlari uchun Telegram bot. Asosiy qiymat taklifi —
**"hisobot" emas, "pulingizni qaytaring"**. Bot sellerning do'kon
ma'lumotlarini kunlik tahlil qilib, Uzum tomonidan yo'qotilgan yoki
ortiqcha ushlangan pulni topadi va da'vo (pretenziya) uchun hujjat tayyorlaydi.

**Maqsadli mijoz:** 1–3 do'konli, oyiga 20–100 mln so'm aylanmasi bor seller.
**Narx:** 99 000 so'm/oy, 7 kun bepul sinov.
**Raqobatchi:** Market Plus (@uzumplusbot) — 290 000–490 000 so'm/oy, keng
funksional. Biz tor va arzon segmentni olamiz.

### Raqobatchi tahlili (2026-08-05, tarif rasmidan)

| Tarif | Narx | Do'kon | Asosiy |
|---|---|---|---|
| Premium | 490 000 | 5 | Uzum + Yandex, AI sharh javoblari, Avtobidder, Word pretenziya |
| Standard | 290 000 | 3 | Uzum, yo'qolgan mahsulot **faqat FBO**, Excel |
| Bepul | 5 kun | 1 | Excel **shtrix kodlarsiz** (da'vo qilib bo'lmaydi) |

**Muhim xulosalar:**

1. **Yo'qolgan mahsulot tahlili — ularning ham asosiy funksiyasi.** Bizning
   farqimiz funksiyada emas, **pul topish usullari sonida**: ularda 1 ta
   (yo'qolgan tovar), bizda 5 ta (5.1–5.5). Qaytarish, komissiya, logistika
   auditi va kompensatsiya sverkasi ularda **yo'q**.
2. Standard'da "faqat FBO" yozilishi — FBO qoldig'i API'da yo'qligini va
   ular kabinet kirishiga tayanishini tasdiqlaydi.
3. Bepul tarifda shtrix kodni yashirish — pulni ko'rsatib, da'vo qilishga
   yo'l bermaslik. **Biz buni nusxalamaymiz:** butun pozitsiyamiz ishonch
   ustida, sinov davrida to'liq ma'lumot beriladi.
4. Quvmaymiz: Yandex Market, AI sharh javoblari, Avtobidder, Didox.
   Bular kenglik; biz chuqurlikda raqobatlashamiz.

### Premium tarifidagi 18 xizmat — tasnif

**A. Qila olamiz, API tayyor (8 ta)**

| Xizmat | Manba |
|---|---|
| 5 ta do'kon | `GET /v1/shops` |
| Kunlik/haftalik/oylik savdo hisoboti | `/v1/finance/orders` |
| 10+ turdagi hisobot | hosila |
| Yunit iqtisodiyot | `commissionDto` + `expenses` + tannarx |
| FBS/DBS + QR/yorliq chiqarish | `GET /v1/fbs/order/{id}/labels/print`, `/v1/fbs/invoice/{id}/print` |
| 10+ tezkor xabar | hosila |
| Botga hodim qo'shish | Telegram tomoni |
| Botni guruh/kanalga qo'shish | Telegram tomoni |

**B. Asosiy funksiya — bizda kuchliroq (1 ta)**

Yo'qolgan mahsulot + Excel + Word pretenziya. Ularda **1 xil** audit,
bizda **5 xil** (5.1–5.5). Asosiy raqobat maydoni.

**C. Qila olmaymiz (2 ta)**

| Xizmat | Sabab |
|---|---|
| AI sharh javoblari | Sharhlar Seller API'da yo'q + javob yozish = **yozish amali** (9.1 buzadi) |
| Avtobidder (TOP-1) | Reklama stavkasi = yozish amali, API'da ham yo'q |

**D. Boshqa mahsulot — quvmaymiz (7 ta)**

Yandex Market integratsiyasi (4 band), Uzum→Yandex kartochka ko'chirish,
ETTY Didox, qo'shimcha do'kon narxi.

> Ularning ro'yxatining **39% i Yandex** — Premium (490k) va Standard (290k)
> orasidagi 200k farq asosan shu. Uzum tomonidagi funksiyalarning **~90%**
> ini qila olamiz.

**Pozitsiya:** *"Uzum uchun hammasi bor, Yandex yo'q — shuning uchun ancha
arzon. Va pulingizni 5 xil yo'l bilan qidiramiz, ular bitta yo'l bilan."*

---

## 2. Texnologiyalar

| Qatlam | Tanlov |
|---|---|
| Bot | Python 3.11+, aiogram 3.x |
| Backend | FastAPI (admin API va webhook uchun) |
| Baza | PostgreSQL 15+ |
| ORM | SQLAlchemy 2.0 (async) + Alembic |
| Fon vazifalari | APScheduler (MVP), keyin Celery + Redis |
| HTTP klient | httpx (async, retry bilan) |
| Hujjatlar | openpyxl (Excel), python-docx (pretenziya) |
| Shifrlash | cryptography (Fernet) |
| Deploy | Docker Compose, VPS (2 vCPU / 4GB yetadi) |

Loyiha strukturasi:

```
app/
  bot/            # aiogram: handlers, keyboards, states, texts
  core/           # config, security, logging
  db/             # models, migrations, repositories
  uzum/           # Uzum bilan integratsiya (client, auth, parsers)
  services/       # biznes-mantiq: sync, audit, reports
  workers/        # scheduler joblari
  docs/           # excel va docx generatorlar
tests/
```

---

## 3. Uzum bilan ulanish — ENG MUHIM QISM

### 3.1 Ikki manba

**A. Rasmiy Seller API** — `https://api-seller.uzum.uz`
Seller kabinetdan token oladi. Barqaror, lekin ma'lumot chegaralangan.
Birinchi navbatda SHU ishlatiladi.

**B. Kabinet sessiyasi (xodim usuli)** — API bermaydigan ma'lumot uchun.
Biz o'z telefon raqamimizga Uzum seller akkaunti ochamiz. Seller o'z
kabinetida **Xodimlar → Xodimni qo'shish** orqali bizning raqamni
qo'shadi va do'konlarga kirish beradi. Shundan keyin bizda o'sha
do'konlarga kabinet darajasidagi kirish bo'ladi.

> **Muhim:** rolni imkon qadar past huquqli qilib tanlang. Kodda
> **write-operatsiyalar umuman bo'lmasin** — `uzum/client.py` faqat GET
> qilsin, bu qattiq qoida.

**Qaysi rol so'raladi (raqobatchi tahlilidan, 2026-08-05).** Uzum "Xodimni
qo'shish" oynasidagi rollar (matn videodan aynan olingan):

| Rol | Huquqlar |
|---|---|
| Менеджер | do'konni boshqarishning **butun funksionali**, faqat pul yechish yaratib bo'lmaydi |
| Поддержка | tovarlar, taymerli chegirmalar, promokodlarni ko'rish |
| **Финансовый менеджер** | tovarlar, promokodlar, **yuk xatlari (накладные), moliya**, **ombor qoldiqlarini yuklab olish** |
| Маркетолог | tovarlarni ko'rish/tahrirlash, aksiyalarni boshqarish, moliyani ko'rish, **sotuvlar ro'yxatini yuklab olish** |
| Контент менеджер | tovar yaratish, sotuvda bo'lmagan tovar va narxlarni tahrirlash |
| Tovarlarni tayyorlash markazi xodimi | tovar, yuk xati, etiketka yaratish |

Raqobatchi (Market Plus) **Менеджер** so'raydi — bu ortiqcha huquq va
sellerni cho'chitadi. Biz **Финансовый менеджер** so'raymiz: tovar
tahrirlash huquqisiz, ammo audit uchun kerakli asos bor. Bu to'g'ridan-to'g'ri
sotuv argumenti: *"Biz do'koningizni o'zgartira olmaymiz — faqat o'qiymiz."*

> ⚠️ **Phase 0 da tekshirilishi shart:** rol tavsifida "sotuvlar ro'yxatini
> yuklab olish" **Маркетолог** da yozilgan, Финансовый менеджер da emas.
> Qaytarishlar (возвраты) esa hech qaysi rolda aniq aytilmagan. 5.1
> formulasiga `sotilgan` va `qaytib tushgan` kerak. Shuning uchun
> inventarizatsiyada aynan **Финансовый менеджер roli bilan kirib**,
> buyurtma/sotuv/qaytarish ma'lumoti ochiqmi — tekshiring (ehtimol
> "Mablag'lar/Moliya" bo'limidagi tranzaksiya hisobotida bor). Agar
> yetmasa — variantlar: (a) qo'shimcha rol so'rash, (b) Менеджер ga
> qaytish. Qarorni ma'lumot bilan qabul qiling, taxmin bilan emas.

### 3.1-bis QABUL QILINGAN ARXITEKTURA (2026-08-06 yangilandi)

> ✅ **YAKUNIY QAROR: faqat API kalit. Kabinet kerak emas.**

2026-08-06 da aniqlandi: `GET /v1/product/shop/{shopId}` javobidagi
**`quantityActive` — bu FBO ombor qoldig'i** (kabinetdagi «FBO qoldiqlar,
dona» ustuni bilan bir xil). Shuningdek `quantitySold`, `quantityReturned`,
`skuDimension`, `blocked` ham shu yerda.

```
API kalit  →  YAGONA manba, hammasi shu bilan ishlaydi
              shops, products (FBO+FBS qoldiq, jami sotilgan/qaytgan,
              o'lchamlar, blok holati), orders, returns, finance,
              yuk xatlari.
```

**Xodim mexanizmi, yagona raqam, kabinet sessiyasi — BEKOR QILINDI.**
Ular endi kerak emas. Bu bizga raqobatchidan aniq ustunlik beradi:

| | Raqobatchi (Market Plus) | Biz |
|---|---|---|
| Ulanish | 5 qadam, Менеджер roli | **1 qadam, API kalit** |
| Bizga Uzum akkaunt | kerak | **kerak emas** |
| Sessiya boshqaruvi (SMS, cookie) | kerak | **kerak emas** |
| Bitta nuqta xavfi | bor | **yo'q** (har seller o'z kaliti) |

Seller botga API kalitini yuboradi → bot do'konlarni o'zi topadi →
darhol ishga tushadi.

> **Xavf (ochiq tan olinadi):** yagona raqam — bitta nuqta. Uzum uni
> bloklasa, FBO auditi barcha mijozlarda bir vaqtda to'xtaydi. Shuning
> uchun FBO **qo'shimcha**, asosiy emas: kalit ishlayotgan mijozlar
> ta'sirlanmaydi. Rate limit qat'iy saqlanadi (do'konга 1 so'rov/sek).

> ✅ **HAL QILINDI (2026-08-06).** Raqam **Uzum Sellers akkaunti** sifatida
> ro'yxatdan o'tishi shart — oddiy xaridor akkaunti yetmaydi. Rasmiy
> qo'llanma (13-bo'lim): *"Raqam Uzum platformasida sotuvchi akkaunti
> sifatida ro'yxatdan o'tgan bo'lishi kerak."*
>
> Ro'yxatdan o'tish: `seller.uzum.uz/seller/signup` → biznes turi
> **«Нет юрлица»** → hujjat/INN kerak emas. Do'kon yaratilmaydi.
>
> Yagona raqam: `+998 99 262 01 01`. Elore Parfume ga xodim qilib
> qo'shildi va ishladi.

> **Tekshirilmagan imkoniyat:** `GET /v1/product/shop/{shopId}` javobidagi
> `skuList[].quantityActive` FBO qoldig'i bo'lishi mumkin. Agar shunday
> bo'lsa — xodim mexanizmi umuman kerak emas, ulanish 1 qadamga tushadi.
> Sinov do'koni bo'sh bo'lgani uchun aniqlanmadi. **Qoldig'i bor do'konda
> birinchi bo'lib shuni tekshiring.**

### 3.2 Qilinadigan birinchi ish (kod yozishdan oldin)

1. Test seller kabinetiga kiring, Swagger'ni token bilan oching:
   `https://api-seller.uzum.uz/api/seller-openapi/swagger/...`
   Barcha endpointlarni `docs/api-inventory.md` fayliga yozib chiqing:
   yo'l, metod, parametrlar, javob strukturasi namunasi.
2. Kabinetda F12 → Network ochib, quyidagi sahifalarni bosing va
   ketgan so'rovlarni yozib oling:
   - FBO qoldiqlari / ombor harakati
   - Moliya / hisob-kitob
   - Qaytarishlar
   - Kompensatsiyalar
3. Har bir kerakli ma'lumot uchun manbani belgilang: API yoki kabinet.

**Bu inventarizatsiya tugamaguncha keyingi bosqichga o'tmang.**

### 3.3 Sessiyani boshqarish

- Login SMS-kod bilan bo'lsa, kod qo'lda kiritiladigan admin-panel qiling
- Cookie/token'ni bazada Fernet bilan shifrlab saqlang
- Har so'rovdan oldin amal qilish muddatini tekshiring, kerak bo'lsa yangilang
- Sessiya o'lsa — adminga Telegram orqali darhol alert
- Rate limit: bitta do'konga soniyada 1 tadan ko'p bo'lmagan so'rov,
  do'konlar orasida navbat. Bitta akkaunt yuzlab do'konga so'rov yuboradi —
  agressiv bo'lsangiz bloklanasiz.

---

## 4. Ma'lumotlar bazasi sxemasi

```sql
users            -- telegram_id, phone, lang, created_at
subscriptions    -- user_id, plan, status, trial_ends_at, paid_until
shops            -- user_id, uzum_shop_id, title, connected_at, is_active
shop_credentials -- shop_id, auth_type(api|cabinet), encrypted_token, expires_at

products         -- shop_id, sku, barcode, title, category, size, weight
                 -- cost_price (seller o'zi kiritadi), commission_pct

orders           -- shop_id, uzum_order_id, sku, qty, price, status,
                 -- commission_amount, delivery_amount, created_at, closed_at
returns          -- shop_id, order_id, sku, qty, reason, status, received_at

stock_snapshots  -- shop_id, sku, qty, warehouse, captured_at   [KUNIGA 1 MARTA]
stock_movements  -- shop_id, sku, type(in|sale|return|writeoff), qty, at

finance_ops      -- shop_id, type, amount, description, at
compensations    -- shop_id, sku, qty, amount, status, at

discrepancies    -- shop_id, sku, kind, qty, amount, period, detected_at,
                 -- status(new|claimed|resolved|rejected), claim_doc_path
claims           -- shop_id, discrepancy_ids[], doc_path, sent_at, result

alerts_config    -- shop_id, alert_type, enabled, threshold
sync_runs        -- shop_id, started_at, finished_at, status, error
```

> `stock_snapshots` — mahsulotning yuragi. Uzum "hozirgi holat"ni beradi,
> tarixni faqat biz saqlaymiz. Bot ishga tushgan kundan hisob boshlanadi.

---

## 5. Biznes-mantiq: auditlar

### 5.1 Yo'qolgan tovar (FBO)

Har bir SKU uchun, `[T1, T2]` davri bo'yicha:

```
kutilgan_qoldiq = qoldiq(T1)
                + omborga_qabul(T1..T2)
                + qaytib_tushgan(T1..T2)
                - sotilgan(T1..T2)
                - hisobdan_chiqarilgan(T1..T2)

farq = kutilgan_qoldiq - haqiqiy_qoldiq(T2)

agar farq > 0  →  yo'qolgan tovar
zarar = farq × tannarx   (yoki sotuv narxi — sellerning tanlovi)
```

Shovqinni kamaytirish:
- `farq == 0` bo'lsa yozmaslik
- 1 dona farqni "kuzatuvda" deb belgilash, 2+ dan da'vo qilish
- Inventarizatsiya kunlarini istisno qilish

### 5.2 Qaytarish auditi

Mijoz qaytardi, lekin omborga tushmadi:

```
qaytarish statusi = "qaytarildi"  AND
omborga qabul yozuvi yo'q  AND
qaytargan sanadan 14+ kun o'tgan
→ yo'qolgan qaytarish
```

### 5.3 Komissiya auditi

```
kutilgan_komissiya = sotuv_summasi × shartnomadagi_foiz(kategoriya)
farq = ushlangan_komissiya - kutilgan_komissiya
agar farq > 1000 so'm → ortiqcha ushlangan
```

Kategoriya foizlarini `commission_rates` jadvalida saqlang, admin qo'lda
yangilaydi (Uzum foizlarni o'zgartiradi).

### 5.4 Logistika auditi

```
kartochkadagi o'lcham/og'irlik → tarif bo'yicha kutilgan to'lov
haqiqiy ushlangan to'lov bilan solishtirish
farq > 15% → tekshirish kerak
```

### 5.5 Kompensatsiya sverkasi

`discrepancies` da yozilgan zarar uchun `compensations` da to'lov
kelganmi va summasi to'g'rimi — tekshirish.

---

## 6. Chiqadigan hujjatlar

### 6.1 Excel (openpyxl)

Ustunlar: SKU, shtrix kod, tovar nomi, davr, kutilgan qoldiq, haqiqiy
qoldiq, farq (dona), tannarx, zarar (so'm), turi, aniqlangan sana.
Pastda jami. Shtrix kod **majburiy** — usiz seller Uzumga hech narsa
isbotlay olmaydi.

### 6.2 Pretenziya (python-docx)

Shablon: sarlavha, seller rekvizitlari, do'kon nomi va ID, davr,
yo'qolgan tovarlar jadvali, umumiy zarar summasi (raqam va so'z bilan),
talab matni, sana, imzo joyi. Ma'lumotlar shablonga o'rnatiladi.

> Shablon matnini haqiqiy sellerdan yoki yuristdan oling — Uzum qabul
> qiladigan shakl bo'lishi kerak.

---

## 7. Bot menyusi

```
/start
 └─ Til: 🇺🇿 O'zbek / 🇷🇺 Русский
 └─ Oferta bilan tanishish → Qabul qilaman
 └─ Telefon raqamini ulashish (Telegram contact tugmasi)
 └─ Do'konni ulash (yo'riqnoma + skrinshotlar)
      └─ Xodim qo'shish → do'kon ID'larini yuborish
      └─ Tekshiruv → "✅ Ulandi. 20-30 daqiqa kuting"

ASOSIY MENYU
├─ 💰 Yo'qotilgan pul
│   ├─ Yo'qolgan tovarlar
│   ├─ Yo'qolgan qaytarishlar
│   ├─ Ortiqcha komissiya
│   ├─ 📄 Excel yuklab olish
│   └─ 📝 Pretenziya tayyorlash
├─ 📊 Hisobotlar
│   ├─ Bugun / Kecha
│   ├─ Hafta / Oy
│   └─ Tovarlar bo'yicha (ABC)
├─ 📦 Qoldiqlar
│   ├─ Tugayotgan tovarlar
│   └─ Sotib olish rejasi
├─ 🧮 Yunit-iqtisodiyot
│   └─ Tannarx kiritish (SKU bo'yicha yoki Excel yuklash)
├─ 🔔 Bildirishnomalar (yoqish/o'chirish, chegaralar)
└─ ⚙️ Sozlamalar (do'konlar, tarif, til, yordam)
```

**Kunlik avtomatik xabar (har kuni 09:00):**

```
📊 Kecha, 4-avgust — Royal Home

Buyurtmalar: 42 ta (+12%)
Tushum: 6 240 000 so'm
Sof foyda: 1 380 000 so'm (marja 22%)
Qaytarishlar: 3 ta

⚠️ 3 ta tovar 7 kundan kam qoldi
💰 Bu oy topilgan yo'qotish: 1 840 000 so'm
```

---

## 8. Bosqichlar (Claude Code uchun vazifalar)

### Phase 0 — Tayyorgarlik
- [ ] `docs/api-inventory.md` — barcha endpointlar inventarizatsiyasi
- [ ] Docker Compose: postgres + app
- [ ] Config, logging, Alembic sozlash

### Phase 1 — Skelet
- [ ] aiogram bot, /start, til tanlash, oferta, telefon olish
- [ ] DB modellar va birinchi migratsiya
- [ ] `uzum/client.py` — **faqat GET**, retry, rate limit, xato boshqaruvi

### Phase 2 — Ulanish
- [ ] Do'kon ulash oqimi + yo'riqnoma matni
- [ ] Do'kon ID validatsiyasi (test so'rov)
- [ ] Credential'larni Fernet bilan shifrlab saqlash
- [ ] Birinchi to'liq sinxronizatsiya (tarixiy ma'lumot)

### Phase 3 — Sync
- [ ] Scheduler: har soatda buyurtma/qaytarish, kuniga 1 marta snapshot
- [ ] Idempotent upsert (takroriy yozuv bo'lmasin)
- [ ] `sync_runs` jurnali va xato bo'lsa admin alerti

### Phase 4 — Audit yadrosi
- [ ] Yo'qolgan tovar hisobi (5.1)
- [ ] Qaytarish auditi (5.2)
- [ ] Komissiya auditi (5.3)
- [ ] `discrepancies` ga yozish, dublikat qilmaslik
- [ ] **Unit testlar** — bu qism xato qilsa mahsulot o'ladi

### Phase 5 — Chiqish
- [ ] Excel generator (shtrix kod bilan)
- [ ] Pretenziya .docx generator
- [ ] Kunlik hisobot xabari
- [ ] Qoldiq va boshqa alertlar

### Phase 6 — Monetizatsiya
- [ ] 7 kunlik trial, obuna holati, muddati tugaganda cheklash
- [ ] To'lov (Payme/Click) yoki qo'lda tasdiqlash — MVP'da qo'lda ham bo'ladi
- [ ] Admin panel: mijozlar, sync holati, xatolar

---

## 9. Qattiq qoidalar

1. **Hech qanday yozish amali yo'q.** Uzum tomoniga faqat GET.
2. Barcha credential shifrlangan holda saqlanadi, logga hech qachon tushmaydi.
3. Seller yuborgan maxfiy ma'lumot (token bo'lsa) qabul qilingach xabar o'chiriladi.
4. Har bir do'kon ma'lumoti qat'iy izolyatsiya — `shop_id` bo'yicha filtr
   har bir so'rovda majburiy.
5. Audit natijasi "aniq fakt" emas, "tekshirish kerak" deb taqdim etiladi —
   noto'g'ri da'vo sellerni Uzum oldida noqulay ahvolga solmasin.
6. Sync xatolari jim yutilmaydi, adminga chiqadi.

---

## 10. Birinchi kun uchun test rejasi

Bitta haqiqiy do'konni ulang va qo'lda tekshiring:
- 3 oylik ma'lumotni qo'lda Excel'da hisoblang
- Bot chiqargan farq bilan solishtiring
- Mos kelmasa — formulani emas, **ma'lumot manbasini** tekshiring
  (ko'pincha ombor harakati to'liq tortilmagan bo'ladi)

Agar haqiqiy yo'qotilgan pul topilsa — mahsulot bor.
Topilmasa — yo'nalishni o'zgartiring, kod yozishda davom etmang.
