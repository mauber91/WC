from __future__ import annotations

import os
from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    db_path = Path(config.rootpath) / ".pytest_cache" / "worldcup_test.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # SQLite WAL sidecars outlive the main file after interrupted/repeated test
    # runs. Removing only the database can leave a mismatched shared-memory file
    # and produce a misleading "disk I/O error" during application startup.
    for candidate in (db_path, Path(f"{db_path}-shm"), Path(f"{db_path}-wal")):
        if candidate.exists():
            candidate.unlink()
    os.environ["WC_DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["WC_MARKET_SYNC_ENABLED"] = "false"
    os.environ["WC_SEED_REFRESH_ENABLED"] = "false"
    os.environ["WC_ENABLE_SCHEDULER"] = "false"
    from world_cup_api.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
def db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from world_cup_api.db.models import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
