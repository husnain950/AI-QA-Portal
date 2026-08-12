"""Import a converted Acts corpus into runtime storage, as versions.

Two source layouts are understood:

``--acts-repo PATH``
    The Acts_fbr pipeline repository itself. The corpus is ``output/*.json`` (its
    ``_provisional/``, ``_refused/`` and ``_run/`` directories are subdirectories, so the
    glob already excludes them) and each JSON names its own PDF in
    ``metadata.filename``, which is resolved against ``Acts/**``. This mirrors
    ``Acts_fbr/scripts/audit_all.py:source_for`` -- deliberately, so the portal and the
    pipeline agree on which PDF a JSON came from. PDFs are detected by magic bytes
    because six source files carry no ``.pdf`` suffix.

``--source PATH``
    One directory per Act, each holding exactly one PDF and one JSON.

Re-running is cheap and safe: the PDF is content-addressed and never rewritten, and a
JSON whose bytes are unchanged produces no new version. When the pipeline is fixed, the
new JSON lands as the next version and reviewer findings are carried across it -- see
``backend.services.document_store.apply_parsed_document``.
"""

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiosqlite

from backend.database import DB_PATH
from backend.runtime import (  # noqa: F401  (tests patch these)
    UPLOAD_DIR,
    bootstrap_runtime,
)
from backend.services import blob_store, versions
from backend.services.document_store import STRICT, SUPERSEDE, ReviewConflict
from backend.services.json_parser import parse_json_document
from backend.services.pdf_service import get_pdf_page_count

SOURCE_TYPE = "acts_corpus"
PDF_MAGIC = b"%PDF-"


@dataclass(frozen=True)
class ExportPair:
    source_key: str
    pdf_path: Path
    json_path: Path


@dataclass
class ValidatedPair:
    pair: ExportPair
    document_id: str
    source_hash: str
    pdf_hash: str
    json_hash: str
    total_pages: int
    sections: List[dict]
    footnotes: List[dict]
    issues: List[str] = field(default_factory=list)


def is_pdf(path: Path) -> bool:
    """Magic-byte test. Six corpus sources have no ``.pdf`` extension."""
    try:
        with path.open("rb") as handle:
            return handle.read(len(PDF_MAGIC)) == PDF_MAGIC
    except OSError:
        return False


def discover_pairs(source: Path) -> List[ExportPair]:
    """One directory per Act, each with exactly one PDF and one JSON."""
    source = source.expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Source directory does not exist: {source}")

    pairs: List[ExportPair] = []
    failures: List[str] = []
    for directory in sorted(source.iterdir(), key=lambda item: item.name.casefold()):
        if not directory.is_dir():
            continue
        if directory.is_symlink():
            failures.append(f"{directory.name}: symbolic-link directories are not allowed")
            continue
        pdfs = sorted(directory.glob("*.pdf"), key=lambda item: item.name.casefold())
        json_files = sorted(
            directory.glob("*.json"),
            key=lambda item: item.name.casefold(),
        )
        if len(pdfs) != 1 or len(json_files) != 1:
            failures.append(
                f"{directory.name}: expected one PDF and one JSON "
                f"(found {len(pdfs)} PDF, {len(json_files)} JSON)"
            )
            continue
        if pdfs[0].is_symlink() or json_files[0].is_symlink():
            failures.append(f"{directory.name}: symbolic-link source files are not allowed")
            continue
        pairs.append(
            ExportPair(
                source_key=directory.name,
                pdf_path=pdfs[0].resolve(),
                json_path=json_files[0].resolve(),
            )
        )

    if failures:
        raise ValueError("; ".join(failures))
    if not pairs:
        raise ValueError(f"No complete export pairs found in {source}")
    return pairs


def _source_pdf_index(root: Path, pdf_dir: Optional[Path]) -> Dict[str, Path]:
    """Every source PDF in a pipeline repository, indexed by basename.

    ``Acts_fbr`` keeps its sources under ``Acts/``; the Income Tax Ordinance pipeline
    keeps them beside ``output/`` in a differently named folder. Rather than hardcode
    either, search from the given directory (or the repository root), skipping
    ``output/`` -- which holds converted JSON, not sources -- and any nested directory
    that is itself a pipeline repository, so scanning ``CC-FBR/`` does not drag in
    ``CC-FBR/Acts_fbr/Acts/``.
    """
    search_root = pdf_dir if pdf_dir is not None else (
        root / "Acts" if (root / "Acts").is_dir() else root
    )
    if not search_root.is_dir():
        raise ValueError(f"PDF directory does not exist: {search_root}")

    by_name: Dict[str, Path] = {}
    stack = [search_root]
    while stack:
        directory = stack.pop()
        for entry in sorted(directory.iterdir()):
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in {"output", ".git", "__pycache__", "node_modules"}:
                    continue
                if entry != search_root and (entry / "output").is_dir():
                    continue  # a nested pipeline repository owns its own sources
                stack.append(entry)
            elif entry.is_file() and is_pdf(entry):
                by_name.setdefault(entry.name, entry)
    return by_name


