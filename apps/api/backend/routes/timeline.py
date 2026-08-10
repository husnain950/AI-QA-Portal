"""Cross-edition timeline for a (family, section_code)."""

from __future__ import annotations

from typing import Any, Dict, List

import aiosqlite
from fastapi import APIRouter, Depends

from backend.database import get_db
from backend.services.detectors import family_key as family_key_fn
from backend.services.variants import timeline as variants_timeline
from backend.services.versions import _text_diff

router = APIRouter(tags=["timeline"])


@router.get("/timeline/{family}/{section_code}")
async def timeline(
    family: str,
    section_code: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    fam = family_key_fn(family)
    rows = await variants_timeline(db, family=fam, section_code=section_code)
    if not rows:
        # Fallback: try raw family param
        rows = await variants_timeline(db, family=family.lower(), section_code=section_code)

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
        "family_label": family,
        "section_code": section_code,
        "section_heading": heading,
        "events": events,
        "editions": len(rows),
    }
