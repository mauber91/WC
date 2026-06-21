#!/bin/sh
set -eu

mkdir -p /data/app

cd /app/backend
alembic upgrade head

exec uvicorn world_cup_api.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8080}" \
  --proxy-headers \
  --forwarded-allow-ips="*"
