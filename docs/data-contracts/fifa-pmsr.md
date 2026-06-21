# FIFA PMSR extraction contract

The `world_cup_api.pipelines.fifa_pmsr` package extracts the FIFA 2026 post-match summary report template into lossless source artifacts and normalized analytical datasets. It is deliberately template-specific: a new layout must be registered and tested instead of silently using approximate page-number rules.

## Commands

```text
world-cup-report inspect FILE
world-cup-report extract FILE --output DIRECTORY [--template auto]
world-cup-report ingest FILE [--force] [--dry-run]
world-cup-report batch DIRECTORY --glob "*.pdf" --workers 4
world-cup-report validate DOCUMENT_ID
world-cup-report export DOCUMENT_ID --format jsonl|parquet [--output DIRECTORY]
```

`inspect` hashes the file and detects its template without writing to the database. `extract` writes a versioned artifact directory. `ingest` copies the source to a content-addressed raw path, extracts it, and loads one transaction. A completed run with the same source hash, pipeline version, and template version is reused unless `--force` is supplied.

The required Tesseract 5 executable must be on `PATH` for targeted numeric-cell OCR fallback. The supported template normally decodes physical data from a deterministic private-use font map, so full-page OCR is never used.

## Artifact layout

```text
data/raw/match_reports/{pdf_sha256}.pdf
data/processed/match_reports/{sha256_prefix}/fifa-pmsr-v1/
├── extraction.json
├── audit.html
├── font-maps.json
├── renders/page-001.png
└── images/page-...      # extracted embedded image streams
```

Each raw element has a stable page-scoped ID and exactly one classification:

- `mapped`: preserved in a processable raw or semantic representation.
- `decorative`: preserved but deliberately excluded from football metrics.
- `unresolved`: preserved with evidence and added to the review queue.

No low-level element may lack a classification. Coverage is `(mapped + decorative) / all elements`.

## Normalized datasets

The database migration adds these tables:

- `match_report_documents` and `match_report_extraction_runs`: source identity, versions, status, quality, and immutable run history.
- `match_report_pages` and `match_report_page_payloads`: rendered page metadata plus complete glyph, text-span, vector, image, and table-cell arrays.
- `match_report_participants`: report identities linked to application teams/squad players when possible.
- `match_report_metric_definitions` and `match_report_observations`: typed match/team/player/table values; explicit zero and blank are separate flags.
- `match_report_events`: timestamped and/or spatial attempts, crosses, substitutions, card markers, pressures, regains, goalkeeper actions, and other events.
- `match_report_spatial_features`: formation points/summaries, polygons, extents, and other geometries.
- `match_report_network_edges`: directed source-player/target-player pass counts and shares.
- `match_report_timeseries_points`: calibrated period/minute/value series.
- `match_report_issues`: unresolved extraction evidence and invariant failures.

Every normalized row stores its source page, extraction method, confidence, source bounding box or element IDs, and versioned extraction run.

## Coordinate spaces

Spatial records retain four representations where applicable:

1. Original PDF coordinates in points, with top-left origin for page geometry.
2. Page-normalized coordinates in `[0, 1]`.
3. Canonical pitch coordinates in metres on a `105 × 68` pitch.
4. Pitch-normalized coordinates in `[0, 1]`.

Teams shown attacking left/down are rotated 180 degrees so normalized analysis always attacks toward `x=105`. `attacking_direction` and the original direction remain explicit. Goal-mouth targets use a separate `[0, 1] × [0, 1]` coordinate space and are linked to their numbered pitch origins.

## Visual mappings

| Source visual | Stored representation |
| --- | --- |
| Formation | Player points, role band, attacking direction, centroid, width, depth, line spacing |
| Numbered shot maps | Linked pitch origin and goal-mouth target, event number, player, minute, outcome, body part |
| Marker maps | One event per vector marker with category/color and canonical pitch point |
| Cross/GK arrows | Raw and normalized endpoints, length, angle, outcome color, endpoint-direction confidence |
| Line/team extents | Raw/normalized/canonical polygons plus width/depth attributes |
| Passing matrix | Directed edge, pass count, share, source/target participant links |
| Goalkeeper timeline | Calibrated match second/minute and involvement value |
| Physical glyphs | Numeric observation using a font-checksum registry; targeted OCR only as fallback |
| Tables | Original table cells plus typed observations; null and explicit zero stay distinct |
| Artwork | Raw image/vector payload marked decorative |

Labeled values are authoritative. Vector geometry is retained even when a text label supplies the final numeric value, allowing reconciliation and future reprocessing.

## Promotion and review

- Confidence `>= 0.95`: eligible for automatic promotion.
- Confidence `0.80–0.95`: promoted only when required invariants pass.
- Confidence `< 0.80`: retained with evidence but not considered analytical truth.

The extraction run is `completed` only when required match metadata, page classification, lineups, pass networks, physical values, timelines, and raw coverage invariants pass. Otherwise it is `needs_review`. Failed semantic promotion never removes the lossless raw payload.

Open `audit.html` to review every rendered page, page classifier, payload counts, confidence, and issue. Use `world-cup-report validate DOCUMENT_ID` for the persisted invariant result.

## Python interface

```python
from world_cup_api.pipelines.fifa_pmsr import (
    export_document,
    extract_report,
    ingest_report,
    inspect_report,
    load_extraction,
)
```

The functions return Pydantic models. `load_extraction(session, bundle)` participates in the caller's transaction; `ingest_report` owns its transaction and rolls back the complete load on error.
