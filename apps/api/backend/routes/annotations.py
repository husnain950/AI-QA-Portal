import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from backend.database import DatabaseConnection, get_db
from backend.deps import require_reviewer
from backend.models import AnnotationCreate, AnnotationResponse, AnnotationUpdate
from backend.services import events, review_state
from backend.services.disposition import normalize_disposition

logger = logging.getLogger(__name__)

router = APIRouter(tags=["annotations"])

ANCHOR_STATUSES = frozenset({"anchored", "needs_recheck", "orphaned"})


def _annotation_from_row(r) -> AnnotationResponse:
    try:
        disposition = r["disposition"]
    except (KeyError, IndexError):
        disposition = "open"
    return AnnotationResponse(
        id=r["id"],
        document_id=r["document_id"],
        section_id=r["section_id"],
        footnote_id=r["footnote_id"],
        highlighted_text=r["highlighted_text"],
        context_before=r["context_before"],
        context_after=r["context_after"],
        start_offset=r["start_offset"],
        end_offset=r["end_offset"],
        issue_description=r["issue_description"],
        severity=r["severity"],
        created_at=r["created_at"],
        reviewer_name=r["reviewer_name"],
        status=r["status"],
        anchor_status=r["anchor_status"],
        disposition=disposition or "open",
        orphan_context=json.loads(r["orphan_context"]) if r["orphan_context"] else None,
    )


