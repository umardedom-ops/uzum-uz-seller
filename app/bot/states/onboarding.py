"""Onboarding oqimi holatlari (SPEC 7).

til → oferta → telefon → yo'riqnoma → do'kon ID → asosiy menyu
"""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    choosing_lang = State()
    accepting_oferta = State()
    sharing_phone = State()
    reading_instruction = State()
    entering_api_key = State()
    done = State()
