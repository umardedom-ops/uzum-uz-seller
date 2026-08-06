# Uzum Seller Bot
FROM python:3.12-slim

# fonts-dejavu-core — PDF hisobotlarda kirill va o'zbekcha harflar uchun
# (app/docs/fonts.py shu shriftni qidiradi). Bo'lmasa matn "□□□" bo'ladi.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Tashkent

WORKDIR /app

# Avval requirements — kod o'zgarganda qayta o'rnatilmasin (qatlam keshi)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Chiqariladigan hujjatlar shu yerga yoziladi
RUN mkdir -p /app/generated

RUN chmod +x /app/scripts/entrypoint.sh
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["bot"]
