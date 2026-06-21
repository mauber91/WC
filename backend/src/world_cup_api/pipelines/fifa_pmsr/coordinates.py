from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, hypot

from world_cup_api.pipelines.fifa_pmsr.constants import PITCH_LENGTH_M, PITCH_WIDTH_M


@dataclass(frozen=True)
class PitchTransform:
    bbox: tuple[float, float, float, float]
    attacking_direction: str = "right"

    def point(self, x: float, y: float) -> dict[str, float]:
        x0, y0, x1, y1 = self.bbox
        nx = min(1.0, max(0.0, (x - x0) / (x1 - x0)))
        ny = min(1.0, max(0.0, (y - y0) / (y1 - y0)))
        if self.attacking_direction in {"left", "down"}:
            nx, ny = 1.0 - nx, 1.0 - ny
        return {
            "norm_x": nx,
            "norm_y": ny,
            "pitch_x_m": nx * PITCH_LENGTH_M,
            "pitch_y_m": ny * PITCH_WIDTH_M,
        }

    def line(self, x0: float, y0: float, x1: float, y1: float) -> dict[str, float]:
        start = self.point(x0, y0)
        end = self.point(x1, y1)
        dx = end["pitch_x_m"] - start["pitch_x_m"]
        dy = end["pitch_y_m"] - start["pitch_y_m"]
        return {
            **{f"start_{key}": value for key, value in start.items()},
            **{f"end_{key}": value for key, value in end.items()},
            "length_m": hypot(dx, dy),
            "angle_degrees": degrees(atan2(dy, dx)),
        }


def normalize_page_point(x: float, y: float, width: float, height: float) -> tuple[float, float]:
    return x / width, y / height


def normalize_goal_mouth_point(
    x: float, y: float, bbox: tuple[float, float, float, float]
) -> tuple[float, float]:
    x0, y0, x1, y1 = bbox
    return (
        min(1.0, max(0.0, (x - x0) / (x1 - x0))),
        min(1.0, max(0.0, (y - y0) / (y1 - y0))),
    )
