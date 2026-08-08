"""Onboarding oqimi holatlari (SPEC 7).

til → oferta → telefon → yo'riqnoma → API kalit → tarif → asosiy menyu

Tarif tanlash do'kon ulangandan **keyin** turadi: seller avval o'z
do'koni ulanganini ko'radi, keyin tarif tanlaydi. Tanlamaguncha asosiy
menyu ochilmaydi.
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
