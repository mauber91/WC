FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app/backend

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/README.md ./README.md
COPY backend/src ./src
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
RUN uv sync --frozen --no-dev

COPY data/seed /app/data/seed
COPY scripts/docker-entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh \
    && mkdir -p /data/app

ENV PATH="/app/backend/.venv/bin:${PATH}" \
    PYTHONPATH="/app/backend/src"

WORKDIR /app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
