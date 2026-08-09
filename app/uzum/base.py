"""Uzum bilan aloqa uchun quyi qatlam — HTTP klient.

Bu qatlam:
  - GET so'rov yuboradi (o'qish — audit/hisobot shu orqali),
  - rate limit qo'yadi (do'konга soniyada 1 so'rov, SPEC 3.3),
  - GET vaqtinchalik xatolarda retry qiladi.

⚠️ YOZISH (`post`) — alohida, ehtiyot bilan. GET dan farqli o'laroq
**qayta urinilmaydi**: `POST /v2/fbs/sku/stocks` idempotentligi tasdiqlanmagan,
qayta yuborsak qoldiq ikki marta o'zgarishi mumkin. `post` faqat
`app/uzum/writes.py` orqali chaqiriladi; audit/sync yo'li uni ishlatmaydi
(CLAUDE.md qoida #1).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)

# Retry qilinadigan HTTP status kodlari
_RETRY_STATUS = {429, 500, 502, 503, 504}

# MUHIM (Phase 0 topilmasi): Uzum brauzerga o'xshamagan so'rovlarga 403 qaytaradi,
# auth to'g'ri bo'lsa ham. User-Agent majburiy.
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class RateLimiter:
    """Kalit bo'yicha (odatda shop_id) soniyaga N so'rov cheklovi.

    Bitta akkaunt yuzlab do'konга so'rov yuboradi — agressiv bo'lsak
    bloklanamiz (SPEC 3.3). Har do'kon uchun alohida navbat.
    """

    def __init__(self, per_sec: float) -> None:
        self._min_interval = 1.0 / per_sec if per_sec > 0 else 0.0
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def acquire(self, key: str) -> None:
        async with self._lock(key):
            now = time.monotonic()
            wait = self._min_interval - (now - self._last.get(key, 0.0))
            if wait > 0:
                await asyncio.sleep(wait)
            self._last[key] = time.monotonic()


class UzumHTTP:
    """Async HTTP klient — rate limit va retry bilan.

    O'qish: `get`, `get_bytes` — retry bilan.
    Yozish: `post` — retry YO'Q, faqat `writes.py` uchun (yuqoridagi izoh).
    """

    def __init__(
        self,
        base_url: str,
        rate_limit_per_sec: float = 1.0,
        timeout: float = 20.0,
        max_retries: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._limiter = RateLimiter(rate_limit_per_sec)
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": _DEFAULT_UA, "Accept": "application/json"},
        )

    async def _request(
        self,
        path: str,
        *,
        rate_key: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Bitta GET so'rov, retry bilan. `rate_key` — odatda shop_id."""
        url = path if path.startswith("http") else f"{self._base_url}/{path.lstrip('/')}"

        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            await self._limiter.acquire(rate_key)
            try:
                resp = await self._client.get(
                    url, params=params, headers=headers, cookies=cookies
                )
                if resp.status_code in _RETRY_STATUS:
                    raise httpx.HTTPStatusError(
                        f"status {resp.status_code}", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                return resp
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt >= self._max_retries:
                    break
                backoff = 2 ** (attempt - 1)  # 1s, 2s, 4s...
                log.warning(
                    "Uzum GET qayta urinish %s/%s (%s) — %ss kutamiz",
                    attempt,
                    self._max_retries,
                    type(exc).__name__,
                    backoff,
                )
                await asyncio.sleep(backoff)

        assert last_exc is not None
        raise last_exc

    async def get(
        self,
        path: str,
        *,
        rate_key: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> Any:
        """JSON qaytaradigan GET."""
        resp = await self._request(
            path, rate_key=rate_key, params=params, headers=headers, cookies=cookies
        )
        return resp.json()

    async def get_bytes(
        self,
        path: str,
        *,
        rate_key: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[bytes, str]:
        """Binary qaytaradigan GET — yorliq, akt va h.k. (PDF).

        `(mazmun, content_type)` qaytaradi. Bu ham GET, ya'ni qattiq
        qoida (SPEC 9.1) buzilmaydi: hujjat yaratilmaydi, tayyorini olamiz.
        """
        resp = await self._request(
            path,
            rate_key=rate_key,
            params=params,
            headers={**(headers or {}), "Accept": "*/*"},
        )
        return resp.content, resp.headers.get("content-type", "")

    async def post(
        self,
        path: str,
        *,
        rate_key: str,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """YOZISH so'rovi — JSON qaytaradi. ⚠️ Faqat `writes.py` uchun.

        GET dan farqi — **retry yo'q**. Yozishni qayta yuborish xavfli:
        so'rov serverga yetib, javob yo'lda uzilgan bo'lsa, ikkinchi urinish
        qoldiqni ikki marta o'zgartiradi. Shuning uchun bitta urinish; xato
        bo'lsa chaqiruvchiga ochiq qaytaramiz (jim yutmaymiz — qoida #4).

        Rate limit baribir qo'llanadi (do'kon bloklanmasin).
        """
        url = path if path.startswith("http") else f"{self._base_url}/{path.lstrip('/')}"
        await self._limiter.acquire(rate_key)
        resp = await self._client.post(
            url, json=json, headers={**(headers or {}), "Accept": "application/json"}
        )
        resp.raise_for_status()
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            # Uzum ba'zan bo'sh yoki matnli javob qaytaradi — bu ham natija
            return resp.text

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> UzumHTTP:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
