#!/usr/bin/env python3
"""
Backfill / fix document provenance in the QA portal database.

This is primarily used to re-derive `provenance.source_kind` for documents that
were uploaded with JSON metadata lacking an `metadata.ocr` block.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "packages"))


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(ROOT / ".env")
os.environ.setdefault("DATABASE_PATH", str(ROOT / "data" / "db" / "qa_portal.db"))
os.environ.setdefault("UPLOAD_DIR", str(ROOT / "data" / "uploads"))

from backend.database import get_db  # noqa: E402
from backend.services import blob_store  # noqa: E402
from backend.services.document_provenance import (  # noqa: E402
    backfill_provenance_row,
    deserialize_provenance,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Backfill provenance for portal documents")
    p.add_argument("--limit", type=int, default=0, help="Stop after N documents (0 = all)")
    p.add_argument("--dry-run", action="store_true", help="Derive provenance, but do not update")
    return p


async def count_by_kind(db) -> Counter[str]:
    counts: Counter[str] = Counter()
    async with db.execute("SELECT provenance FROM documents") as cursor:
        rows = await cursor.fetchall()
    for row in rows:
        prov = deserialize_provenance(row["provenance"])
        counts[prov.source_kind if prov else "unknown"] += 1
    return counts


async def main() -> int:
    args = build_parser().parse_args()

    async for db in get_db():
        before = await count_by_kind(db)
        print("Before:", dict(sorted(before.items())), flush=True)

        # Only rows with JSON and a real blob on disk can be re-derived.
        query = """
            SELECT id, pdf_filename, json_filename, total_pages, provenance
            FROM documents
            WHERE json_filename IS NOT NULL AND json_filename != ''
        """
        if args.limit and args.limit > 0:
            query += " LIMIT ?"
            params = (args.limit,)
        else:
            params = ()

        updated = 0
        processed = 0
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        for row in rows:
            processed += 1
            pdf_path = blob_store.blob_path(row["pdf_filename"])
            existing_raw = row["provenance"]

            # `force_native_reinfer=True` means: if JSON lacks `metadata.ocr` and the
            # stored provenance is native-digital, prefer the PDF heuristic.
            if args.dry_run:
                _ = await backfill_provenance_row(
                    db,
                    document_id=row["id"],
                    json_filename=row["json_filename"],
                    total_pages=row["total_pages"],
                    existing_raw=existing_raw,
                    pdf_path=pdf_path,
                    force_native_reinfer=True,
                )
            else:
                proven = await backfill_provenance_row(
                    db,
                    document_id=row["id"],
                    json_filename=row["json_filename"],
                    total_pages=row["total_pages"],
                    existing_raw=existing_raw,
                    pdf_path=pdf_path,
                    force_native_reinfer=True,
                )
                if proven is not None and proven.pages_ocred:
                    # pages_ocred is empty for native-digital.
                    updated += 1

            if processed % 10 == 0:
                print(f"  processed {processed}/{len(rows)}", flush=True)

        if not args.dry_run:
            await db.commit()

        after = await count_by_kind(db)
        print("After:", dict(sorted(after.items())), flush=True)
        if not args.dry_run:
            print(f"Updated (native -> non-native): {updated}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

