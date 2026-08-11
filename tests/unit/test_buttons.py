"""Har bir tugmaning handleri bormi — o'lik tugma qolmasin.

2026-08-11 da topilgan: «🚀 Boshlash» tugmasi `start:go` callback bilan
chizilardi, lekin unga handler yo'q edi — bosilsa bot **jim qolardi**.
Klaviaturaning o'zi ham ishlatilmasdi.

Shu test butun kod bo'ylab yuradi: klaviaturalarda va handlerlarda
uchraydigan har bir `callback_data` uchun mos handler borligini
tekshiradi. Yangi tugma qo'shilib, handleri unutilsa — test yiqiladi.
"""
from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app" / "bot"

#: `callback_data="..."` va `callback_data=f"...{x}"`
_CB = re.compile(r'callback_data=f?"([^"]+)"')
#: Handler filtrlari
_EQ = re.compile(r'F\.data\s*==\s*"([^"]+)"')
_STARTS = re.compile(r'F\.data\.startswith\(\s*\(?([^)]+?)\)?\s*\)')
_IN = re.compile(r'F\.data\.in_\(\s*\{([^}]+)\}')
_QUOTED = re.compile(r'"([^"]+)"')


def _sources(folder: str) -> list[str]:
    return [
        path.read_text(encoding="utf-8")
        for path in (APP / folder).glob("*.py")
        if path.name != "__init__.py"
    ]


def _used_callbacks() -> set[str]:
    """Kodda chiziladigan barcha callback_data (shablon qismisiz)."""
    found: set[str] = set()
    for text in _sources("keyboards") + _sources("handlers"):
        for raw in _CB.findall(text):
            # `f"fbs:label:{id}"` → `fbs:label:` (prefiks qismi)
            found.add(raw.split("{", 1)[0])
    return found


def _handled() -> tuple[set[str], set[str]]:
    """`(aniq_tenglik, prefikslar)` — handlerlar nimani ushlaydi."""
    exact: set[str] = set()
    prefixes: set[str] = set()

    for text in _sources("handlers"):
        exact.update(_EQ.findall(text))
        for group in _STARTS.findall(text):
            prefixes.update(_QUOTED.findall(group))
        for group in _IN.findall(text):
            exact.update(_QUOTED.findall(group))

    return exact, prefixes


def _is_handled(cb: str, exact: set[str], prefixes: set[str]) -> bool:
    if cb in exact:
        return True
    if any(cb.startswith(p) for p in prefixes):
        return True
    # Shablonli tugma (`fbs:label:`) — prefiksning o'zi handler bo'lishi
    # mumkin, yoki handler undan uzunroq prefiks bilan yozilgan.
    return any(p.startswith(cb) for p in prefixes)


class TestNoDeadButtons:
    def test_every_callback_has_handler(self) -> None:
        exact, prefixes = _handled()
        orphans = sorted(
            cb for cb in _used_callbacks() if not _is_handled(cb, exact, prefixes)
        )
        assert not orphans, (
            "Handleri yo'q tugmalar (bosilsa bot jim qoladi): "
            f"{orphans}"
        )

    def test_found_something(self) -> None:
        """Test o'zi ishlayotganini tasdiqlaymiz (regex buzilib qolmasin)."""
        assert len(_used_callbacks()) > 20
        exact, prefixes = _handled()
        assert len(exact) > 10 and len(prefixes) > 10


class TestMenuTextsHandled:
    """Reply-klaviaturadagi matn tugmalari ham handlersiz qolmasin."""

    def test_every_menu_button_has_handler(self) -> None:
        from app.bot.keyboards.menu import (
            folder_analytics_kb,
            folder_settings_kb,
            folder_warehouse_kb,
            main_menu_kb,
        )
        from app.bot.texts import LANGS, t

        buttons: set[str] = set()
        for lang in LANGS:
            for kb in (
                main_menu_kb(lang),
                folder_analytics_kb(lang),
                folder_warehouse_kb(lang),
                folder_settings_kb(lang),
            ):
                buttons.update(b.text for row in kb.keyboard for b in row)

        handler_text = "\n".join(_sources("handlers"))
        keys = re.findall(r't\("((?:menu|folder)_[a-z_]+)"', handler_text)
        handled = {t(key, lang) for key in set(keys) for lang in LANGS}

        missing = sorted(buttons - handled)
        assert not missing, f"Handleri yo'q menyu tugmalari: {missing}"
