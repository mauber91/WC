from __future__ import annotations

import re
import unicodedata


def team_slug(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")


def team_ref_matches(team_name: str, fifa_code: str, ref: str) -> bool:
    lowered = ref.lower().strip()
    return lowered == team_slug(team_name) or lowered == fifa_code.lower()
