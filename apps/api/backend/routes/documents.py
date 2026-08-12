import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from backend.database import get_db
from backend.models import (
    DocumentEditionsResponse,
    DocumentProvenance,
    DocumentResponse,
    DocumentStats,
    EditionSibling,
    VersionMetrics,
    VersionResponse,
)
from backend.services import blob_store, versions
from backend.services.corpus_lanes import classify_lane, normalize_lane
from backend.services.document_provenance import (
    backfill_provenance_row,
)
from backend.services.document_store import ReviewConflict, document_status
from backend.services.editions import (
    edition_date_from_name,
    family_key_from_name,
    family_title_from_key,
)
from backend.services.json_parser import parse_json_document
from backend.services.pdf_service import get_pdf_page_count

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


def get_upload_path(filename: str) -> str:
    """Absolute path of a stored blob (or a legacy flat upload)."""
    os.makedirs(blob_store.upload_root(), exist_ok=True)
    return blob_store.blob_path(filename)


def safe_upload_name(filename: str | None, fallback: str) -> str:
    cleaned = os.path.basename(filename or "").replace("\x00", "")
    return cleaned or fallback


def _version_response(row, metrics_row=None) -> VersionResponse:
    return VersionResponse(
        id=row["id"],
        document_id=row["document_id"],
        version_no=row["version_no"],
        json_filename=row["json_filename"],
        json_sha256=row["json_sha256"] or "",
        source_name=row["source_name"],
        created_at=row["created_at"],
        created_by=row["created_by"],
        note=row["note"],
        total_sections=row["total_sections"] or 0,
        is_active=bool(row["is_active"]),
        stats=json.loads(row["stats_json"]) if row["stats_json"] else None,
        metrics=_metrics_response(metrics_row),
    )


def _metrics_response(row) -> Optional[VersionMetrics]:
    if row is None:
        return None
    detail = json.loads(row["detail_json"]) if row["detail_json"] else {}
    return VersionMetrics(
        invariants_passed=row["invariants_passed"],
        invariants_total=row["invariants_total"],
        cases_passed=row["cases_passed"],
        cases_total=row["cases_total"],
        body_conserved=row["body_conserved"],
        body_missing=row["body_missing"],
        footnote_conserved=row["footnote_conserved"],
        footnote_missing=row["footnote_missing"],
        gate_ok=None if row["gate_ok"] is None else bool(row["gate_ok"]),
        measured_at=row["measured_at"],
        failing_invariants=detail.get("failing_invariants", []),
    )


