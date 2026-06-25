#!/bin/sh
set -eu

mkdir -p /data/app

cd /app/backend
if [ "${WC_SIMULATIONS_ENABLED:-true}" != "false" ]; then
  alembic upgrade head
else
  echo "Published mode: skipping alembic migrations (database is pre-built)"
fi

exec uvicorn world_cup_api.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8080}" \
  --proxy-headers \
  --forwarded-allow-ips="*"
