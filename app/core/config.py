"""Ilova sozlamalari — .env dan o'qiladi (pydantic-settings)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Telegram ---
    bot_token: str = Field(..., alias="BOT_TOKEN")
    # Satr sifatida o'qiladi: pydantic-settings ro'yxat maydonini JSON deb
    # tahlil qilishga urinadi va bo'sh qiymatda yiqiladi.
    # Asosiy admin manbai — baza; bu zaxira ro'yxat (`admin_ids` xossasi).
    admin_ids_raw: str = Field("", alias="ADMIN_IDS")

    # --- Baza ---
    database_url: str = Field(
        "sqlite+aiosqlite:///./uzumbot.db", alias="DATABASE_URL"
    )

    # --- Shifrlash ---
    fernet_key: str = Field(..., alias="FERNET_KEY")

    # --- Uzum ---
    uzum_api_base: str = Field(
        "https://api-seller.uzum.uz/api/seller-openapi", alias="UZUM_API_BASE"
    )
    # ⚠️ Bu yerda umumiy Uzum kaliti YO'Q va bo'lmasligi kerak. Har bir
    # do'kon kaliti `shop_credentials` jadvalida shifrlangan holda
    # saqlanadi va `sync._api_secret()` orqali olinadi. Global kalit
    # xavfli edi: 2026-08-07 da `.env` da butunlay boshqa do'konning
    # (Elore Parfume, 125841) kaliti turgani aniqlandi — u hech qayerda
    # ishlatilmasa ham, tekshiruv paytida chalg'itdi.
    uzum_rate_limit_per_sec: float = Field(1.0, alias="UZUM_RATE_LIMIT_PER_SEC")
    # Birinchi ulanishda qancha tarix tortiladi. Buyurtma/qaytarish/moliya
    # uchun API tarix beradi — qoldiq uchun bermaydi (docs/api-inventory.md).
    initial_history_days: int = Field(365, alias="INITIAL_HISTORY_DAYS")

    # --- Onboarding (SPEC 7) ---
    # Seller kabinetida "Xodim" sifatida qo'shadigan BIZNING raqamimiz.
    # Videodagi raqobatchi: +998 33 510 43 53. O'zimiznikini .env dan olamiz.
    employee_phone: str = Field("+998 XX XXX XX XX", alias="EMPLOYEE_PHONE")
    employee_name: str = Field("Seller yordamchisi", alias="EMPLOYEE_NAME")
    # So'raladigan rol — SPEC 3.1 ga qarang (Финансовый менеджер, Менеджер emas)
    employee_role: str = Field("Финансовый менеджер", alias="EMPLOYEE_ROLE")

    oferta_url: str = Field("https://example.com/oferta", alias="OFERTA_URL")
    support_username: str = Field("@support", alias="SUPPORT_USERNAME")

    # --- Tariflar (SPEC Phase 6) ---
    trial_days: int = Field(3, alias="TRIAL_DAYS")
    price_basic: int = Field(149_000, alias="PRICE_BASIC")
    price_pro: int = Field(299_000, alias="PRICE_PRO")

    # Telegram Payments provayder tokeni (@BotFather → Payments).
    payment_provider_token: str | None = Field(None, alias="PAYMENT_PROVIDER_TOKEN")
    payment_currency: str = Field("UZS", alias="PAYMENT_CURRENCY")
    # Qo'lda to'lov uchun rekvizit (karta raqami emas — matn ko'rsatma)
    payment_details: str = Field("", alias="PAYMENT_DETAILS")

    # --- Click (Shop API) ---
    # Maxfiy: faqat `.env` da. Kodga yozilmaydi, logga chiqmaydi.
    click_service_id: str = Field("", alias="CLICK_SERVICE_ID")
    click_merchant_id: str = Field("", alias="CLICK_MERCHANT_ID")
    click_secret_key: str = Field("", alias="CLICK_SECRET_KEY")
    # Webhook serveri manzili (Click shu yerga murojaat qiladi)
    click_base_url: str = Field("", alias="CLICK_BASE_URL")

    @property
    def click_enabled(self) -> bool:
        return bool(
            self.click_service_id and self.click_merchant_id and self.click_secret_key
        )

    @property
    def payments_enabled(self) -> bool:
        """Avtomatik to'lov yoqilganmi (Click yoki Telegram Payments)."""
        return self.click_enabled or bool(self.payment_provider_token)

    # --- Umumiy ---
    env: str = Field("dev", alias="ENV")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    tz: str = Field("Asia/Tashkent", alias="TZ")

    @property
    def admin_ids(self) -> list[int]:
        """Zaxira admin ro'yxati `.env` dan.

        Bo'sh bo'lishi normal — adminlar bazadan aniqlanadi (birinchi
        foydalanuvchi avtomatik admin bo'ladi). Noto'g'ri yozilgan qiymat
        botni yiqitmasin, shuning uchun raqam bo'lmaganlari tashlanadi.
        """
        ids: list[int] = []
        for part in self.admin_ids_raw.replace(" ", "").split(","):
            if part.isdigit():
                ids.append(int(part))
        return ids

    @property
    def is_prod(self) -> bool:
        return self.env.lower() == "prod"


@lru_cache
def get_settings() -> Settings:
    """Sozlamalarni bir marta o'qib, keshlab qaytaradi."""
    return Settings()  # type: ignore[call-arg]
