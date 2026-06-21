from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WC_",
        env_file=ENV_FILE,
        extra="ignore",
    )

    app_name: str = "World Cup Forecast"
    database_url: str = f"sqlite:///{ROOT_DIR / 'data' / 'app' / 'worldcup.db'}"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    admin_api_key: str | None = None
    enable_scheduler: bool = True
    simulation_max_workers: int = 4
    attena_api_base: str = "https://attena-api.fly.dev/api/search/"
    kalshi_api_base: str = "https://api.elections.kalshi.com/trade-api/v2"
    polymarket_gamma_api_base: str = "https://gamma-api.polymarket.com"
    kalshi_wc_winner_event: str = "KXMENWORLDCUP-26"
    market_sync_enabled: bool = True
    market_sync_on_startup: bool = True
    seed_refresh_enabled: bool = True
    seed_refresh_on_startup: bool = True
    seed_regenerate_csvs: bool = True
    seed_refresh_hour_utc: int = 6
    seed_refresh_minute_utc: int = 0
    market_sync_interval_minutes: int = 30
    fifa_api_base: str = "https://api.fifa.com/api/v3"
    api_football_key: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