def discover_acts_repo(
    root: Path, pdf_dir: Optional[Path] = None
) -> Tuple[List[ExportPair], List[str]]:
    """Pair ``output/*.json`` with its source PDF.

    Returns ``(pairs, unmatched)``. A JSON whose PDF cannot be found is reported, never
    guessed at: the mapping is by exact ``metadata.filename``, which resolves both live
    corpora, so a miss means something really is wrong upstream.
    """
    root = root.expanduser().resolve()
    output_dir = root / "output"
    if not output_dir.is_dir():
        raise ValueError(f"Not a pipeline repository (no output/): {root}")

    by_name = _source_pdf_index(root, pdf_dir)

    pairs, unmatched = [], []
    for json_path in sorted(output_dir.glob("*.json"), key=lambda p: p.name.casefold()):
        try:
            metadata = json.loads(json_path.read_text(encoding="utf-8")).get("metadata") or {}
        except (ValueError, OSError) as error:
            unmatched.append(f"{json_path.name}: unreadable ({error})")
            continue
        wanted = metadata.get("filename")
        if not wanted:
            unmatched.append(f"{json_path.name}: no metadata.filename to resolve a PDF")
            continue
        pdf_path = by_name.get(wanted)
        if pdf_path is None:
            unmatched.append(f"{json_path.name}: no PDF named {wanted!r} under Acts/")
            continue
        pairs.append(
            ExportPair(
                source_key=json_path.stem,
                pdf_path=pdf_path.resolve(),
                json_path=json_path.resolve(),
            )
        )

    if not pairs:
        raise ValueError(f"No corpus JSON matched a source PDF in {root}")
    return pairs, unmatched


def hash_file(path: Path) -> str:
    return blob_store.sha256_file(path)


def deterministic_document_id(source_key: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"pdf-qa-portal:{SOURCE_TYPE}:{source_key}",
        )
    )


def _page_range_issues(sections: List[dict], total_pages: int) -> List[str]:
    """Report leaves the parser flagged as having impossible page ranges.

    The flag itself is minted in ``parse_quality.assess_page_range`` so that every
    ingest path carries it; this only surfaces the same finding on the sync's stderr,
    and cross-checks the JSON's declared page count against the actual PDF.
    """
    issues: List[str] = []
    for section in sections:
        reasons = [
            flag["reason"]
            for flag in (section.get("quality_flags") or [])
            if flag.get("code") == "page_range_out_of_bounds"
        ]
        end = section.get("end_page")
        if not reasons and isinstance(end, int) and end > total_pages:
            # The JSON's own metadata.total_pages disagreed with the real PDF.
            reason = f"Declared end page {end} is past the PDF's {total_pages} pages."
            section.setdefault("quality_flags", []).append(
                {"code": "page_range_out_of_bounds", "reason": reason}
            )
            reasons = [reason]
        label = section.get("section_code") or section["source_key"]
        issues.extend(f"{label}: {reason}" for reason in reasons)
    return issues


def validate_pair(pair: ExportPair) -> ValidatedPair:
    """Parse and check one pair. Raises only on defects that make it unreviewable."""
    document_id = deterministic_document_id(pair.source_key)
    json_content = pair.json_path.read_text(encoding="utf-8")
    sections, footnotes = parse_json_document(json_content, document_id=document_id)
    if not sections:
        raise ValueError(f"{pair.source_key}: JSON has no reviewable sections")

    total_pages = get_pdf_page_count(str(pair.pdf_path))
    if total_pages < 1:
        raise ValueError(f"{pair.source_key}: PDF has no readable pages")

    source_keys = [section["source_key"] for section in sections]
    if len(source_keys) != len(set(source_keys)):
        raise ValueError(f"{pair.source_key}: duplicate section source keys")

    issues = _page_range_issues(sections, total_pages)

    pdf_hash = hash_file(pair.pdf_path)
    json_hash = hash_file(pair.json_path)
    source_hash = hashlib.sha256(
        f"{pdf_hash}:{json_hash}".encode("ascii")
    ).hexdigest()
    return ValidatedPair(
        pair=pair,
        document_id=document_id,
        source_hash=source_hash,
        pdf_hash=pdf_hash,
        json_hash=json_hash,
        total_pages=total_pages,
        sections=sections,
        footnotes=footnotes,
        issues=issues,
    )


