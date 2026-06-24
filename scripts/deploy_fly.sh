#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/deploy_env.sh"

APP=""
CORS_ORIGIN=""
API_BASE_URL=""
SCENARIO_FILE=""
SCENARIO_TITLE="Author scenario"
SCENARIO_DESCRIPTION="A fixed what-if bracket built from chosen group-stage results."
SIMULATION_ID=""
SKIP_PUBLISH=0
SKIP_DEPLOY=0
SKIP_DB_UPLOAD=0
INIT_VOLUME=0
REGION="ord"

usage() {
  cat <<'EOF'
Deploy the read-only published API to Fly.io.

Usage:
  scripts/deploy_fly.sh [options]

Defaults (from .env when set):
  --app             WC_FLY_APP (default: wc-forecast-api)
  --cors-origin     WC_PAGES_ORIGIN (default: https://wc-forecast.pages.dev)
  --api-base-url    WC_PUBLISH_API_BASE_URL (default: https://<app>.fly.dev/api/v1)

Options:
  --api-base-url    Public API URL for frontend build env (default: https://<app>.fly.dev/api/v1)
  --scenario-file   scenario.json exported from the local Scenario tab
  --simulation-id   Publish a specific completed simulation UUID
  --region          Fly region for volume creation (default: ord)
  --init-volume     Create the wc_data volume before deploy (first-time setup)
  --skip-publish    Reuse existing publish/ bundle
  --skip-deploy     Upload DB + secrets only, do not run fly deploy
  --skip-db-upload  Deploy without replacing /data/app/worldcup.db

Examples:
  scripts/deploy_fly.sh --app wc-forecast-api --cors-origin https://wc.pages.dev --init-volume
  scripts/deploy_fly.sh --app wc-forecast-api --cors-origin https://wc.pages.dev --scenario-file ./scenario.json
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app) APP="$2"; shift 2 ;;
    --cors-origin) CORS_ORIGIN="$2"; shift 2 ;;
    --api-base-url) API_BASE_URL="$2"; shift 2 ;;
    --scenario-file) SCENARIO_FILE="$2"; shift 2 ;;
    --scenario-title) SCENARIO_TITLE="$2"; shift 2 ;;
    --scenario-description) SCENARIO_DESCRIPTION="$2"; shift 2 ;;
    --simulation-id) SIMULATION_ID="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --init-volume) INIT_VOLUME=1; shift ;;
    --skip-publish) SKIP_PUBLISH=1; shift ;;
    --skip-deploy) SKIP_DEPLOY=1; shift ;;
    --skip-db-upload) SKIP_DB_UPLOAD=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$APP" ]]; then
  APP="$(deploy_fly_app)"
fi
if [[ -z "$CORS_ORIGIN" ]]; then
  CORS_ORIGIN="$(deploy_pages_origin)"
fi

if [[ -z "$APP" || -z "$CORS_ORIGIN" ]]; then
  usage
  exit 1
fi

if ! command -v fly >/dev/null 2>&1; then
  echo "fly CLI not found. Install: https://fly.io/docs/flyctl/install/" >&2
  exit 1
fi

if [[ -z "$API_BASE_URL" ]]; then
  API_BASE_URL="$(deploy_api_base_url)"
fi

PUBLISH_ARGS=(--api-base-url "$API_BASE_URL" --scenario-title "$SCENARIO_TITLE" --scenario-description "$SCENARIO_DESCRIPTION")
if [[ -n "$SCENARIO_FILE" ]]; then
  PUBLISH_ARGS+=(--scenario-file "$SCENARIO_FILE")
fi
if [[ -n "$SIMULATION_ID" ]]; then
  PUBLISH_ARGS+=(--simulation-id "$SIMULATION_ID")
fi

if [[ "$SKIP_PUBLISH" -eq 0 ]]; then
  echo "==> Building publish bundle"
  (cd backend && uv run python ../scripts/publish.py "${PUBLISH_ARGS[@]}")
fi

MANIFEST="$ROOT/publish/manifest.json"
DB_FILE="$ROOT/publish/worldcup.db"
if [[ ! -f "$MANIFEST" || ! -f "$DB_FILE" ]]; then
  echo "Missing publish bundle. Run make publish first." >&2
  exit 1
fi

PUBLISHED_ID="$(python3 -c "import json; print(json.load(open('$MANIFEST'))['simulation_id'])")"

if [[ "$INIT_VOLUME" -eq 1 ]]; then
  echo "==> Creating Fly volume wc_data in ${REGION} (skip if it already exists)"
  fly volumes create wc_data --app "$APP" --region "$REGION" --size 1 --yes || true
fi

echo "==> Setting Fly secrets"
fly secrets set \
  --app "$APP" \
  "WC_PUBLISHED_SIMULATION_ID=${PUBLISHED_ID}" \
  "WC_CORS_ORIGINS=${CORS_ORIGIN}"

if [[ -f "$ROOT/.env" ]] && grep -q '^WC_API_FOOTBALL_KEY=' "$ROOT/.env"; then
  API_KEY="$(grep '^WC_API_FOOTBALL_KEY=' "$ROOT/.env" | cut -d= -f2-)"
  if [[ -n "$API_KEY" ]]; then
    fly secrets set --app "$APP" "WC_API_FOOTBALL_KEY=${API_KEY}"
  fi
fi

if [[ "$SKIP_DEPLOY" -eq 0 ]]; then
  echo "==> Deploying ${APP}"
  fly deploy --app "$APP"
fi

if [[ "$SKIP_DB_UPLOAD" -eq 0 ]]; then
  echo "==> Uploading published database to /data/app/worldcup.db"
  fly ssh console --app "$APP" -C "rm -f /data/app/worldcup.db /data/app/worldcup.db-wal /data/app/worldcup.db-shm"
  fly ssh sftp put "$DB_FILE" /data/app/worldcup.db --app "$APP"
  echo "==> Restarting app to pick up database"
  fly apps restart "$APP"
fi

cat <<EOF

Done.

Backend:  https://${APP}.fly.dev
Health:   https://${APP}.fly.dev/api/v1/health
Forecast: ${PUBLISHED_ID}

Frontend (Cloudflare Pages build env from publish/frontend.env):
  VITE_APP_MODE=published
  VITE_API_BASE_URL=${API_BASE_URL}
  VITE_PUBLISHED_SIMULATION_ID=${PUBLISHED_ID}

Re-publish later:
  scripts/deploy_fly.sh --app ${APP} --cors-origin ${CORS_ORIGIN} --skip-deploy

EOF
