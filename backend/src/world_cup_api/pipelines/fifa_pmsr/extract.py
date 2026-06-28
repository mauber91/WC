from __future__ import annotations

from pathlib import Path

from world_cup_api.pipelines.fifa_pmsr.audit import write_audit_report
from world_cup_api.pipelines.fifa_pmsr.constants import PIPELINE_VERSION
from world_cup_api.pipelines.fifa_pmsr.extractors import extract_core_semantics, extract_visual_semantics
from world_cup_api.pipelines.fifa_pmsr.extractors.core import PUA_DIGIT_MAP
from world_cup_api.pipelines.fifa_pmsr.fontmap import write_font_map_registry
from world_cup_api.pipelines.fifa_pmsr.inspect import inspect_report
from world_cup_api.pipelines.fifa_pmsr.raw import extract_raw_pages
from world_cup_api.pipelines.fifa_pmsr.teams import ReportTeams
from world_cup_api.pipelines.fifa_pmsr.template import load_template
from world_cup_api.pipelines.fifa_pmsr.types import ExtractionBundle
from world_cup_api.pipelines.fifa_pmsr.validate import calculate_quality, validate_bundle


PUA_TYPOGRAPHY_MAP = {
    "\ue081": "(",
    "\ue082": ")",
    "\ue088": "-",
    "\ue092": ":",
    "\ue09d": "+",
}


def _resolve_known_glyphs(bundle: ExtractionBundle) -> None:
    glyph_map = {**PUA_DIGIT_MAP, **PUA_TYPOGRAPHY_MAP}
    for page in bundle.pages:
        for glyph in page.payloads.get("glyphs", []):
            text = str(glyph.get("text", ""))
            if text and all(character in glyph_map for character in text):
                glyph["classification"] = "mapped"
                glyph["mapped_by"] = "fifa_pmsr_font_map"
                glyph["decoded_text"] = "".join(glyph_map[character] for character in text)


def _stats(bundle: ExtractionBundle) -> dict[str, int]:
    return {
        "pages": len(bundle.pages),
        "raw_elements": sum(page.element_count for page in bundle.pages),
        "participants": len(bundle.participants),
        "observations": len(bundle.observations),
        "events": len(bundle.events),
        "spatial_features": len(bundle.spatial_features),
        "network_edges": len(bundle.network_edges),
        "timeseries_points": len(bundle.timeseries_points),
        "issues": len(bundle.issues),
    }


def extract_report(
    path: str | Path,
    artifact_root: str | Path,
    template: str = "auto",
) -> ExtractionBundle:
    manifest = inspect_report(path)
    if template != "auto" and manifest.template_key != template:
        raise ValueError(f"Document matched {manifest.template_key!r}, not requested template {template!r}")
    definition = load_template(manifest.template_key or "fifa_pmsr_2026")
    root = Path(artifact_root).expanduser().resolve() / manifest.sha256[:16] / PIPELINE_VERSION
    root.mkdir(parents=True, exist_ok=True)
    teams = ReportTeams.from_manifest(manifest.home_team, manifest.away_team)
    pages = extract_raw_pages(path, root, teams=teams)
    core = extract_core_semantics(pages, teams=teams)
    visual = extract_visual_semantics(pages, core.attempt_details, core.participants, teams=teams)
    bundle = ExtractionBundle(
        manifest=manifest,
        pipeline_version=PIPELINE_VERSION,
        template_version=definition.version,
        artifact_root=str(root),
        pages=pages,
        participants=core.participants,
        observations=core.observations,
        events=core.events + visual.events,
        spatial_features=visual.spatial_features,
        network_edges=core.network_edges,
        timeseries_points=visual.timeseries_points,
        issues=core.issues + visual.issues,
    )
    _resolve_known_glyphs(bundle)
    bundle.issues.extend(validate_bundle(bundle))
    bundle.quality_score, bundle.coverage, raw_counts = calculate_quality(bundle)
    has_errors = any(issue.severity == "error" for issue in bundle.issues)
    invariants_pass = not has_errors
    if bundle.quality_score >= 0.95 and invariants_pass:
        bundle.status = "completed"
    elif bundle.quality_score >= 0.80 and invariants_pass:
        bundle.status = "completed"
    else:
        bundle.status = "needs_review"
    bundle.stats = {**_stats(bundle), **{f"raw_{key}": value for key, value in raw_counts.items()}}
    write_font_map_registry(pages, root / "font-maps.json")
    bundle.write_json(root / "extraction.json")
    write_audit_report(bundle, root / "audit.html")
    return bundle
