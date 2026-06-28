from __future__ import annotations

from world_cup_api.pipelines.fifa_pmsr.extractors.core import CoreExtraction, _extract_key_statistics
from world_cup_api.pipelines.fifa_pmsr.teams import ReportTeams
from world_cup_api.pipelines.fifa_pmsr.types import PageClassification, RawPage


def test_key_statistics_use_manifest_team_names() -> None:
    page = RawPage(
        page_number=3,
        width_points=960,
        height_points=540,
        rotation=0,
        raw_text=(
            "Match Summary - Key Statistics\n"
            "Total 57.1% 6.7% 36.1% Total\n"
            "xG Expected Goals          1.78          0.10"
        ),
        render_uri="/tmp/page.png",
        render_sha256="abc",
        classification=PageClassification(page_type="key_statistics", confidence=0.99),
        payloads={},
    )
    teams = ReportTeams(home_team="Mexico", away_team="South Africa")
    result = CoreExtraction()
    _extract_key_statistics(page, result, teams)
    by_team = {observation.team_source_name: observation.value_numeric for observation in result.observations}
    assert by_team["Mexico"] == 57.1
    assert by_team["South Africa"] == 36.1