async def _require_document(db: aiosqlite.Connection, document_id: str):
    async with db.execute(
        "SELECT * FROM documents WHERE id = ?", (document_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return row


def _document_stats(
    *,
    reviewed: int,
    approved: int,
    has_issues: int,
    pending: int,
    open_annotations: int = 0,
) -> DocumentStats:
    return DocumentStats(
        reviewed=reviewed,
        approved=approved,
        has_issues=has_issues,
        pending=pending,
        flagged_sections=has_issues,
        open_annotations=open_annotations,
    )


async def _resolve_provenance(
    db: aiosqlite.Connection, row
) -> Optional[DocumentProvenance]:
    keys = row.keys() if hasattr(row, "keys") else []
    raw = row["provenance"] if "provenance" in keys else None
    return await backfill_provenance_row(
        db,
        document_id=row["id"],
        json_filename=row["json_filename"],
        total_pages=row["total_pages"],
        existing_raw=raw,
    )


async def _resolve_corpus_lane(db: aiosqlite.Connection, row) -> Optional[str]:
    keys = row.keys() if hasattr(row, "keys") else []
    existing = normalize_lane(row["corpus_lane"] if "corpus_lane" in keys else None)
    if existing:
        return existing
    lane = classify_lane(
        row["name"],
        source_type=row["source_type"] if "source_type" in keys else "upload",
    )
    await db.execute(
        "UPDATE documents SET corpus_lane = ? WHERE id = ?",
        (lane, row["id"]),
    )
    return lane


async def _document_response(
    db: aiosqlite.Connection, r
) -> DocumentResponse:
    provenance = await _resolve_provenance(db, r)
    corpus_lane = await _resolve_corpus_lane(db, r)
    return DocumentResponse(
        id=r["id"],
        name=r["name"],
        pdf_filename=r["pdf_filename"],
        json_filename=r["json_filename"],
        total_sections=r["total_sections"],
        total_pages=r["total_pages"],
        uploaded_at=r["uploaded_at"],
        status=r["status"],
        source_type=r["source_type"],
        source_key=r["source_key"],
        stats=_document_stats(
            reviewed=r["reviewed"],
            approved=r["approved"],
            has_issues=r["has_issues"],
            pending=r["pending"],
            open_annotations=r["open_annotations"] or 0,
        ),
        version_count=r["version_count"] or 1,
        active_version_no=r["active_version_no"] or 1,
        health=_metrics_response(r if r["measured_at"] else None),
        provenance=provenance,
        corpus_lane=corpus_lane,
    )


_DOC_VERSION_SELECT = """
    (SELECT COUNT(*) FROM document_versions dv WHERE dv.document_id = d.id)
        AS version_count,
    v.version_no AS active_version_no,
    m.invariants_passed, m.invariants_total, m.cases_passed, m.cases_total,
    m.body_conserved, m.body_missing, m.footnote_conserved, m.footnote_missing,
    m.gate_ok, m.measured_at, m.detail_json
"""

_DOC_VERSION_JOIN = """
    LEFT JOIN document_versions v ON v.document_id = d.id AND v.is_active = 1
    LEFT JOIN version_metrics m ON m.version_id = v.id
"""

_DOC_STATS_SELECT = """
    COUNT(CASE WHEN s.review_status != 'pending' THEN 1 END) as reviewed,
    COUNT(CASE WHEN s.review_status = 'approved' THEN 1 END) as approved,
    COUNT(CASE WHEN s.review_status = 'has_issues' THEN 1 END) as has_issues,
    COUNT(CASE WHEN s.review_status = 'pending' THEN 1 END) as pending,
    (
        -- Keyed off annotations.document_id, not a join through sections, so a finding
        -- orphaned by a later JSON version is still counted as open work.
        SELECT COUNT(*)
        FROM annotations a
        WHERE a.document_id = d.id AND a.status = 'open'
    ) as open_annotations
"""

@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    pdf: UploadFile = File(...),
    json_file: UploadFile = File(...),
    name: str = Form(...),
    db: aiosqlite.Connection = Depends(get_db)
):
    # Validate file formats
    if not (pdf.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF file must have .pdf extension")
    if not (json_file.filename or "").lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="JSON file must have .json extension")

    doc_id = str(uuid.uuid4())

    # Blobs are content-addressed: an identical PDF uploaded twice is stored once, and a
    # failed ingest leaves behind nothing but an unreferenced (and reusable) blob rather
    # than a half-written pair that has to be unlinked by hand.
    try:
        # Streamed, not buffered: a large PDF must not be held in memory at once.
        pdf_filename = await blob_store.store_upload(pdf, "pdf")
    except Exception as e:
        logger.exception("PDF store failed")
        raise HTTPException(status_code=500, detail="Failed to save PDF file")

    try:
        json_content_bytes = await json_file.read()
        json_content = json_content_bytes.decode("utf-8")
    except Exception as e:
        logger.exception("JSON file read failed")
        raise HTTPException(status_code=500, detail="Failed to read JSON file")

    total_pages = get_pdf_page_count(blob_store.blob_path(pdf_filename))
    if total_pages == 0:
        raise HTTPException(status_code=400, detail="Failed to read pages from PDF file")

    # Parse before any row is written: an unparseable JSON is not a document.
    try:
        parse_json_document(json_content, document_id=doc_id)
    except Exception as e:
        logger.exception("JSON parse failed on upload")
        raise HTTPException(status_code=400, detail="Failed to parse JSON document")

    uploaded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    try:
        await db.execute("PRAGMA foreign_keys = ON;")
        await db.execute(
            """
            INSERT INTO documents (
                id, name, pdf_filename, json_filename, total_sections,
                total_pages, uploaded_at, status, source_type, source_key,
                source_hash, corpus_lane
            ) VALUES (?, ?, ?, '', 0, ?, ?, 'pending', 'upload', NULL, NULL, ?)
            """,
            (doc_id, name, pdf_filename, total_pages, uploaded_at, "manual"),
        )
        # Version 1 writes the sections, footnotes and the active-version row, through
        # exactly the same path every later version takes.
        _row, outcome = await versions.create_version(
            db,
            doc_id,
            json_content_bytes,
            source_name=safe_upload_name(json_file.filename, "document.json"),
            note="Initial upload.",
        )
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.exception("Database write failed during upload")
        raise HTTPException(status_code=500, detail="Database write failed")

    stats = outcome["stats"]
    doc_status = document_status(stats)
    doc_row = await _require_document(db, doc_id)
    json_filename = doc_row["json_filename"]
    provenance = await _resolve_provenance(db, doc_row)
    corpus_lane = await _resolve_corpus_lane(db, doc_row)
    await db.commit()

    return DocumentResponse(
        id=doc_id,
        name=name,
        pdf_filename=pdf_filename,
        json_filename=json_filename,
        total_sections=stats["total"],
        total_pages=total_pages,
        uploaded_at=uploaded_at,
        status=doc_status,
        source_type="upload",
        source_key=None,
        stats=_document_stats(
            reviewed=stats["reviewed"],
            approved=stats["approved"],
            has_issues=stats["has_issues"],
            pending=stats["pending"],
            open_annotations=0,
        ),
        provenance=provenance,
        corpus_lane=corpus_lane,
    )

@router.get("", response_model=list[DocumentResponse])
async def list_documents(db: aiosqlite.Connection = Depends(get_db)):
    query = f"""
        SELECT 
            d.id, d.name, d.pdf_filename, d.json_filename, d.total_sections,
            d.total_pages, d.uploaded_at, d.status, d.source_type, d.source_key,
            d.provenance, d.corpus_lane,
            {_DOC_STATS_SELECT},
            {_DOC_VERSION_SELECT}
        FROM documents d
        LEFT JOIN sections s ON s.document_id = d.id
        {_DOC_VERSION_JOIN}
        GROUP BY d.id
        ORDER BY d.uploaded_at DESC
    """
    async with db.execute(query) as cursor:
        rows = await cursor.fetchall()

    results = []
    for r in rows:
        results.append(await _document_response(db, r))
    await db.commit()
    return results

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str, db: aiosqlite.Connection = Depends(get_db)):
    query = f"""
        SELECT 
            d.id, d.name, d.pdf_filename, d.json_filename, d.total_sections,
            d.total_pages, d.uploaded_at, d.status, d.source_type, d.source_key,
            d.provenance, d.corpus_lane,
            {_DOC_STATS_SELECT},
            {_DOC_VERSION_SELECT}
        FROM documents d
        LEFT JOIN sections s ON s.document_id = d.id
        {_DOC_VERSION_JOIN}
        WHERE d.id = ?
        GROUP BY d.id
    """
    async with db.execute(query, (document_id,)) as cursor:
        r = await cursor.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail="Document not found")

    response = await _document_response(db, r)
    await db.commit()
    return response


