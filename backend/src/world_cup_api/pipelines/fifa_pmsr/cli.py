from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Sequence

from world_cup_api.config import ROOT_DIR
from world_cup_api.db.session import SessionLocal
from world_cup_api.pipelines.fifa_pmsr.db_validation import validate_document
from world_cup_api.pipelines.fifa_pmsr.export import export_document
from world_cup_api.pipelines.fifa_pmsr.extract import extract_report
from world_cup_api.pipelines.fifa_pmsr.inspect import inspect_report
from world_cup_api.pipelines.fifa_pmsr.loader import load_extraction
from world_cup_api.pipelines.fifa_pmsr.service import ingest_report
from world_cup_api.pipelines.fifa_pmsr.types import ExtractionBundle


DEFAULT_ARTIFACT_ROOT = ROOT_DIR / "data" / "processed" / "match_reports"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="world-cup-report", description="Extract FIFA PMSR match reports")
    subcommands = parser.add_subparsers(dest="command", required=True)

    inspect_command = subcommands.add_parser("inspect", help="Inspect and identify a report")
    inspect_command.add_argument("file", type=Path)

    extract_command = subcommands.add_parser("extract", help="Extract to lossless and normalized artifacts")
    extract_command.add_argument("file", type=Path)
    extract_command.add_argument("--output", type=Path, required=True)
    extract_command.add_argument("--template", default="auto")

    ingest_command = subcommands.add_parser("ingest", help="Extract and load into the application database")
    ingest_command.add_argument("file", type=Path)
    ingest_command.add_argument("--force", action="store_true")
    ingest_command.add_argument("--dry-run", action="store_true")

    batch_command = subcommands.add_parser("batch", help="Extract PDFs concurrently and load sequentially")
    batch_command.add_argument("directory", type=Path)
    batch_command.add_argument("--glob", default="*.pdf")
    batch_command.add_argument("--workers", type=int, default=4)

    validate_command = subcommands.add_parser("validate", help="Validate a stored document")
    validate_command.add_argument("document_id")

    export_command = subcommands.add_parser("export", help="Export a stored document")
    export_command.add_argument("document_id")
    export_command.add_argument("--format", choices=("jsonl", "parquet"), required=True)
    export_command.add_argument("--output", type=Path)
    return parser


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _batch_extract(path: str) -> str:
    bundle = extract_report(path, DEFAULT_ARTIFACT_ROOT)
    return str(Path(bundle.artifact_root) / "extraction.json")


def _run_batch(directory: Path, pattern: str, workers: int) -> int:
    files = sorted(directory.expanduser().resolve().glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files match {pattern!r} in {directory}")
    extracted: list[Path] = []
    failures: list[dict[str, str]] = []
    with ProcessPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_batch_extract, str(path)): path for path in files}
        for future in as_completed(futures):
            source = futures[future]
            try:
                extracted.append(Path(future.result()))
            except Exception as exc:
                failures.append({"file": str(source), "error": str(exc)})
    loaded: list[dict[str, object]] = []
    with SessionLocal() as session:
        for artifact in extracted:
            bundle = ExtractionBundle.model_validate_json(artifact.read_text(encoding="utf-8"))
            run = load_extraction(session, bundle)
            session.commit()
            loaded.append({"file": bundle.manifest.source_path, "document_id": run.document_id, "run_id": run.id})
    _print({"loaded": loaded, "failures": failures})
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "inspect":
            _print(inspect_report(args.file).model_dump(mode="json"))
        elif args.command == "extract":
            bundle = extract_report(args.file, args.output, template=args.template)
            _print(
                {
                    "status": bundle.status,
                    "artifact_root": bundle.artifact_root,
                    "quality_score": bundle.quality_score,
                    "coverage": bundle.coverage,
                    "stats": bundle.stats,
                    "issues": [issue.model_dump(mode="json") for issue in bundle.issues],
                }
            )
        elif args.command == "ingest":
            with SessionLocal() as session:
                _print(
                    ingest_report(
                        session,
                        args.file,
                        force=args.force,
                        dry_run=args.dry_run,
                    ).model_dump(mode="json")
                )
        elif args.command == "batch":
            return _run_batch(args.directory, args.glob, args.workers)
        elif args.command == "validate":
            with SessionLocal() as session:
                _print(validate_document(session, args.document_id))
        elif args.command == "export":
            output = args.output or ROOT_DIR / "data" / "processed" / "match_reports" / args.document_id / "exports" / args.format
            with SessionLocal() as session:
                files = export_document(session, args.document_id, output, args.format)
            _print({"document_id": args.document_id, "format": args.format, "files": [str(path) for path in files]})
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
