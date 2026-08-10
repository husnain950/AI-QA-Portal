import re

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.database import get_db
from backend.models import SearchResultResponse

router = APIRouter(prefix="/documents", tags=["search"])

def clean_fts_query(q: str) -> str:
    # Remove special chars that might crash FTS5 search
    q = re.sub(r'[^\w\s\-\*]', '', q)
    # Trim and split into words
    words = q.strip().split()
    if not words:
        return ""
    # Format words as search terms (implicit AND, with wildcard option)
    terms = []
    for word in words:
        if word.endswith("*"):
            terms.append(word)
        else:
            terms.append(f"{word}*")
    return " ".join(terms)

@router.get("/{document_id}/search", response_model=list[SearchResultResponse])
async def search_document(
    document_id: str,
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=100),
    db: aiosqlite.Connection = Depends(get_db)
):
    # Verify document exists
    async with db.execute("SELECT 1 FROM documents WHERE id = ?", (document_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Document not found")

    cleaned_q = clean_fts_query(q)
    results = []

    if cleaned_q:
        try:
            # Try FTS5 search
            # plain_text column is index 4 in sections_fts
            query = """
                SELECT 
                    s.id as section_id,
                    s.section_code,
                    s.section_heading,
                    s.chapter_code,
                    snippet(sections_fts, 4, '<b>', '</b>', '...', 15) as snippet_content
                FROM sections_fts fts
                JOIN sections s ON s.rowid = fts.rowid
                WHERE s.document_id = ? AND sections_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            async with db.execute(query, (document_id, cleaned_q, limit)) as cursor:
                rows = await cursor.fetchall()
                
            for r in rows:
                results.append(SearchResultResponse(
                    section_id=r["section_id"],
                    section_code=r["section_code"],
                    section_heading=r["section_heading"],
                    chapter_code=r["chapter_code"],
                    snippet=r["snippet_content"],
                    match_count=1
                ))
        except aiosqlite.OperationalError as e:
            # Fallback to LIKE if FTS5 query fails or throws an operational error
            print(f"FTS5 search error: {e}. Falling back to LIKE search.")
            results = []

    # Fallback/alternative search using LIKE if FTS results are empty or query is simple
    if not results:
        like_pattern = f"%{q}%"
        query = """
            SELECT 
                s.id as section_id,
                s.section_code,
                s.section_heading,
                s.chapter_code,
                s.plain_text
            FROM sections s
            WHERE s.document_id = ? AND (s.plain_text LIKE ? OR s.section_heading LIKE ?)
            LIMIT ?
        """
        async with db.execute(query, (document_id, like_pattern, like_pattern, limit)) as cursor:
            rows = await cursor.fetchall()

        for r in rows:
            text = r["plain_text"] or ""
            # Simple snippet extraction in python
            match_idx = text.lower().find(q.lower())
            if match_idx != -1:
                start = max(0, match_idx - 40)
                end = min(len(text), match_idx + len(q) + 40)
                snippet_text = text[start:end]
                # Wrap matching term in bold tags
                pattern = re.compile(re.escape(q), re.IGNORECASE)
                snippet_html = pattern.sub(lambda m: f"<b>{m.group(0)}</b>", snippet_text)
                if start > 0:
                    snippet_html = "..." + snippet_html
                if end < len(text):
                    snippet_html = snippet_html + "..."
            else:
                snippet_html = text[:100] + "..." if len(text) > 100 else text

            results.append(SearchResultResponse(
                section_id=r["section_id"],
                section_code=r["section_code"],
                section_heading=r["section_heading"],
                chapter_code=r["chapter_code"],
                snippet=snippet_html,
                match_count=1
            ))

    return results