@router.get("/{document_id}/editions", response_model=DocumentEditionsResponse)
async def list_document_editions(
    document_id: str, db: aiosqlite.Connection = Depends(get_db)
):
    """Sibling editions of the same statute family, newest year last."""
    current = await _require_document(db, document_id)
    family_key = family_key_from_name(current["name"])
    async with db.execute(
        "SELECT id, name, corpus_lane FROM documents"
    ) as cursor:
        rows = await cursor.fetchall()

    siblings: list[EditionSibling] = []
    for row in rows:
        if family_key_from_name(row["name"]) != family_key:
            continue
        edition = edition_date_from_name(row["name"])
        lane = normalize_lane(row["corpus_lane"]) or classify_lane(
            row["name"],
            source_type="acts_corpus",
        )
        siblings.append(
            EditionSibling(
                id=row["id"],
                name=row["name"],
                year=edition.get("year"),
                year_label=edition.get("label") or "year unknown",
                corpus_lane=lane,
                is_current=row["id"] == document_id,
            )
        )
    siblings.sort(key=lambda item: (item.year is None, item.year or 0, item.name))
    return DocumentEditionsResponse(
        family_key=family_key,
        family_title=family_title_from_key(family_key),
        editions=siblings,
    )

@router.get("/{document_id}/raw-files")
async def get_raw_files(document_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT pdf_filename, json_filename FROM documents WHERE id = ?", (document_id,)) as cursor:
        r = await cursor.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"pdf_filename": r["pdf_filename"], "json_filename": r["json_filename"]}

