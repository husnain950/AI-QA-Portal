"""Findings queue routes — triage and export automated detector findings."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.database import get_db
from backend.deps import require_reviewer
from backend.runtime import BACKEND_DIR
from backend.services import events, findings_store
from backend.services.editions import family_key_from_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/findings", tags=["findings"])


def _detail(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("detail_json")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}


@router.get("")
async def list_findings(
    triage: Optional[str] = Query("new"),
    detector: Optional[str] = Query(None),
    document_id: Optional[str] = Query(None),
    section_id: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = await findings_store.list_findings(
        db,
        triage=triage,
        detector=detector,
        document_id=document_id,
        section_id=section_id,
        limit=limit,
        offset=offset,
    )

    # Enrich with variant blast radius for the triage queue UI.
    section_ids = [r["section_id"] for r in rows]
    variant_by_section: Dict[str, Dict[str, Any]] = {}
    if section_ids:
        placeholders = ",".join("?" * len(section_ids))
        async with db.execute(
            f"""
            SELECT section_id, variant_key, family_key
            FROM section_variants
            WHERE section_id IN ({placeholders})
            """,
            tuple(section_ids),
        ) as cur:
            for r in await cur.fetchall():
                variant_by_section[r["section_id"]] = dict(r)

    blast: Dict[str, int] = {}
    families_per_variant: Dict[str, set] = {}
    keys = {v["variant_key"] for v in variant_by_section.values() if v.get("variant_key")}
    if keys:
        placeholders = ",".join("?" * len(keys))
        async with db.execute(
            f"""
            SELECT variant_key, family_key, COUNT(*) AS n
            FROM section_variants
            WHERE variant_key IN ({placeholders})
            GROUP BY variant_key, family_key
            """,
            tuple(keys),
        ) as cur:
            for r in await cur.fetchall():
                vk = r["variant_key"]
                blast[vk] = blast.get(vk, 0) + int(r["n"])
                families_per_variant.setdefault(vk, set()).add(r["family_key"])

    # start_page for rows (list_findings omits it)
    start_pages: Dict[str, Any] = {}
    if section_ids:
        placeholders = ",".join("?" * len(section_ids))
        async with db.execute(
            f"SELECT id, start_page FROM sections WHERE id IN ({placeholders})",
            tuple(section_ids),
        ) as cur:
            for r in await cur.fetchall():
                start_pages[r["id"]] = r["start_page"]

    items: List[Dict[str, Any]] = []
    for r in rows:
        detail = _detail(r)
        meta = variant_by_section.get(r["section_id"], {})
        vk = meta.get("variant_key")
        fam = meta.get("family_key") or family_key_from_name(r.get("doc_name") or "")
        items.append(
            {
                **r,
                "document_name": r.get("doc_name"),
                "start_page": start_pages.get(r["section_id"]),
                "variant_key": vk,
                "family_key": fam,
                "family_label": r.get("doc_name"),
                "blast_radius": blast.get(vk, 1) if vk else 1,
                "cross_family": len(families_per_variant.get(vk or "", ())) > 1,
                "summary": detail.get("assertion")
                or (
                    f"{detail.get('prev_len')}→{detail.get('curr_len')}"
                    if detail.get("prev_len") is not None
                    else None
                ),
                "detail": detail,
            }
        )

    async with db.execute(
        "SELECT triage, COUNT(*) AS n FROM findings GROUP BY triage"
    ) as cur:
        by_triage = {row["triage"]: row["n"] for row in await cur.fetchall()}
    total = sum(by_triage.values())
    return {
        "findings": items,
        "stats": {
            "total": total,
            "done": total - by_triage.get("new", 0),
            "left": by_triage.get("new", 0),
            "by_triage": by_triage,
        },
    }


@router.patch("/{finding_id}/status")
async def triage_finding(
    finding_id: int,
    body: dict,
    db: aiosqlite.Connection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    triage = body.get("triage")
    if not triage:
        raise HTTPException(status_code=400, detail="triage is required")

    note = body.get("note")
    result = await findings_store.triage_finding(
        db, finding_id, triage=triage, note=note, actor=actor
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    async with db.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)) as cur:
        row = await cur.fetchone()
    row = dict(row) if row else result

    version_id = await events.active_version_id(db, row["document_id"])
    await events.record(
        db,
        actor=actor,
        action="finding_triage",
        document_id=row["document_id"],
        section_id=row["section_id"],
        version_id=version_id,
        to_value=row.get("triage"),
        detail={"finding_id": finding_id, "note": note},
    )
    await db.commit()
    return row


@router.post("/{finding_id}/export-case")
async def export_finding_case(
    finding_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    async with db.execute(
        """
        SELECT f.*, s.section_code, s.plain_text, d.name AS document_name, d.source_key
        FROM findings f
        JOIN sections s ON s.id = f.section_id
        JOIN documents d ON d.id = f.document_id
        WHERE f.id = ?
        """,
        (finding_id,),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Finding not found")
    row = dict(row)
    detail = _detail(row)
    token = detail.get("token") or detail.get("assertion") or row["detector"]
    case = {
        "description": detail.get("assertion") or f"Portal finding {row['detector']}",
        "applies_to": row.get("source_key") or row["document_name"],
        "target": row["section_code"],
        "check": "plain_not_contains" if row["detector"] == "glyph_split" else "plain_contains",
        "arg": token if isinstance(token, str) else str(token),
        "from_finding_id": finding_id,
        "detector": row["detector"],
        "exported_by": actor,
    }

    root = Path(BACKEND_DIR).resolve()
    for _ in range(4):
        if (root / "data").is_dir() or (root / "apps").is_dir():
            break
        root = root.parent
    out_dir = Path(os.environ.get("CASE_EXPORT_DIR", root / "data" / "exports" / "cases"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"finding_{finding_id}.json"
    out_path.write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")

    await events.record(
        db,
        actor=actor,
        action="finding_export_case",
        document_id=row["document_id"],
        section_id=row["section_id"],
        version_id=await events.active_version_id(db, row["document_id"]),
        detail={"path": str(out_path), "case": case},
    )
    await db.commit()
    return {"path": str(out_path), "case": case}
