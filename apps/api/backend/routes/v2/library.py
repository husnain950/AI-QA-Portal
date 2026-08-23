"""Cursor-paginated v2 read contracts for Library, Review, and Triage."""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.database import DatabaseConnection, get_db, json_column
from backend.routes.documents import _document_response_by_id
from backend.routes.search import _safe_snippet
from backend.routes.v2.pagination import decode_cursor, encode_cursor
from backend.services.clock import iso_now

router = APIRouter(tags=["v2-library"])


def _fingerprint(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


@router.get("/documents")
async def documents_page(
    cursor: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    q: Optional[str] = None,
    status: Optional[str] = None,
    corpus_lane: Optional[str] = None,
    sort: str = Query("name", pattern="^(name|newest|risk)$"),
    db: DatabaseConnection = Depends(get_db),
):
    fp = _fingerprint(q, status, corpus_lane, sort)
    offset = decode_cursor(cursor, fp)
    clauses: list[str] = []
    params: list = []
    if q:
        clauses.append("d.name ILIKE ?")
        params.append(f"%{q.strip()}%")
    if status:
        clauses.append("d.status = ?")
        params.append(status)
    if corpus_lane:
        clauses.append("d.corpus_lane = ?")
        params.append(corpus_lane)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    order = {
        "name": "lower(d.name), d.id",
        "newest": "d.uploaded_at DESC, d.id",
        "risk": "CASE d.status WHEN 'blocked' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END, lower(d.name), d.id",
    }[sort]
    async with db.execute(f"SELECT COUNT(*) FROM documents d{where}", params) as cur:
        total = int((await cur.fetchone())[0])
    async with db.execute(
        f"SELECT d.id FROM documents d{where} ORDER BY {order} LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ) as cur:
        ids = [row["id"] for row in await cur.fetchall()]
    items = [(await _document_response_by_id(db, document_id)).model_dump() for document_id in ids]
    next_offset = offset + len(ids)
    return {
        "items": items,
        "total": total,
        "next_cursor": encode_cursor(next_offset, fp) if next_offset < total else None,
        "refreshed_at": iso_now(),
    }


@router.get("/documents/{document_id}/sections")
async def sections_page(
    document_id: str,
    cursor: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    status: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1),
    db: DatabaseConnection = Depends(get_db),
):
    fp = _fingerprint(document_id, status, page)
    offset = decode_cursor(cursor, fp)
    clauses = ["document_id = ?"]
    params: list = [document_id]
    if status:
        clauses.append("effective_status = ?")
        params.append(status)
    if page:
        clauses.append("start_page <= ? AND end_page >= ?")
        params.extend((page, page))
    where = " WHERE " + " AND ".join(clauses)
    async with db.execute(f"SELECT COUNT(*) FROM sections{where}", params) as cur:
        total = int((await cur.fetchone())[0])
    async with db.execute(
        f"""
        SELECT id, document_id, section_code, section_heading, start_page, end_page,
               sort_order, reviewer_verdict, effective_status, review_status,
               sanitizer_version, sanitized_changed
        FROM sections{where} ORDER BY sort_order, id LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    ) as cur:
        items = [dict(row) for row in await cur.fetchall()]
    next_offset = offset + len(items)
    return {
        "items": items,
        "total": total,
        "next_cursor": encode_cursor(next_offset, fp) if next_offset < total else None,
        "refreshed_at": iso_now(),
    }


@router.get("/findings")
async def findings_page(
    cursor: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    triage: Optional[str] = "new",
    detector: Optional[str] = None,
    severity: Optional[str] = None,
    document_id: Optional[str] = None,
    q: Optional[str] = Query(None, max_length=200),
    sort: str = Query("risk", pattern="^(risk|score|blast|page|newest)$"),
    db: DatabaseConnection = Depends(get_db),
):
    fp = _fingerprint(triage, detector, severity, document_id, q, sort)
    offset = decode_cursor(cursor, fp)
    clauses: list[str] = []
    params: list = []
    for column, value in (
        ("f.triage", triage),
        ("f.detector", detector),
        ("f.severity", severity),
        ("f.document_id", document_id),
    ):
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    if q and q.strip():
        clauses.append(
            """
            (f.detector ILIKE ? OR d.name ILIKE ? OR s.section_code ILIKE ?
             OR s.section_heading ILIKE ? OR CAST(f.detail_json AS text) ILIKE ?)
            """
        )
        needle = f"%{q.strip()}%"
        params.extend([needle] * 5)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    order = {
        "risk": (
            "CASE f.severity WHEN 'error' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, "
            "f.score DESC NULLS LAST, f.id"
        ),
        "score": "f.score DESC NULLS LAST, f.id",
        "blast": "GREATEST(COALESCE(vb.blast_radius, 1), 1) DESC, f.score DESC NULLS LAST, f.id",
        "page": "s.start_page NULLS LAST, d.name, f.id",
        "newest": "f.first_seen_at DESC, f.id",
    }[sort]
    joins = """
        LEFT JOIN sections s ON s.id = f.section_id
        JOIN documents d ON d.id = f.document_id
        LEFT JOIN section_variants sv ON sv.section_id = f.section_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS blast_radius, COUNT(DISTINCT family_key) AS family_count
            FROM section_variants grouped WHERE grouped.variant_key = sv.variant_key
        ) vb ON TRUE
    """
    async with db.execute(f"SELECT COUNT(*) FROM findings f {joins}{where}", params) as cur:
        total = int((await cur.fetchone())[0])
    async with db.execute(
        f"""
        SELECT f.*, s.section_code, s.section_heading, s.start_page,
               d.name AS document_name, d.name AS family_label,
               sv.family_key, sv.variant_key,
               GREATEST(COALESCE(vb.blast_radius, 1), 1) AS blast_radius,
               COALESCE(vb.family_count, 0) > 1 AS cross_family
        FROM findings f
        {joins}
        {where} ORDER BY {order} LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    ) as cur:
        items = []
        for row in await cur.fetchall():
            item = dict(row)
            detail = json_column(item.get("detail_json"), {}) or {}
            item["detail"] = detail
            item["summary"] = detail.get("assertion")
            items.append(item)
    async with db.execute("SELECT triage, COUNT(*) AS n FROM findings GROUP BY triage") as cur:
        by_triage = {row["triage"]: int(row["n"]) for row in await cur.fetchall()}
    all_total = sum(by_triage.values())
    next_offset = offset + len(items)
    return {
        "items": items,
        "total": total,
        "next_cursor": encode_cursor(next_offset, fp) if next_offset < total else None,
        "refreshed_at": iso_now(),
        "stats": {
            "total": all_total,
            "done": all_total - by_triage.get("new", 0),
            "left": by_triage.get("new", 0),
            "by_triage": by_triage,
        },
    }


