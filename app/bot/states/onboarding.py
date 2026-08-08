"""Onboarding oqimi holatlari (SPEC 7).

til → tarif → oferta → telefon → yo'riqnoma → API kalit → asosiy menyu

Tarif til tanlangandan keyin turadi va tanlash **majburiy**. Pullik
tarif tanlansa to'lov shu yerda emas, do'kon ulangandan keyin
so'raladi — oferta qabul qilinmasdan pul so'ramaymiz.
"""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    choosing_lang = State()
    accepting_oferta = State()
    sharing_phone = State()
    reading_instruction = State()
    entering_api_key = State()
    choosing_plan = State()
    done = State()
