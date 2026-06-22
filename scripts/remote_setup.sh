#!/usr/bin/env bash
# One-time bootstrap for running World Cup Forecast on a remote Linux host (e.g. DGX Spark).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> World Cup Forecast remote setup ($(uname -m))"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required. On Ubuntu: sudo apt-get install -y curl"
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "==> Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
fi

echo "==> Ensuring Python 3.13"
uv python install 3.13

NODE_MAJOR=""
if command -v node >/dev/null 2>&1; then
  NODE_MAJOR="$(node -v | sed 's/^v//' | cut -d. -f1)"
fi

if [[ -z "${NODE_MAJOR}" || "${NODE_MAJOR}" -lt 20 ]]; then
  if command -v fnm >/dev/null 2>&1; then
    echo "==> Installing Node 20 via fnm"
    fnm install 20
    fnm use 20
  elif [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
    echo "==> Installing Node 20 via nvm"
    # shellcheck disable=SC1091
    source "${HOME}/.nvm/nvm.sh"
    nvm install 20
    nvm use 20
  else
    echo "Node 20+ is required. Install fnm (https://github.com/Schniz/fnm) or nvm, then re-run this script."
    exit 1
  fi
fi

echo "==> Python: $(uv python find 3.13)"
echo "==> Node: $(node -v)"

if [[ ! -f .env ]]; then
  echo "==> Creating .env from .env.example"
  cp .env.example .env
  echo "    Edit .env and set WC_API_FOOTBALL_KEY (and WC_ADMIN_API_KEY if you use admin routes)."
fi

make setup
make migrate

echo
echo "Remote setup complete."
echo "Start dev servers:  make dev-remote"
echo "From your laptop:   make ssh-tunnel REMOTE=user@your-dgx-spark"
echo "Then open:          http://localhost:5173"
