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
from typing import Any, Dict, List, Optional, Tuple

from backend.database import DatabaseConnection, DatabaseRow
from backend.services import blob_store
from backend.services.clock import iso_now_z as _now
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


class StaleVersion(Exception):
    def __init__(self, current_version_id: str | None):
        super().__init__("stale active version")
        self.current_version_id = current_version_id




def _version_id(document_id: str, version_no: int) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"pdf-qa-portal:version:{document_id}:{version_no}",
        )
    )


async def active_version(
    db: DatabaseConnection, document_id: str, *, lock: bool = False
) -> Optional[DatabaseRow]:
    suffix = " FOR UPDATE" if lock else ""
    async with db.execute(
        "SELECT * FROM document_versions WHERE document_id = ? AND is_active = TRUE" + suffix,
        (document_id,),
    ) as cursor:
        return await cursor.fetchone()


async def list_versions(
    db: DatabaseConnection, document_id: str
) -> List[DatabaseRow]:
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
    db: DatabaseConnection, document_id: str, version_id: str
) -> Optional[DatabaseRow]:
    async with db.execute(
        "SELECT * FROM document_versions WHERE document_id = ? AND id = ?",
        (document_id, version_id),
    ) as cursor:
        return await cursor.fetchone()


async def _ensure_hash(db: DatabaseConnection, row: DatabaseRow) -> str:
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
    db: DatabaseConnection,
    document_id: str,
    json_bytes: bytes,
    *,
    source_name: Optional[str] = None,
    note: Optional[str] = None,
    created_by: Optional[str] = None,
    mode: str = SUPERSEDE,
    expected_version_id: Optional[str] = None,
) -> Tuple[DatabaseRow, Dict[str, Any]]:
    """Store a JSON as the document's next version and make it active.

    Returns ``(version_row, outcome)``. ``outcome['status']`` is ``'unchanged'`` when
    the bytes match the active version -- re-running a sync must not manufacture
    versions that say nothing.
    """
    async with db.execute(
        "SELECT id FROM documents WHERE id = ? FOR UPDATE", (document_id,)
    ) as cursor:
        if await cursor.fetchone() is None:
            raise KeyError(document_id)
    digest = blob_store.sha256_bytes(json_bytes)
    current = await active_version(db, document_id, lock=True)
    if expected_version_id is not None and (
        current is None or current["id"] != expected_version_id
    ):
        raise StaleVersion(current["id"] if current else None)
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
        "UPDATE document_versions SET is_active = FALSE WHERE document_id = ?",
        (document_id,),
    )
    await db.execute(
        """
        INSERT INTO document_versions (
            id, document_id, version_no, json_filename, json_sha256, source_name,
            created_at, created_by, note, total_sections, is_active, stats_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE, ?)
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
    pdf_filename = await _document_pdf_filename(db, document_id)
    provenance = derive_from_json_content(
        json_bytes,
        total_pages=await _document_total_pages(db, document_id),
        pdf_path=blob_store.blob_path(pdf_filename) if pdf_filename else None,
    )
    await db.execute(
        """
        UPDATE documents
        SET json_filename = ?, total_sections = ?, status = ?, provenance = ?,
            signoff_stage = 'draft', signoff_reviewed_by = NULL,
            signoff_legal_by = NULL, row_revision = row_revision + 1
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

    from backend.services.identity import persist_inferred_identity

    async with db.execute("SELECT name FROM documents WHERE id = ?", (document_id,)) as cursor:
        document_name = (await cursor.fetchone())["name"]
    await persist_inferred_identity(db, document_id, document_name)

    from backend.services.occurrences import record_version_revisions

    await record_version_revisions(
        db, document_id, _version_id(document_id, version_no)
    )

    from backend.services.variants import rebuild_document

    await rebuild_document(db, document_id)

    row = await get_version(db, document_id, _version_id(document_id, version_no))
    return row, {"status": "created", "version_no": version_no, "stats": stats}


async def _document_total_pages(
    db: DatabaseConnection, document_id: str
) -> Optional[int]:
    async with db.execute(
        "SELECT total_pages FROM documents WHERE id = ?", (document_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    return int(row["total_pages"]) if row["total_pages"] is not None else None


async def _document_pdf_filename(
    db: DatabaseConnection,
    document_id: str,
) -> Optional[str]:
    async with db.execute(
        "SELECT pdf_filename FROM documents WHERE id = ?", (document_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    return str(row["pdf_filename"]) if row["pdf_filename"] is not None else None


async def activate_version(
    db: DatabaseConnection,
    document_id: str,
    version_id: str,
    *,
    mode: str = SUPERSEDE,
    expected_version_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Roll the document back (or forward) to an existing version.

    The stored blob is re-applied through the same upsert as any other ingest, so
    review state is carried the same way in both directions.
    """
    async with db.execute(
        "SELECT id FROM documents WHERE id = ? FOR UPDATE", (document_id,)
    ) as cursor:
        if await cursor.fetchone() is None:
            raise LookupError("document not found")
    current = await active_version(db, document_id, lock=True)
    if expected_version_id is not None and (
        current is None or current["id"] != expected_version_id
    ):
        raise StaleVersion(current["id"] if current else None)
    target = await get_version(db, document_id, version_id)
    if target is None:
        raise LookupError("version not found")
    if target["is_active"]:
        return {"status": "unchanged", "version_no": target["version_no"]}

    content = read_version_json(target)
    sections, footnotes = parse_json_document(content, document_id=document_id)
    stats = await apply_parsed_document(db, document_id, sections, footnotes, mode=mode)

    await db.execute(
        "UPDATE document_versions SET is_active = FALSE WHERE document_id = ?",
        (document_id,),
    )
    await db.execute(
        "UPDATE document_versions SET is_active = TRUE WHERE id = ?",
        (version_id,),
    )
    pdf_filename = await _document_pdf_filename(db, document_id)
    provenance = derive_from_json_content(
        content,
        total_pages=await _document_total_pages(db, document_id),
        pdf_path=blob_store.blob_path(pdf_filename) if pdf_filename else None,
    )
    await db.execute(
        """
        UPDATE documents
        SET json_filename = ?, total_sections = ?, status = ?, provenance = ?,
            signoff_stage = 'draft', signoff_reviewed_by = NULL,
            signoff_legal_by = NULL, row_revision = row_revision + 1
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
    from backend.services.variants import rebuild_document

    await rebuild_document(db, document_id)
    return {
        "status": "activated",
        "version_no": target["version_no"],
        "stats": stats,
    }


def _leaf_key(section: Dict[str, Any]) -> str:
    """The identity two versions of a document are compared on.

    The same order ``apply_parsed_document`` matches by, so the diff shown to a
    reviewer and the upsert that moved their review state cannot disagree about what
    "the same leaf" means. ``source_key`` remains the fallback for a document
    converted before the contract, and the ``node:`` prefix keeps the two namespaces
    from ever colliding.
    """
    node_key = section.get("node_key")
    return f"node:{node_key}" if node_key else section["source_key"]


def _leaves(content: str) -> Dict[str, Dict[str, Any]]:
    sections, _ = parse_json_document(content, document_id="diff")
    return {_leaf_key(section): section for section in sections}


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

    Matching is by ``node_key`` where the pipeline supplied one and ``source_key``
    otherwise -- the same identity the upsert uses, so the diff and the ingest agree
    on what "the same leaf" means.

    On ``source_key`` alone they agreed on something false: inserting one leaf
    reported every later sibling as "changed", measured at 386 leaves across 84
    documents with 16 of them churning 100%.
    """
    before, after = _leaves(before_content), _leaves(after_content)
    added, removed, changed, unchanged = [], [], [], 0

    for key, section in after.items():
        previous = before.get(key)
        if previous is None:
            added.append(
                {
                    "source_key": section["source_key"],
                    "node_key": section.get("node_key"),
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
                "source_key": section["source_key"],
                "node_key": section.get("node_key"),
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
                    "source_key": section["source_key"],
                    "node_key": section.get("node_key"),
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

    # ---- the property `node_key` exists for -------------------------------
    # Everything above appends at the END, which is the one insertion a positional
    # key survives. Inserting at the FRONT is what the corpus actually does when a
    # parser fix recovers a section, and on `source_key` it reported every later
    # sibling as changed -- 386 leaves across 84 documents, 16 of them churning 100%.
    def _doc(codes):
        return json.dumps({
            "metadata": {"total_pages": 3, "contract_version": 1},
            "chapters": [{
                "code": "I", "heading": "General", "type": "chapter",
                "node_key": "ch:i", "parts": [], "divisions": [],
                "sections": [
                    {"code": c, "heading": f"S{c}", "start_page": 1, "end_page": 1,
                     "type": "section", "node_key": f"ch:i/s:{c.lower()}",
                     "html": f"<p>body {c}</p>", "plain_text": f"body {c}",
                     "footnotes": []}
                    for c in codes
                ],
            }],
            "schedules": [],
        })

    inserted = diff_documents(_doc(["2", "3", "4"]), _doc(["1", "2", "3", "4"]))
    assert inserted["summary"] == {
        "added": 1, "removed": 0, "changed": 0, "unchanged": 3
    }, inserted["summary"]
    assert inserted["sections"][0]["node_key"] == "ch:i/s:1", inserted["sections"]

    # ...and a leaf really changing is still reported as changed, so the key narrows
    # the report rather than switching it off.
    edited = json.loads(_doc(["1", "2", "3"]))
    edited["chapters"][0]["sections"][1]["plain_text"] = "body 2 corrected"
    edited["chapters"][0]["sections"][1]["html"] = "<p>body 2 corrected</p>"
    result = diff_documents(_doc(["1", "2", "3"]), json.dumps(edited))
    assert result["summary"] == {
        "added": 0, "removed": 0, "changed": 1, "unchanged": 2
    }, result["summary"]
    assert result["sections"][0]["node_key"] == "ch:i/s:2", result["sections"]

    # A removal is a removal, not a rename of its neighbour.
    removed = diff_documents(_doc(["1", "2", "3"]), _doc(["1", "3"]))
    assert removed["summary"] == {
        "added": 0, "removed": 1, "changed": 0, "unchanged": 2
    }, removed["summary"]
    assert removed["sections"][0]["node_key"] == "ch:i/s:2", removed["sections"]

    print("versions: ok")


if __name__ == "__main__":
    demo()