@router.delete("/{document_id}")
async def delete_document(document_id: str, db: aiosqlite.Connection = Depends(get_db)):
    row = await _require_document(db, document_id)

    # Collect every blob this document points at, including superseded versions, before
    # the cascade removes the rows that name them.
    candidates = {row["pdf_filename"], row["json_filename"]}
    async with db.execute(
        "SELECT json_filename FROM document_versions WHERE document_id = ?",
        (document_id,),
    ) as cursor:
        candidates.update(item["json_filename"] for item in await cursor.fetchall())

    try:
        await db.execute("PRAGMA foreign_keys = ON;")
        await db.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.exception("Database deletion failed")
        raise HTTPException(status_code=500, detail="Database deletion failed")

    # Content addressing means another document may share these bytes; only unlink what
    # nothing else references.
    for name in candidates:
        await blob_store.unlink_if_unreferenced(db, name)

    return JSONResponse(
        content={"message": "Document and all associated data deleted successfully"}
    )


async def _document_response_by_id(
    db: aiosqlite.Connection, document_id: str
) -> DocumentResponse:
    query = f"""
        SELECT
            d.id, d.name, d.pdf_filename, d.json_filename, d.total_sections,
            d.total_pages, d.uploaded_at, d.status, d.source_type, d.source_key,
            d.provenance, d.corpus_lane,
            {_DOC_STATS_SELECT},
            {_DOC_VERSION_SELECT}
        FROM documents d
        LEFT JOIN sections s ON s.document_id = d.id
        {_DOC_VERSION_JOIN}
        WHERE d.id = ?
        GROUP BY d.id
    """
    async with db.execute(query, (document_id,)) as cursor:
        r = await cursor.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Document not found")
    return await _document_response(db, r)


async def _add_version(
    db: aiosqlite.Connection,
    document_id: str,
    json_file: UploadFile,
    note: Optional[str],
    created_by: Optional[str],
):
    """Shared body of replace-json and POST /versions."""
    if not (json_file.filename or "").lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="JSON file must have .json extension")
    # Callers that invoke the route directly (the backend tests do) pass no Form
    # defaults, so the unresolved `Form(None)` sentinel can arrive here.
    note = note if isinstance(note, str) else None
    created_by = created_by if isinstance(created_by, str) else None
    await _require_document(db, document_id)

    json_bytes = await json_file.read()
    try:
        json_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail="JSON file is not valid UTF-8")

    try:
        await db.execute("PRAGMA foreign_keys = ON;")
        row, outcome = await versions.create_version(
            db,
            document_id,
            json_bytes,
            source_name=json_file.filename,
            note=note,
            created_by=created_by,
        )
        await db.commit()
    except ReviewConflict as conflict:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(conflict))
    except (ValueError, KeyError, TypeError) as e:
        await db.rollback()
        logger.exception("JSON parse failed on replace")
        raise HTTPException(status_code=400, detail="Failed to parse JSON document")
    except Exception as e:
        await db.rollback()
        logger.exception("Database update failed on replace-json")
        raise HTTPException(status_code=500, detail="Database update failed")
    return row, outcome


