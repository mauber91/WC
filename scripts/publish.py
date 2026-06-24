#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from world_cup_api.config import ENV_FILE, ROOT_DIR, get_settings
from world_cup_api.db.models import SimulationTeamR32Rival
from world_cup_api.db.session import SessionLocal
from world_cup_api.services.simulations import backfill_r32_rivals


def _default_db_path() -> Path:
    settings = get_settings()
    if settings.database_url.startswith("sqlite:///"):
        return Path(settings.database_url.removeprefix("sqlite:///"))
    raise SystemExit("Publish script currently supports SQLite databases only.")


def _latest_completed_simulation(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        """
        SELECT id
        FROM simulations
        WHERE status = 'completed'
        ORDER BY completed_at DESC, created_at DESC
        LIMIT 1
        """,
    ).fetchone()
    return row[0] if row else None


def _simulation_exists(conn: sqlite3.Connection, simulation_id: str) -> bool:
    row = conn.execute(
        "SELECT id FROM simulations WHERE id = ? AND status = 'completed'",
        (simulation_id,),
    ).fetchone()
    return row is not None


def _checkpoint_source_db(source_db: Path) -> None:
    with sqlite3.connect(source_db) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _prune_simulations(conn: sqlite3.Connection, keep_id: str) -> None:
    conn.execute("DELETE FROM simulations WHERE id != ?", (keep_id,))
    conn.commit()


def _load_scenario(path: Path | None) -> dict | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Scenario file must contain a JSON object: {path}")
    return payload


def _write_env_file(path: Path, lines: dict[str, str]) -> None:
    parts: list[str] = []
    for key, value in lines.items():
        if any(character in value for character in ' "\'#\\$'):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'{key}="{escaped}"')
        else:
            parts.append(f"{key}={value}")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def _dotenv_values(*keys: str) -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        return values
    wanted = set(keys)
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        key = key.strip()
        if key not in wanted:
            continue
        value = raw.strip().strip('"').strip("'")
        if value:
            values[key] = value
    return values


