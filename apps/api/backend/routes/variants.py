"""Variant and timeline routes."""

from __future__ import annotations

from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.database import get_db
from backend.deps import require_reviewer
from backend.services import events, variants

router = APIRouter(prefix="/variants", tags=["variants"])


@router.get("")
async def list_variants(
    family: Optional[str] = Query(None),
    section_code: Optional[str] = Query(None),
    min_size: int = Query(2, ge=1),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = await variants.get_variants(
        db, family=family, section_code=section_code, limit=limit, offset=offset
    )
    filtered = [r for r in rows if int(r.get("edition_count") or 0) >= min_size]
    return {"variants": filtered}


@router.get("/{variant_key}")
async def get_variant(
    variant_key: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    members = await variants.get_variant_detail(db, variant_key)
    if not members:
        raise HTTPException(status_code=404, detail="Variant not found")
    families = {m["family_key"] for m in members}
    return {
        "variant_key": variant_key,
        "count": len(members),
        "cross_family": len(families) > 1,
        "families": sorted(families),
        "members": [
            {
                "section_id": m["section_id"],
                "document_id": m["document_id"],
                "document_name": m.get("doc_name"),
                "section_code": m.get("section_code"),
                "section_heading": m.get("section_heading"),
                "review_status": m.get("review_status"),
                "family_key": m.get("family_key"),
                "content_sha": m.get("text_sha"),
            }
            for m in members
        ],
        "assertion": (
            f"These {len(members)} leaves are byte-identical in text and block structure "
            f"(sha {variant_key[:12]}…). Approving covers all of them."
        ),
    }


@router.post("/{variant_key}/approve")
async def approve_variant(
    variant_key: str,
    db: aiosqlite.Connection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    # Triage queue may approve 1–2 edition groups; identity still holds.
    result = await variants.approve_variant(
        db, variant_key, actor=actor, min_editions=1
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    members = await variants.get_variant_detail(db, variant_key)
    source_id = result.get("source_id")
    source = next((m for m in members if m["section_id"] == source_id), members[0] if members else None)
    version_id = (
        await events.active_version_id(db, source["document_id"]) if source else None
    )
    event_id = await events.record(
        db,
        actor=actor,
        action="variant_approve",
        document_id=source["document_id"] if source else None,
        section_id=source["section_id"] if source else None,
        version_id=version_id,
        detail={"variant_key": variant_key, "inherited": result.get("inherited", 0)},
    )
    await db.commit()
    granted = int(result.get("inherited", 0))
    return {
        **result,
        "granted": granted,
        "count": granted + 1,
        "event_id": event_id,
        "source_section_id": source_id,
    }


@router.delete("/{variant_key}/approve")
async def revoke_variant_approval(
    variant_key: str,
    db: aiosqlite.Connection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    members = await variants.get_variant_detail(db, variant_key)
    result = await variants.revoke_variant_approval(db, variant_key)

    if members:
        await events.record(
            db,
            actor=actor,
            action="variant_revoke",
            document_id=members[0]["document_id"],
            section_id=members[0]["section_id"],
            version_id=await events.active_version_id(db, members[0]["document_id"]),
            detail={"variant_key": variant_key, **result},
        )
    await db.commit()
    return {"variant_key": variant_key, **result}
