"""Scan portal DB sections for structural parse-quality failures.

Upstream Acts-Discovery must emit real <table> / <sup class=\"cite\"> markup;
re-sync via ``backend.sync_acts`` or JSON replace clears flags when structure is fixed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from typing import Any, Dict, List, Optional

from backend.database import DatabaseConnection, database_connection, init_db
from backend.services.parse_quality import (
    assess_section_quality,
    deserialize_quality_flags,
)


async def _resolve_document_id(
    db: DatabaseConnection,
    document: Optional[str],
) -> Optional[str]:
    if not document:
        return None
    async with db.execute(
        "SELECT id FROM documents WHERE id = ?",
        (document,),
    ) as cursor:
        row = await cursor.fetchone()
    if row:
        return row["id"]
    async with db.execute(
        "SELECT id FROM documents WHERE name LIKE ? ORDER BY uploaded_at DESC LIMIT 1",
        (f"%{document}%",),
    ) as cursor:
        row = await cursor.fetchone()
    if row:
        return row["id"]
    raise SystemExit(f"No document matching id/name: {document!r}")


async def scan_sections(
    db: DatabaseConnection,
    *,
    document_id: Optional[str] = None,
    reassess: bool = False,
) -> List[Dict[str, Any]]:
    """Return ranked offender rows (most flags first)."""

    query = """
        SELECT
            s.id AS section_id,
            s.document_id,
            d.name AS document_name,
            s.source_key,
            s.section_code,
            s.section_heading,
            s.start_page,
            s.end_page,
            s.review_status,
            s.html_content,
            s.plain_text,
            s.quality_flags
        FROM sections s
        JOIN documents d ON d.id = s.document_id
    """
    params: tuple = ()
    if document_id:
        query += " WHERE s.document_id = ?"
        params = (document_id,)
    query += " ORDER BY s.sort_order ASC"

    offenders: List[Dict[str, Any]] = []
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()

    for row in rows:
        if reassess:
            flags = assess_section_quality(
                html_content=row["html_content"] or "",
                plain_text=row["plain_text"] or "",
                section_heading=row["section_heading"] or "",
            )
        else:
            flags = deserialize_quality_flags(row["quality_flags"])
            if not flags and (
                row["html_content"] or row["plain_text"]
            ):
                # Older rows may lack stored flags — compute on the fly.
                flags = assess_section_quality(
                    html_content=row["html_content"] or "",
                    plain_text=row["plain_text"] or "",
                    section_heading=row["section_heading"] or "",
                )
        if not flags:
            continue
        offenders.append(
            {
                "document_id": row["document_id"],
                "document_name": row["document_name"],
                "section_id": row["section_id"],
                "source_key": row["source_key"],
                "section_code": row["section_code"],
                "section_heading": (row["section_heading"] or "")[:80],
                "pages": f"{row['start_page']}-{row['end_page']}",
                "review_status": row["review_status"],
                "flag_count": len(flags),
                "flags": flags,
                "flag_codes": [f["code"] for f in flags],
            }
        )

    offenders.sort(
        key=lambda item: (-item["flag_count"], item["document_name"], item["pages"])
    )
    return offenders


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.audit_parse_quality",
        description=(
            "Scan QA Portal section HTML for structural parse-quality failures "
            "(missing tables, footnote glue, wall-of-text, heading bleed)."
        ),
        epilog=(
            "Upstream note: Acts-Discovery must fix tables/footnotes in the export. "
            "After a corrected JSON is available, re-sync with backend.sync_acts "
            "(or replace JSON) so quality_flags clear when structure is fixed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--document",
        "-d",
        help="Limit to one document by id or name substring",
    )
    parser.add_argument(
        "--reassess",
        action="store_true",
        help="Recompute heuristics from stored HTML (ignore stored quality_flags)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print machine-readable JSON instead of a ranked table",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max offenders to print (0 = all)",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    await init_db()
    async with database_connection() as db:
        document_id = await _resolve_document_id(db, args.document)
        offenders = await scan_sections(
            db,
            document_id=document_id,
            reassess=args.reassess,
        )

    if args.limit and args.limit > 0:
        offenders = offenders[: args.limit]

    code_counts: Counter[str] = Counter()
    for item in offenders:
        code_counts.update(item["flag_codes"])

    if args.as_json:
        print(
            json.dumps(
                {
                    "offender_count": len(offenders),
                    "flag_totals": dict(code_counts),
                    "offenders": offenders,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print(f"Parse-quality offenders: {len(offenders)}")
    if code_counts:
        print(
            "Flag totals: "
            + ", ".join(f"{code}={count}" for code, count in sorted(code_counts.items()))
        )
    print()
    for item in offenders:
        codes = ",".join(item["flag_codes"])
        print(
            f"[{item['flag_count']}] {codes}  "
            f"{item['document_name']}  "
            f"{item['section_code'] or '—'} · {item['section_heading']!r}  "
            f"pages {item['pages']}  "
            f"status={item['review_status']}  "
            f"key={item['source_key']}"
        )
        for flag in item["flags"]:
            print(f"      - {flag['code']}: {flag['reason']}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        return asyncio.run(_run(args))
    except SystemExit:
        raise
    except Exception as error:
        print(f"Audit failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
