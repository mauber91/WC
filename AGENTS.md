# AGENTS.md

## Cursor Cloud specific instructions

This is a two-part monorepo for **World Cup Forecast**: a `backend/` (Python 3.13, FastAPI, managed by `uv`) and a `frontend/` (React + Vite, npm). Standard commands live in the `Makefile` and `README.md` — prefer those over re-deriving commands.

### Services
- **Backend API** — FastAPI/Uvicorn on port `8000`. Start with `make dev-api`. Serves `/api/v1`; OpenAPI docs at `http://localhost:8000/docs`.
- **Frontend** — Vite dev server on port `5173`. Start with `make dev-web`. Calls `http://localhost:8000/api/v1`.
- **SQLite** — embedded file at `data/app/worldcup.db`; no separate server process.

### Startup notes (non-obvious)
- The startup dependency refresh installed `uv` into `~/.local/bin` (already sourced via `~/.bashrc`). In a non-login shell, run `source "$HOME/.local/bin/env"` if `uv` is not on `PATH`.
- `data/app/` is gitignored, so the SQLite DB is not in the repo. Run `make migrate` once after a fresh checkout to create the schema. (The API also calls `create_all` + seeds from `data/seed/*.csv` on startup, but `make migrate` is the canonical path and applies Alembic migrations.)
- `make dev-api` intentionally sets `WC_SEED_REFRESH_ON_STARTUP=false` and `WC_MARKET_SYNC_ON_STARTUP=false`, so the API runs fully offline using bundled seed CSVs — no external network calls are needed for local dev. A `.env` file is optional; config defaults in `backend/src/world_cup_api/config.py` already point the DB at `data/app/worldcup.db`.
- All external integrations (FIFA calendar API, Attena/Kalshi/Polymarket, API-Football) are optional and disabled in the default dev flow.
- `tesseract-ocr` is only needed for the FIFA PMSR PDF extraction pipeline (optional); not required to run or test the dashboard.

### Test / lint caveats (non-obvious)
- The backend test suite (`make test` / `uv run pytest`) is CPU-heavy (Monte Carlo + hypothesis) and takes ~3–4 minutes; run it in the background rather than blocking on it.
- A handful of backend golden/integration tests (e.g. `test_official_standings`, `test_api`, `test_simulation_coverage`) currently fail because the committed `data/seed/*.csv` reflect a more advanced tournament state than the golden snapshots expect (e.g. Mexico shows 9 pts vs an expected 6). These are pre-existing data-dependent failures, not environment problems.
- `make lint` (backend ruff + frontend eslint) also reports pre-existing errors in the current codebase.
