"""Immutable, content-addressed legal review evidence bundles."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

from backend.database import DatabaseConnection
from backend.services import blob_store


async def _rows(db: DatabaseConnection, sql: str, params=()) -> list[dict]:
    async with db.execute(sql, params) as cur:
        return [dict(row) for row in await cur.fetchall()]


async def build_document_bundle(db: DatabaseConnection, document_id: str) -> dict:
    async with db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)) as cur:
        document = await cur.fetchone()
    if not document:
        raise KeyError(document_id)
    document = dict(document)
    versions = await _rows(
        db, "SELECT * FROM document_versions WHERE document_id = ? ORDER BY version_no", (document_id,)
    )
    sections = await _rows(
        db,
        """
        SELECT id, occurrence_id, source_key, section_code, section_heading, start_page,
               end_page, sort_order, reviewer_verdict, effective_status, review_status,
               quality_flags, sanitizer_version, sanitized_changed, sanitizer_diagnostics
        FROM sections WHERE document_id = ? ORDER BY sort_order
        """,
        (document_id,),
    )
    manifest = {
        "format": "crx-evidence-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "identity_assurance": "self_asserted",
        "document": document,
        "source_blobs": {
            "pdf": {"key": document["pdf_filename"], "sha256": blob_store._digest_from_key(document["pdf_filename"])},
            "active_json": {"key": document["json_filename"], "sha256": blob_store._digest_from_key(document["json_filename"])},
        },
        "versions": versions,
        "source_pages": await _rows(
            db, "SELECT * FROM source_pages WHERE document_id = ? ORDER BY page_number", (document_id,)
        ),
        "leaf_occurrences": await _rows(
            db, "SELECT * FROM leaf_occurrences WHERE document_id = ? ORDER BY created_at, id", (document_id,)
        ),
        "leaf_revisions": await _rows(
            db,
            """
            SELECT lr.* FROM leaf_revisions lr JOIN leaf_occurrences lo ON lo.id = lr.occurrence_id
            WHERE lo.document_id = ? ORDER BY lr.sort_order, lr.version_id
            """,
            (document_id,),
        ),
        "sections": sections,
        "footnotes": await _rows(
            db,
            """
            SELECT f.* FROM footnotes f JOIN sections s ON s.id = f.section_id
            WHERE s.document_id = ? ORDER BY s.sort_order, f.page, f.marker
            """,
            (document_id,),
        ),
        "annotations_including_orphans": await _rows(
            db, "SELECT * FROM annotations WHERE document_id = ? ORDER BY created_at, id", (document_id,)
        ),
        "findings": await _rows(
            db, "SELECT * FROM findings WHERE document_id = ? ORDER BY id", (document_id,)
        ),
        "approval_inheritance": await _rows(
            db,
            """
            SELECT ai.* FROM approval_inheritance ai
            WHERE ai.source_id IN (SELECT id FROM sections WHERE document_id = ?)
               OR ai.inheritor_id IN (SELECT id FROM sections WHERE document_id = ?)
            ORDER BY ai.id
            """,
            (document_id, document_id),
        ),
        "ai_evidence": await _rows(
            db, "SELECT * FROM fix_proposals WHERE document_id = ? ORDER BY created_at", (document_id,)
        ),
        "events": await _rows(
            db, "SELECT * FROM review_events WHERE document_id = ? ORDER BY id", (document_id,)
        ),
        "signoff": {
            "stage": document["signoff_stage"],
            "reviewed_by": document["signoff_reviewed_by"],
            "legal_approved_by": document["signoff_legal_by"],
        },
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n")
    data = buffer.getvalue()
    key = blob_store.store_bytes(data, "evidence")
    return {"key": key, "download_url": f"/uploads/{key}", "sha256": blob_store.sha256_bytes(data), "bytes": len(data)}


async def build_regression_bundle(db: DatabaseConnection, finding_id: int) -> dict:
    async with db.execute(
        """
        SELECT f.*, s.section_code, s.section_heading, s.plain_text, s.html_content,
               d.name AS document_name, d.pdf_filename, d.json_filename
        FROM findings f LEFT JOIN sections s ON s.id = f.section_id
        JOIN documents d ON d.id = f.document_id WHERE f.id = ?
        """,
        (finding_id,),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise KeyError(finding_id)
    payload = dict(row)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("finding.json", json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n")
    data = buffer.getvalue()
    key = blob_store.store_bytes(data, "evidence")
    return {"key": key, "download_url": f"/uploads/{key}", "sha256": blob_store.sha256_bytes(data), "bytes": len(data)}
