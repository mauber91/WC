from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

import pytest

from world_cup_api.pipelines.fifa_pmsr.extract import extract_report


DEFAULT_SAMPLE = Path("/Users/mberlanga/Documents/wcreports/PMSR-M29-BRA-V-HAI.pdf")


@pytest.fixture(scope="module")
def pmsr_bundle(tmp_path_factory: pytest.TempPathFactory):
    sample = Path(os.getenv("PMSR_SAMPLE_PDF", DEFAULT_SAMPLE))
    if not sample.exists():
        pytest.skip("Set PMSR_SAMPLE_PDF to run the FIFA PMSR golden extraction")
    return extract_report(sample, tmp_path_factory.mktemp("pmsr-artifacts"))


def test_supplied_report_is_losslessly_classified(pmsr_bundle) -> None:
    assert pmsr_bundle.status == "completed"
    assert pmsr_bundle.quality_score >= 0.95
    assert pmsr_bundle.coverage == 1
    assert len(pmsr_bundle.pages) == 52
    assert all(page.classification.page_type != "unknown" for page in pmsr_bundle.pages)
    assert pmsr_bundle.stats["raw_elements"] > 40_000
    assert pmsr_bundle.stats.get("raw_unresolved", 0) == 0


def test_match_metadata_lineups_and_formations(pmsr_bundle) -> None:
    manifest = pmsr_bundle.manifest
    assert (manifest.official_match_number, manifest.home_team, manifest.away_team) == (29, "Brazil", "Haiti")
    assert (manifest.home_score, manifest.away_score) == (3, 0)
    assert (manifest.match_date, manifest.kickoff_time, manifest.venue) == (
        "19 June 2026",
        "20:30",
        "Philadelphia Stadium",
    )
    assert len(pmsr_bundle.participants) == 52
    formation_players = [feature for feature in pmsr_bundle.spatial_features if feature.feature_type == "formation_player"]
    assert Counter(feature.team_source_name for feature in formation_players) == {"Brazil": 11, "Haiti": 11}
    assert all(0 <= feature.canonical_geometry["coordinates"][0] <= 105 for feature in formation_players)
    assert all(0 <= feature.canonical_geometry["coordinates"][1] <= 68 for feature in formation_players)
    assert any(event.event_type == "substitution" for event in pmsr_bundle.events)
    assert any(event.event_type == "card" for event in pmsr_bundle.events)


def test_statistics_networks_spatial_events_and_physical_values(pmsr_bundle) -> None:
    possession = {
        observation.team_source_name: observation.value_numeric
        for observation in pmsr_bundle.observations
        if observation.metric_key == "summary.possession"
    }
    assert possession == {"Brazil": 49, "Haiti": 43.2}
    assert len(pmsr_bundle.network_edges) > 200
    assert {edge.team_source_name for edge in pmsr_bundle.network_edges} == {"Brazil", "Haiti"}
    event_counts = Counter(event.event_type for event in pmsr_bundle.events)
    assert event_counts["attempt_spatial"] == 14
    assert event_counts["cross"] == 14
    assert event_counts["pressure"] >= 480
    assert len(pmsr_bundle.timeseries_points) >= 190
    alisson = [
        observation.value_numeric
        for observation in pmsr_bundle.observations
        if observation.participant_name == "ALISSON"
        and observation.metric_key == "physical.total_distance"
    ]
    assert alisson == [5530.5]
