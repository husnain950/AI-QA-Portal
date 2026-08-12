"""JSON version history for a document whose PDF never changes.

The PDF is the fixed thing being reviewed; the parse of it is what the pipeline keeps
correcting. So a document owns one PDF and an ordered list of JSON versions, exactly one
of which is active. Blobs are content-addressed and immutable, which makes "did this
JSON actually change?" a hash comparison and makes an old version's file safe to keep.

Callers own the transaction: nothing here commits.
"""

from __future__ import annotations

import difflib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

from backend.services import blob_store
from backend.services.document_provenance import (
    derive_from_json_content,
    serialize_provenance,
)
from backend.services.document_store import (
    SUPERSEDE,
    apply_parsed_document,
    document_status,
)
from backend.services.json_parser import parse_json_document

DIFF_CONTEXT_LINES = 2
MAX_DIFF_LINES = 400


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _version_id(document_id: str, version_no: int) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"pdf-qa-portal:version:{document_id}:{version_no}",
        )
    )


async def active_version(
    db: aiosqlite.Connection, document_id: str
) -> Optional[aiosqlite.Row]:
    async with db.execute(
        "SELECT * FROM document_versions WHERE document_id = ? AND is_active = 1",
        (document_id,),
    ) as cursor:
        return await cursor.fetchone()


async def list_versions(
    db: aiosqlite.Connection, document_id: str
) -> List[aiosqlite.Row]:
    async with db.execute(
        """
        SELECT * FROM document_versions
        WHERE document_id = ?
        ORDER BY version_no DESC
        """,
        (document_id,),
    ) as cursor:
        return list(await cursor.fetchall())


async def get_version(
    db: aiosqlite.Connection, document_id: str, version_id: str
) -> Optional[aiosqlite.Row]:
    async with db.execute(
        "SELECT * FROM document_versions WHERE document_id = ? AND id = ?",
        (document_id, version_id),
    ) as cursor:
        return await cursor.fetchone()


async def _ensure_hash(db: aiosqlite.Connection, row: aiosqlite.Row) -> str:
    """Backfilled v1 rows carry no hash until their blob is first read.

    Filling it lazily keeps the migration free of file IO while still making the
    "identical JSON is a no-op" check work from the very first re-sync.
    """
    if row["json_sha256"]:
        return row["json_sha256"]
    path = blob_store.blob_path(row["json_filename"])
    if not blob_store.usable(path):
        return ""
    digest = blob_store.sha256_file(path)
    await db.execute(
        "UPDATE document_versions SET json_sha256 = ? WHERE id = ?",
        (digest, row["id"]),
    )
    return digest


def read_version_json(row) -> str:
    path = blob_store.blob_path(row["json_filename"])
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


