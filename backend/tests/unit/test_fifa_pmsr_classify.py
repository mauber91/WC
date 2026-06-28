from __future__ import annotations

import pytest

from world_cup_api.pipelines.fifa_pmsr.classify import classify_page
from world_cup_api.pipelines.fifa_pmsr.teams import ReportTeams


TEAMS = ReportTeams(home_team="Brazil", away_team="Haiti")


@pytest.mark.parametrize(
    ("text", "page_number", "expected"),
    [
        ("POST MATCH SUMMARY REPORT", 1, "cover"),
        ("Match Summary - Key Statistics\nCompleted Line Breaks", 3, "key_statistics"),
        ("IN POSSESSION\nBrazilvHaiti", 5, "in_possession_section"),
        ("Line Breaks Brazil\nDirection Distribution Type", 10, "line_breaks_table"),
        ("Defensive Actions Brazil\nAttempts at Goal", 25, "defensive_actions"),
        ("Goalkeeping Distribution Brazil\nCompleted Line Breaks", 32, "goalkeeper_distribution"),
        ("In Possession - Distributions Brazil\nLine Breaks Attempted", 42, "individual_distribution"),
        ("", 52, "closing_artwork"),
    ],
)
def test_template_page_classifier(text: str, page_number: int, expected: str) -> None:
    assert classify_page(text, page_number, 52, teams=TEAMS).page_type == expected
