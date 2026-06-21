from __future__ import annotations

from collections import Counter

from world_cup_api.pipelines.fifa_pmsr.types import ExtractionBundle, IssueRecord


VALID_CLASSIFICATIONS = {"mapped", "decorative", "unresolved"}


def validate_bundle(bundle: ExtractionBundle) -> list[IssueRecord]:
    issues: list[IssueRecord] = []
    if bundle.manifest.template_key is None:
        issues.append(
            IssueRecord(
                severity="error",
                code="template_not_recognized",
                message="The document does not match a registered FIFA PMSR template",
            )
        )
    if bundle.manifest.page_count != len(bundle.pages):
        issues.append(
            IssueRecord(
                severity="error",
                code="page_count_mismatch",
                message=f"Manifest has {bundle.manifest.page_count} pages but {len(bundle.pages)} were extracted",
            )
        )
    unknown_pages = [page.page_number for page in bundle.pages if page.classification.page_type == "unknown"]
    if unknown_pages:
        issues.append(
            IssueRecord(
                severity="error",
                code="unknown_page_types",
                message=f"Page types are unresolved: {unknown_pages}",
                evidence={"page_numbers": unknown_pages},
            )
        )

    unclassified: list[str] = []
    unresolved: list[str] = []
    for page in bundle.pages:
        for elements in page.payloads.values():
            for element in elements:
                classification = element.get("classification")
                if classification not in VALID_CLASSIFICATIONS:
                    unclassified.append(str(element.get("id", "unknown")))
                elif classification == "unresolved":
                    unresolved.append(str(element.get("id", "unknown")))
    if unclassified:
        issues.append(
            IssueRecord(
                severity="error",
                code="raw_artifact_unclassified",
                message=f"{len(unclassified)} low-level artifacts have no valid classification",
                source_element_ids=unclassified[:100],
            )
        )
    if unresolved:
        issues.append(
            IssueRecord(
                severity="warning",
                code="raw_artifact_unresolved",
                message=f"{len(unresolved)} low-level artifacts require review",
                source_element_ids=unresolved[:100],
                evidence={"total": len(unresolved)},
            )
        )

    required_fields = {
        "official_match_number": bundle.manifest.official_match_number,
        "home_team": bundle.manifest.home_team,
        "away_team": bundle.manifest.away_team,
        "home_score": bundle.manifest.home_score,
        "away_score": bundle.manifest.away_score,
        "match_date": bundle.manifest.match_date,
        "kickoff_time": bundle.manifest.kickoff_time,
        "venue": bundle.manifest.venue,
    }
    missing = [name for name, value in required_fields.items() if value is None]
    if missing:
        issues.append(
            IssueRecord(
                page_number=1,
                severity="error",
                code="match_metadata_missing",
                message=f"Required match metadata was not extracted: {', '.join(missing)}",
                evidence={"missing": missing},
            )
        )

    if len(bundle.participants) < 40:
        issues.append(
            IssueRecord(
                page_number=2,
                severity="error",
                code="lineup_incomplete",
                message=f"Only {len(bundle.participants)} participants were extracted",
            )
        )
    if not bundle.network_edges:
        issues.append(
            IssueRecord(
                severity="error",
                code="passing_network_empty",
                message="No directed passing-network edges were extracted",
            )
        )
    if not bundle.timeseries_points:
        issues.append(
            IssueRecord(
                page_number=31,
                severity="error",
                code="goalkeeper_timeline_empty",
                message="No goalkeeper timeline points were extracted",
            )
        )

    physical = [observation for observation in bundle.observations if observation.metric_key.startswith("physical.")]
    if len(physical) < 100:
        issues.append(
            IssueRecord(
                severity="error",
                code="physical_table_incomplete",
                message=f"Only {len(physical)} physical table values were decoded",
            )
        )
    if bundle.manifest.official_match_number == 29:
        alisson = [
            observation
            for observation in physical
            if observation.metric_key == "physical.total_distance"
            and observation.participant_name == "ALISSON"
        ]
        if not alisson or alisson[0].value_numeric != 5530.5:
            issues.append(
                IssueRecord(
                    page_number=50,
                    severity="error",
                    code="physical_golden_value_failed",
                    message="Alisson total distance did not decode to 5530.5 m",
                )
            )

    return issues


def calculate_quality(bundle: ExtractionBundle) -> tuple[float, float, dict[str, int]]:
    classifications: Counter[str] = Counter()
    for page in bundle.pages:
        for elements in page.payloads.values():
            classifications.update(str(element.get("classification", "missing")) for element in elements)
    total = sum(classifications.values())
    coverage = (classifications["mapped"] + classifications["decorative"]) / total if total else 0.0
    error_count = sum(issue.severity == "error" for issue in bundle.issues)
    warning_count = sum(issue.severity == "warning" for issue in bundle.issues)
    base = 0.55 * bundle.manifest.template_confidence + 0.45 * coverage
    quality = max(0.0, min(1.0, base - 0.08 * error_count - 0.01 * warning_count))
    return round(quality, 4), round(coverage, 4), dict(classifications)
