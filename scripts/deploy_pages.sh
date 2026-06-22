#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT="wc-forecast"
API_BASE_URL=""
SCENARIO_FILE=""
SCENARIO_TITLE="Author scenario"
SCENARIO_DESCRIPTION="A fixed what-if bracket built from chosen group-stage results."
SIMULATION_ID=""
SKIP_PUBLISH=0
SKIP_BUILD=0
BRANCH=""

usage() {
  cat <<'EOF'
Deploy the published frontend to Cloudflare Pages.

Usage:
  scripts/deploy_pages.sh [options]

Options:
  --project             Cloudflare Pages project name (default: wc-forecast)
  --api-base-url        Fly API URL for VITE_API_BASE_URL (required unless publish/ exists)
  --scenario-file       scenario.json exported from the local Scenario tab
  --simulation-id       Publish a specific completed simulation UUID
  --branch              Pages branch alias (default: production)
  --skip-publish        Reuse existing publish/frontend.env
  --skip-build          Deploy existing frontend/dist without rebuilding

Examples:
  scripts/deploy_pages.sh --api-base-url https://wc-forecast-api.fly.dev/api/v1
  scripts/deploy_pages.sh --project wc-forecast --scenario-file ./scenario.json --skip-publish
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --api-base-url) API_BASE_URL="$2"; shift 2 ;;
    --scenario-file) SCENARIO_FILE="$2"; shift 2 ;;
    --scenario-title) SCENARIO_TITLE="$2"; shift 2 ;;
    --scenario-description) SCENARIO_DESCRIPTION="$2"; shift 2 ;;
    --simulation-id) SIMULATION_ID="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --skip-publish) SKIP_PUBLISH=1; shift ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if ! command -v npx >/dev/null 2>&1; then
  echo "npx not found. Install Node.js 20+." >&2
  exit 1
fi

FRONTEND_ENV="$ROOT/publish/frontend.env"
if [[ "$SKIP_PUBLISH" -eq 0 ]]; then
  if [[ -z "$API_BASE_URL" ]]; then
    echo "--api-base-url is required when publishing." >&2
    exit 1
  fi
  echo "==> Building publish bundle"
  PUBLISH_ARGS=(--api-base-url "$API_BASE_URL" --scenario-title "$SCENARIO_TITLE" --scenario-description "$SCENARIO_DESCRIPTION")
  if [[ -n "$SCENARIO_FILE" ]]; then
    PUBLISH_ARGS+=(--scenario-file "$SCENARIO_FILE")
  fi
  if [[ -n "$SIMULATION_ID" ]]; then
    PUBLISH_ARGS+=(--simulation-id "$SIMULATION_ID")
  fi
  (cd backend && uv run python ../scripts/publish.py "${PUBLISH_ARGS[@]}")
fi

if [[ ! -f "$FRONTEND_ENV" ]]; then
  echo "Missing $FRONTEND_ENV. Run make publish first." >&2
  exit 1
fi

echo "==> Loading publish/frontend.env"
set -a
# shellcheck disable=SC1090
source "$FRONTEND_ENV"
set +a

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  echo "==> Building frontend (published mode)"
  (cd frontend && npm ci && npm run build)
else
  echo "==> Skipping frontend build (--skip-build)"
  if ! rg -q "Published forecast" frontend/dist/assets/*.js 2>/dev/null; then
    echo "ERROR: frontend/dist was not built in published mode. Re-run without --skip-build." >&2
    exit 1
  fi
  if rg -q '"/admin/data"|Admin workspace' frontend/dist/assets/*.js 2>/dev/null; then
    echo "ERROR: frontend/dist contains admin routes. Re-run without --skip-build." >&2
    exit 1
  fi
fi

if [[ ! -d "$ROOT/frontend/dist" ]]; then
  echo "Missing frontend/dist. Run npm run build in frontend/." >&2
  exit 1
fi

DEPLOY_ARGS=(pages deploy dist --project-name "$PROJECT")
if [[ -n "$BRANCH" ]]; then
  DEPLOY_ARGS+=(--branch "$BRANCH")
fi

echo "==> Deploying to Cloudflare Pages (${PROJECT})"
if ! npx wrangler pages project list 2>/dev/null | rg -q "${PROJECT}"; then
  echo "==> Creating Cloudflare Pages project ${PROJECT}"
  npx wrangler pages project create "$PROJECT" --production-branch main
fi
(cd frontend && npx wrangler pages deploy dist --project-name "$PROJECT" --commit-dirty=true)

PAGES_URL="https://${PROJECT}.pages.dev"
if [[ -n "$BRANCH" && "$BRANCH" != "production" ]]; then
  PAGES_URL="https://${BRANCH}.${PROJECT}.pages.dev"
fi

cat <<EOF

Done.

Site:    ${PAGES_URL}
API env: ${VITE_API_BASE_URL:-unset}

Update Fly CORS if this is a new Pages URL:
  fly secrets set --app <fly-app> WC_CORS_ORIGINS=${PAGES_URL}

EOF
