"""Web-kabinet uchun token va sessiya.

⚠️ Raqobatchining xatosini takrorlamaymiz. Ularda:
  * `token` har bir havolada **ochiq** yuriydi (brauzer tarixi, loglar,
    referer — hammasiga tushadi),
  * login = Telegram ID, ya'ni oson taxmin qilinadi.

Bizda:
  * **Kirish tokeni bir martalik** va 15 daqiqada o'chadi. U faqat
    cookie'ga almashish uchun ishlatiladi, sahifalarda ko'rinmaydi.
  * **Sessiya cookie'da** — httponly, secure, samesite. URL'da hech
    qachon token bo'lmaydi.
  * Token bazaga **xesh** holida yoziladi: baza o'g'irlansa ham
    sessiyani tiklab bo'lmaydi (parol xeshlash bilan bir mantiq).
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Enum, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UtcDateTime


class TokenKind(str, enum.Enum):
    LOGIN = "login"      # bir martalik kirish havolasi (botdan)
    SESSION = "session"  # brauzer cookie'si


class WebToken(Base, TimestampMixin):
    __tablename__ = "web_tokens"
    __table_args__ = (Index("ix_web_tokens_expires", "expires_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Kim uchun. `users` ga FK qo'yilmagan: token do'kon emas, odamga
    #: tegishli va foydalanuvchi o'chirilsa token baribir amal qilmaydi
    #: (tekshiruvda user qidiriladi).
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    #: SHA-256 xesh. Ochiq token faqat foydalanuvchida bo'ladi.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[TokenKind] = mapped_column(
        Enum(TokenKind, native_enum=False, length=16)
    )
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    #: Bir martalik token ishlatilgan payt. To'lgan bo'lsa — qayta
    #: ishlatib bo'lmaydi (havola nusxalansa ham foydasi yo'q).
    used_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    def __repr__(self) -> str:  # xesh ham logga chiqmasin
        return f"<WebToken tg={self.telegram_id} kind={self.kind.value}>"
