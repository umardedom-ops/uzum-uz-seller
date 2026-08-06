#!/bin/sh
# Konteyner kirish nuqtasi.
#
#   bot  — Telegram bot + rejalashtiruvchi (sync, audit, hisobot)
#   web  — Click webhook serveri (FastAPI)
#
# Migratsiya faqat `bot` konteynerida yuritiladi: ikki jarayon bir vaqtda
# `alembic upgrade` qilsa, jadval yaratishda ziddiyat chiqadi.

set -e

case "$1" in
  bot)
    echo "→ Migratsiyalar qo'llanmoqda..."
    alembic upgrade head
    echo "→ Bot ishga tushmoqda"
    exec python -m app.bot.main
    ;;

  web)
    # Baza tayyor bo'lishini kutamiz (bot migratsiyani tugatgunicha)
    echo "→ Webhook serveri ishga tushmoqda"
    exec uvicorn app.web.click_api:app \
        --host 0.0.0.0 \
        --port "${PORT:-8000}" \
        --proxy-headers \
        --forwarded-allow-ips='*'
    ;;

  migrate)
    exec alembic upgrade head
    ;;

  *)
    exec "$@"
    ;;
esac
