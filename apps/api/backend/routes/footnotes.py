import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from backend.database import get_db
from backend.deps import require_reviewer
from backend.models import FootnoteStatusUpdate
from backend.services import events

router = APIRouter(prefix="/footnotes", tags=["footnotes"])


@router.patch("/{footnote_id}/status")
async def update_footnote_status(
    footnote_id: str,
    body: FootnoteStatusUpdate,
    db: aiosqlite.Connection = Depends(get_db),
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

        if body.review_status == "has_issues":
            await db.execute(
                "UPDATE sections SET review_status = 'has_issues' WHERE id = ?",
                (section_id,)
            )

        async with db.execute(
            """
            SELECT
                COUNT(*) AS total_sections,
                SUM(CASE WHEN review_status = 'pending' THEN 1 ELSE 0 END)
                    AS pending_sections
            FROM sections
            WHERE document_id = ?
            """,
            (doc_id,),
        ) as cursor:
            section_stats = await cursor.fetchone()
        async with db.execute(
            """
            SELECT COUNT(*) AS reviewed_footnotes
            FROM footnotes f
            JOIN sections s ON s.id = f.section_id
            WHERE s.document_id = ? AND f.review_status != 'pending'
            """,
            (doc_id,),
        ) as cursor:
            footnote_stats = await cursor.fetchone()

        total_sections = section_stats["total_sections"]
        pending_sections = section_stats["pending_sections"] or 0
        reviewed_footnotes = footnote_stats["reviewed_footnotes"]
        if pending_sections == 0 and total_sections:
            document_status = "completed"
        elif pending_sections == total_sections and reviewed_footnotes == 0:
            document_status = "pending"
        else:
            document_status = "in_progress"

        await db.execute(
            "UPDATE documents SET status = ? WHERE id = ?",
            (document_status, doc_id),
        )

        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update footnote status")

    return {"footnote_id": footnote_id, "review_status": body.review_status}