@router.get("/search")
async def search_page(
    q: str = Query(..., min_length=1, max_length=200),
    document_id: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: DatabaseConnection = Depends(get_db),
):
    term = q.strip()
    fp = _fingerprint(term, document_id)
    offset = decode_cursor(cursor, fp)
    clauses = ["s.plain_text ILIKE ?"]
    params: list = [f"%{term}%"]
    if document_id:
        clauses.append("s.document_id = ?")
        params.append(document_id)
    where = " WHERE " + " AND ".join(clauses)
    async with db.execute(f"SELECT COUNT(*) FROM sections s{where}", params) as cur:
        total = int((await cur.fetchone())[0])
    async with db.execute(
        f"""
        SELECT s.id AS section_id, s.document_id, s.section_code, s.section_heading,
               s.plain_text FROM sections s{where}
        ORDER BY s.document_id, s.sort_order, s.id LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    ) as cur:
        rows = await cur.fetchall()
    items = []
    for row in rows:
        snippet, ranges, matches = _safe_snippet(row["plain_text"] or "", term)
        items.append(
            {
                "section_id": row["section_id"],
                "document_id": row["document_id"],
                "section_code": row["section_code"],
                "section_heading": row["section_heading"],
                "snippet_text": snippet,
                "match_ranges": ranges,
                "match_count": matches,
            }
        )
    next_offset = offset + len(items)
    return {
        "items": items,
        "total": total,
        "next_cursor": encode_cursor(next_offset, fp) if next_offset < total else None,
        "refreshed_at": iso_now(),
    }
