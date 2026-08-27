"""Cursor-paginated v2 read contracts for Library, Review, and Triage."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.database import DatabaseConnection, get_db, json_column
from backend.routes.documents import _document_response
from backend.routes.search import _safe_snippet
from backend.routes.v2.pagination import decode_cursor, encode_cursor
from backend.services import library_query as lq
from backend.services.clock import iso_now
from backend.services.corpus_lanes import LANE_ORDER

router = APIRouter(tags=["v2-library"])

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _fingerprint(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


def _csv(raw: Optional[str]) -> tuple:
    return tuple(part.strip() for part in (raw or "").split(",") if part.strip())


def _flag(raw: Optional[str]) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "flagged")


def _validated(values: tuple, allowed: tuple, name: str) -> tuple:
    unknown = [value for value in values if value not in allowed]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unknown {name}: {', '.join(unknown)} (allowed: {', '.join(allowed)})",
        )
    return values


def _date_param(raw: Optional[str], name: str) -> str:
    value = (raw or "").strip()
    if value and not _DATE_RE.match(value):
        raise HTTPException(status_code=422, detail=f"{name} must be YYYY-MM-DD")
    return value


def _years(raw: Optional[str]) -> tuple:
    values = _csv(raw)
    if not values:
        return ()
    if not all(re.fullmatch(r"\d{4}", value) for value in values):
        raise HTTPException(status_code=422, detail="year must be a comma list of 4-digit years")
    return tuple(int(value) for value in values)


def _library_filters(
    q: Optional[str],
    status: Optional[str],
    lane: Optional[str],
    corpus_lane: Optional[str],
    kind: Optional[str],
    health: Optional[str],
    review: Optional[str],
    flagged: Optional[str],
    annotations: Optional[str],
    year: Optional[str],
    year_from: Optional[int],
    year_to: Optional[int],
    added_after: Optional[str],
    added_before: Optional[str],
    pages_min: Optional[int],
    pages_max: Optional[int],
    tag: Optional[str],
    ids: Optional[str],
) -> lq.LibraryFilters:
    """Normalize + validate the Library query string into the shared filter shape."""
    lanes = _csv(lane) or _csv(corpus_lane)
    status_value = (status or "").strip()
    if status_value:
        _validated((status_value,), lq.DOC_STATUSES, "status")
    tags = _csv(tag)
    if not all(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,49}", value) for value in tags):
        raise HTTPException(status_code=422, detail="tag values must be lowercase slugs")
    return lq.LibraryFilters(
        q=(q or "").strip(),
        lanes=_validated(lanes, LANE_ORDER, "lane"),
        kinds=_validated(_csv(kind), lq.SOURCE_KINDS + ("unknown",), "kind"),
        health=_validated(_csv(health), lq.HEALTH_FACETS, "health"),
        review=_validated(_csv(review), lq.REVIEW_FACETS, "review"),
        flagged=_flag(flagged),
        annotations=_flag(annotations),
        status=status_value,
        years=_years(year),
        year_from=year_from,
        year_to=year_to,
        added_after=_date_param(added_after, "added_after"),
        added_before=_date_param(added_before, "added_before"),
        pages_min=pages_min,
        pages_max=pages_max,
        tags=tags,
        ids=_csv(ids)[: lq.MAX_IDS],
    )


def _sort_param(sort: str) -> str:
    if sort not in lq.SORT_VALUES:
        raise HTTPException(
            status_code=422,
            detail=f"unknown sort: {sort} (allowed: {', '.join(lq.SORT_VALUES)})",
        )
    return sort


@router.get("/documents")
async def documents_page(
    cursor: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(None, max_length=200),
    status: Optional[str] = None,
    lane: Optional[str] = Query(None, max_length=400),
    corpus_lane: Optional[str] = None,
    kind: Optional[str] = Query(None, max_length=200),
    health: Optional[str] = Query(None, max_length=200),
    review: Optional[str] = Query(None, max_length=200),
    flagged: Optional[str] = None,
    annotations: Optional[str] = None,
    year: Optional[str] = Query(None, max_length=200),
    year_from: Optional[int] = Query(None, ge=1800, le=2200),
    year_to: Optional[int] = Query(None, ge=1800, le=2200),
    added_after: Optional[str] = None,
    added_before: Optional[str] = None,
    pages_min: Optional[int] = Query(None, ge=0),
    pages_max: Optional[int] = Query(None, ge=0),
    tag: Optional[str] = Query(None, max_length=400),
    ids: Optional[str] = Query(None, max_length=20000),
    sort: str = Query("name", max_length=20),
    db: DatabaseConnection = Depends(get_db),
):
    """One page of the Library: filtered, sorted, and counted server-side so the
    UI never has to hold the whole corpus to browse it."""
    filters = _library_filters(
        q, status, lane, corpus_lane, kind, health, review, flagged, annotations,
        year, year_from, year_to, added_after, added_before, pages_min, pages_max, tag, ids,
    )
    sort = _sort_param(sort)
    fp = _fingerprint(filters.fingerprint_parts(), sort)
    offset = decode_cursor(cursor, fp)
    where, params = lq.build_where(filters)
    order, order_params = lq.order_sql(sort, filters.q)

    async with db.execute(
        f"SELECT COUNT(*) {lq.FROM_DOCUMENTS}{where}", params
    ) as cur:
        total = int((await cur.fetchone())[0])
    async with db.execute(
        f"{lq.PAGE_SELECT} {lq.FROM_DOCUMENTS}{where} "
        f"ORDER BY {order} LIMIT ? OFFSET ?",
        (*params, *order_params, limit, offset),
    ) as cur:
        rows = await cur.fetchall()
    items = [(await _document_response(db, row)).model_dump() for row in rows]
    next_offset = offset + len(rows)
    return {
        "items": items,
        "total": total,
        "next_cursor": encode_cursor(next_offset, fp) if next_offset < total else None,
        "refreshed_at": iso_now(),
    }


@router.get("/documents/facets")
async def documents_facets(
    q: Optional[str] = Query(None, max_length=200),
    status: Optional[str] = None,
    lane: Optional[str] = Query(None, max_length=400),
    corpus_lane: Optional[str] = None,
    kind: Optional[str] = Query(None, max_length=200),
    health: Optional[str] = Query(None, max_length=200),
    review: Optional[str] = Query(None, max_length=200),
    flagged: Optional[str] = None,
    annotations: Optional[str] = None,
    year: Optional[str] = Query(None, max_length=200),
    year_from: Optional[int] = Query(None, ge=1800, le=2200),
    year_to: Optional[int] = Query(None, ge=1800, le=2200),
    added_after: Optional[str] = None,
    added_before: Optional[str] = None,
    pages_min: Optional[int] = Query(None, ge=0),
    pages_max: Optional[int] = Query(None, ge=0),
    tag: Optional[str] = Query(None, max_length=400),
    ids: Optional[str] = Query(None, max_length=20000),
    db: DatabaseConnection = Depends(get_db),
):
    """Live counts for the filter panel. Each dimension's counts respect every
    other active filter but not its own, so multi-select never collapses the
    list you are picking from."""
    filters = _library_filters(
        q, status, lane, corpus_lane, kind, health, review, flagged, annotations,
        year, year_from, year_to, added_after, added_before, pages_min, pages_max, tag, ids,
    )

    async def count_by(expression: str, exclude: str) -> dict:
        where, params = lq.build_where(filters, exclude=exclude)
        async with db.execute(
            f"SELECT {expression} AS k, COUNT(*) AS n {lq.FROM_DOCUMENTS}{where} "
            "GROUP BY k",
            params,
        ) as cur:
            return {row["k"]: int(row["n"]) for row in await cur.fetchall()}

    lanes = await count_by(lq.LANE_SQL, "lane")
    kinds_raw = await count_by(lq.KIND_SQL, "kind")
    kinds = {("unknown" if key is None else key): n for key, n in kinds_raw.items()}
    health = await count_by(lq.HEALTH_SQL, "health")
    review = await count_by(lq.REVIEW_SQL, "review")

    where, params = lq.build_where(filters, exclude="year")
    # Row-level NULL screening belongs in WHERE; HAVING cannot see the y alias.
    years_where = where + (" AND " if where else " WHERE ") + f"({lq.YEAR_SQL}) IS NOT NULL"
    async with db.execute(
        f"SELECT {lq.YEAR_SQL} AS y, COUNT(*) AS n {lq.FROM_DOCUMENTS}{years_where} "
        "GROUP BY y ORDER BY y DESC",
        params,
    ) as cur:
        years = [{"year": int(row["y"]), "count": int(row["n"])} for row in await cur.fetchall()]

    where, params = lq.build_where(filters, exclude="tags")
    async with db.execute(
        f"""
        SELECT tag, COUNT(*) AS n
        {lq.FROM_DOCUMENTS}
        JOIN LATERAL jsonb_array_elements_text({lq.TAGS_SQL}) AS tag ON TRUE
        {where + " AND " if where else " WHERE "}d.provenance IS JSON
        GROUP BY tag ORDER BY n DESC, tag LIMIT 50
        """,
        params,
    ) as cur:
        tags = [{"tag": row["tag"], "count": int(row["n"])} for row in await cur.fetchall()]

    where, params = lq.build_where(filters)
    async with db.execute(
        f"""
        SELECT COUNT(*) AS documents,
               COUNT(*) FILTER (WHERE stats.has_issues > 0) AS flagged,
               COUNT(*) FILTER (WHERE stats.open_annotations > 0) AS annotated,
               COUNT(*) FILTER (WHERE {lq.REVIEW_SQL} = 'complete') AS complete
        {lq.FROM_DOCUMENTS}{where}
        """,
        params,
    ) as cur:
        totals_row = await cur.fetchone()
    async with db.execute(
        f"""
        SELECT COUNT(*) AS documents,
               COUNT(*) FILTER (WHERE stats.has_issues > 0) AS flagged,
               COUNT(*) FILTER (WHERE {lq.REVIEW_SQL} = 'complete') AS complete
        {lq.FROM_DOCUMENTS}
        """
    ) as cur:
        library_row = await cur.fetchone()

    return {
        "lanes": lanes,
        "kinds": kinds,
        "health": health,
        "review": review,
        "years": years,
        "tags": tags,
        "totals": {
            "documents": int(totals_row["documents"]),
            "flagged": int(totals_row["flagged"]),
            "annotated": int(totals_row["annotated"]),
            "complete": int(totals_row["complete"]),
        },
        "library": {
            "documents": int(library_row["documents"]),
            "flagged": int(library_row["flagged"]),
            "complete": int(library_row["complete"]),
        },
        "library_total": int(library_row["documents"]),
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
