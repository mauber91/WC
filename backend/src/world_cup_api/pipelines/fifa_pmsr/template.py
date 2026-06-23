from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from world_cup_api.pipelines.fifa_pmsr.constants import DEFAULT_TEMPLATE_KEY


@dataclass(frozen=True)
class TemplateDefinition:
    key: str
    version: str
    config: dict[str, Any]

    @property
    def pitch_regions(self) -> dict[str, list[float]]:
        return self.config.get("pitch_regions", {})


def load_template(key: str = DEFAULT_TEMPLATE_KEY) -> TemplateDefinition:
    resource = files(__package__).joinpath("templates", f"{key}.json")
    config = json.loads(resource.read_text(encoding="utf-8"))
    return TemplateDefinition(key=config["key"], version=config["version"], config=config)
