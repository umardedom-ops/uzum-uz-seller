"""Handler'larni haqiqiy chaqirib sinash.

Sabab: 2026-08-06 da bot yiqildi — `start.py` da olib tashlangan sozlama
(`price_monthly`) ishlatilib qolgan edi. Barcha testlar o'tgan, chunki
handler'lar hech qachon chaqirilmagan.

Bu fayl asosiy oqim handler'larini soxta Telegram obyektlari bilan
chaqiradi. Sozlama nomi o'zgarsa yoki matn kaliti yo'qolsa — test yiqiladi.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import start
from app.bot.states.onboarding import Onboarding


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=1, user_id=1),
    )


def make_callback(data: str) -> MagicMock:
    """Soxta CallbackQuery — javob yuborish metodlari yozib olinadi."""
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = 555
    cb.from_user.full_name = "Test Seller"
    cb.from_user.username = "testseller"
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    # Tarif ekrani banner bilan chiqadi — bu ham kutilishi kerak
    cb.message.answer_photo = AsyncMock()
    return cb


def sent_text(mock: AsyncMock) -> str:
    """Chaqiruvdan yuborilgan matnni oladi."""
    args, kwargs = mock.call_args
    return kwargs.get("text") or (args[0] if args else "")


def plans_screen(cb: MagicMock) -> tuple[str, object]:
    """Tarif ekranining matni va klaviaturasi.

    Banner bo'lsa `answer_photo` (matn — `caption`), bo'lmasa `answer`.
    Test ikkalasida ham ishlashi kerak: rasm loyihada bo'lishi ham,
    bo'lmasligi ham mumkin.
    """
    if cb.message.answer_photo.await_args is not None:
        kwargs = cb.message.answer_photo.await_args.kwargs
        return kwargs["caption"], kwargs["reply_markup"]
    kwargs = cb.message.answer.await_args.kwargs
    args = cb.message.answer.await_args.args
    return (kwargs.get("text") or args[0]), kwargs["reply_markup"]


class TestLanguageChoice:
    """Til tanlash → xush kelibsiz matni. Aynan shu yerda bot yiqilgandi."""

    @pytest.fixture(autouse=True)
    def _no_db(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(start.svc, "save_user", AsyncMock())

    @pytest.mark.parametrize("lang", ["uz", "ru"])
    async def test_renders_welcome(self, lang: str, state: FSMContext) -> None:
        cb = make_callback(f"lang:{lang}")
        await start.on_lang(cb, state)

        cb.message.edit_text.assert_called_once()
        text = sent_text(cb.message.edit_text)
        assert text, "xush kelibsiz matni bo'sh"
        # To'ldirilmagan shablon qolmasin
        assert "{" not in text and "}" not in text

    async def test_shows_price_and_trial(self, state: FSMContext) -> None:
        """Narx va sinov muddati sozlamadan olinadi — nomi o'zgarsa yiqiladi.

        Ular xush kelibsiz ekranida EMAS, tarif ekranida: takrorlanmasin
        va birinchi ekran qisqa qolsin.
        """
        cb = make_callback("lang:uz")
        await start.on_lang(cb, state)

        text, kb = plans_screen(cb)
        assert "3 kun" in text

        labels = " ".join(b.text for row in kb.inline_keyboard for b in row)
        assert "149 000" in labels
        assert "299 000" in labels

    async def test_saves_language_to_state(self, state: FSMContext) -> None:
        cb = make_callback("lang:ru")
        await start.on_lang(cb, state)
        assert (await state.get_data())["lang"] == "ru"

    async def test_moves_to_plan_step(self, state: FSMContext) -> None:
        """Til tanlangach darhol tarif — oraliq «Boshlash» tugmasi yo'q."""
        cb = make_callback("lang:uz")
        await start.on_lang(cb, state)
        assert await state.get_state() == Onboarding.choosing_plan.state


class TestPlanStep:
    async def test_language_choice_offers_three_plans(
        self, state: FSMContext
    ) -> None:
        """Til tanlangandan keyingi BIRINCHI ekran — 3 variantli tarif."""
        cb = make_callback("lang:uz")
        await start.on_lang(cb, state)

        text, kb = plans_screen(cb)
        assert "Tarifni tanlang" in text
        assert "{" not in text

        labels = [b.text for row in kb.inline_keyboard for b in row]
        assert len(labels) == 3
        assert any("Bepul" in x for x in labels)
        assert any("Basic" in x for x in labels)
        assert any("Pro" in x for x in labels)


