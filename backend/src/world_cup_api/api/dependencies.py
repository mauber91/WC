from fastapi import Header, HTTPException

from world_cup_api.config import get_settings


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    expected = get_settings().admin_api_key
    if expected and x_admin_key != expected:
        raise HTTPException(status_code=401, detail="A valid X-Admin-Key header is required")
