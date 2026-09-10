import re

from fastapi import APIRouter, Depends, HTTPException

from backend.database import DatabaseConnection, get_db
from backend.deps import ensure_exists, require_reviewer
from backend.models import (
    FootnoteResponse,
    QualityFlag,
    SectionMetadataResponse,
    SectionResponse,
    SectionStatusUpdate,
)
from backend.services import events, review_state
from backend.services.parse_quality import deserialize_quality_flags

router = APIRouter(prefix="/documents", tags=["sections"])


_FOOTNOTE_COLS = ("SELECT id, section_id, marker, page, text, html_content, "
                  "review_status FROM footnotes WHERE section_id = ?")

#: A footnote marker is the pipeline's ref, "<printed page>.<marker>" -- "7.2",
#: "9.45", "7.1a".  Splitting it is what makes it sortable.
_REF_RE = re.compile(r"^(\d+)\.(\d+)([a-z]*)$", re.IGNORECASE)


def _footnote_sort_key(marker: str):
    """Order footnotes the way the document prints them.

    The query that reads them carries no ORDER BY, so Postgres returned physical
    row order, which an UPDATE-in-place version sync shuffles: the 30.06.2025
    Customs Act served s.2's fifty notes ending 45, 49, 50, 46, 47, 48 while the
    pipeline JSON had them in order.  QA logged it as a parser defect; it was
    this.

    A plain ``ORDER BY marker`` in SQL does not fix it either -- the marker is
    text, so "7.10" sorts before "7.2".  The three parts have to be compared as
    (page, number, suffix), which is what ``legal_ingest.footnotes.ref_sort_key``
    does on the pipeline side.  It is reimplemented here rather than imported:
    the API deliberately does not depend on the pipeline package at request time.

    Anything that does not parse sorts last, in its own text order, so a marker
    shape nobody anticipated is never silently dropped or interleaved.
    """
    m = _REF_RE.match((marker or "").strip())
    if not m:
        return (1, 0, 0, "", marker or "")
    return (0, int(m.group(1)), int(m.group(2)), m.group(3).lower(), "")


async def _footnotes_for_section(db, section_id) -> list[FootnoteResponse]:
    """Every footnote on one section, in printed order."""
    async with db.execute(_FOOTNOTE_COLS, (section_id,)) as cursor:
        rows = await cursor.fetchall()
    return sorted(
        (FootnoteResponse(
            id=fn["id"],
            section_id=fn["section_id"],
            marker=fn["marker"],
            page=fn["page"],
            text=fn["text"],
            html_content=fn["html_content"],
            review_status=fn["review_status"],
        ) for fn in rows),
        key=lambda fn: _footnote_sort_key(fn.marker),
    )


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


def _source_key_from_row(row) -> str | None:
    try:
        value = row["source_key"]
    except (KeyError, IndexError):
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _section_metadata_kwargs(r) -> dict:
    return dict(
        id=r["id"],
        document_id=r["document_id"],
        instrument_code=r["instrument_code"],
        instrument_heading=r["instrument_heading"],
        chapter_code=r["chapter_code"],
        chapter_heading=r["chapter_heading"],
        part_code=r["part_code"],
        part_heading=r["part_heading"],
        division_code=r["division_code"],
        division_heading=r["division_heading"],
        hierarchy_kind=_hierarchy_kind_from_row(r),
        section_code=r["section_code"],
        section_heading=r["section_heading"],
        source_key=_source_key_from_row(r),
        start_page=r["start_page"],
        end_page=r["end_page"],
        review_status=r["review_status"],
        reviewer_verdict=r["reviewer_verdict"],
        effective_status=r["effective_status"],
        annotation_count=r["annotation_count"],
        sort_order=r["sort_order"],
        quality_flags=_quality_flags_from_row(r),
    )


_SECTION_META_COLS = """
    s.id, s.document_id, s.instrument_code, s.instrument_heading,
    s.chapter_code, s.chapter_heading, s.part_code, s.part_heading,
    s.division_code, s.division_heading, s.hierarchy_kind, s.section_code, s.section_heading,
    s.source_key, s.start_page, s.end_page, s.review_status, s.reviewer_verdict,
    s.effective_status, s.sort_order, s.quality_flags
"""


@router.get("/{document_id}/sections", response_model=list[SectionMetadataResponse])
async def list_sections(document_id: str, db: DatabaseConnection = Depends(get_db)):
    # Check if document exists first
    await ensure_exists(db, "documents", document_id, "Document not found")

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
async def get_section(document_id: str, section_id: str, db: DatabaseConnection = Depends(get_db)):
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

    footnotes = await _footnotes_for_section(db, section_id)

    return SectionResponse(
        **_section_metadata_kwargs(r),
        html_content=r["html_content"],
        plain_text=r["plain_text"],
        footnotes=footnotes
    )

@router.get("/{document_id}/sections/by-page/{page_number}", response_model=list[SectionResponse])
async def get_sections_by_page(document_id: str, page_number: int, db: DatabaseConnection = Depends(get_db)):
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
        footnotes = await _footnotes_for_section(db, r["id"])

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
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    async with db.execute(
        "SELECT id, review_status FROM sections WHERE document_id = ? AND id = ? FOR UPDATE",
        (document_id, section_id),
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Section not found")
        from_value = row["review_status"]

    verdict = "needs_work" if body.review_status == "has_issues" else body.review_status
    try:
        state = await review_state.set_verdict(db, section_id, verdict)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    version_id = await events.active_version_id(db, document_id)
    await events.record(
        db,
        actor=actor,
        action="section_status",
        document_id=document_id,
        section_id=section_id,
        version_id=version_id,
        from_value=from_value,
        to_value=verdict,
    )
    await db.commit()

    return state