class TestOfertaStep:
    async def test_shows_key_terms_inline(self, state: FSMContext) -> None:
        """Asosiy shartlar Telegram ichida ko'rinadi — havolaga bog'liq emas.

        Sabab: server internetda bo'lmasa havola ochilmaydi va seller
        oqimda qotib qoladi.
        """
        await state.update_data(lang="uz")
        cb = make_callback("start:go")
        await start.show_oferta(cb, state)

        text = sent_text(cb.message.answer)
        assert "faqat o'qish" in text      # nima qilamiz
        assert "shifrlangan" in text       # kalit qanday saqlanadi
        assert "yuridik dalil emas" in text  # hisobotning maqomi
        assert "Uzum Market bilan bog'liq emasmiz" in text  # muhim ogohlantirish
        assert "{" not in text
        assert await state.get_state() == Onboarding.accepting_oferta.state

    async def test_full_text_button_sends_file(self, state: FSMContext) -> None:
        """To'liq matn fayl sifatida yuboriladi — serversiz ham ishlaydi."""
        await state.update_data(lang="uz")
        cb = make_callback("oferta:full")
        cb.message.answer_document = AsyncMock()

        await start.on_oferta_full(cb, state)

        cb.message.answer_document.assert_called_once()

    async def test_accept_moves_to_phone(
        self, state: FSMContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(start.svc, "accept_oferta", AsyncMock())
        await state.update_data(lang="uz")
        cb = make_callback("oferta:accept")

        await start.on_oferta_accept(cb, state)

        assert await state.get_state() == Onboarding.sharing_phone.state
        cb.message.answer.assert_called()


class TestAdminMenu:
    """Admin o'z huquqini menyuda ko'rishi kerak."""

    def test_admin_sees_extra_button(self) -> None:
        from app.bot.keyboards.menu import main_menu_kb

        admin_kb = main_menu_kb("uz", is_admin=True)
        labels = [b.text for row in admin_kb.keyboard for b in row]
        assert "👑 Admin" in labels

    def test_regular_user_does_not(self) -> None:
        from app.bot.keyboards.menu import main_menu_kb

        kb = main_menu_kb("uz", is_admin=False)
        labels = [b.text for row in kb.keyboard for b in row]
        assert "👑 Admin" not in labels

    def test_admin_button_is_last(self) -> None:
        """Asosiy bo'limlarni surib yubormasin."""
        from app.bot.keyboards.menu import main_menu_kb

        kb = main_menu_kb("uz", is_admin=True)
        assert kb.keyboard[-1][0].text == "👑 Admin"
        assert kb.keyboard[0][0].text.endswith("Yo'qotilgan pul")


class TestApiKeyStep:
    """Kalit qabul qilish — xabar o'chirilishi shart (SPEC 9.3)."""

    def _message(self, text: str) -> MagicMock:
        msg = MagicMock()
        msg.text = text
        msg.from_user.id = 555
        msg.answer = AsyncMock()
        msg.delete = AsyncMock()
        return msg

    async def test_rejects_garbage_without_calling_uzum(
        self, state: FSMContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Kalitga o'xshamagan matn uchun Uzumga so'rov yubormaymiz."""
        connect = AsyncMock()
        monkeypatch.setattr(start.svc, "connect_with_api_key", connect)
        await state.update_data(lang="uz")

        msg = self._message("salom qalesan")
        await start.on_api_key(msg, state)

        connect.assert_not_called()
        msg.delete.assert_not_called()  # oddiy xabar o'chirilmaydi
        msg.answer.assert_called_once()

    async def test_deletes_message_before_checking(
        self, state: FSMContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Kalit chatda turgan har soniya xavf — avval o'chiramiz."""
        from app.services.onboarding import ConnectResult

        monkeypatch.setattr(
            start.svc,
            "connect_with_api_key",
            AsyncMock(return_value=ConnectResult(ok=False, shops=[], error="invalid_key")),
        )
        await state.update_data(lang="uz")

        msg = self._message("A" * 40)
        await start.on_api_key(msg, state)

        msg.delete.assert_called_once()

    async def test_success_shows_shop_names(
        self, state: FSMContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.onboarding import ConnectResult

        monkeypatch.setattr(
            start.svc,
            "connect_with_api_key",
            AsyncMock(
                return_value=ConnectResult(
                    ok=True, shops=[{"id": "125841", "title": "Elore Parfume"}]
                )
            ),
        )
        await state.update_data(lang="uz")

        status = AsyncMock()
        status.edit_text = AsyncMock()
        msg = self._message("A" * 40)
        msg.answer = AsyncMock(return_value=status)

        await start.on_api_key(msg, state)

        text = sent_text(status.edit_text)
        assert "Elore Parfume" in text
        assert await state.get_state() == Onboarding.done.state

    async def test_paid_plan_asks_payment_after_connect(
        self, state: FSMContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Boshida pullik tarif tanlangan bo'lsa — to'lov endi so'raladi.

        To'lov onboarding boshida emas, aynan shu yerda: seller do'koni
        ulanganini ko'rgandan keyin.
        """
        from app.bot.handlers import billing as billing_handlers
        from app.services.onboarding import ConnectResult

        monkeypatch.setattr(
            start.svc,
            "connect_with_api_key",
            AsyncMock(return_value=ConnectResult(ok=True, shops=[{"id": "1"}])),
        )
        offer = AsyncMock(return_value=True)
        monkeypatch.setattr(billing_handlers, "offer_payment_after_connect", offer)

        await state.update_data(lang="uz", chosen_plan="pro")
        msg = self._message("A" * 40)
        msg.answer = AsyncMock(return_value=AsyncMock())

        await start.on_api_key(msg, state)

        offer.assert_awaited_once()
        # To'lov ekrani ko'rsatilgani uchun menyu hali chiqmaydi
        texts = [c.args[0] for c in msg.answer.await_args_list if c.args]
        assert not any("Asosiy menyu" in x for x in texts)


class TestTariffBanner:
    """Banner rasmi tarif ekranida ko'rinishi.

    2026-08-09: fayl `tariffs.png.jpg` nomi bilan saqlangan edi, kod esa
    faqat `tariffs.png` ni qidirardi — banner jimgina ko'rinmay qolgan.
    Shuning uchun bir nechta kengaytma qidiriladi.
    """

    def test_banner_exists_in_repo(self) -> None:
        from app.bot.handlers.start import tariff_banner

        assert tariff_banner() is not None, "banner fayli yo'q — tarif ekrani rasmsiz"

    def test_caption_fits_telegram_limit(self) -> None:
        """Matn 1024 belgidan oshsa rasm sarlavhasiga sig'maydi."""
        from app.bot.handlers.start import _CAPTION_LIMIT, plans_text

        for lang in ("uz", "ru"):
            assert len(plans_text(lang)) <= _CAPTION_LIMIT

    async def test_falls_back_to_text_when_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Banner yo'q bo'lsa oqim to'xtamaydi — matn yuboriladi."""
        from app.bot.handlers import start as start_module

        monkeypatch.setattr(start_module, "tariff_banner", lambda: None)
        target = AsyncMock()

        await start_module.send_with_banner(target, "matn", None)

        target.answer.assert_awaited_once()
        target.answer_photo.assert_not_awaited()


class TestGuideVideo:
    """API kalit yo'riqnomasidagi video qo'llanma.

    Video Telegramning 50 MB chegarasiga sig'ishi shart, aks holda
    umuman yuborilmaydi va seller buni bilmay qoladi.
    """

    def test_video_exists_and_fits_limit(self) -> None:
        from app.bot.handlers.start import _ASSETS

        video = _ASSETS / "api-guide.mp4"
        assert video.exists(), "video qo'llanma yo'q"
        size_mb = video.stat().st_size / 1024 / 1024
        assert size_mb < 50, f"Telegram 50 MB dan kattasini yubormaydi ({size_mb:.1f} MB)"

    async def test_missing_video_does_not_break_flow(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Video yo'q bo'lsa yozma yo'riqnoma bilan davom etadi."""
        from app.bot.handlers import start as start_module

        monkeypatch.setattr(start_module, "_ASSETS", tmp_path)  # bo'sh papka
        target = AsyncMock()

        await start_module._send_guide_video(target, "uz")

        target.answer_video.assert_not_awaited()
