# World Cup Forecast

Local-first World Cup 2026 standings, prediction, and Monte Carlo simulation dashboard. The backend implements FIFA's May 2026 head-to-head tiebreak rules and uses the complete 495-option Annexe C matrix for third-place Round-of-32 assignments.

## Run locally

Requirements: Python 3.13 with `uv`, and Node 20 or newer.

```bash
make setup
make migrate
make dev-api
```

In a second terminal:

```bash
make dev-web
```

Open `http://localhost:5173`. API documentation is at `http://localhost:8000/docs`.

## Data status

The bundled seed uses FIFA's published 2026 draw, official match schedule, FIFA rankings (2026-06-11 edition), World Football Elo ratings, group-stage results through 2026-06-20 (with conduct columns where FIFA reports exist), and pre-match bookmaker/prediction-market snapshots for remaining fixtures. Regenerate seed CSVs with `make seed-data` after importing newer fixtures, rankings, results, or market data through the admin page.

Accepted CSV datasets and required columns are documented in `docs/data-contracts/csv.md`.

### Live prediction markets (Polymarket + Kalshi)

Upcoming fixture odds can be refreshed from [Attena](https://www.attena.xyz/) search (`https://attena-api.fly.dev/api/search/`). The sync builds queries from team names and kickoff dates, maps Attena hits to 1X2 selections, and enriches incomplete Kalshi brackets via the public Kalshi trade API.

```bash
make sync-markets                         # all upcoming group fixtures
make sync-markets -- --match-number 33    # single fixture
```

Or via admin API: `POST /api/v1/admin/markets/sync?match_number=33` (requires `WC_ADMIN_API_KEY`).

Market sync also runs automatically on API startup when `WC_MARKET_SYNC_ENABLED=true` (default). Set it to `false` to skip live fetches during local development or tests.

### Automated tournament refresh

During the tournament the API keeps itself current without manual imports:

- **Results** — fetched daily (and on startup) from FIFA's public calendar API (`WC_FIFA_API_BASE`), applied to the DB, and merged into seed CSVs via `make seed-data` logic
- **Markets** — synced from Attena/Kalshi every `WC_MARKET_SYNC_INTERVAL_MINUTES` (default 30), including on startup

Configure scheduling with:

```bash
WC_SEED_REFRESH_ENABLED=true          # daily results refresh (06:00 UTC)
WC_SEED_REFRESH_HOUR_UTC=6
WC_SEED_REGENERATE_CSVS=true        # rewrite data/seed/*.csv after new results
WC_MARKET_SYNC_INTERVAL_MINUTES=30
WC_ENABLE_SCHEDULER=true
```

Manual triggers:

```bash
curl -X POST "http://localhost:8000/api/v1/admin/tournament/refresh" -H "X-Admin-Key: $WC_ADMIN_API_KEY"
curl -X POST "http://localhost:8000/api/v1/admin/markets/sync" -H "X-Admin-Key: $WC_ADMIN_API_KEY"
```

## Verification

```bash
make test
make lint
make build
make benchmark
```

Simulation runs freeze their inputs, model/rules/engine versions, seed, and content hash. Aggregate counts are stored; individual trials are not.

## Architecture

- React/Vite frontend with TanStack Query and Recharts.
- FastAPI application with SQLAlchemy 2 and Alembic.
- SQLite WAL mode with one application scheduler.
- APScheduler launches deterministic process-parallel Monte Carlo chunks.
- RQ/Redis and PostgreSQL are deferred until multi-instance deployment is required.
