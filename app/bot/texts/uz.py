"""O'zbekcha matnlar."""

TEXTS: dict[str, str] = {
    # --- Til ---
    "choose_lang": "Tilni tanlang / Выберите язык",
    "lang_uz": "🇺🇿 O'zbek",
    "lang_ru": "🇷🇺 Русский",
    # --- Xush kelibsiz ---
    # Qisqa bo'lishi shart: bu birinchi ekran, uzun matn o'qilmaydi.
    # Narx bu yerda YO'Q — u keyingi ekranda va tugmalarda, takrorlanmasin.
    "welcome": (
        "👋 <b>Uzum sizga to'lamagan pulni topaman.</b>\n\n"
        "Har kuni do'koningizni tekshiraman:\n"
        "📦 omborda yo'qolgan tovar\n"
        "↩️ qaytib kelmagan qaytarish\n"
        "💸 ortiqcha ushlangan komissiya\n\n"
        "Topilganiga <b>Excel dalil</b> va <b>tayyor pretenziya</b> beraman — "
        "Uzumga yuborasiz, pulingizni qaytarasiz."
    ),
    "btn_start": "🚀 Boshlash",
    # --- Oferta ---
    # Bandlar bir qatorli: uzun matnni hech kim o'qimaydi, lekin har
    # bir band muhim va tushib qolmasligi kerak.
    "oferta": (
        "📄 <b>Foydalanish shartlari</b>\n\n"
        "<blockquote>🔒 Do'konga <b>faqat o'qish</b> uchun ulanamiz — hech "
        "narsani o'zgartirmaymiz\n\n"
        "🔑 API kalitingiz <b>shifrlangan</b>, istalgan payt bekor qila "
        "olasiz\n\n"
        "📊 Hisobot — <b>tahliliy taxmin</b>, yuridik dalil emas. Da'vodan "
        "oldin tekshiring\n\n"
        "⚖️ Biz Uzum Market bilan bog'liq emasmiz — mustaqil "
        "xizmatmiz</blockquote>\n\n"
        "Davom etsangiz, shartlarni qabul qilgan hisoblanasiz."
    ),
    "btn_oferta_full": "📄 Oferta",
    "oferta_file_caption": (
        "📄 To'liq ommaviy oferta.\n\nFaylni ochib, oxirigacha o'qing."
    ),
    "btn_accept": "✅ Qabul qilaman",
    # --- Telefon ---
    "ask_phone": (
        "📱 Telefon raqamingizni ulashing.\n\n"
        "Bu siz bilan bog'lanish va akkauntingizni aniqlash uchun kerak."
    ),
    "btn_share_phone": "📱 Raqamni ulashish",
    "phone_saved": "✅ Raqam qabul qilindi: {phone}",
    "phone_invalid": "❌ Iltimos, pastdagi tugma orqali raqamingizni ulashing.",
    # --- Do'kon ulash: yo'riqnoma ---
    "connect_intro": (
        "🔗 <b>Endi do'koningizni ulaymiz</b>\n\n"
        "Buning uchun Uzum kabinetidan <b>API kalit</b> olasiz. "
        "Parolingizni bermaysiz, va biz do'koningizni <b>faqat o'qiymiz</b> — "
        "hech narsani o'zgartira olmaymiz."
    ),
    "btn_how_to": "📖 Qanday qilish kerak?",
    # Xavfsizlik izohi yig'iladigan blokda: u muhim, lekin har safar
    # ko'rinib turishi shart emas — qadamlar ustidan diqqatni oladi.
    "instruction": (
        "📖 <b>API kalitni qanday olish</b>\n\n"
        "1️⃣ Kompyuterda <code>seller.uzum.uz</code> ga kiring\n"
        "2️⃣ <b>Mening profilim</b> → <b>API kalitlar</b>\n"
        "3️⃣ Yangi kalit yarating\n"
        "4️⃣ Kalitni nusxalab, shu yerga yuboring\n\n"
        "<blockquote expandable>🔒 <b>Xavfsizlik</b>\n"
        "Kalit shifrlangan holda saqlanadi, xabaringiz darhol o'chiriladi. "
        "Do'koningizni faqat o'qiymiz — tovar, narx yoki qoldiqni "
        "o'zgartira olmaymiz. Kalitni istalgan payt kabinetdan bekor "
        "qilishingiz mumkin.</blockquote>"
    ),
    "ask_api_key": (
        "🔑 <b>API kalitni yuboring</b>\n\n"
        "Kalitni yuborganingizdan keyin do'konlaringizni <b>o'zim topaman</b> — "
        "do'kon ID qidirishingiz shart emas."
    ),
    "key_invalid_format": (
        "❌ Bu API kalitga o'xshamaydi.\n\n"
        "Kabinetdan nusxalangan kalitni to'liq yuboring."
    ),
    "key_checking": "⏳ Kalitni tekshiryapman...",
    "delete_failed": (
        "⚠️ Xabaringizni o'chira olmadim. <b>Iltimos, o'zingiz o'chiring</b> — "
        "kalit chatda qolmasin."
    ),
    "key_rejected": (
        "❌ <b>Kalit ishlamadi.</b>\n\n"
        "Sabablari:\n"
        "• Kalit noto'g'ri nusxalangan\n"
        "• Kalit kabinetda bekor qilingan\n\n"
        "Kabinetdan yangi kalit yaratib, qayta yuboring."
    ),
    "key_no_shops": (
        "⚠️ Kalit ishladi, lekin <b>do'kon topilmadi</b>.\n\n"
        "Kabinetda do'kon yaratilganini tekshiring."
    ),
    # Sinov haqidagi gap OLIB TASHLANDI: tarif endi oldinroq tanlanadi
    # va pullik tanlagan sellerga "sinov boshlandi" deyish noto'g'ri.
    "shop_connected": (
        "✅ <b>Ulandi:</b> {shops}\n\n"
        "🗑 Kalit shifrlab saqlandi, xabaringiz o'chirildi.\n\n"
        "⏳ Ma'lumot yig'ilyapti — bir necha daqiqa. Tugaganda xabar beraman."
    ),
    "first_sync_found": (
        "🔍 <b>Tahlil tugadi.</b>\n\n"
        "Diqqat talab qiladigan <b>{count} ta</b> holat topildi.\n\n"
        "«💰 Yo'qotilgan pul» bo'limini oching — batafsil ko'rasiz."
    ),
    "first_sync_clean": (
        "✅ <b>Tahlil tugadi.</b>\n\n"
        "Yig'ildi: {products} ta mahsulot, {orders} ta buyurtma.\n"
        "Hozircha nomuvofiqlik topilmadi.\n\n"
        "Har kuni tekshirib boraman — nimadir chiqsa darhol xabar beraman."
    ),
    "first_sync_failed": (
        "⚠️ Ma'lumot yig'ishda muammo bo'ldi.\n\n"
        "Keyingi avtomatik urinish bir soatdan so'ng. Muammo takrorlansa — "
        "kalitni kabinetdan qayta yarating."
    ),
    # --- Asosiy menyu ---
    "main_menu": "🏠 <b>Asosiy menyu</b>\n\nNima qilamiz?",
    "main_menu_admin": (
        "🏠 <b>Asosiy menyu</b>\n\n"
        "👑 Siz <b>administrator</b>siz — pastda «Admin» tugmasi bor.\n\n"
        "Nima qilamiz?"
    ),
    "menu_admin": "👑 Admin",
    "menu_lost_money": "💰 Yo'qotilgan pul",
    "menu_reports": "📊 Hisobotlar",
    "menu_fbs": "🏷 FBS buyurtmalar",
    "menu_stock": "📦 Qoldiqlar",
    "menu_unit_econ": "🧮 Yunit-iqtisodiyot",
    "menu_alerts": "🔔 Bildirishnomalar",
    "menu_settings": "⚙️ Sozlamalar",
    # --- Davr tanlash ---
    "choose_period": "📅 <b>Qaysi davr uchun tekshiramiz?</b>",
    "period_today": "Bugun",
    "period_yesterday": "Kecha",
    "period_week": "7 kun",
    "period_month": "Shu oy",
    "period_prev_month": "O'tgan oy",
    "period_all": "📊 Butun tarix",
    "period_custom": "📅 Kalendar",
    "btn_change_period": "📅 Davrni o'zgartirish",
    "pick_start_date": "📅 <b>Boshlanish sanasini tanlang</b>",
    "pick_end_date": "📅 <b>Tugash sanasini tanlang</b>\n\nBoshlanish: {start}",
    "period_label": "📅 <b>{start} — {end}</b>",
    "analyzing": "🔍 Tahlil qilyapman...",
    "history_available": (
        "ℹ️ Qoldiq tarixi: <b>{start}</b> dan <b>{end}</b> gacha ({days} kun)."
    ),
    "history_empty": (
        "ℹ️ Qoldiq tarixi hali yig'ilmagan. Uzum faqat hozirgi holatni beradi — "
        "tarixni biz kundan kunga saqlaymiz. Har kuni ma'lumot to'planadi."
    ),
    "period_before_history": (
        "ℹ️ Siz tanlagan davr tarix boshlanishidan oldin. Bizdagi ma'lumot "
        "<b>{start}</b> dan boshlanadi — undan oldingi davrni hisoblab bo'lmaydi."
    ),
    # --- Yo'qotilgan pul ---
    "losses_header": "💰 <b>{shop} — topilgan yo'qotishlar</b>",
    "losses_header_short": "💰 <b>Topilgan yo'qotishlar</b>",
    "losses_total": "Jami: <b>{total} so'm</b>",
    "btn_excel": "📄 Excel yuklab olish",
    "btn_claim": "📝 Pretenziya",
    "excel_caption": (
        "📄 Dalil hisoboti. Shtrix kodsiz qatorlar sariq bilan belgilangan — "
        "ular bo'yicha da'vo qilish qiyin."
    ),
    "claim_caption": (
        "📝 Pretenziya loyihasi.\n\n"
        "⚠️ Yuborishdan oldin chiziqchali joylarni to'ldiring:\n"
        "• F.I.Sh. va tadbirkorlik shakli\n"
        "• PINFL\n"
        "• Hisob raqam va MFO\n\n"
        "Bularsiz Uzum pul o'tkaza olmaydi."
    ),
    "agreement_caption": (
        "📑 Qo'shimcha kelishuv (2 nusxada).\n\n"
        "⚠️ Pretenziyaning o'zi yetarli emas — Uzum to'lovni shu kelishuv "
        "imzolangandan keyin qiladi. Ikkala hujjatni birga yuboring.\n\n"
        "Shartnoma raqami va sanasini kabinetdan ko'chiring "
        "(Oferta bo'limida)."
    ),
    "claim_seller_placeholder": "____________________ (rekvizitlaringizni yozing)",
    "no_shop": (
        "🔗 Avval do'koningizni ulang.\n\n"
        "/start buyrug'i bilan boshlang."
    ),
    "no_losses_yet": (
        "✅ Hozircha yo'qotish topilmadi.\n\n"
        "Ma'lumot yig'ilishi va tahlil qilinishi bir necha kun oladi — "
        "qoldiq tarixi to'planishi kerak. Topilishi bilan xabar beraman."
    ),
    "audit_data_missing": (
        "⚠️ <b>Tekshiruv to'liq o'tkazilmadi.</b>\n\n"
        "Uzum quyidagi ma'lumotni bermadi: <b>{sources}</b>.\n"
        "Shu sababli ishlamagan auditlar: {audits}.\n\n"
        "Bu «yo'qotish yo'q» degani <b>emas</b> — shunchaki tekshirib "
        "bo'lmadi. Ko'pincha sabab: API kalitida moliya bo'limiga ruxsat "
        "yo'q. Uzum kabinetida xodim huquqlarini tekshiring."
    ),
    # --- Yunit-iqtisodiyot ---
    "econ_header": "🧮 <b>Yunit-iqtisodiyot</b> · {start} — {end}",
    "econ_revenue": "Tushum: <b>{value}</b> so'm",
    "econ_commission": "Komissiya: −{value} so'm",
    "econ_logistics": "Logistika: −{value} so'm",
    "econ_storage": "Saqlash: −{value} so'm  ⚠️",
    "econ_profit": "💰 <b>Sof foyda: {value} so'm</b> (marja {margin}%)",
    "econ_abc": "📊 ABC: A — {a} ta · B — {b} ta · C — {c} ta",
    "econ_losers": "📉 <b>Zarar keltiryapti: {count} ta</b>",
    "econ_dead": "🧊 <b>Sotilmayapti, omborda turibdi: {count} ta</b>",
    "econ_dead_cost": "   Ular uchun saqlash puli: {value} so'm",
    "econ_empty": (
        "🧮 Hisoblash uchun ma'lumot yetarli emas.\n\n"
        "Sotuv bo'lgach yoki birinchi sinxronizatsiyadan keyin paydo bo'ladi."
    ),
    "econ_caption": (
        "🧮 Yunit-iqtisodiyot. Qizil — zarar keltiruvchi, "
        "sariq — sotilmayotgan tovarlar."
    ),
    "btn_returns": "↩️ Qaytarish tahlili",
    # --- Qaytarish tahlili ---
    "returns_header": "↩️ <b>Qaytarish tahlili</b>",
    "returns_overall": "Jami: {returned} ta qaytgan / {sold} ta sotilgan — <b>{pct}%</b>",
    "returns_reasons": "<b>Eng ko'p sabablar:</b>",
    "returns_problem": "<b>Muammoli tovarlar:</b>",
    "returns_ok": "✅ Qaytarish darajasi normal — muammoli tovar yo'q.",
    "returns_empty": (
        "↩️ Qaytarish tahlili uchun sotuv ma'lumoti yo'q.\n\n"
        "Sotuvlar bo'lgach hisoblanadi."
    ),
    # --- Qoldiqlar ---
    "stock_header": "📦 <b>Qoldiqlar — {total} ta SKU</b>",
    "stock_totals": "FBO omborda: <b>{fbo}</b> dona · FBS: <b>{fbs}</b> dona",
    "stock_blocked": "🚫 <b>Bloklangan: {count} ta</b> — sotuv to'xtagan!",
    "stock_out": "⛔ <b>Tugagan: {count} ta</b>",
    "stock_low": "⏳ <b>Tugayapti: {count} ta</b>",
    "stock_all_ok": "✅ Diqqat talab qiladigan tovar yo'q.",
    "stock_empty": (
        "📦 Qoldiq ma'lumoti hali yig'ilmagan.\n\n"
        "Birinchi sinxronizatsiyadan keyin paydo bo'ladi."
    ),
    "stock_caption": "📦 Qoldiqlar hisoboti. Diqqat talab qiladiganlar sariq bilan.",
    "btn_excel_short": "📊 Excel",
    "btn_pdf_short": "📄 PDF",
    # --- FBS buyurtmalar ---
    "fbs_loading": "⏳ Buyurtmalarni olyapman...",
    "fbs_header": "🏷 <b>Yig'ilishi kerak: {count} ta buyurtma</b>",
    "fbs_empty": (
        "✅ Yig'ilishi kerak bo'lgan buyurtma yo'q.\n\n"
        "Yangi buyurtma kelganda xabar beraman."
    ),
    "fbs_more": "...va yana {rest} ta buyurtma",
    "btn_label_for": "🏷 №{order} yorlig'i",
    "fbs_preparing": "Yorliq tayyorlanyapti...",
    "fbs_label_caption": "🏷 №{order} buyurtma yorlig'i — chop etishga tayyor",
    "fbs_label_failed": (
        "❌ №{order} yorlig'ini olib bo'lmadi.\n\n"
        "Buyurtma holati o'zgargan bo'lishi mumkin. Birozdan so'ng urinib ko'ring."
    ),
    # --- Tariflar va to'lov ---
    "plan_trial": "Sinov",
    "plan_basic": "Basic",
    "plan_pro": "Pro",
    "plans": (
        "💎 <b>Tariflar</b>\n\n"
        "<b>Basic — {basic} so'm/oy</b>\n"
        "💰 Yo'qotilgan pul (6 xil audit)\n"
        "📦 Qoldiqlar va tugash prognozi\n"
        "📊 Kunlik/haftalik/oylik hisobot\n"
        "🔔 Blok va qoldiq xabarnomalari\n"
        "📄 Excel, PDF, pretenziya\n\n"
        "<b>Pro — {pro} so'm/oy</b>\n"
        "✅ Basic'dagi hammasi, plus:\n"
        "🧮 Yunit-iqtisodiyot va ABC tahlil\n"
        "🏷 FBS yorliqlar (bir tugma bilan)\n"
        "↩️ Qaytarish sabablari tahlili\n"
        "💸 Saqlash xarajati nazorati\n\n"
        "🎁 <b>{trial} kun bepul</b> — Pro darajasida, cheklovsiz."
    ),
    "plan_current": "Hozirgi tarif: <b>{plan}</b> · {days} kun qoldi",
    # --- Onboarding: tarif tanlash (do'kon ulangandan keyin) ---
    "choose_plan": (
        # Har tarif alohida <blockquote> — Telegram ularni chap tomonda
        # rangli chiziq va och fon bilan chizadi, ya'ni uch dona
        # KARTOCHKA ko'rinadi. Tekis matnda ular bir-biriga qo'shilib
        # ketardi va tanlash qiyin edi.
        #
        # Narx bu yerda takrorlanmaydi — u tugmalarda. Matn faqat
        # tariflar ORASIDAGI FARQNI aytadi.
        "💎 <b>Tarifni tanlang</b>\n\n"
        "<blockquote>🎁 <b>Bepul</b> · {trial_days} kun\n"
        "Karta so'ralmaydi</blockquote>\n"
        "<blockquote>📦 <b>Basic</b>\n"
        "Yo'qotishlarni topish · Excel dalil · pretenziya</blockquote>\n"
        "<blockquote>🚀 <b>Pro</b>\n"
        "Basic'dagi hammasi + yunit-iqtisodiyot · FBS yorliqlar · "
        "ogohlantirishlar</blockquote>"
    ),
    "btn_plan_free": "🎁 Bepul · {trial_days} kun",
    "btn_plan_basic": "📦 Basic · {price} so'm/oy",
    "btn_plan_pro": "🚀 Pro · {price} so'm/oy",
    "plan_free_started": (
        "🎁 <b>Bepul muddat boshlandi — {trial_days} kun.</b>\n\n"
        "Basic imkoniyatlari ochiq. Istalgan payt /tarif orqali "
        "Pro'ga o'tishingiz mumkin."
    ),
    "plan_paid_later": (
        "✅ <b>{plan}</b> tarifi tanlandi.\n\n"
        "To'lov do'koningiz ulangandan keyin so'raladi — avval "
        "botning sizning do'koningizda qanday ishlashini ko'rasiz."
    ),
    "plan_must_choose": (
        "💎 Avval tarifni tanlang — yuqoridagi tugmalardan birini bosing."
    ),
    "btn_tariffs": "💎 Tariflar",
    "btn_buy_basic": "Basic tarifni olish",
    "btn_buy_pro": "Pro tarifni olish",
    "btn_i_paid": "✅ To'ladim",
    "btn_pay_click": "💳 Click orqali to'lash",
    "click_payment": (
        "💳 <b>{plan} — {amount} so'm</b>\n\n"
        "Quyidagi tugmani bosing va to'lovni amalga oshiring.\n"
        "Karta ma'lumotlari <b>Click sahifasida</b> kiritiladi — bizga tegmaydi.\n\n"
        "To'lov o'tishi bilan obunangiz <b>avtomatik</b> faollashadi."
    ),
    "invoice_desc": "{plan} tarifi — 1 oy",
    "manual_payment": (
        "💳 <b>{plan} — {amount} so'm</b>\n\n"
        "{details}\n\n"
        "To'lagach <b>«To'ladim»</b> tugmasini bosing. "
        "Tekshirib, obunangizni faollashtiramiz."
    ),
    "payment_not_ready": (
        "⏳ <b>Onlayn to'lov hozircha ulanmagan.</b>\n\n"
        "Tarifni faollashtirish uchun {support} ga yozing — qo'lda "
        "ulab beramiz.\n\n"
        "Shu vaqtgacha bepul muddat bilan ishlashda davom eting: "
        "yo'qotishlarni topish, Excel dalil va pretenziya ochiq."
    ),
    "payment_details_missing": (
        "⚠️ To'lov rekvizitlari sozlanmagan. Yordam xizmatiga murojaat qiling."
    ),
    "payment_pending": (
        "⏳ <b>To'lovingiz tekshirilmoqda.</b>\n\n"
        "Odatda bu 15-30 daqiqa oladi. Tasdiqlangach xabar beramiz."
    ),
    "payment_success": (
        "✅ <b>To'lov qabul qilindi!</b>\n\n"
        "Tarif: <b>{plan}</b> · {days} kun.\n"
        "Rahmat — ishni davom ettiramiz."
    ),
    "sub_expired": (
        "⏳ <b>Sinov muddati tugadi.</b>\n\n"
        "Do'koningiz ma'lumotlari saqlanib turibdi — tarifni tanlasangiz, "
        "hammasi joyida davom etadi."
    ),
    "sub_upgrade": (
        "💎 <b>Bu bo'lim Pro tarifida.</b>\n\n"
        "Yunit-iqtisodiyot, FBS yorliqlar va qaytarish tahlili Pro'ga kiradi."
    ),
    # --- Umumiy ---
    "btn_back": "⬅️ Orqaga",
    "not_ready": (
        "🚧 Bu bo'lim hali tayyorlanmoqda.\n\n"
        "Ma'lumotlaringiz yig'ilgach ishga tushadi."
    ),
    "error": "😔 Xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.",
}
