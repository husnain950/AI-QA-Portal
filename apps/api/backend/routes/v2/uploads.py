"""Two-phase PDF/JSON uploads backed by private object storage."""

from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from pypdf import PdfReader

from backend.database import DatabaseConnection, get_db, json_column
from backend.deps import require_reviewer
from backend.routes.documents import _document_response_by_id
from backend.services import blob_store, versions
from backend.services.corpus_lanes import LANE_MANUAL, normalize_lane
from backend.services.json_parser import parse_json_document

router = APIRouter(tags=["v2-uploads"])
PDF_LIMIT = 150 * 1024 * 1024
JSON_LIMIT = 50 * 1024 * 1024


async def _stage(upload: UploadFile, path: Path, limit: int) -> tuple[int, str, bytes]:
    digest = hashlib.sha256()
    size = 0
    prefix = b""
    with path.open("wb") as target:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            if not prefix:
                prefix = chunk[:16]
            size += len(chunk)
            if size > limit:
                raise HTTPException(status_code=413, detail=f"{upload.filename or 'file'} exceeds size limit")
            digest.update(chunk)
            target.write(chunk)
    return size, digest.hexdigest(), prefix


def _json_errors(data, sections, pages: int) -> list[dict]:
    errors: list[dict] = []
    if not sections:
        errors.append({"pointer": "/", "code": "zero_sections", "message": "JSON has no reviewable sections"})
    declared = (data.get("metadata") or {}).get("total_pages") if isinstance(data, dict) else None
    if declared is not None and declared != pages:
        errors.append(
            {
                "pointer": "/metadata/total_pages",
                "code": "page_count_mismatch",
                "message": f"JSON declares {declared} pages but PDF has {pages}",
            }
        )
    for section in sections:
        start, end = section.get("start_page"), section.get("end_page")
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start or end > pages:
            errors.append(
                {
                    "pointer": section.get("source_key") or "/",
                    "code": "invalid_page_span",
                    "message": f"page span {start}-{end} is outside PDF pages 1-{pages}",
                }
            )
    return errors[:500]


@router.post("/uploads/preflight", status_code=201)
async def preflight_upload(
    pdf: UploadFile = File(...),
    json_file: UploadFile = File(...),
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    token = str(uuid.uuid4())
    root = Path(blob_store.upload_root()) / ".preflight"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as temp:
        pdf_path = Path(temp) / "source.pdf"
        json_path = Path(temp) / "structure.json"
        pdf_size, pdf_sha, magic = await _stage(pdf, pdf_path, PDF_LIMIT)
        json_size, json_sha, _ = await _stage(json_file, json_path, JSON_LIMIT)
        if not magic.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail={"errors": [{"pointer": "/pdf", "code": "invalid_magic", "message": "PDF magic bytes are invalid"}]})
        try:
            reader = PdfReader(str(pdf_path))
            if reader.is_encrypted:
                raise ValueError("encrypted PDF")
            pages = len(reader.pages)
            if pages < 1:
                raise ValueError("zero-page PDF")
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail={"errors": [{"pointer": "/pdf", "code": "unreadable_pdf", "message": str(exc)}]},
            ) from exc
        try:
            content = json_path.read_text(encoding="utf-8")
            data = json.loads(content)
            sections, footnotes = parse_json_document(content, document_id=f"staging:{token}")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail={"errors": [{"pointer": "/json", "code": "invalid_utf8", "message": str(exc)}]}) from exc
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail={"errors": [{"pointer": "/json", "code": "invalid_json", "message": f"line {exc.lineno}, column {exc.colno}: {exc.msg}"}]},
            ) from exc
        errors = _json_errors(data, sections, pages)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})

        pdf_key = f"staging/{token}/source.pdf"
        json_key = f"staging/{token}/structure.json"
        storage = blob_store.get_storage()
        storage.put_file(pdf_key, pdf_path, content_type="application/pdf")
        storage.put_file(json_key, json_path, content_type="application/json")

    metadata = data.get("metadata") if isinstance(data, dict) and isinstance(data.get("metadata"), dict) else {}
    summary = {
        "pdf_bytes": pdf_size,
        "json_bytes": json_size,
        "pages": pages,
        "sections": len(sections),
        "footnotes": len(footnotes),
        "inferred_metadata": {
            "title": metadata.get("title") or metadata.get("name"),
            "edition_date": metadata.get("edition_date"),
            "amendment_through_date": metadata.get("amendment_through_date"),
        },
    }
    now = datetime.now(timezone.utc)
    await db.execute(
        """
        INSERT INTO upload_staging
            (token, pdf_key, json_key, pdf_sha256, json_sha256, summary, warnings,
             created_by, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, CAST(? AS jsonb), '[]'::jsonb, ?, ?, ?)
        """,
        (
            token,
            pdf_key,
            json_key,
            pdf_sha,
            json_sha,
            json.dumps(summary),
            actor,
            now.isoformat(),
            (now + timedelta(hours=24)).isoformat(),
        ),
    )
    await db.commit()
    return {"token": token, "errors": [], "warnings": [], **summary, "expires_at": (now + timedelta(hours=24)).isoformat()}


class CommitUpload(BaseModel):
    token: str
    name: str = Field(min_length=1, max_length=500)
    corpus_lane: str | None = None


@router.post("/documents", status_code=201)
async def commit_upload(
    body: CommitUpload,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    async with db.execute(
        "SELECT * FROM upload_staging WHERE token = ? FOR UPDATE", (body.token,)
    ) as cur:
        staged = await cur.fetchone()
    if not staged:
        raise HTTPException(status_code=404, detail="upload token not found")
    if staged["committed_at"]:
        raise HTTPException(status_code=409, detail="upload token was already committed")
    now = datetime.now(timezone.utc)
    if staged["expires_at"] <= now.isoformat():
        raise HTTPException(status_code=410, detail="upload token expired")
    storage = blob_store.get_storage()
    pdf_name = blob_store.rel_name("pdf", staged["pdf_sha256"])
    json_name = blob_store.rel_name("json", staged["json_sha256"])
    storage.copy(staged["pdf_key"], pdf_name, content_type="application/pdf")
    storage.copy(staged["json_key"], json_name, content_type="application/json")
    json_stat = storage.stat(staged["json_key"])
    json_bytes = storage.read_range(staged["json_key"], 0, json_stat.size - 1)
    summary = json_column(staged["summary"])
    document_id = str(uuid.uuid4())
    await db.execute(
        """
        INSERT INTO documents
            (id, name, pdf_filename, json_filename, total_sections, total_pages,
             uploaded_at, status, source_type, corpus_lane)
        VALUES (?, ?, ?, '', 0, ?, ?, 'pending', 'upload', ?)
        """,
        (
            document_id,
            body.name.strip(),
            pdf_name,
            int(summary["pages"]),
            now.isoformat(),
            normalize_lane(body.corpus_lane) or LANE_MANUAL,
        ),
    )
    await versions.create_version(
        db,
        document_id,
        json_bytes,
        source_name="structure.json",
        note="Committed from validated staged upload.",
        created_by=actor,
    )
    await db.execute(
        "UPDATE upload_staging SET committed_at = ? WHERE token = ?",
        (now.isoformat(), body.token),
    )
    await db.commit()
    storage.delete(staged["pdf_key"])
    storage.delete(staged["json_key"])
    return (await _document_response_by_id(db, document_id)).model_dump()
