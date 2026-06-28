from __future__ import annotations

from world_cup_api.pipelines.fifa_pmsr.classify import classify_page
from world_cup_api.pipelines.fifa_pmsr.inspect import _cover_fields
from world_cup_api.pipelines.fifa_pmsr.teams import ReportTeams


def test_report_teams_compact_header() -> None:
    teams = ReportTeams(home_team="Mexico", away_team="South Africa")
    assert teams.compact_header("inpossession") == "inpossessionmexicovsouthafrica"


def test_cover_fields_parse_team_name_adjacent_to_score() -> None:
    fields = _cover_fields("Mexico2 - 0\nSouth Africa\nGroup A - Match 1\n11 June 2026")
    assert fields["home_team"] == "Mexico"
    assert fields["away_team"] == "South Africa"
    assert fields["home_score"] == 2
    assert fields["away_score"] == 0


def test_classify_page_uses_manifest_teams_for_section_headers() -> None:
    teams = ReportTeams(home_team="Mexico", away_team="South Africa")
    result = classify_page("IN POSSESSION\nMexico v South Africa", 5, 52, teams=teams)
    assert result.page_type == "in_possession_section"
