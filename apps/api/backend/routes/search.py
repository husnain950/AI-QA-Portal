import re

from fastapi import APIRouter, Depends, Query

from backend.database import DatabaseConnection, get_db
from backend.deps import ensure_exists
from backend.models import SearchResultResponse

router = APIRouter(prefix="/documents", tags=["search"])

def clean_fts_query(q: str) -> str:
    # PostgreSQL ``simple`` dictionary prefix terms joined with AND.
    q = re.sub(r'[^\w\s\-\*]', '', q)
    words = q.strip().split()
    if not words:
        return ""
    return " & ".join(f"{word.rstrip('*')}:*" for word in words if word.rstrip("*"))


def _safe_snippet(text: str, query: str) -> tuple[str, list[dict], int]:
    """Return a plain excerpt and match offsets relative to that excerpt."""
    source = text or ""
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    matches = list(pattern.finditer(source))
    if not matches:
        excerpt = source[:100]
        return excerpt + ("…" if len(source) > 100 else ""), [], 0
    first = matches[0]
    start = max(0, first.start() - 50)
    end = min(len(source), first.end() + 70)
    prefix = "…" if start else ""
    suffix = "…" if end < len(source) else ""
    excerpt_body = source[start:end]
    ranges = [
        {"start": len(prefix) + match.start() - start, "end": len(prefix) + match.end() - start}
        for match in matches
        if match.start() >= start and match.end() <= end
    ]
    return prefix + excerpt_body + suffix, ranges, len(matches)

@router.get("/{document_id}/search", response_model=list[SearchResultResponse])
async def search_document(
    document_id: str,
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=100),
    db: DatabaseConnection = Depends(get_db)
):
    # Verify document exists
    await ensure_exists(db, "documents", document_id, "Document not found")

    cleaned_q = clean_fts_query(q)
    rows = []

    if cleaned_q:
        query = """
            SELECT s.id AS section_id, s.section_code, s.section_heading,
                   s.chapter_code, s.plain_text,
                   ts_rank(
                     to_tsvector('simple', coalesce(s.section_code,'') || ' ' ||
                       coalesce(s.section_heading,'') || ' ' || coalesce(s.plain_text,'')),
                     to_tsquery('simple', ?)
                   ) AS rank
            FROM sections s
            WHERE s.document_id = ?
              AND to_tsvector('simple', coalesce(s.section_code,'') || ' ' ||
                    coalesce(s.section_heading,'') || ' ' || coalesce(s.plain_text,''))
                  @@ to_tsquery('simple', ?)
            ORDER BY rank DESC, s.sort_order
            LIMIT ?
        """
        async with db.execute(query, (cleaned_q, document_id, cleaned_q, limit)) as cursor:
            rows = await cursor.fetchall()

    # Fallback/alternative search using LIKE if FTS results are empty or query is simple
    if not rows:
        like_pattern = f"%{q}%"
        query = """
            SELECT 
                s.id as section_id,
                s.section_code,
                s.section_heading,
                s.chapter_code,
                s.plain_text
            FROM sections s
            WHERE s.document_id = ? AND (s.plain_text ILIKE ? OR s.section_heading ILIKE ?)
            ORDER BY s.sort_order
            LIMIT ?
        """
        async with db.execute(query, (document_id, like_pattern, like_pattern, limit)) as cursor:
            rows = await cursor.fetchall()

    results = []
    for row in rows:
        snippet, ranges, match_count = _safe_snippet(row["plain_text"] or "", q)
        results.append(SearchResultResponse(
            section_id=row["section_id"],
            section_code=row["section_code"],
            section_heading=row["section_heading"],
            chapter_code=row["chapter_code"],
            snippet=snippet,
            snippet_text=snippet,
            match_ranges=ranges,
            match_count=match_count or 1,
        ))

    return results
