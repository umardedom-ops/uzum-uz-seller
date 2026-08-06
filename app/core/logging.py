"""Markazlashtirilgan logging sozlash.

Qattiq qoida (SPEC 9.2): credential yoki token hech qachon logga tushmaydi.
Shuning uchun log yozganda maxfiy qiymatlarni hech qachon uzatmang.
"""
from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:  # takroriy sozlashning oldini olish
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Shovqinli kutubxonalarni jimlashtirish
    for noisy in ("httpx", "httpcore", "aiosqlite"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
