"""Audit that every portal document has a readable PDF under UPLOAD_DIR.

Emits a JSON report with per-document status:
  ok | missing_file | unreadable | url_mismatch

Optional ``--source`` lists export folders that lack a usable PDF as
``out_of_scope`` findings (no PDF available for portal sync to copy).

Usage:
  python -m backend.audit_pdf_serving
  python -m backend.audit_pdf_serving --check-url http://localhost:8000
  python -m backend.audit_pdf_serving --source /path/to/acts-export --out report.json

If the local DB is empty, bootstrap via seed or sync first:
  python -m backend.sync_acts --source /path/to/acts-export
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend import runtime
from backend.database import (
    DATABASE_URL,
    DatabaseConnection,
    DatabaseRow,
    database_connection,
    init_db,
)
from backend.services.pdf_service import get_pdf_page_count

OUT_OF_SCOPE = "out_of_scope"
STATUSES = ("ok", "missing_file", "unreadable", "url_mismatch", OUT_OF_SCOPE)


def _usable_path(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def discover_source_pdf_gaps(source: Path) -> List[Dict[str, Any]]:
    """Folders under ``source`` that cannot supply a PDF for portal sync."""

    source = source.expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Source directory does not exist: {source}")

    findings: List[Dict[str, Any]] = []
    for directory in sorted(source.iterdir(), key=lambda item: item.name.casefold()):
        if not directory.is_dir() or directory.is_symlink():
            continue
        pdfs = [
            path
            for path in directory.glob("*.pdf")
            if path.is_file() and not path.is_symlink()
        ]
        if not pdfs:
            findings.append(
                {
                    "status": OUT_OF_SCOPE,
                    "source_key": directory.name,
                    "reason": "no_pdf_in_sync_source",
                    "pdf_path": None,
                }
            )
            continue
        usable = [path for path in pdfs if _usable_path(path)]
        if not usable:
            findings.append(
                {
                    "status": OUT_OF_SCOPE,
                    "source_key": directory.name,
                    "reason": "empty_or_unusable_pdf_in_sync_source",
                    "pdf_path": str(pdfs[0]),
                }
            )
    return findings


def check_uploads_url(base_url: str, pdf_filename: str) -> Optional[str]:
    """Return an error string when /uploads/{filename} is not reachable, else None."""

    url = f"{base_url.rstrip('/')}/uploads/{urllib.parse.quote(pdf_filename)}"
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = getattr(response, "status", None) or response.getcode()
            if status >= 400:
                return f"HTTP {status} for {url}"
            length = response.headers.get("Content-Length")
            if length is not None and int(length) == 0:
                return f"empty Content-Length for {url}"
            return None
    except urllib.error.HTTPError as error:
        # Some StaticFiles stacks reject HEAD; fall back to a ranged GET.
        if error.code in {405, 501}:
            get_request = urllib.request.Request(
                url,
                method="GET",
                headers={"Range": "bytes=0-0"},
            )
            try:
                with urllib.request.urlopen(get_request, timeout=10) as response:
                    status = getattr(response, "status", None) or response.getcode()
                    if status >= 400:
                        return f"HTTP {status} for {url}"
                    return None
            except Exception as fallback_error:  # noqa: BLE001
                return f"{type(fallback_error).__name__}: {fallback_error}"
        return f"HTTP {error.code} for {url}"
    except Exception as error:  # noqa: BLE001
        return f"{type(error).__name__}: {error}"


async def audit_documents(
    db: DatabaseConnection,
    *,
    check_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    # Read at call time: binding runtime.UPLOAD_DIR at import made the audit look at
    # the real uploads directory even when the caller had pointed it elsewhere.
    upload_dir = Path(runtime.UPLOAD_DIR)
    rows: List[DatabaseRow] = []
    async with db.execute(
        """
        SELECT id, name, pdf_filename, total_pages, source_type, source_key
        FROM documents
        ORDER BY lower(name), name
        """
    ) as cursor:
        rows = await cursor.fetchall()

    results: List[Dict[str, Any]] = []
    for row in rows:
        pdf_filename = row["pdf_filename"] or ""
        entry: Dict[str, Any] = {
            "document_id": row["id"],
            "name": row["name"],
            "source_type": row["source_type"],
            "source_key": row["source_key"],
            "pdf_filename": pdf_filename,
            "db_total_pages": row["total_pages"],
            "upload_path": str(upload_dir / pdf_filename) if pdf_filename else None,
            "status": "ok",
            "detail": None,
            "page_count": None,
            "size_bytes": None,
        }

        if not pdf_filename:
            entry["status"] = "missing_file"
            entry["detail"] = "documents.pdf_filename is empty"
            results.append(entry)
            continue

        path = upload_dir / pdf_filename
        if not path.exists():
            entry["status"] = "missing_file"
            entry["detail"] = f"file not found under UPLOAD_DIR: {path}"
            results.append(entry)
            continue

        try:
            size = path.stat().st_size
        except OSError as error:
            entry["status"] = "unreadable"
            entry["detail"] = f"stat failed: {error}"
            results.append(entry)
            continue

        entry["size_bytes"] = size
        if size <= 0:
            entry["status"] = "unreadable"
            entry["detail"] = "file size is 0"
            results.append(entry)
            continue

        page_count = get_pdf_page_count(str(path))
        entry["page_count"] = page_count
        if page_count < 1:
            entry["status"] = "unreadable"
            entry["detail"] = "get_pdf_page_count returned < 1"
            results.append(entry)
            continue

        if check_url:
            url_error = check_uploads_url(check_url, pdf_filename)
            if url_error:
                entry["status"] = "url_mismatch"
                entry["detail"] = url_error
                results.append(entry)
                continue

        entry["status"] = "ok"
        results.append(entry)

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.audit_pdf_serving",
        description=(
            "Check every portal DB document's pdf_filename under UPLOAD_DIR "
            "for existence, non-zero size, and readable page count."
        ),
        epilog=(
            "Repair: re-run ``python -m backend.sync_acts --source <export>`` "
            "(add ``--force`` if hashes match but uploads were wiped). "
            "Acts with no PDF in the export appear as out_of_scope when "
            "``--source`` is provided."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--check-url",
        metavar="BASE",
        help="Optional API base URL to HEAD/GET /uploads/{pdf_filename}",
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="Optional Acts-Discovery export root; list folders lacking a PDF",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Write the full JSON report to this path (also printed to stdout)",
    )
    parser.add_argument(
        "--failures-only",
        action="store_true",
        help="Omit ok rows from the documents list in the report",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    await init_db()
    async with database_connection() as db:
        documents = await audit_documents(db, check_url=args.check_url)

    out_of_scope: List[Dict[str, Any]] = []
    if args.source:
        out_of_scope = discover_source_pdf_gaps(args.source)

    status_counts: Counter[str] = Counter(item["status"] for item in documents)
    for item in out_of_scope:
        status_counts[item["status"]] += 1

    listed = (
        [item for item in documents if item["status"] != "ok"]
        if args.failures_only
        else documents
    )

    report = {
        "database": DATABASE_URL.rsplit("@", 1)[-1],
        "upload_dir": runtime.UPLOAD_DIR,
        "document_count": len(documents),
        "status_counts": {status: status_counts.get(status, 0) for status in STATUSES},
        "documents": listed,
        "out_of_scope": out_of_scope,
        "sync_hint": (
            "python -m backend.sync_acts --source <acts-export-dir> "
            "[--force]"
        ),
    }

    payload = json.dumps(report, indent=2, ensure_ascii=False)
    print(payload)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")

    portal_failures = sum(
        status_counts.get(status, 0)
        for status in ("missing_file", "unreadable", "url_mismatch")
    )
    return 1 if portal_failures else 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        return asyncio.run(_run(args))
    except SystemExit:
        raise
    except Exception as error:  # noqa: BLE001
        print(f"PDF serving audit failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
