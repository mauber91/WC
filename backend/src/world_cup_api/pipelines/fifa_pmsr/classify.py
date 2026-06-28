from __future__ import annotations

import re

from world_cup_api.pipelines.fifa_pmsr.teams import ReportTeams
from world_cup_api.pipelines.fifa_pmsr.types import PageClassification


SECTION_BY_TYPE = {
    "in_possession_section": "in_possession",
    "out_of_possession_section": "out_of_possession",
    "goalkeeping_section": "goalkeeping",
    "set_plays_section": "set_plays",
    "individual_in_possession_section": "individual_in_possession",
    "individual_out_of_possession_section": "individual_out_of_possession",
    "individual_physical_section": "individual_physical",
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\x00", "f")).strip()


def classify_page(
    text: str,
    page_number: int,
    page_count: int,
    *,
    teams: ReportTeams | None = None,
) -> PageClassification:
    cleaned = _clean(text)
    low = cleaned.lower()
    compact = re.sub(r"[^a-z]", "", low)
    page_type = "unknown"
    anchors: list[str] = []

    if teams is not None:
        section_headers = (
            ("in_possession_section", "IN POSSESSION teams section", "inpossession"),
            ("out_of_possession_section", "OUT OF POSSESSION teams section", "outofpossession"),
            ("goalkeeping_section", "GOALKEEPING teams section", "goalkeeping"),
            ("set_plays_section", "SET PLAYS teams section", "setplays"),
        )
        for candidate_type, anchor, prefix in section_headers:
            if compact.startswith(teams.compact_header(prefix)):
                page_type, anchors = candidate_type, [anchor]
                break

    rules = [
        ("cover", "post match summary report"),
        ("match_summary_teams", "match summary - teams"),
        ("key_statistics", "match summary - key statistics"),
        ("phases_of_play", "phases of play"),
        ("individual_in_possession_section", "individual data in possession"),
        ("individual_out_of_possession_section", "individual data out of possession"),
        ("individual_physical_section", "individual data physical"),
        ("defensive_pressure", "defensive pressure"),
        ("goalkeeper_involvement", "goalkeeping involvement"),
        ("goalkeeper_distribution", "goalkeeping distribution"),
        ("goal_prevention", "goal prevention"),
        ("aerial_control", "aerial control"),
        ("passing_network", "passing networks"),
        ("crosses", "crosses (open play)"),
        ("offers_to_receive", "ering to receive"),
        ("movement_to_receive", "movement to receive"),
        ("defensive_actions", "defensive actions"),
        ("physical_data", "physical data"),
        ("individual_offers", "in possession - o"),
        ("individual_distribution", "in possession - distributions"),
        ("individual_out_of_possession", "out of possession"),
        ("set_plays", "set plays"),
    ]
    if page_type == "unknown":
        for candidate, anchor in rules:
            if anchor in low:
                page_type = candidate
                anchors.append(anchor)
                break

    if low.startswith("line breaks"):
        page_type = "line_breaks_table" if "direction distribution type" in low else "line_breaks_summary"
        anchors.append("line breaks")
    elif low.startswith("attempts at goal"):
        page_type = "attempts_table" if "time player outcome" in low else "attempts_map"
        anchors.append("attempts at goal")
    elif "line height & team length" in low:
        page_type = "defensive_line_height" if "high block / press" in low else "line_height"
        anchors.append("line height & team length")

    if not cleaned and page_number == page_count:
        page_type = "closing_artwork"
        anchors.append("last blank-text page")

    section = SECTION_BY_TYPE.get(page_type)
    if section is None:
        if page_number in range(6, 24):
            section = "in_possession"
        elif page_number in range(25, 30):
            section = "out_of_possession"
        elif page_number in range(31, 38):
            section = "goalkeeping"
        elif page_number in range(39, 41):
            section = "set_plays"
        elif page_number in range(42, 46):
            section = "individual_in_possession"
        elif page_number in range(47, 49):
            section = "individual_out_of_possession"
        elif page_number in range(50, 52):
            section = "individual_physical"

    confidence = 0.99 if anchors and page_type != "unknown" else 0.0
    return PageClassification(
        page_type=page_type,
        section=section,
        team_scope=teams.matches_scope(cleaned) if teams is not None else None,
        confidence=confidence,
        matched_anchors=anchors,
    )
