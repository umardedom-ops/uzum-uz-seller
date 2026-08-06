"""Credential shifrlash — Fernet (SPEC 9.2).

Barcha token/cookie bazaga SHIFRLANGAN holda yoziladi. Ochiq matn hech
qachon logga yoki bazaga tushmasin.
"""
from __future__ import annotations

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _cipher() -> Fernet:
    return Fernet(get_settings().fernet_key.encode())


def encrypt(plaintext: str) -> str:
    """Ochiq matnni shifrlab, bazaga yoziladigan satr qaytaradi."""
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Bazadagi shifrlangan satrni ochib beradi."""
    return _cipher().decrypt(token.encode()).decode()


def generate_key() -> str:
    """Yangi Fernet kalit generatsiya qiladi (bir marta, .env uchun)."""
    return Fernet.generate_key().decode()
