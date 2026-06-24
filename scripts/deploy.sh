#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/deploy_env.sh"

usage() {
  cat <<'EOF'
Deploy the published forecast site.

Usage:
  scripts/deploy.sh [mode] [extra deploy flags...]

Modes:
  all   Publish latest simulation to Fly, then deploy frontend (default)
  sim   Publish latest simulation to Fly only
  ui    Deploy frontend only (reuses publish/frontend.env)

Defaults are read from .env:
  WC_FLY_APP, WC_PAGES_ORIGIN, WC_PUBLISH_API_BASE_URL, CF_PAGES_PROJECT

Examples:
  make deploy
  make deploy-sim
  make deploy-ui
  make deploy ARGS="--simulation-id <uuid>"
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

MODE="all"
if [[ $# -gt 0 && "$1" != --* ]]; then
  MODE="$1"
  shift
fi

  case "$MODE" in
  all|sim|ui) ;;
  *)
    echo "Unknown mode: $MODE" >&2
    usage
    exit 1
    ;;
esac

API_BASE_URL="$(deploy_api_base_url)"
PAGES_ORIGIN="$(deploy_pages_origin)"
FLY_APP="$(deploy_fly_app)"
PAGES_PROJECT="$(deploy_pages_project)"

FLY_ARGS=(
  --app "$FLY_APP"
  --cors-origin "$PAGES_ORIGIN"
  --api-base-url "$API_BASE_URL"
  --skip-deploy
)

PAGES_ARGS=(
  --api-base-url "$API_BASE_URL"
  --project "$PAGES_PROJECT"
  --skip-publish
)

case "$MODE" in
  sim)
    exec "$ROOT/scripts/deploy_fly.sh" "${FLY_ARGS[@]}" "$@"
    ;;
  ui)
    exec "$ROOT/scripts/deploy_pages.sh" "${PAGES_ARGS[@]}" "$@"
    ;;
  all)
    "$ROOT/scripts/deploy_fly.sh" "${FLY_ARGS[@]}" "$@"
    exec "$ROOT/scripts/deploy_pages.sh" "${PAGES_ARGS[@]}" "$@"
    ;;
esac
