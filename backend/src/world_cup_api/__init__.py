"""World Cup 2026 prediction and simulation API."""

from world_cup_api.main import app

__all__ = ["app"]


def main() -> None:
    import uvicorn

    uvicorn.run("world_cup_api.main:app", host="127.0.0.1", port=8000, reload=True)
