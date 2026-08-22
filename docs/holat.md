# Loyiha holati — 2026-08-11

> Yangi suhbat boshlanganda **shu faylni birinchi bo'lib o'qing**.
> Texnik topshiriq: `SPEC.md`. API ma'lumotnomasi: `docs/api-inventory.md`.

## Qisqacha

Uzum Market sellerlari uchun Telegram bot. **921 test o'tadi**, lint toza,
serverda 24/7 ishlaydi va haqiqiy do'kon bilan ulangan (231 mahsulot).

**Nima ishlaydi:** audit va pretenziya · hisobotlar · qoldiq · FBS
buyurtma/yorliq/akt · yunit-iqtisodiyot · Click to'lovi · hodimlar ·
guruh/kanal · web-kabinet · Google Sheets · qoldiqqa **yozish** (jonli).

**Raqobatchi bilan holat:** `@uzumplusbot` (Market Plus) to'liq tahlil
qilingan. Ularda bor-u bizda yo'q narsa qolmadi (Yandex/AI/Didox —
ataylab chiqarilgan; aksiya endpointi Uzum API'da umuman yo'q).

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
| **Papkali bosh menyu** | ✅ flagman + 3 papka (`keyboards/menu.py`, 2026-08-09) |
| **Top tovarlar** hisoboti | ✅ soni/foyda bo'yicha (`handlers/top.py`, 2026-08-09) |
| **Barcha yorliqlar bitta PDF** | ✅ FBS'da (`services/fbs.py`, `pypdf`, 2026-08-09) |
| **Ko'p do'kon tanlash** | ✅ Sozlamalar → Do'konlarim (`User.active_shop_id`, 2026-08-10) |
| **Qoldiq o'zgartirish (YOZISH)** | ✅ **JONLI** — sxema spetsifikatsiyadan, tasdiq + jurnal bilan |
| **Qaytgan tovarni qoldiqqa qo'shish** | ✅ tasdiq bilan, har qaytarish bir marta |
| **Hodimlar · Guruh/kanal · Web-kabinet** | ✅ jamoa fichalari (2026-08-11) |
| **Google Sheets** | ✅ ulangan, kunlik 09:30 + `/sheets`, diagrammalar bilan |
| **Click to'lovi** | ✅ **YOQILGAN** — `click: on`, webhook ishlaydi |
| `/stopapi` · yashirin `/admindad` | ✅ 2026-08-11 (uzilganda do'kon **butunlay o'chadi** — 2026-08-14) |

> ✅ **Click ishlaydi** (2026-08-11). Servis «Uzum Seller FinBot»,
> `SERVICE_ID=109666`, `MERCHANT_ID=63121`. Webhook manzillari Click
> kabinetida sozlangan: `<domen>/click/prepare` va `/click/complete`.
> Tekshirish: `curl -s https://uzumbot.8xspuf.easypanel.host/health`
> → `{"status":"ok","click":"on"}`.
>
> ⚠️ `CLICK_SECRET_KEY` bir marta chatga tushgan — **almashtirish tavsiya
> etiladi** (Click kabinetidan Reset, keyin `.env` da yangilash).

### Click auditi (2026-08-22)

Integratsiya rasmiy talablarga solishtirildi. **Asosiy qism to'g'ri:**
imzo formulasi ikkala bosqichda hujjatdagidek, imzo birinchi bo'lib
tekshiriladi, javob har doim HTTP 200, xato kodlari to'liq, so'rov va
javob jurnalga yoziladi, sir logga tushmaydi.

⭐ Eng qimmat xato **yo'q**: summa mijozdan olinmaydi. `create_payment`
uni `price_for(plan) * months` bilan serverda hisoblaydi, ya'ni
brauzerdan «1000 so'm» yozib yuborib bo'lmaydi.

Uchta narsa tuzatildi:

1. **To'lov havolasidagi summa formati.** `amount=149000` yuborilardi,
   hujjat esa **N.NN** talab qiladi. Endi `{amount:.2f}` → `149000.00`.
