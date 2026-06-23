from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from world_cup_api.config import ROOT_DIR

RAW_DIR = ROOT_DIR / "data" / "raw"
DEFAULT_HEADERS = {
    "User-Agent": "world-cup-forecast/0.1",
    "Accept": "application/json",
}


def fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    retries: int = 4,
    pause_seconds: float = 1.0,
) -> Any:
    merged = {**DEFAULT_HEADERS, **(headers or {})}
    last_error: Exception | None = None
    for attempt in range(retries):
        request = Request(url, headers=merged)
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(pause_seconds * (attempt + 1))
    raise RuntimeError(f"Request failed for {url}: {last_error}") from last_error


def load_cache(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_cache(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
