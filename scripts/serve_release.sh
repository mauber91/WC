#!/usr/bin/env bash
# Build the published frontend and serve it locally with a read-only API.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PATH="${HOME}/.local/bin:${PATH}"

port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t >/dev/null 2>&1
    return
  fi
  nc -z 127.0.0.1 "${port}" >/dev/null 2>&1
}

find_free_port() {
  local start="$1"
  local port="$1"
  local exclude="${2:-}"
  local announced=0
  while port_in_use "${port}" || [[ -n "${exclude}" && "${port}" == "${exclude}" ]]; do
    if [[ "${announced}" -eq 0 ]]; then
      echo "==> Port ${start} is in use, searching for a free port" >&2
      announced=1
    fi
    port=$((port + 1))
    if [[ $((port - start)) -ge 100 ]]; then
      echo "No free port found near ${start}." >&2
      exit 1
    fi
  done
  if [[ "${port}" != "${start}" ]]; then
    echo "==> Using port ${port} instead of ${start}" >&2
  fi
  echo "${port}"
}

REQUESTED_API_PORT="${WC_API_PORT:-8000}"
REQUESTED_WEB_PORT="${WC_WEB_PORT:-4173}"
API_PORT="$(find_free_port "${REQUESTED_API_PORT}")"
WEB_PORT="$(find_free_port "${REQUESTED_WEB_PORT}" "${API_PORT}")"
API_BASE="http://127.0.0.1:${API_PORT}/api/v1"
CORS="http://127.0.0.1:${WEB_PORT},http://localhost:${WEB_PORT}"
FRONTEND_ENV="$ROOT/publish/frontend.env"
PUBLISH_DB="$ROOT/publish/worldcup.db"

cleanup() {
  local pid
  for pid in $(jobs -p); do
    kill "${pid}" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

if [[ "${SKIP_PUBLISH:-0}" != 1 ]]; then
  echo "==> Preparing publish bundle"
  (cd "${ROOT}/backend" && uv run python ../scripts/publish.py --api-base-url "${API_BASE}" "$@")
fi

if [[ ! -f "${FRONTEND_ENV}" ]]; then
  echo "Missing ${FRONTEND_ENV}. Run without SKIP_PUBLISH=1 or run make publish first." >&2
  exit 1
fi

if [[ ! -f "${PUBLISH_DB}" ]]; then
  echo "Missing ${PUBLISH_DB}. Run without SKIP_PUBLISH=1 or run make publish first." >&2
  exit 1
fi

echo "==> Building frontend (published mode)"
set -a
# shellcheck disable=SC1090
source "${FRONTEND_ENV}"
export VITE_API_BASE_URL="${API_BASE}"
set +a
(cd "${ROOT}/frontend" && npm run build)

PUBLISHED_ID="$(
  cd "${ROOT}/backend" && uv run python -c \
    "import json; print(json.load(open('../publish/manifest.json'))['simulation_id'])"
)"

echo "API: ${API_BASE} (simulation ${PUBLISHED_ID})"
echo "Web: http://127.0.0.1:${WEB_PORT}"
echo "Press Ctrl+C to stop both servers."

(
  cd "${ROOT}/backend"
  WC_DATABASE_URL="sqlite:///${PUBLISH_DB}" \
  WC_PUBLISHED_SIMULATION_ID="${PUBLISHED_ID}" \
  WC_SIMULATIONS_ENABLED=false \
  WC_SEED_REFRESH_ON_STARTUP=false \
  WC_MARKET_SYNC_ON_STARTUP=false \
  WC_ENABLE_SCHEDULER=false \
  WC_CORS_ORIGINS="${CORS}" \
    uv run uvicorn world_cup_api.main:app \
      --host 127.0.0.1 \
      --port "${API_PORT}"
) &

(
  cd "${ROOT}/frontend"
  npm run preview -- --host 127.0.0.1 --port "${WEB_PORT}"
) &

wait
