#!/usr/bin/env bash
# Run API + Vite on a remote host, bound for SSH port forwarding or LAN access.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PATH="${HOME}/.local/bin:${PATH}"

API_HOST="${WC_DEV_HOST:-0.0.0.0}"
WEB_HOST="${WC_DEV_HOST:-0.0.0.0}"
API_PORT="${WC_API_PORT:-8000}"
WEB_PORT="${WC_WEB_PORT:-5173}"

cleanup() {
  local pid
  for pid in $(jobs -p); do
    kill "${pid}" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

echo "API: http://${API_HOST}:${API_PORT}/docs"
echo "Web: http://${WEB_HOST}:${WEB_PORT}"
echo "Press Ctrl+C to stop both servers."

(
  cd "${ROOT}/backend"
  WC_SEED_REFRESH_ON_STARTUP=false WC_MARKET_SYNC_ON_STARTUP=false \
    uv run uvicorn world_cup_api.main:app \
      --reload --reload-dir src \
      --host "${API_HOST}" \
      --port "${API_PORT}"
) &

(
  cd "${ROOT}/frontend"
  npm run dev -- --host "${WEB_HOST}" --port "${WEB_PORT}"
) &

wait
