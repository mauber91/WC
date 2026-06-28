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


def test_cover_fields_parse_unicode_team_names_and_venue() -> None:
    cover = (
        "Australia 2 - 0\nTürkiye\nGroup D - Match 6\n13 June 2026\n"
        "21:00 Kick Of\nBC Place Vancouver\nPOST MATCH SUMMARY REPORT"
    )
    fields = _cover_fields(cover)
    assert fields["home_team"] == "Australia"
    assert fields["away_team"] == "Türkiye"
    assert fields["venue"] == "BC Place Vancouver"

    cover_ci = "Côte d'Ivoire 1 - 0\nEcuador\nGroup E - Match 9\n14 June 2026"
    fields_ci = _cover_fields(cover_ci)
    assert fields_ci["home_team"] == "Côte d'Ivoire"
    assert fields_ci["away_team"] == "Ecuador"


def test_classify_page_falls_back_to_section_prefix_without_team_header() -> None:
    result = classify_page("IN POSSESSION\nAustraliav\nTürkiye", 5, 52)
    assert result.page_type == "in_possession_section"


def test_classify_page_uses_manifest_teams_for_section_headers() -> None:
    teams = ReportTeams(home_team="Mexico", away_team="South Africa")
    result = classify_page("IN POSSESSION\nMexico v South Africa", 5, 52, teams=teams)
    assert result.page_type == "in_possession_section"
