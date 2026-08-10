import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from backend.database import get_db
from backend.deps import require_reviewer
from backend.models import (
    FootnoteResponse,
    QualityFlag,
    SectionMetadataResponse,
    SectionResponse,
    SectionStatusUpdate,
)
from backend.services import events
from backend.services.parse_quality import deserialize_quality_flags

router = APIRouter(prefix="/documents", tags=["sections"])


def _quality_flags_from_row(row) -> list[QualityFlag]:
    raw = None
    try:
        raw = row["quality_flags"]
    except (KeyError, IndexError):
        raw = None
    return [QualityFlag(**flag) for flag in deserialize_quality_flags(raw)]


def _hierarchy_kind_from_row(row) -> str | None:
    try:
        value = row["hierarchy_kind"]
    except (KeyError, IndexError):
        return None
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _section_metadata_kwargs(r) -> dict:
    return dict(
        id=r["id"],
        document_id=r["document_id"],
        chapter_code=r["chapter_code"],
        chapter_heading=r["chapter_heading"],
        part_code=r["part_code"],
        part_heading=r["part_heading"],
        division_code=r["division_code"],
        division_heading=r["division_heading"],
        hierarchy_kind=_hierarchy_kind_from_row(r),
        section_code=r["section_code"],
        section_heading=r["section_heading"],
        start_page=r["start_page"],
        end_page=r["end_page"],
        review_status=r["review_status"],
        annotation_count=r["annotation_count"],
        sort_order=r["sort_order"],
        quality_flags=_quality_flags_from_row(r),
    )


_SECTION_META_COLS = """
    s.id, s.document_id, s.chapter_code, s.chapter_heading, s.part_code, s.part_heading,
    s.division_code, s.division_heading, s.hierarchy_kind, s.section_code, s.section_heading,
    s.start_page, s.end_page, s.review_status, s.sort_order, s.quality_flags
"""


@router.get("/{document_id}/sections", response_model=list[SectionMetadataResponse])
async def list_sections(document_id: str, db: aiosqlite.Connection = Depends(get_db)):
    # Check if document exists first
    async with db.execute("SELECT 1 FROM documents WHERE id = ?", (document_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Document not found")

    query = f"""
        SELECT 
            {_SECTION_META_COLS},
            COUNT(a.id) as annotation_count
        FROM sections s
        LEFT JOIN annotations a ON a.section_id = s.id
        WHERE s.document_id = ?
        GROUP BY s.id
        ORDER BY s.sort_order ASC
    """
    async with db.execute(query, (document_id,)) as cursor:
        rows = await cursor.fetchall()

    return [SectionMetadataResponse(**_section_metadata_kwargs(r)) for r in rows]

@router.get("/{document_id}/sections/{section_id}", response_model=SectionResponse)
async def get_section(document_id: str, section_id: str, db: aiosqlite.Connection = Depends(get_db)):
    # Get section main data
    query = f"""
        SELECT 
            {_SECTION_META_COLS},
            s.html_content, s.plain_text,
            COUNT(a.id) as annotation_count
        FROM sections s
        LEFT JOIN annotations a ON a.section_id = s.id
        WHERE s.document_id = ? AND s.id = ?
        GROUP BY s.id
    """
    async with db.execute(query, (document_id, section_id)) as cursor:
        r = await cursor.fetchone()
        
    if not r:
        raise HTTPException(status_code=404, detail="Section not found")

    # Get footnotes for this section
    async with db.execute("SELECT id, section_id, marker, page, text, html_content, review_status FROM footnotes WHERE section_id = ?", (section_id,)) as cursor:
        fn_rows = await cursor.fetchall()

    footnotes = [FootnoteResponse(
        id=fn["id"],
        section_id=fn["section_id"],
        marker=fn["marker"],
        page=fn["page"],
        text=fn["text"],
        html_content=fn["html_content"],
        review_status=fn["review_status"]
    ) for fn in fn_rows]

    return SectionResponse(
        **_section_metadata_kwargs(r),
        html_content=r["html_content"],
        plain_text=r["plain_text"],
        footnotes=footnotes
    )

@router.get("/{document_id}/sections/by-page/{page_number}", response_model=list[SectionResponse])
async def get_sections_by_page(document_id: str, page_number: int, db: aiosqlite.Connection = Depends(get_db)):
    # Range match covers body pages.  Also include leaves whose footnotes were
    # printed on this PDF page (Customs collector pages sit outside every
    # body-only start/end range until end_page is extended, and even then the
    # notes often belong to earlier citing leaves).
    query = f"""
        SELECT 
            {_SECTION_META_COLS},
            s.html_content, s.plain_text,
            COUNT(a.id) as annotation_count
        FROM sections s
        LEFT JOIN annotations a ON a.section_id = s.id
        WHERE s.document_id = ?
          AND (
            (? >= s.start_page AND ? <= s.end_page)
            OR s.id IN (
              SELECT section_id FROM footnotes
              WHERE page = ?
            )
          )
        GROUP BY s.id
        ORDER BY s.sort_order ASC
    """
    async with db.execute(
        query, (document_id, page_number, page_number, page_number)
    ) as cursor:
        rows = await cursor.fetchall()
        
    results = []
    for r in rows:
        # Fetch footnotes for each section
        async with db.execute("SELECT id, section_id, marker, page, text, html_content, review_status FROM footnotes WHERE section_id = ?", (r["id"],)) as cursor:
            fn_rows = await cursor.fetchall()

        footnotes = [FootnoteResponse(
            id=fn["id"],
            section_id=fn["section_id"],
            marker=fn["marker"],
            page=fn["page"],
            text=fn["text"],
            html_content=fn["html_content"],
            review_status=fn["review_status"]
        ) for fn in fn_rows]

        results.append(SectionResponse(
            **_section_metadata_kwargs(r),
            html_content=r["html_content"],
            plain_text=r["plain_text"],
            footnotes=footnotes
        ))
    return results

@router.patch("/{document_id}/sections/{section_id}/status")
async def update_section_status(
    document_id: str,
    section_id: str,
    body: SectionStatusUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    async with db.execute(
        "SELECT id, review_status FROM sections WHERE document_id = ? AND id = ?",
        (document_id, section_id),
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Section not found")
        from_value = row["review_status"]

    await db.execute(
        "UPDATE sections SET review_status = ? WHERE id = ?",
        (body.review_status, section_id)
    )

    version_id = await events.active_version_id(db, document_id)
    await events.record(
        db,
        actor=actor,
        action="section_status",
        document_id=document_id,
        section_id=section_id,
        version_id=version_id,
        from_value=from_value,
        to_value=body.review_status,
    )

    query = """
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN review_status = 'pending' THEN 1 END) as pending
        FROM sections
        WHERE document_id = ?
    """
    async with db.execute(query, (document_id,)) as cursor:
        r = await cursor.fetchone()
        
    total_sections = r["total"]
    pending_sections = r["pending"]

    if pending_sections == 0:
        doc_status = "completed"
    elif pending_sections == total_sections:
        doc_status = "pending"
    else:
        doc_status = "in_progress"

    await db.execute("UPDATE documents SET status = ? WHERE id = ?", (doc_status, document_id))
    await db.commit()

    return {"section_id": section_id, "review_status": body.review_status, "document_status": doc_status}