2. **`complete` da tekshiruv tartibi.** `error < 0` sharti holat
   tekshiruvidan **oldin** turardi: to'langan yozuvga kelgan reversal
   avval `reject_payment` ga tushardi va javob «bekor qilindi» bo'lardi.
   Obuna zarar ko'rmasdi (`reject_payment` faqat `PENDING` ni
   o'zgartiradi) — ya'ni himoya **tasodifiy** edi. Endi holat birinchi
   tekshiriladi va javob `ALREADY_PAID` bo'ladi.
3. **`int(req.error)` qo'riqsiz edi.** Raqam bo'lmagan qiymat kelsa
   webhook **500** qaytarardi; Click 500 ni «javob yo'q» deb hisoblab
   so'rovni takrorlayverardi. Endi `_click_failed()` uni yutmaydi —
   sababni logga yozadi va oqim davom etadi.

### Fiskalizatsiya (OFD) — kod yozilgan, sozlanmagan

Ilgari umuman yo'q edi: **pul olinardi, soliq cheki yaratilmasdi.**
Endi `app/services/click_ofd.py` bor (21 test).

⚠️ **Bu Shop API emas, Merchant API.** Autentifikatsiya boshqacha:
Shop API — MD5 imzo (Click bizga keladi), Merchant API — SHA1 `Auth`
sarlavhasi (biz Click'ga boramiz).

Chek `complete` muvaffaqiyatli bo'lganda yuboriladi
(`click_api._fiscalize`). **To'lov javobiga ta'sir qilmaydi** — chek
yaratilmasa ham Click «muvaffaqiyat» ko'radi, aks holda u to'lovni xato
deb hisoblab pulni qaytaradi. Sabab esa `log.error` bilan yoziladi.

Soliq subyekti: **YaTT** → `CommissionInfo` da `PINFL` (JSHSHIR, 14
raqam). Qiymat `.env` da, git'ga tushmaydi.

**Deploy holati (2026-08-22):** kod `master` da va serverda jonli
(`3beef6e`). Lekin **server `.env` da OFD qiymatlari yo'q** — lokalda
bor, serverga qo'shilmagan. Tekshirish:

```bash
ssh root@46.62.199.124 "docker exec uzumbot-bot-1 python -c \"from app.services.click_ofd import check_ready; from app.core.config import get_settings; print(check_ready(get_settings()) or 'TAYYOR')\""
```

❗ **Hali ishlamaydi** — sozlamalar bo'sh, `check_ready()` qaysi biri
yo'qligini aniq aytadi:

| Sozlama | Holat |
|---|---|
| `CLICK_MERCHANT_USER_ID` | ✅ `89568` — lokal va serverda |
| `CLICK_OFD_PINFL` | ✅ YaTT JSHSHIR — lokal va serverda |
| `CLICK_OFD_SPIC` | ❌ pastdagi izlanishga qarang |
| `CLICK_OFD_PACKAGE_CODE` | ❌ kabinetdan olinadi |

#### IKPU izlanishi (2026-08-22)

`tasnif.soliq.uz` ning ichki API'si orqali tasniflagich daraxti
ochildi (`/api/cls-api/group`, `/class/short-info`,
`/position/short-info`, `/subposition/short-info`). Portal qidiruvi
(`elasticsearch/search`) **ishlatib bo'lmaydi** — u kod bo'yicha aniq
moslik topmaydi va har qanday so'rovga Coca-Cola qaytaradi.

Xizmat guruhlari `100`–`118`. Bizga tegishlilari:

* **`103` — Ахборот ва алоқа соҳасидаги хизматлар** (80 ta kod)
* `112` — Рақамли ахборот технологиялари (atigi 2 ta kod)

Eng mos joy — **klass `10305`, pozitsiya `10305008`**
(«Оплата за право на использование программного обеспечения»):

| Subpozitsiya | Nomi | Mosligi |
|---|---|---|
| **`10305008002`** | dasturiy ta'minotga (bazaga) **kirish berish** | ⭐ SaaS uchun aynan shu |
| `10305008003` | foydalanish **huquqini** berish (litsenziya) | litsenziya modeli uchun |
| `10305001001` | loyihalash / ishlab chiqish / sotish | ❌ bizniki emas |
| `11201001001` | raqamli AT xizmatlari (umumiy) | zaxira variant |

⚠️ Internetda uchraydigan **`10305001001000000`** — bu **ishlab
chiqish** xizmati (buyurtma asosida dastur yozish). Obunaga mos emas.

Xizmat o'lchov birliklari: `id=25` «услуга (сум)», `id=85` «услуга (раз)».

**Qolgan ish:** to'liq 17 xonali MXIK va unga biriktirilgan
`PackageCode` — bularni `tasnif.soliq.uz` **shaxsiy kabinetidan**
(E-IMZO bilan kirib, «Танланган МХИКлар») olish kerak. Ochiq API ularni
bermaydi.

`CLICK_OFD_VAT_PERCENT` standart **0** — soddalashtirilgan tartibdagi
YaTT QQS to'lovchisi emas. QQS to'lovchisi bo'lsangiz 12 qo'ying.

> Eslatma: `data.py` dagi `ikpu` maydoni — bu **Uzum mahsulotlariniki**,
> fiskalizatsiyaga aloqasi yo'q. Adashtirmang.

> ⚠️ Guvohnomadagi faoliyat turi — **chakana savdo** (oziq-ovqat va
> nooziq-ovqat tovarlari). Bot esa **dasturiy xizmat obunasi** sotadi.
> IKPU tanlashdan oldin buni buxgalter bilan aniqlang: faoliyat turi
> mos kelmasa chek o'tsa ham keyin savol tug'ilishi mumkin.

**Qolgan ish:** chek QR havolasini (`receipt_qr`) bazaga saqlash va
mijozga ko'rsatish. Hozir `payments` jadvalida maydon yo'q — migratsiya
kerak. Kalitlar kelgach qilinadi.

## Telegram Mini App (2026-08-22)

Veb-kabinetdagi ma'lumot endi **Telegram ichida** ham ochiladi.

**Kirish sharti ikkita:** faol obuna (sinov ham) **va** ulangan do'kon.
Ikkalasi ham `app/web/miniapp.py` da tekshiriladi — bo'lmasa ochiq sabab
va chiqish yo'li ko'rsatiladi, bo'sh ekran qolmaydi.

**Botda qayerda ko'rinadi:**

| Joy | Qachon paydo bo'ladi |
|---|---|
| Pastdagi «Kabinet» menyu tugmasi | Do'kon ulangan zahoti, **shu foydalanuvchida** (`set_chat_menu_button`) |
| «📊 Kabinetni ochish» inline tugma | Birinchi sync **tugagach** — ko'rsatadigan ma'lumot paydo bo'lganda |

Ikkinchisining vaqti ataylab shunday: kalit ulangan zahoti baza bo'sh
bo'ladi va o'sha payt ochilsa seller birinchi marta bo'sh ekran ko'rardi.

### Imzo tekshiruvi — eng nozik joy

`app/services/telegram_webapp.py`, 22 test. Telegram `initData` beradi;
u **oddiy matn**, brauzer konsolidan istalgan `id` yozish mumkin.
Tekshirmasak har kim istalgan sellerning do'konini ko'radi — raqobatchida
(`@uzumplusbot`) aynan shu xato bor.

```
secret_key = HMAC_SHA256(key="WebAppData", msg=<bot token>)
hash       = HMAC_SHA256(key=secret_key,  msg=data_check_string)
```

⚠️ Kalit va xabar **teskari** tuyuladi: kalit — o'zgarmas `"WebAppData"`
satri, xabar — bot tokeni. Odatdagidek yozilsa imzo hech qachon to'g'ri
chiqmaydi va sabab ko'rinmaydi.

Qo'shimcha himoya: `auth_date` 24 soatdan eski bo'lsa rad etiladi
(o'g'irlangan `initData` muddatsiz ishlatilmasin), kelajakdagi sana ham
rad etiladi (soat farqiga 5 daqiqa zaxira).

Rad etilganda foydalanuvchiga **umumiy** xabar ketadi, sabab esa log'da —
soxta so'rov yuborayotgan odamga yo'l ko'rsatmaymiz.

### Sozlama

Manzil `CLICK_BASE_URL` dan olinadi (`<base>/app`). U **https** bo'lmasa
`webapp_url` bo'sh qaytadi va tugmalar **umuman chizilmaydi** — Telegram
noto'g'ri manzilni rad etadi va tugma jimgina ishlamay qolardi.

### Keyingi bo'lak

Qoldiq tahrirlash va FBS ko'p tanlash ekranlari. Maket:
`https://claude.ai/code/artifact/0c0e4c1e-7a64-427e-a33e-4070b59f23ac`

## Yozish (POST) — JONLI

Ilgari Uzumga faqat GET yuborardik. **2026-08-11 dan yozish yoqilgan**
(`UZUM_WRITES_ENABLED=true` serverda).

**Sxema taxmin emas, spetsifikatsiyadan.** ⭐ Muhim topilma: OpenAPI
spetsifikatsiyasi **API kalit bilan** ochiladi:

```
GET /swagger/api-docs  +  Authorization: <TOKEN>   →  274 KB JSON
```

Brauzerda `RBAC: access denied` chiqadi, kalit bilan esa ishlaydi.
**Body kerak bo'lsa shu yerdan oling, taxmin qilmang.**

`POST /v2/fbs/sku/stocks`:

```json
{ "skuAmountList": [ { "barcode": "1000113258397", "amount": 30 } ] }
```

⚠️ Identifikator — **`barcode`** (majburiy), `skuId` **ixtiyoriy**.
Bizning eski taxminimiz (`{"skus":[{"skuId":...}]}`) noto'g'ri edi.
Shu sabab servis shtrix kodni bazadan izlaydi; topilmasa sababni ochiq
aytadi. Barcha yozish endpointlari: `docs/api-inventory.md §5-quinquies`.

**Xavfsizlik uch qatlam saqlanib qoldi:**

1. **Ajratilgan** — yozish faqat `app/uzum/writes.py`; audit uni import
   qilmaydi, "audit faqat GET" kodda ko'rinadi.
2. **Bayroq** — `UZUM_WRITES_ENABLED` (o'chiq bo'lsa demo rejim).
3. **Tasdiq + jurnal** — har amal tasdiq bilan, `stock_write_log` ga
   yoziladi (kim, sku, eski→yangi, natija). `base.post` qayta urinmaydi.

**Ikki oqim:**

| Oqim | Qayerda |
|---|---|
| Qo'lda: SKU tanlash → yangi son → tasdiq | `handlers/stock_edit.py` |
| Qaytgan tovarni qoldiqqa qo'shish | `services/returns_restock.py` |

Qaytarish oqimida: faqat **qabul qilingan** qaytarish (`received_at`),
har biri **bir marta** (`Return.restocked_at`), tasdiq har doim.

> ⚠️ **Sinalmagan:** hozirgi do'konlar FBO (FBS qoldig'i 0). Jonli yozish
> haqiqiy FBS do'konda hali sinab ko'rilmagan. Birinchi sinovda kichik
> o'zgarishdan boshlang va Uzum kabinetida tekshiring.

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

