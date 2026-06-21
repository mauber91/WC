from __future__ import annotations

import pytest

from world_cup_api.pipelines.fifa_pmsr.coordinates import PitchTransform, normalize_goal_mouth_point
from world_cup_api.pipelines.fifa_pmsr.extractors.core import decode_pua_number


def test_pitch_transform_normalizes_rightward_attack() -> None:
    transform = PitchTransform((10, 20, 110, 220), attacking_direction="right")
    point = transform.point(60, 120)
    assert point["norm_x"] == pytest.approx(0.5)
    assert point["norm_y"] == pytest.approx(0.5)
    assert point["pitch_x_m"] == pytest.approx(52.5)
    assert point["pitch_y_m"] == pytest.approx(34)


def test_pitch_transform_rotates_opposite_attack() -> None:
    transform = PitchTransform((0, 0, 100, 100), attacking_direction="left")
    point = transform.point(20, 30)
    assert point["norm_x"] == pytest.approx(0.8)
    assert point["norm_y"] == pytest.approx(0.7)


def test_goal_mouth_coordinates_are_clamped() -> None:
    assert normalize_goal_mouth_point(150, 25, (100, 0, 200, 50)) == (0.5, 0.5)
    assert normalize_goal_mouth_point(250, -5, (100, 0, 200, 50)) == (1.0, 0.0)


def test_fifa_private_use_font_digits_decode() -> None:
    assert decode_pua_number("\ue076\ue076\ue074\ue071\ue094\ue076") == 5530.5
    assert decode_pua_number("unmapped") is None
