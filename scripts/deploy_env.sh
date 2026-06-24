# Shared deploy defaults for scripts/deploy.sh, deploy_fly.sh, and deploy_pages.sh.
# Values come from .env when set; otherwise the wc-forecast production defaults apply.

deploy_env_root() {
  if [[ -n "${ROOT:-}" ]]; then
    printf '%s\n' "$ROOT"
    return
  fi
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[1]:-${BASH_SOURCE[0]}}")" && pwd)"
  cd "${script_dir}/.." && pwd
}

deploy_env_value() {
  local key="$1"
  local default="$2"
  local root env_file line value

  root="$(deploy_env_root)"
  env_file="${root}/.env"
  if [[ ! -f "$env_file" ]]; then
    printf '%s\n' "$default"
    return
  fi

  line="$(grep -E "^${key}=" "$env_file" | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    printf '%s\n' "$default"
    return
  fi

  value="${line#*=}"
  value="${value%$'\r'}"
  value="${value#\"}"
  value="${value%\"}"
  value="${value#\'}"
  value="${value%\'}"
  if [[ -z "$value" ]]; then
    printf '%s\n' "$default"
    return
  fi
  printf '%s\n' "$value"
}

deploy_fly_app() {
  deploy_env_value WC_FLY_APP wc-forecast-api
}

deploy_pages_origin() {
  deploy_env_value WC_PAGES_ORIGIN https://wc-forecast.pages.dev
}

deploy_api_base_url() {
  local configured app
  configured="$(deploy_env_value WC_PUBLISH_API_BASE_URL "")"
  if [[ -n "$configured" ]]; then
    printf '%s\n' "$configured"
    return
  fi
  app="$(deploy_fly_app)"
  printf 'https://%s.fly.dev/api/v1\n' "$app"
}

deploy_pages_project() {
  deploy_env_value CF_PAGES_PROJECT wc-forecast
}
