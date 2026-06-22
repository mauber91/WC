#!/usr/bin/env bash
# Forward local ports to a remote dev session (run from your laptop).
set -euo pipefail

REMOTE="${REMOTE:-}"
API_PORT="${WC_API_PORT:-8000}"
WEB_PORT="${WC_WEB_PORT:-5173}"

if [[ -z "${REMOTE}" ]]; then
  echo "Usage: REMOTE=user@dgx-spark ./scripts/ssh_tunnel.sh"
  echo "   or: make ssh-tunnel REMOTE=user@dgx-spark"
  exit 1
fi

echo "Forwarding localhost:${WEB_PORT} and localhost:${API_PORT} -> ${REMOTE}"
echo "Open http://localhost:${WEB_PORT} after starting 'make dev-remote' on the remote host."
echo "Press Ctrl+C to close the tunnel."

exec ssh -N \
  -L "127.0.0.1:${WEB_PORT}:127.0.0.1:${WEB_PORT}" \
  -L "127.0.0.1:${API_PORT}:127.0.0.1:${API_PORT}" \
  "${REMOTE}"