@router.post("/{document_id}/replace-json", response_model=DocumentResponse)
async def replace_json(
    document_id: str,
    json_file: UploadFile = File(...),
    note: Optional[str] = Form(None),
    reviewer_name: Optional[str] = Form(None),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Add a JSON version and make it active.

    ACT-corpus documents are no longer refused here. The 409 this used to raise existed
    because a replacement overwrote history in place; versions make the operation
    reversible, and ``sync_acts`` reconciles by content hash either way.
    """
    await _add_version(db, document_id, json_file, note, reviewer_name)
    return await _document_response_by_id(db, document_id)


@router.get("/{document_id}/versions", response_model=list[VersionResponse])
async def list_document_versions(
    document_id: str, db: aiosqlite.Connection = Depends(get_db)
):
    await _require_document(db, document_id)
    rows = await versions.list_versions(db, document_id)
    async with db.execute(
        """
        SELECT m.* FROM version_metrics m
        JOIN document_versions v ON v.id = m.version_id
        WHERE v.document_id = ?
        """,
        (document_id,),
    ) as cursor:
        metrics = {row["version_id"]: row for row in await cursor.fetchall()}
    return [_version_response(row, metrics.get(row["id"])) for row in rows]


@router.post("/{document_id}/versions", response_model=VersionResponse)
async def create_document_version(
    document_id: str,
    json_file: UploadFile = File(...),
    note: Optional[str] = Form(None),
    reviewer_name: Optional[str] = Form(None),
    db: aiosqlite.Connection = Depends(get_db),
):
    row, _outcome = await _add_version(db, document_id, json_file, note, reviewer_name)
    return _version_response(row)


@router.post("/{document_id}/versions/{version_id}/activate", response_model=VersionResponse)
async def activate_document_version(
    document_id: str,
    version_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Roll back (or forward) to a stored version."""
    await _require_document(db, document_id)
    try:
        await db.execute("PRAGMA foreign_keys = ON;")
        await versions.activate_version(db, document_id, version_id)
        await db.commit()
    except LookupError:
        await db.rollback()
        raise HTTPException(status_code=404, detail="Version not found")
    except ReviewConflict as conflict:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(conflict))
    except FileNotFoundError:
        await db.rollback()
        raise HTTPException(
            status_code=410,
            detail="The stored JSON for this version is missing from upload storage.",
        )
    except Exception as e:
        await db.rollback()
        logger.exception("Version activation failed")
        raise HTTPException(status_code=500, detail="Activation failed")

    row = await versions.get_version(db, document_id, version_id)
    return _version_response(row)


@router.get("/{document_id}/versions/{version_id}/diff")
async def diff_document_version(
    document_id: str,
    version_id: str,
    against: Optional[str] = Query(
        None, description="Version id to compare with; defaults to the previous version"
    ),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Leaf-level difference between two versions of this document."""
    await _require_document(db, document_id)
    target = await versions.get_version(db, document_id, version_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Version not found")

    if against:
        base = await versions.get_version(db, document_id, against)
    else:
        async with db.execute(
            """
            SELECT * FROM document_versions
            WHERE document_id = ? AND version_no < ?
            ORDER BY version_no DESC LIMIT 1
            """,
            (document_id, target["version_no"]),
        ) as cursor:
            base = await cursor.fetchone()
    if base is None:
        return {
            "base": None,
            "target": {"id": target["id"], "version_no": target["version_no"]},
            "summary": {"added": 0, "removed": 0, "changed": 0, "unchanged": 0},
            "sections": [],
            "note": "This is the first version; there is nothing to compare it with.",
        }

    try:
        result = versions.diff_documents(
            versions.read_version_json(base), versions.read_version_json(target)
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=410,
            detail="A stored JSON for one of these versions is missing from upload storage.",
        )
    result["base"] = {"id": base["id"], "version_no": base["version_no"]}
    result["target"] = {"id": target["id"], "version_no": target["version_no"]}
    return result
