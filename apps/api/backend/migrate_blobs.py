"""Move existing flat uploads into content-addressed blob storage.

Before: ``uploads/<uuid>_<original name>.pdf`` -- one copy per document row, so the same
source PDF re-uploaded under a new document was stored again, and every JSON fix meant
shipping the PDF with it.

After: ``uploads/pdf/<sha256>.pdf`` and ``uploads/json/<sha256>.json``, with
``documents.pdf_filename`` / ``documents.json_filename`` / ``document_versions.json_filename``
holding that relative name. The ``/uploads`` static mount serves subpaths already, so
the URLs the frontend builds keep working.

Idempotent: a second run finds everything already addressed and reports ``0 moved``.

    python -m backend.migrate_blobs --dry-run
    python -m backend.migrate_blobs
    python -m backend.migrate_blobs --prune-orphans
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import aiosqlite

from backend import database
from backend.database import init_db
from backend.services import blob_store


def _kind(name: str) -> str:
    return "json" if name.lower().endswith(".json") else "pdf"


async def _rows(db: aiosqlite.Connection) -> List[dict]:
    """Every (table, column, id, filename) the migration has to consider."""
    collected: List[dict] = []
    async with db.execute(
        "SELECT id, pdf_filename, json_filename FROM documents"
    ) as cursor:
        for row in await cursor.fetchall():
            for column in ("pdf_filename", "json_filename"):
                if row[column]:
                    collected.append(
                        {
                            "table": "documents",
                            "column": column,
                            "id": row["id"],
                            "name": row[column],
                        }
                    )
    async with db.execute(
        "SELECT id, json_filename, json_sha256 FROM document_versions"
    ) as cursor:
        for row in await cursor.fetchall():
            if row["json_filename"]:
                collected.append(
                    {
                        "table": "document_versions",
                        "column": "json_filename",
                        "id": row["id"],
                        "name": row["json_filename"],
                        "sha256": row["json_sha256"],
                    }
                )
    return collected


async def migrate(dry_run: bool = False, prune_orphans: bool = False) -> Dict[str, object]:
    upload_root = Path(blob_store.upload_root())
    report: Dict[str, object] = {
        "upload_dir": str(upload_root),
        "dry_run": dry_run,
        "already_addressed": 0,
        "moved": 0,
        "deduped": 0,
        "bytes_reclaimed": 0,
        "missing": [],
        "orphans": [],
        "pruned": 0,
    }
    if not upload_root.is_dir():
        report["missing"] = ["upload directory does not exist"]
        return report

    # Resolved at call time, not import time: the test sandbox monkeypatches it.
    async with aiosqlite.connect(database.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")
        rows = await _rows(db)

        # A legacy name may be shared by a document and its backfilled version 1, so
        # hash each distinct source file once and reuse the result.
        resolved: Dict[str, Optional[str]] = {}
        digests: Dict[str, str] = {}
        seen: set = set()
        for entry in rows:
            name = entry["name"]
            if blob_store.is_blob_name(name):
                report["already_addressed"] = int(report["already_addressed"]) + 1
                continue
            if name in resolved:
                continue
            source = upload_root / name
            if not blob_store.usable(source):
                resolved[name] = None
                report["missing"].append(name)  # type: ignore[union-attr]
                continue
            digest = blob_store.sha256_file(source)
            digests[name] = digest
            target = blob_store.rel_name(_kind(name), digest)
            # `seen` matters for --dry-run, where nothing is written and the on-disk
            # check alone would count every duplicate as a fresh move.
            if target in seen or blob_store.usable(blob_store.blob_path(target)):
                # Another row already contributed these exact bytes.
                report["deduped"] = int(report["deduped"]) + 1
                report["bytes_reclaimed"] = int(report["bytes_reclaimed"]) + source.stat().st_size
            else:
                seen.add(target)
                report["moved"] = int(report["moved"]) + 1
                if not dry_run:
                    blob_store.store_file(source, _kind(name))
            resolved[name] = target

        if not dry_run:
            for entry in rows:
                target = resolved.get(entry["name"])
                if target is None:
                    continue
                await db.execute(
                    f"UPDATE {entry['table']} SET {entry['column']} = ? WHERE id = ?",
                    (target, entry["id"]),
                )
                if entry["table"] == "document_versions" and not entry.get("sha256"):
                    await db.execute(
                        "UPDATE document_versions SET json_sha256 = ? WHERE id = ?",
                        (digests.get(entry["name"], ""), entry["id"]),
                    )
            await db.commit()

            # The originals are only removed once every row points at the new name.
            for name, target in resolved.items():
                if target and blob_store.usable(blob_store.blob_path(target)):
                    try:
                        (upload_root / name).unlink()
                    except OSError:
                        pass

        # Anything left in the store that no row references. Both the legacy name and
        # the address it maps to count as referenced -- otherwise --dry-run, where
        # nothing has moved yet, would report every file in the store as an orphan.
        referenced = set()
        for entry in rows:
            referenced.add(entry["name"])
            referenced.add(resolved.get(entry["name"]))
        referenced.discard(None)
        for path in sorted(upload_root.rglob("*")):
            if not path.is_file() or path.name == ".gitkeep":
                continue
            relative = str(path.relative_to(upload_root))
            if relative in referenced:
                continue
            report["orphans"].append(relative)  # type: ignore[union-attr]
            if prune_orphans and not dry_run:
                try:
                    path.unlink()
                    report["pruned"] = int(report["pruned"]) + 1
                except OSError:
                    pass

    orphans = report["orphans"]
    assert isinstance(orphans, list)
    report["orphans"] = orphans[:50]
    report["orphan_count"] = len(orphans)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument(
        "--prune-orphans",
        action="store_true",
        help="delete stored files that no document or version references",
    )
    args = parser.parse_args()

    async def _run():
        await init_db()
        return await migrate(dry_run=args.dry_run, prune_orphans=args.prune_orphans)

    report = asyncio.run(_run())
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["missing"]:
        print(
            f"WARNING: {len(report['missing'])} referenced file(s) are missing from "
            f"{report['upload_dir']}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