async def sync_validated_pair(
    db: aiosqlite.Connection,
    validated: ValidatedPair,
    force: bool = False,
    mode: str = SUPERSEDE,
    note: Optional[str] = None,
    corpus_origin: Optional[str] = None,
) -> str:
    from backend.services.corpus_lanes import classify_lane

    pair = validated.pair
    async with db.execute(
        "SELECT * FROM documents WHERE source_type = ? AND source_key = ?",
        (SOURCE_TYPE, pair.source_key),
    ) as cursor:
        existing_row = await cursor.fetchone()
    existing = dict(existing_row) if existing_row else None
    document_id = existing["id"] if existing else validated.document_id

    pdf_filename = blob_store.rel_name("pdf", validated.pdf_hash)
    pdf_stored = blob_store.usable(blob_store.blob_path(pdf_filename))

    if (
        existing
        and existing.get("source_hash") == validated.source_hash
        and pdf_stored
        and blob_store.usable(blob_store.blob_path(existing["json_filename"]))
        and not force
        and existing.get("corpus_lane")
    ):
        return "skipped"

    # The PDF is immutable and shared; storing it is idempotent and outside the
    # transaction on purpose, so a rolled-back version does not orphan a needed file.
    # Both writes also repair a truncated blob left by an interrupted run -- the
    # unchanged-hash fast path above would otherwise skip such a document forever.
    repaired = False
    if not pdf_stored:
        blob_store.store_file(pair.pdf_path, "pdf")
        repaired = existing is not None

    previous_pdf = existing["pdf_filename"] if existing else None
    json_bytes = pair.json_path.read_bytes()
    json_filename = blob_store.rel_name("json", blob_store.sha256_bytes(json_bytes))
    if not blob_store.usable(blob_store.blob_path(json_filename)):
        blob_store.store_bytes(json_bytes, "json")
        repaired = repaired or existing is not None

    corpus_lane = classify_lane(
        pair.source_key,
        source_type=SOURCE_TYPE,
        corpus_origin=corpus_origin,
    )

    await db.execute("BEGIN IMMEDIATE")
    try:
        # Approved AI fixes ride on top of whatever the pipeline produced. The
        # overlay store also detects the two ways a fix can die: the parser now
        # agrees with it (superseded) or the parser changed the leaf on its own
        # (stale — never silently overwritten, the section is re-flagged below).
        from backend.services import overlays

        json_bytes, overlay_report = await overlays.apply_overlays(
            db, validated.pdf_hash, json_bytes
        )
        if existing:
            await db.execute(
                """
                UPDATE documents
                SET name = ?, pdf_filename = ?, total_pages = ?, source_hash = ?,
                    corpus_lane = ?
                WHERE id = ?
                """,
                (
                    pair.source_key,
                    pdf_filename,
                    validated.total_pages,
                    validated.source_hash,
                    corpus_lane,
                    document_id,
                ),
            )
        else:
            await db.execute(
                """
                INSERT INTO documents (
                    id, name, pdf_filename, json_filename, total_sections,
                    total_pages, uploaded_at, status, source_type, source_key,
                    source_hash, corpus_lane
                ) VALUES (?, ?, ?, '', 0, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (
                    document_id,
                    pair.source_key,
                    pdf_filename,
                    validated.total_pages,
                    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    SOURCE_TYPE,
                    pair.source_key,
                    validated.source_hash,
                    corpus_lane,
                ),
            )

        _row, outcome = await versions.create_version(
            db,
            document_id,
            json_bytes,
            source_name=pair.json_path.name,
            note=note or f"Synced from {pair.json_path.parent.name}/{pair.json_path.name}",
            created_by="sync_acts",
            mode=mode,
        )
        if overlay_report.stale:
            await overlays.flag_stale_sections(
                db, document_id, overlay_report.stale
            )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    if previous_pdf and previous_pdf != pdf_filename:
        await blob_store.unlink_if_unreferenced(db, previous_pdf)

    if outcome["status"] == "unchanged":
        return "updated" if repaired else "skipped"
    return "updated" if existing else "added"


async def run_sync(
    source: Path,
    dry_run: bool = False,
    force: bool = False,
    acts_repo: bool = False,
    strict: bool = False,
    metrics_dir: Optional[Path] = None,
    pdf_dir: Optional[Path] = None,
    corpus_origin: Optional[str] = None,
) -> Dict[str, object]:
    if acts_repo:
        pairs, unmatched = discover_acts_repo(source, pdf_dir)
    else:
        pairs, unmatched = discover_pairs(source), []

    summary: Dict[str, object] = {
        "discovered": len(pairs),
        "validated": 0,
        "added": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "unmatched": len(unmatched),
        "flagged_pages": 0,
        "sections": 0,
        "footnotes": 0,
        "pdf_pages": 0,
        "problems": [],
    }
    problems: List[str] = list(unmatched)
    for line in unmatched:
        print(f"UNMATCHED {line}", file=sys.stderr)

    validated_pairs: List[ValidatedPair] = []
    for pair in pairs:
        try:
            validated = validate_pair(pair)
        except Exception as error:
            summary["failed"] = int(summary["failed"]) + 1
            problems.append(f"{pair.source_key}: {error}")
            print(f"ERROR {pair.source_key}: {error}", file=sys.stderr)
            continue
        validated_pairs.append(validated)
        summary["validated"] = int(summary["validated"]) + 1
        summary["sections"] = int(summary["sections"]) + len(validated.sections)
        summary["footnotes"] = int(summary["footnotes"]) + len(validated.footnotes)
        summary["pdf_pages"] = int(summary["pdf_pages"]) + validated.total_pages
        if validated.issues:
            summary["flagged_pages"] = int(summary["flagged_pages"]) + len(validated.issues)
            for issue in validated.issues:
                print(f"FLAG {pair.source_key}: {issue}", file=sys.stderr)

    # A defective edition no longer holds the other seventy-nine hostage. --strict
    # restores the all-or-nothing behaviour for CI.
    if dry_run or (strict and (summary["failed"] or unmatched)):
        summary["problems"] = problems
        return summary

    await bootstrap_runtime()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")
        for validated in validated_pairs:
            try:
                result = await sync_validated_pair(
                    db,
                    validated,
                    force=force,
                    mode=STRICT if strict else SUPERSEDE,
                    corpus_origin=corpus_origin,
                )
                summary[result] = int(summary[result]) + 1
            except ReviewConflict as conflict:
                summary["failed"] = int(summary["failed"]) + 1
                problems.append(f"{validated.pair.source_key}: {conflict}")
                print(f"CONFLICT {validated.pair.source_key}: {conflict}", file=sys.stderr)
            except Exception as error:
                summary["failed"] = int(summary["failed"]) + 1
                problems.append(f"{validated.pair.source_key}: {error}")
                print(f"ERROR {validated.pair.source_key}: {error}", file=sys.stderr)

        if metrics_dir is not None:
            from backend.services import acts_metrics

            summary["metrics"] = await acts_metrics.ingest(db, metrics_dir)
            await db.commit()

        # Corpus-wide seam: variants → detectors → optional OCR disagreements.
        try:
            from backend.services.findings_store import run_detectors_and_store
            from backend.services.variants import rebuild

            summary["variants"] = await rebuild(db)
            summary["findings"] = await run_detectors_and_store(db, seed_flags=True)
            await db.commit()
        except Exception as error:
            summary["detector_error"] = str(error)
            print(f"DETECTORS {error}", file=sys.stderr)

        if metrics_dir is not None:
            ocr_reports_dir = metrics_dir if metrics_dir.is_dir() else source / "reports"
            if ocr_reports_dir.is_dir():
                try:
                    from backend.services import ocr_ingest

                    summary["ocr_findings"] = await ocr_ingest.ingest_ocr_findings(
                        db, ocr_reports_dir
                    )
                    await db.commit()
                except Exception as ocr_err:
                    print(f"OCR ingest failed (non-fatal): {ocr_err}", file=sys.stderr)
                    summary["ocr_findings"] = {"error": str(ocr_err)}

    summary["problems"] = problems
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync a converted Acts corpus into the PDF-QA Portal",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--acts-repo",
        type=Path,
        help="Acts_fbr pipeline repository (uses output/*.json + Acts/**)",
    )
    group.add_argument(
        "--source",
        type=Path,
        help="Directory containing one folder per exported Act or edition",
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        help=(
            "Where the source PDFs live. Defaults to <repo>/Acts when present, "
            "otherwise the repository root (skipping output/ and nested pipelines)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the complete corpus without writing files or database rows",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-apply pairs even when source_hash and files are unchanged",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Abort the whole run on any validation problem, and refuse an ingest that "
            "would supersede reviewer state (the pre-versioning behaviour)"
        ),
    )
    parser.add_argument(
        "--metrics",
        nargs="?",
        const="",
        metavar="DIR",
        help=(
            "Ingest pipeline QA reports after syncing. Defaults to <repo>/reports; "
            "see backend.services.acts_metrics for the expected files"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.acts_repo or args.source
    metrics_dir = None
    if args.metrics is not None:
        metrics_dir = Path(args.metrics) if args.metrics else root / "reports"
    try:
        summary = asyncio.run(
            run_sync(
                root,
                dry_run=args.dry_run,
                force=args.force,
                acts_repo=args.acts_repo is not None,
                strict=args.strict,
                metrics_dir=metrics_dir,
                pdf_dir=args.pdf_dir,
            )
        )
    except Exception as error:
        print(f"Sync failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 1 if summary["failed"] or (args.strict and summary["unmatched"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