def _ensure_r32_rivals(simulation_id: str) -> None:
    db = SessionLocal()
    try:
        rival_count = db.scalar(
            select(func.count())
            .select_from(SimulationTeamR32Rival)
            .where(SimulationTeamR32Rival.simulation_id == simulation_id),
        )
        if rival_count:
            return
        print(f"Backfilling Round-of-32 rivals for simulation {simulation_id}...", file=sys.stderr)
        rows = backfill_r32_rivals(
            db,
            simulation_id,
            progress=lambda done, total: print(f"  {done:,} / {total:,} trials", file=sys.stderr, flush=True),
        )
        print(f"Wrote {rows:,} rival rows.", file=sys.stderr)
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a read-only publish bundle for the hosted forecast.")
    parser.add_argument("--simulation-id", help="Completed simulation UUID to publish (default: latest completed)")
    parser.add_argument("--scenario-file", type=Path, help="Exported scenario JSON from the local Scenario tab")
    parser.add_argument("--scenario-title", default="Author scenario")
    parser.add_argument("--scenario-description", default="A fixed what-if bracket built from chosen group-stage results.")
    parser.add_argument("--output-dir", type=Path, default=ROOT_DIR / "publish")
    parser.add_argument("--api-base-url", default="https://your-api.example.com/api/v1")
    args = parser.parse_args()

    source_db = _default_db_path()
    if not source_db.exists():
        raise SystemExit(f"Database not found: {source_db}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    target_db = args.output_dir / "worldcup.db"
    if target_db.exists():
        target_db.unlink()
    for sidecar in (Path(f"{target_db}-wal"), Path(f"{target_db}-shm")):
        if sidecar.exists():
            sidecar.unlink()

    with sqlite3.connect(source_db) as conn:
        simulation_id = args.simulation_id or _latest_completed_simulation(conn)
        if not simulation_id:
            raise SystemExit("No completed simulation found to publish.")
        if not _simulation_exists(conn, simulation_id):
            raise SystemExit(f"Completed simulation not found: {simulation_id}")

    _ensure_r32_rivals(simulation_id)
    _checkpoint_source_db(source_db)
    shutil.copy2(source_db, target_db)

    with sqlite3.connect(target_db) as conn:
        _prune_simulations(conn, simulation_id)
        row = conn.execute(
            """
            SELECT iterations, seed, input_cutoff_at, model_version, ruleset_version, completed_at, duration_ms
            FROM simulations
            WHERE id = ?
            """,
            (simulation_id,),
        ).fetchone()
        assert row is not None

    scenario = _load_scenario(args.scenario_file)
    backend_env = {
        "WC_DATABASE_URL": f"sqlite:////data/app/worldcup.db",
        "WC_SIMULATIONS_ENABLED": "false",
        "WC_PUBLISHED_SIMULATION_ID": simulation_id,
        "WC_ENABLE_SCHEDULER": "true",
        "WC_MARKET_SYNC_ENABLED": "true",
        "WC_SEED_REFRESH_ENABLED": "true",
        "WC_CORS_ORIGINS": "https://your-frontend.example.com",
    }
    frontend_env = {
        "VITE_APP_MODE": "published",
        "VITE_API_BASE_URL": args.api_base_url,
        "VITE_PUBLISHED_SIMULATION_ID": simulation_id,
        "VITE_PUBLISHED_SCENARIO_TITLE": args.scenario_title,
        "VITE_PUBLISHED_SCENARIO_DESCRIPTION": args.scenario_description,
    }
    if scenario is not None:
        frontend_env["VITE_PUBLISHED_SCENARIO"] = json.dumps(scenario, separators=(",", ":"))
    frontend_env.update(_dotenv_values("VITE_CF_WEB_ANALYTICS_TOKEN"))

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "simulation_id": simulation_id,
        "iterations": row[0],
        "seed": row[1],
        "input_cutoff_at": row[2],
        "model_version": row[3],
        "ruleset_version": row[4],
        "completed_at": row[5],
        "duration_ms": row[6],
        "scenario_included": scenario is not None,
        "web_analytics_enabled": "VITE_CF_WEB_ANALYTICS_TOKEN" in frontend_env,
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if scenario is not None:
        (args.output_dir / "scenario.json").write_text(json.dumps(scenario, indent=2) + "\n", encoding="utf-8")

    _write_env_file(args.output_dir / "backend.env", backend_env)
    _write_env_file(args.output_dir / "frontend.env", frontend_env)

    deploy_steps = f"""Fly.io API (first time)
-------------------
1. Edit fly.toml and set `app = "your-app-name"`.
2. fly apps create your-app-name
3. make deploy-fly ARGS="--app your-app-name --cors-origin https://your-project.pages.dev --init-volume"

Re-publish simulation only (no API image rebuild)
-------------------------------------------------
make deploy-sim

Full publish (simulation + frontend)
------------------------------------
make deploy

Frontend only (reuse publish/frontend.env)
------------------------------------------
make deploy-ui

Manual flags still work:
make deploy-fly ARGS="--app your-app-name --cors-origin https://your-project.pages.dev --skip-deploy"

Cloudflare Pages (GitHub Actions)
---------------------------------
Repository secrets:
  CLOUDFLARE_API_TOKEN
  CLOUDFLARE_ACCOUNT_ID
  VITE_API_BASE_URL={args.api_base_url}
  VITE_PUBLISHED_SIMULATION_ID={simulation_id}
  VITE_PUBLISHED_SCENARIO=<optional JSON from publish/scenario.json>

Repository variables (optional):
  CF_PAGES_PROJECT=wc-forecast

Trigger: GitHub Actions -> Deploy frontend to Cloudflare Pages

After first Pages deploy, set Fly CORS to your Pages URL:
  fly secrets set --app your-app-name WC_CORS_ORIGINS=https://your-project.pages.dev
"""
    (args.output_dir / "DEPLOY.md").write_text(deploy_steps, encoding="utf-8")

    print(json.dumps({"output_dir": str(args.output_dir), **manifest}, indent=2))
    print(f"\nWrote {args.output_dir}/DEPLOY.md")


if __name__ == "__main__":
    main()