@router.get("/sections/{section_id}/annotations", response_model=list[AnnotationResponse])
async def list_annotations(section_id: str, db: DatabaseConnection = Depends(get_db)):
    async with db.execute("SELECT 1 FROM sections WHERE id = ?", (section_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Section not found")

    query = """
        SELECT a.id, a.document_id, a.section_id, a.footnote_id, a.highlighted_text,
               a.start_offset, a.end_offset, a.issue_description, a.severity,
               a.created_at, a.reviewer_name, a.status, a.anchor_status,
               a.context_before, a.context_after, a.orphan_context, a.disposition
        FROM annotations a
        WHERE a.section_id = ?
        ORDER BY a.created_at ASC
    """
    async with db.execute(query, (section_id,)) as cursor:
        rows = await cursor.fetchall()

    return [_annotation_from_row(r) for r in rows]


@router.post("/sections/{section_id}/annotations", response_model=AnnotationResponse)
async def create_annotation(
    section_id: str,
    body: AnnotationCreate,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    async with db.execute(
        "SELECT document_id, plain_text FROM sections WHERE id = ? FOR UPDATE",
        (section_id,),
    ) as cursor:
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Section not found")

    doc_id = row["document_id"]
    anchor_text = row["plain_text"] or ""
    if body.footnote_id:
        async with db.execute(
            "SELECT section_id, text FROM footnotes WHERE id = ?",
            (body.footnote_id,),
        ) as cursor:
            footnote = await cursor.fetchone()
        if not footnote or footnote["section_id"] != section_id:
            raise HTTPException(
                status_code=400,
                detail="footnote_id must belong to the target section",
            )
        anchor_text = footnote["text"] or ""
    if body.start_offset < 0 or body.end_offset <= body.start_offset or body.end_offset > len(anchor_text):
        raise HTTPException(status_code=400, detail="annotation offsets are outside rendered text")
    if anchor_text[body.start_offset : body.end_offset] != body.highlighted_text:
        raise HTTPException(
            status_code=400,
            detail="highlighted_text does not match rendered text at the supplied offsets",
        )
    try:
        disposition = normalize_disposition(body.disposition)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    version_id = await events.active_version_id(db, doc_id)
    annotation_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    try:
        await db.execute(
            """
            INSERT INTO annotations (
                id, document_id, section_id, footnote_id, highlighted_text,
                context_before, context_after, start_offset, end_offset,
                issue_description, severity, created_at, reviewer_name, status,
                anchor_status, created_version_id, disposition
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'anchored', ?, ?)
            """,
            (
                annotation_id, doc_id, section_id, body.footnote_id,
                body.highlighted_text, body.context_before, body.context_after,
                body.start_offset, body.end_offset,
                body.issue_description, body.severity, created_at,
                actor, "open", version_id, disposition,
            ),
        )
        await review_state.refresh_section(db, section_id)

        await events.record(
            db,
            actor=actor,
            action="annotation_create",
            document_id=doc_id,
            section_id=section_id,
            version_id=version_id,
            to_value=annotation_id,
        )

        await db.commit()
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create annotation")

    return AnnotationResponse(
        id=annotation_id,
        document_id=doc_id,
        section_id=section_id,
        footnote_id=body.footnote_id,
        highlighted_text=body.highlighted_text,
        context_before=body.context_before,
        context_after=body.context_after,
        start_offset=body.start_offset,
        end_offset=body.end_offset,
        issue_description=body.issue_description,
        severity=body.severity,
        created_at=created_at,
        reviewer_name=actor,
        status="open",
        anchor_status="anchored",
        disposition=disposition,
    )


@router.patch("/annotations/{annotation_id}", response_model=AnnotationResponse)
async def update_annotation(
    annotation_id: str,
    body: AnnotationUpdate,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    async with db.execute("SELECT * FROM annotations WHERE id = ?", (annotation_id,)) as cursor:
        existing = await cursor.fetchone()

    if not existing:
        raise HTTPException(status_code=404, detail="Annotation not found")

    issue_description = body.issue_description if body.issue_description is not None else existing["issue_description"]
    severity = body.severity if body.severity is not None else existing["severity"]
    status_val = body.status if body.status is not None else existing["status"]
    anchor_status = body.anchor_status if body.anchor_status is not None else existing["anchor_status"]

    try:
        existing_disp = existing["disposition"]
    except (KeyError, IndexError):
        existing_disp = "open"
    disposition = existing_disp or "open"
    if body.disposition is not None:
        try:
            disposition = normalize_disposition(body.disposition)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if anchor_status not in ANCHOR_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"anchor_status must be one of {sorted(ANCHOR_STATUSES)}",
        )
    if body.anchor_status == "anchored" and existing["section_id"] is None:
        raise HTTPException(
            status_code=409,
            detail="Orphaned annotation has no section to re-anchor to.",
        )

    try:
        await db.execute(
            """
            UPDATE annotations
            SET issue_description = ?, severity = ?, status = ?, anchor_status = ?, disposition = ?
            WHERE id = ?
            """,
            (issue_description, severity, status_val, anchor_status, disposition, annotation_id),
        )

        if existing["section_id"] is not None:
            await review_state.refresh_section(db, existing["section_id"])

        version_id = await events.active_version_id(db, existing["document_id"])
        await events.record(
            db,
            actor=actor,
            action="annotation_update",
            document_id=existing["document_id"],
            section_id=existing["section_id"],
            version_id=version_id,
            from_value=existing["status"],
            to_value=status_val,
            detail={"disposition": disposition} if body.disposition else None,
        )

        await db.commit()
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update annotation")

    return AnnotationResponse(
        id=annotation_id,
        document_id=existing["document_id"],
        section_id=existing["section_id"],
        footnote_id=existing["footnote_id"],
        highlighted_text=existing["highlighted_text"],
        context_before=existing["context_before"],
        context_after=existing["context_after"],
        start_offset=existing["start_offset"],
        end_offset=existing["end_offset"],
        issue_description=issue_description,
        severity=severity,
        created_at=existing["created_at"],
        reviewer_name=existing["reviewer_name"],
        status=status_val,
        anchor_status=anchor_status,
        disposition=disposition,
        orphan_context=json.loads(existing["orphan_context"]) if existing["orphan_context"] else None,
    )


@router.delete("/annotations/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_annotation(
    annotation_id: str,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    query = """
        SELECT a.section_id, a.document_id
        FROM annotations a
        WHERE a.id = ?
    """
    async with db.execute(query, (annotation_id,)) as cursor:
        r = await cursor.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail="Annotation not found")

    section_id, doc_id = r["section_id"], r["document_id"]

    try:
        await db.execute("DELETE FROM annotations WHERE id = ?", (annotation_id,))

        if section_id is not None:
            await review_state.refresh_section(db, section_id)

        version_id = await events.active_version_id(db, doc_id)
        await events.record(
            db,
            actor=actor,
            action="annotation_delete",
            document_id=doc_id,
            section_id=section_id,
            version_id=version_id,
            from_value=annotation_id,
        )

        await db.commit()
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete annotation")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/documents/{document_id}/annotations", response_model=list[AnnotationResponse])
async def list_document_annotations(document_id: str, db: DatabaseConnection = Depends(get_db)):
    async with db.execute("SELECT 1 FROM documents WHERE id = ?", (document_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Document not found")

    query = """
        SELECT a.id, a.document_id, a.section_id, a.footnote_id, a.highlighted_text,
               a.start_offset, a.end_offset, a.issue_description, a.severity,
               a.created_at, a.reviewer_name, a.status, a.anchor_status,
               a.context_before, a.context_after, a.orphan_context, a.disposition
        FROM annotations a
        WHERE a.document_id = ?
        ORDER BY a.created_at ASC
    """
    async with db.execute(query, (document_id,)) as cursor:
        rows = await cursor.fetchall()

    return [_annotation_from_row(r) for r in rows]
