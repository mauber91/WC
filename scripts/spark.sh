#!/usr/bin/env bash
# Helpers for the DGX Spark (Tailscale: gx10 @ 100.82.97.34, user mauber).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Use ~/.ssh/config Host "spark" (Tailscale + NVIDIA Sync key).
SPARK_HOST="${SPARK_HOST:-spark}"
SPARK_PATH="${SPARK_PATH:-~/WC}"

ssh_spark() {
  ssh "${SPARK_HOST}" "$@"
}

rsync_spark() {
  rsync -avz --delete \
    -e ssh \
    --exclude .git \
    --exclude node_modules \
    --exclude backend/.venv \
    --exclude backend/.pytest_cache \
    --exclude backend/.ruff_cache \
    --exclude data/app \
    --exclude frontend/dist \
    --exclude publish \
    "${ROOT}/" "${SPARK_HOST}:${SPARK_PATH}/"
}

usage() {
  cat <<EOF
Usage: ./scripts/spark.sh <command>

Commands:
  ping          Test SSH connectivity
  sync          Rsync project to ~/WC on the Spark
  setup         sync + copy .env + make remote-setup on the Spark
  start         Start dev servers in background on the Spark (ports 5180/8000)
  dev           Start make dev-remote on the Spark (foreground)
  tunnel        Forward localhost:5180 and :8000 from your Mac

Environment:
  SPARK_HOST    SSH config host (default: spark)
  SPARK_PATH    Remote project path (default: ~/WC)
EOF
}

cmd="${1:-}"
shift || true

case "${cmd}" in
  ping)
    ssh_spark 'uname -a && hostname && echo OK'
    ;;
  sync)
    rsync_spark
    echo "Synced to ${SPARK_HOST}:${SPARK_PATH}/"
    ;;
  setup)
    rsync_spark
    if [[ -f "${ROOT}/.env" ]]; then
      scp "${ROOT}/.env" "${SPARK_HOST}:${SPARK_PATH}/.env"
    fi
    ssh_spark "cd ${SPARK_PATH} && make remote-setup"
    echo "Spark setup complete. Run: make spark-start (Mac) or make spark-tunnel"
    ;;
  start)
    ssh_spark "cd ${SPARK_PATH} && PATH=\$HOME/.local/bin:\$PATH nohup env WC_WEB_PORT=5180 WC_API_PORT=8000 make dev-remote > /tmp/wc-dev.log 2>&1 & sleep 5 && tail -15 /tmp/wc-dev.log"
    echo "Open http://localhost:5180 after: make spark-tunnel"
    ;;
  dev)
    ssh_spark "cd ${SPARK_PATH} && PATH=\$HOME/.local/bin:\$PATH nohup env WC_WEB_PORT=5180 WC_API_PORT=8000 make dev-remote > /tmp/wc-dev.log 2>&1 & sleep 4 && tail -30 /tmp/wc-dev.log"
    ;;
  tunnel)
    WEB_PORT="${WC_WEB_PORT:-5180}"
    API_PORT="${WC_API_PORT:-8000}"
    echo "Forwarding localhost:${WEB_PORT} and localhost:${API_PORT} -> ${SPARK_HOST}"
    exec ssh -N \
      -L "127.0.0.1:${WEB_PORT}:127.0.0.1:${WEB_PORT}" \
      -L "127.0.0.1:${API_PORT}:127.0.0.1:${API_PORT}" \
      "${SPARK_HOST}"
    ;;
  ""|-h|--help|help)
    usage
    ;;
  *)
    echo "Unknown command: ${cmd}" >&2
    usage >&2
    exit 1
    ;;
esac
