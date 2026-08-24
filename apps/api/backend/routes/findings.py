"""Findings queue routes — triage and export automated detector findings."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.database import DatabaseConnection, get_db, json_column
from backend.deps import require_reviewer
from backend.services import events, findings_store, jobs, review_state
from backend.services.editions import family_key_from_name

router = APIRouter(prefix="/findings", tags=["findings"])


def _detail(row: Dict[str, Any]) -> Dict[str, Any]:
    return json_column(row.get("detail_json"), {}) or {}


@router.get("")
async def list_findings(
    triage: Optional[str] = Query("new"),
    detector: Optional[str] = Query(None),
    document_id: Optional[str] = Query(None),
    section_id: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: DatabaseConnection = Depends(get_db),
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
    db: DatabaseConnection = Depends(get_db),
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
    if row.get("section_id"):
        await review_state.refresh_section(db, row["section_id"])
    await db.commit()
    return row


@router.post("/{finding_id}/export-case", status_code=202)
async def export_finding_case(
    finding_id: int,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    async with db.execute(
        """
        SELECT f.*, s.section_code
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
    job = await jobs.enqueue(
        db,
        "regression_bundle",
        payload={"finding_id": finding_id},
        actor=actor,
        idempotency_key=f"finding-regression:{finding_id}:{row['triage']}:{row['last_seen_at']}",
    )
    await events.record(
        db,
        actor=actor,
        action="finding_export_case",
        document_id=row["document_id"],
        section_id=row["section_id"],
        version_id=await events.active_version_id(db, row["document_id"]),
        detail={"job_id": job["id"], "format": "downloadable_zip"},
    )
    await db.commit()
    return {"job_id": job["id"], "state": job["state"]}
