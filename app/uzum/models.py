"""Uzum klient uchun kirish/chiqish tiplari.

Endpoint JSON strukturasi hali noma'lum (Phase 0 tugamagan), shuning uchun
javoblar hozircha xom `RawRecord` (dict) sifatida qaytadi. Inventarizatsiya
tugagach, bu yerga aniq DTO (dataclass/pydantic) modellar qo'shiladi.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any

# Xom yozuv — bitta Uzum obyektining JSON ko'rinishi.
RawRecord = dict[str, Any]


class AuthType(str, Enum):
    """SPEC 3.1 — ikki ulanish usuli."""

    API = "api"          # rasmiy Seller API tokeni
    CABINET = "cabinet"  # "Xodim" mexanizmi orqali kabinet sessiyasi


@dataclass(frozen=True, slots=True)
class SessionCredentials:
    """Bitta do'kon uchun autentifikatsiya ma'lumoti.

    `secret` — DB dan Fernet bilan OCHIB olingan token yoki cookie satri.
    Bu obyekt hech qachon logga yozilmasin (SPEC 9.2).
    """

    auth_type: AuthType
    secret: str


@dataclass(frozen=True, slots=True)
class DateRange:
    """[date_from, date_to] — buyurtma/qaytarish/moliya so'rovlari uchun."""

    date_from: date
    date_to: date


@dataclass(frozen=True, slots=True)
class PageParams:
    """Sahifalash. Uzumning aniq mexanizmi (offset yoki cursor) Phase 0 da
    aniqlanadi; hozircha ikkalasini ham qamrab olamiz."""

    limit: int = 100
    offset: int = 0
    cursor: str | None = None
