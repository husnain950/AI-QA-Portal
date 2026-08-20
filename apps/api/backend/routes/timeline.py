"""Cross-edition timeline for a (family, section_code)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, Query

from backend.database import DatabaseConnection, get_db
from backend.services.detectors import family_key as family_key_fn
from backend.services.editions import family_key_from_name
from backend.services.variants import rebuild_document
from backend.services.variants import timeline as variants_timeline
from backend.services.versions import _text_diff

router = APIRouter(tags=["timeline"])


def _family_candidates(family: str) -> List[str]:
    raw = (family or "").strip()
    if not raw:
        return []
    seen = set()
    out: List[str] = []
    for candidate in (
        family_key_fn(raw),
        raw.lower(),
        family_key_from_name(raw),
    ):
        key = (candidate or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


async def _timeline_rows_for_family(
    db: DatabaseConnection,
    family: str,
    section_code: str,
) -> Tuple[str, List[Dict[str, Any]]]:
    last_key = family_key_fn(family) if family else ""
    for fam in _family_candidates(family):
        last_key = fam
        rows = await variants_timeline(db, family=fam, section_code=section_code)
        if rows:
            return fam, rows

    # Review/editions keys strip parentheses and keep the year; stored variant
    # keys do the opposite. Bridge via the document name that produced the row.
    target = family_key_from_name(family)
    async with db.execute(
        """
        SELECT DISTINCT sv.family_key, d.name AS doc_name
        FROM section_variants sv
        JOIN documents d ON d.id = sv.document_id
        WHERE sv.section_code = ?
        """,
        (section_code,),
    ) as cursor:
        pairs = await cursor.fetchall()
    seen = set()
    for pair in pairs:
        stored = pair["family_key"]
        editions_key = family_key_from_name(pair["doc_name"] or "")
        if editions_key != target and editions_key != (family or "").strip().lower():
            continue
        if stored in seen:
            continue
        seen.add(stored)
        rows = await variants_timeline(db, family=stored, section_code=section_code)
        if rows:
            return stored, rows
    return last_key, []


async def _resolve_from_section_id(
    db: DatabaseConnection, section_id: str
) -> Tuple[str, str, List[Dict[str, Any]], Optional[str]]:
    """Return (family_key, section_code, rows, family_label)."""
    async with db.execute(
        """
        SELECT family_key, section_code
        FROM section_variants
        WHERE section_id = ?
        """,
        (section_id,),
    ) as cursor:
        stored = await cursor.fetchone()
    if stored:
        rows = await variants_timeline(
            db, family=stored["family_key"], section_code=stored["section_code"]
        )
        label = rows[0].get("doc_name") if rows else stored["family_key"]
        return stored["family_key"], stored["section_code"], rows, label

    async with db.execute(
        """
        SELECT s.section_code, s.document_id, d.name AS doc_name
        FROM sections s
        JOIN documents d ON d.id = s.document_id
        WHERE s.id = ?
        """,
        (section_id,),
    ) as cursor:
        section = await cursor.fetchone()
    if not section:
        return "", "", [], None

    await rebuild_document(db, section["document_id"])
    await db.commit()
    async with db.execute(
        """
        SELECT family_key, section_code
        FROM section_variants
        WHERE section_id = ?
        """,
        (section_id,),
    ) as cursor:
        stored = await cursor.fetchone()
    if stored:
        rows = await variants_timeline(
            db, family=stored["family_key"], section_code=stored["section_code"]
        )
        label = rows[0].get("doc_name") if rows else section["doc_name"]
        return stored["family_key"], stored["section_code"], rows, label

    fam = family_key_fn(section["doc_name"])
    rows = await variants_timeline(
        db, family=fam, section_code=section["section_code"]
    )
    return fam, section["section_code"], rows, section["doc_name"]


def _events_payload(
    *,
    fam: str,
    family_label: str,
    section_code: str,
    rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    i = 0
    while i < len(rows):
        cur = rows[i]
        j = i + 1
        while j < len(rows) and rows[j]["text_sha"] == cur["text_sha"]:
            j += 1
        run = rows[i:j]
        if i == 0:
            kind = "first"
        elif len(run) > 1:
            kind = "unchanged"
        else:
            prev = rows[i - 1]
            if prev["html_shape"] != cur["html_shape"] and prev["text_sha"] == cur["text_sha"]:
                kind = "markup_only"
            elif prev["text_sha"] != cur["text_sha"]:
                kind = "changed"
            else:
                kind = "unchanged"

        word_delta = None
        diff_lines = None
        if kind in ("changed", "markup_only") and i > 0:
            prev = rows[i - 1]
            diff_lines = _text_diff(prev.get("plain_text") or "", cur.get("plain_text") or "")
            pw = (prev.get("plain_text") or "").split()
            cw = (cur.get("plain_text") or "").split()
            word_delta = f"+{max(0, len(cw) - len(pw))} / −{max(0, len(pw) - len(cw))} words"

        years = [r.get("edition_date") or "year unknown" for r in run]
        span = f"{years[0]}–{years[-1]}" if len(run) > 1 else ""
        events.append(
            {
                "kind": kind if not (len(run) > 1 and kind != "first") else "unchanged",
                "year": cur.get("edition_date"),
                "year_label": cur.get("edition_date") or "year unknown",
                "count": len(run),
                "span": span,
                "word_delta": word_delta,
                "diff": {"lines": diff_lines} if diff_lines else None,
                "document_id": cur["document_id"],
                "section_id": cur["section_id"],
                "document_name": cur.get("doc_name"),
            }
        )
        i = j

    heading = rows[0].get("section_heading") if rows else None
    return {
        "family": fam,
        "family_label": family_label,
        "section_code": section_code,
        "section_heading": heading,
        "events": events,
        "editions": len(rows),
    }


@router.get("/timeline")
async def timeline_query(
    section_id: Optional[str] = Query(None),
    family: Optional[str] = Query(None),
    section_code: Optional[str] = Query(None),
    db: DatabaseConnection = Depends(get_db),
):
    if section_id:
        fam, code, rows, label = await _resolve_from_section_id(db, section_id)
        return _events_payload(
            fam=fam,
            family_label=label or family or fam,
            section_code=code,
            rows=rows,
        )
    if family and section_code:
        fam, rows = await _timeline_rows_for_family(db, family, section_code)
        return _events_payload(
            fam=fam,
            family_label=family,
            section_code=section_code,
            rows=rows,
        )
    return _events_payload(fam="", family_label=family or "", section_code=section_code or "", rows=[])


@router.get("/timeline/{family}/{section_code}")
async def timeline(
    family: str,
    section_code: str,
    db: DatabaseConnection = Depends(get_db),
):
    fam, rows = await _timeline_rows_for_family(db, family, section_code)
    return _events_payload(
        fam=fam,
        family_label=family,
        section_code=section_code,
        rows=rows,
    )
