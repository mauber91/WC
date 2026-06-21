.PHONY: setup dev-api dev-web test lint build migrate benchmark report-inspect report-extract report-ingest

setup:
	cd backend && uv sync
	cd frontend && npm install

dev-api:
	cd backend && WC_SEED_REFRESH_ON_STARTUP=false WC_MARKET_SYNC_ON_STARTUP=false \
		uv run uvicorn world_cup_api.main:app --reload --reload-dir src --port 8000

dev-web:
	cd frontend && npm run dev

migrate:
	cd backend && uv run alembic upgrade head

seed-data:
	cd backend && uv run python ../scripts/build_official_seed.py

squad-data:
	cd backend && uv run python ../scripts/sync_squad_data.py --skip-injuries

squad-data-full:
	cd backend && uv run python ../scripts/sync_squad_data.py

squad-season-25-26:
	cd backend && uv run python ../scripts/sync_squad_season.py --season 25-26

squad-season-24-25:
	cd backend && uv run python ../scripts/sync_squad_season.py --season 24-25

squad-season-23-24:
	cd backend && uv run python ../scripts/sync_squad_season.py --season 23-24

squad-season-status:
	cd backend && uv run python ../scripts/sync_squad_season.py --status

sync-markets:
	cd backend && uv run python ../scripts/sync_markets.py

publish:
	cd backend && uv run python ../scripts/publish.py $(ARGS)

deploy-fly:
	chmod +x scripts/deploy_fly.sh
	./scripts/deploy_fly.sh $(ARGS)

deploy-pages:
	chmod +x scripts/deploy_pages.sh
	./scripts/deploy_pages.sh $(ARGS)

refresh-tournament:
	cd backend && uv run python ../scripts/refresh_tournament.py

test:
	cd backend && uv run pytest -q
	cd frontend && npm test -- --run

lint:
	cd backend && uv run ruff check src tests
	cd frontend && npm run lint

build:
	cd frontend && npm run build

benchmark:
	cd backend && uv run python scripts/benchmark_simulation.py

report-inspect:
	cd backend && uv run world-cup-report inspect "$(FILE)"

report-extract:
	cd backend && uv run world-cup-report extract "$(FILE)" --output ../data/processed/match_reports

report-ingest:
	cd backend && uv run world-cup-report ingest "$(FILE)"