async def create_version(
    db: aiosqlite.Connection,
    document_id: str,
    json_bytes: bytes,
    *,
    source_name: Optional[str] = None,
    note: Optional[str] = None,
    created_by: Optional[str] = None,
    mode: str = SUPERSEDE,
) -> Tuple[aiosqlite.Row, Dict[str, Any]]:
    """Store a JSON as the document's next version and make it active.

    Returns ``(version_row, outcome)``. ``outcome['status']`` is ``'unchanged'`` when
    the bytes match the active version -- re-running a sync must not manufacture
    versions that say nothing.
    """
    digest = blob_store.sha256_bytes(json_bytes)
    current = await active_version(db, document_id)
    if current is not None and await _ensure_hash(db, current) == digest:
        return current, {"status": "unchanged", "version_no": current["version_no"]}

    # Parse before writing anything: a JSON that cannot be parsed is not a version.
    sections, footnotes = parse_json_document(
        json_bytes.decode("utf-8"), document_id=document_id
    )
    if not sections:
        raise ValueError("JSON has no reviewable sections")

    stats = await apply_parsed_document(db, document_id, sections, footnotes, mode=mode)

    json_filename = blob_store.store_bytes(json_bytes, "json")
    async with db.execute(
        "SELECT COALESCE(MAX(version_no), 0) FROM document_versions WHERE document_id = ?",
        (document_id,),
    ) as cursor:
        version_no = int((await cursor.fetchone())[0]) + 1

    await db.execute(
        "UPDATE document_versions SET is_active = 0 WHERE document_id = ?",
        (document_id,),
    )
    await db.execute(
        """
        INSERT INTO document_versions (
            id, document_id, version_no, json_filename, json_sha256, source_name,
            created_at, created_by, note, total_sections, is_active, stats_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            _version_id(document_id, version_no),
            document_id,
            version_no,
            json_filename,
            digest,
            os.path.basename(source_name or "") or None,
            _now(),
            created_by,
            note,
            stats["total"],
            json.dumps(stats.get("carryover") or {}, ensure_ascii=False),
        ),
    )
    provenance = derive_from_json_content(
        json_bytes,
        total_pages=await _document_total_pages(db, document_id),
    )
    await db.execute(
        """
        UPDATE documents
        SET json_filename = ?, total_sections = ?, status = ?, provenance = ?
        WHERE id = ?
        """,
        (
            json_filename,
            stats["total"],
            document_status(stats),
            serialize_provenance(provenance),
            document_id,
        ),
    )

    row = await get_version(db, document_id, _version_id(document_id, version_no))
    return row, {"status": "created", "version_no": version_no, "stats": stats}


async def _document_total_pages(
    db: aiosqlite.Connection, document_id: str
) -> Optional[int]:
    async with db.execute(
        "SELECT total_pages FROM documents WHERE id = ?", (document_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    return int(row["total_pages"]) if row["total_pages"] is not None else None


async def activate_version(
    db: aiosqlite.Connection,
    document_id: str,
    version_id: str,
    *,
    mode: str = SUPERSEDE,
) -> Dict[str, Any]:
    """Roll the document back (or forward) to an existing version.

    The stored blob is re-applied through the same upsert as any other ingest, so
    review state is carried the same way in both directions.
    """
    target = await get_version(db, document_id, version_id)
    if target is None:
        raise LookupError("version not found")
    if target["is_active"]:
        return {"status": "unchanged", "version_no": target["version_no"]}

    content = read_version_json(target)
    sections, footnotes = parse_json_document(content, document_id=document_id)
    stats = await apply_parsed_document(db, document_id, sections, footnotes, mode=mode)

    await db.execute(
        "UPDATE document_versions SET is_active = 0 WHERE document_id = ?",
        (document_id,),
    )
    await db.execute(
        "UPDATE document_versions SET is_active = 1 WHERE id = ?",
        (version_id,),
    )
    provenance = derive_from_json_content(
        content,
        total_pages=await _document_total_pages(db, document_id),
    )
    await db.execute(
        """
        UPDATE documents
        SET json_filename = ?, total_sections = ?, status = ?, provenance = ?
        WHERE id = ?
        """,
        (
            target["json_filename"],
            stats["total"],
            document_status(stats),
            serialize_provenance(provenance),
            document_id,
        ),
    )
    return {
        "status": "activated",
        "version_no": target["version_no"],
        "stats": stats,
    }


def _leaves(content: str) -> Dict[str, Dict[str, Any]]:
    sections, _ = parse_json_document(content, document_id="diff")
    return {section["source_key"]: section for section in sections}


def _text_diff(before: str, after: str) -> List[str]:
    lines = list(
        difflib.unified_diff(
            (before or "").splitlines(),
            (after or "").splitlines(),
            lineterm="",
            n=DIFF_CONTEXT_LINES,
        )
    )
    return lines[2:][:MAX_DIFF_LINES]  # drop the ---/+++ header, cap runaway leaves


def diff_documents(before_content: str, after_content: str) -> Dict[str, Any]:
    """Leaf-level difference between two versions of the same document.

    Matching is by ``source_key`` -- the JSON-pointer path the parser mints -- which is
    the same identity the upsert uses, so the diff and the ingest agree on what "the
    same leaf" means.
    """
    before, after = _leaves(before_content), _leaves(after_content)
    added, removed, changed, unchanged = [], [], [], 0

    for key, section in after.items():
        previous = before.get(key)
        if previous is None:
            added.append(
                {
                    "source_key": key,
                    "change": "added",
                    "section_code": section.get("section_code"),
                    "section_heading": section.get("section_heading"),
                    "start_page": section.get("start_page"),
                    "diff": [],
                }
            )
            continue
        if (previous.get("plain_text") or "") == (section.get("plain_text") or "") and (
            previous.get("html_content") or ""
        ) == (section.get("html_content") or ""):
            unchanged += 1
            continue
        changed.append(
            {
                "source_key": key,
                "change": "changed",
                "section_code": section.get("section_code"),
                "section_heading": section.get("section_heading"),
                "start_page": section.get("start_page"),
                "diff": _text_diff(
                    previous.get("plain_text") or "", section.get("plain_text") or ""
                ),
            }
        )

    for key, section in before.items():
        if key not in after:
            removed.append(
                {
                    "source_key": key,
                    "change": "removed",
                    "section_code": section.get("section_code"),
                    "section_heading": section.get("section_heading"),
                    "start_page": section.get("start_page"),
                    "diff": [],
                }
            )

    ordered = sorted(
        added + removed + changed,
        key=lambda item: (item.get("start_page") or 0, item["source_key"]),
    )
    return {
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": unchanged,
        },
        "sections": ordered,
    }


def demo() -> None:
    """Self-check for the pure half (the DB half is covered in backend/tests)."""
    base = json.dumps(
        {
            "metadata": {"total_pages": 2},
            "chapters": [
                {
                    "code": "I",
                    "heading": "General",
                    "sections": [
                        {
                            "code": "1",
                            "heading": "First",
                            "start_page": 1,
                            "end_page": 1,
                            "html": "<p>alpha</p>",
                            "plain_text": "alpha",
                            "footnotes": [],
                        },
                        {
                            "code": "2",
                            "heading": "Second",
                            "start_page": 2,
                            "end_page": 2,
                            "html": "<p>beta</p>",
                            "plain_text": "beta",
                            "footnotes": [],
                        },
                    ],
                }
            ],
            "schedules": [],
        }
    )
    same = diff_documents(base, base)
    assert same["summary"] == {
        "added": 0,
        "removed": 0,
        "changed": 0,
        "unchanged": 2,
    }, same

    payload = json.loads(base)
    payload["chapters"][0]["sections"][1]["plain_text"] = "beta corrected"
    payload["chapters"][0]["sections"][1]["html"] = "<p>beta corrected</p>"
    payload["chapters"][0]["sections"].append(
        {
            "code": "3",
            "heading": "Third",
            "start_page": 2,
            "end_page": 2,
            "html": "<p>gamma</p>",
            "plain_text": "gamma",
            "footnotes": [],
        }
    )
    result = diff_documents(base, json.dumps(payload))
    assert result["summary"]["changed"] == 1, result["summary"]
    assert result["summary"]["added"] == 1, result["summary"]
    assert result["summary"]["removed"] == 0, result["summary"]
    body = "\n".join(
        line for item in result["sections"] for line in item["diff"]
    )
    assert "-beta" in body and "+beta corrected" in body, body

    dropped = diff_documents(base, json.dumps({**json.loads(base), "chapters": []}))
    assert dropped["summary"]["removed"] == 2, dropped["summary"]
    print("versions: ok")


if __name__ == "__main__":
    demo()
