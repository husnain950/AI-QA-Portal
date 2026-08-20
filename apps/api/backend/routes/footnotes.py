from fastapi import APIRouter, Depends, HTTPException

from backend.database import DatabaseConnection, get_db
from backend.deps import require_reviewer
from backend.models import FootnoteStatusUpdate
from backend.services import events, review_state

router = APIRouter(prefix="/footnotes", tags=["footnotes"])


@router.patch("/{footnote_id}/status")
async def update_footnote_status(
    footnote_id: str,
    body: FootnoteStatusUpdate,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    query = """
        SELECT f.section_id, f.review_status, s.document_id
        FROM footnotes f
        JOIN sections s ON s.id = f.section_id
        WHERE f.id = ?
    """
    async with db.execute(query, (footnote_id,)) as cursor:
        r = await cursor.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail="Footnote not found")

    section_id, from_status, doc_id = r["section_id"], r["review_status"], r["document_id"]

    try:
        await db.execute(
            "UPDATE footnotes SET review_status = ? WHERE id = ?",
            (body.review_status, footnote_id)
        )

        version_id = await events.active_version_id(db, doc_id)
        await events.record(
            db,
            actor=actor,
            action="footnote_status",
            document_id=doc_id,
            section_id=section_id,
            version_id=version_id,
            from_value=from_status,
            to_value=body.review_status,
        )

        state = await review_state.refresh_section(db, section_id)

        await db.commit()
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update footnote status")

    return {"footnote_id": footnote_id, "review_status": body.review_status, **state}