## 2026-08-10/11 da qilingan ishlar

**Raqobatchi to'liq tahlil qilindi** — `@uzumplusbot` (Market Plus).
Narx: Standard 290k / Premium 490k (bizniki 149k/299k). Ular kabinetga
«Менеджер» xodim bo'lib kiradi (to'liq huquq), bizda faqat API kalit.
Ularning zaifligi: `/start` buzuq, token URL'da ochiq, login = Telegram ID.

**Jamoa fichalari** (ularda bor edi, bizda yo'q edi):
* **Hodimlar** — egasi Telegram ID orqali qo'shadi; hodim biriktirilgan
  do'konni ko'radi, lekin to'lov/tarif/hodim boshqaruviga kira olmaydi
  (`services/team.py`, kirish nazorati 14 ta test bilan).
* **Guruh/kanal** — bot guruhga qo'shiladi, u yerda `/ulash` yoziladi.
  Kunlik hisobot o'sha yerga ham boradi.
* **Web-kabinet** — `/kabinet` bir martalik havola beradi (15 daqiqa),
  ochilgach cookie'ga almashadi va URL tozalanadi. Token bazada sha256
  xesh holida. Raqobatchi xatosi (token har havolada ochiq) takrorlanmadi.

**Google Sheets** — biznes hisoboti avtomatik sinxronlanadi (kunlik 09:30
va `/sheets`). Besh varaq: Xulosa · Obunachilar · To'lovlar · Promokodlar ·
Diagramma (3 grafik). Kalit: `/opt/uzumbot/secrets/google-creds.json`.

**Boshqa qo'shilganlar:** aktlar ro'yxati (o'lik ficha edi) ·
`forecastOutOfStock` (Uzum prognozi, o'rtachadan ustun) · bozor narxi ·
sotuvchi artikuli · `/stopapi` · yashirin `/admindad`.

**Uchta jonli xato tuzatildi:**
1. Promokod faqat bitta FSM holatida qabul qilinardi → bot restartdan
   keyin **jim qolardi**. Endi `handlers/fallback.py` ushlaydi.
2. `/start` do'koni ulangan sellerdan ham **API kalit so'rardi**. Endi
   manba — baza, FSM emas.
3. «🚀 Boshlash» tugmasi handlersiz edi. `tests/unit/test_buttons.py`
   endi har bir tugmaga handler borligini tekshiradi.

## Xavfsizlik (2026-08-11)

* **fail2ban** o'rnatildi — 10 026 ta parol topish urinishi bor edi,
  o'rnatgan zahoti 6 ta IP bloklandi.
* **Web porti yopildi** — 8000 endi `127.0.0.1` da; Traefik konteyner
  tarmog'i orqali yetadi. ⚠️ `ufw` Docker portlarini bloklamaydi
  (DOCKER-USER zanjiri) — port bog'lash yagona ishonchli yo'l.
* **Ochiq qolgan:** SSH parol autentifikatsiyasi hali yoqiq
  (`PasswordAuthentication no` qo'yilmagan). Chatga tushgan sirlar:
  `BOT_TOKEN`, `FERNET_KEY`, `POSTGRES_PASSWORD`, Click va Google
  kalitlari — almashtirish kerak.
* Port **3000** = EasyPanel paneli, internetga ochiq (tegilmagan).

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
14. **`/stopapi` dan keyin ham xabarnoma kelardi** (2026-08-14). Kalit
    o'chardi, lekin do'kon va yig'ilgan ma'lumot joyida qolardi — fon
    vazifalari (sync, audit, xabarnoma, kunlik hisobot) do'konni
    `is_active` bo'yicha tanlaydi va **bazadagi** eski ma'lumot ustida
    ishlashda davom etardi ("tovar bloklangan" xabari uzilgan do'kondan
    kelaverardi).

    Endi `/stopapi` do'konni **butunlay uzadi**: `disconnect_api`
    kalitni, do'kon qatorini va unga tegishli hamma jadvalni o'chiradi
    (`_SHOP_OWNED_TABLES` — mahsulot, buyurtma, qaytarish, qoldiq,
    audit, xabarnoma sozlamasi, jamoa, yozish jurnali), `active_shop_id`
    ni tozalaydi. Xabar yasashga manba qolmaydi. Obuna va to'lov
    tarixi tegilmaydi — ular foydalanuvchida.

    ⚠️ Bola jadvallar DB darajasida `ondelete="CASCADE"`, lekin SQLite
    buni `PRAGMA foreign_keys=ON` siz bajarmaydi — shuning uchun xizmat
    ularni o'zi o'chiradi. Yangi `shop_id` li jadval qo'shsangiz,
    `_SHOP_OWNED_TABLES` ga ham qo'shing.

    Qayta ulash: kalit yuboriladi va **kalit qaysi do'konniki bo'lsa,
    o'sha do'kon** ulanadi (`GET /v1/shops`) — eski do'kon qaytmaydi.

    Qo'shimcha himoya: `alerts.send_alerts` va `reports.send_daily_reports`
    endi `shop_has_valid_key()` shartini qo'yadi — kalitsiz yoki kaliti
    yaroqsiz do'konga xabar ketmaydi.

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

1. **Sirlarni almashtirish** — bir nechtasi chatga tushgan:
   `CLICK_SECRET_KEY` (to'lov xavfi: soxta "to'lov o'tdi" yuborib bepul
   obuna olish mumkin), `BOT_TOKEN`, `POSTGRES_PASSWORD`, Google
   service account kaliti, `FERNET_KEY` (bu eng nozigi — do'kon
   kalitlari shu bilan shifrlangan, almashtirilsa qayta shifrlash kerak).

2. **SSH parolini yopish** — 10 000 dan ortiq urinish bo'lgan:
   ```bash
   ssh root@46.62.199.124 'printf "PasswordAuthentication no
PermitRootLogin prohibit-password
" > /etc/ssh/sshd_config.d/99-harden.conf && sshd -t && systemctl reload ssh'
   ```
   ⚠️ Avval yangi oynada kirib ko'ring, keyin eskisini yoping.

3. **Jonli to'lovni sinash** — Click yoqilgan, lekin haqiqiy pul bilan
   bir marta ham o'tkazilmagan. To'lov → obuna ochilishi zanjiri
   tasdiqlanmagan.

   ⚠️ Sinov to'lovi **haqiqiy** bo'ladi va fiskal chek soliqqa tushadi.
   Shuning uchun quyidagi band **shundan oldin** hal bo'lgani ma'qul.

3-bis. **Fiskalizatsiya (OFD) sozlamalarini to'ldirish** — kod yozilgan
   (`services/click_ofd.py`), lekin uchta qiymat bo'sh:
   `CLICK_MERCHANT_USER_ID`, `CLICK_OFD_SPIC` (IKPU),
   `CLICK_OFD_PACKAGE_CODE`. Ular kelmaguncha chek yaratilmaydi —
   `check_ready()` sababni aniq aytadi. Batafsil:
   «Fiskalizatsiya (OFD)» bo'limi.

4. **Qoldiq yozishni FBS do'konda sinash** — kod jonli, sxema
   spetsifikatsiyadan olingan, lekin hozirgi do'konlar FBO (FBS = 0).
   Kichik o'zgarishdan boshlang, Uzum kabinetida tekshiring.

5. **Audit formulasini tirik ma'lumotda tasdiqlash** — AZIKO sinov
   do'koni, sotuvi 2024-11 da to'xtagan. `SPEC 10` talab qiladi: 3 oylik
   ma'lumotni qo'lda hisoblab, bot natijasi bilan solishtirish. **Bu
   mahsulotning asosiy va'dasi** — tasdiqlanmaguncha sellerga
   "yo'qotishingizni topdim" deyish xavfli.

6. **Ofertaga rekvizit** qo'shish (hozir rekvizitsiz, lekin pul qabul
   qilinyapti).

7. **Zaxira nusxani serverdan tashqariga** chiqarish — hozir o'sha
   serverda yotadi, server yo'qolsa zaxira ham yo'qoladi.

8. **`MemoryStorage` → doimiy saqlash** — bot har restartda FSM holatini
   unutadi. Uch tuzatish buni foydalanuvchi uchun sezilmas qildi, lekin
   ildiz sabab qolgan (`app/bot/main.py` dagi TODO).

9. ~200 do'kondan keyin: sync'ni parallel qilish, audit yig'indilarini
   SQL tomoniga o'tkazish.

### Qilinmaydi (ongli qaror)

Yandex Market · AI sharh javoblari · Didox — mahsulot yo'nalishidan
chiqarilgan. **Aksiyalar** — Uzum API'da endpoint umuman yo'q
(spetsifikatsiya tekshirilgan), raqobatchi boshqa API ishlatadi.

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
