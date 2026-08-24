"""Canonical identity and attribution-only sign-off."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.database import DatabaseConnection, get_db
from backend.deps import require_reviewer
from backend.services import events, jobs
from backend.services.identity import confirm_identity, family_id_for_slug

router = APIRouter(tags=["v2-governance"])


class FamilyCreate(BaseModel):
    canonical_title: str = Field(min_length=1, max_length=500)
    canonical_slug: str = Field(min_length=1, max_length=500)
    aliases: list[str] = Field(default_factory=list)


@router.post("/statute-families", status_code=201)
async def create_family(
    body: FamilyCreate,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    slug = re.sub(r"[^a-z0-9]+", "-", body.canonical_slug.lower()).strip("-")
    family_id = family_id_for_slug(slug)
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """
        INSERT INTO statute_families
            (id, canonical_title, canonical_slug, aliases, created_at, confirmed_at, confirmed_by)
        VALUES (?, ?, ?, CAST(? AS jsonb), ?, ?, ?)
        ON CONFLICT (canonical_slug) DO UPDATE SET canonical_title = excluded.canonical_title,
            aliases = excluded.aliases, confirmed_at = excluded.confirmed_at,
            confirmed_by = excluded.confirmed_by
        """,
        (family_id, body.canonical_title.strip(), slug, json.dumps(body.aliases), now, now, actor),
    )
    await db.commit()
    return {"id": family_id, "canonical_title": body.canonical_title.strip(), "canonical_slug": slug}


class IdentityConfirm(BaseModel):
    family_id: str
    display_title: str = Field(min_length=1, max_length=500)
    edition_date: str | None = None
    amendment_through_date: str | None = None


@router.put("/documents/{document_id}/identity")
async def set_identity(
    document_id: str,
    body: IdentityConfirm,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    try:
        await confirm_identity(
            db,
            document_id,
            family_id=body.family_id,
            display_title=body.display_title.strip(),
            edition_date=body.edition_date,
            amendment_through_date=body.amendment_through_date,
            actor=actor,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="statute family not found") from exc
    await events.record(
        db,
        actor=actor,
        action="document_identity_confirmed",
        document_id=document_id,
        detail=body.model_dump(),
    )
    await db.commit()
    return {**body.model_dump(), "identity_status": "confirmed"}


class SignoffRequest(BaseModel):
    stage: str


@router.post("/documents/{document_id}/signoff")
async def signoff(
    document_id: str,
    body: SignoffRequest,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    async with db.execute("SELECT * FROM documents WHERE id = ? FOR UPDATE", (document_id,)) as cur:
        document = await cur.fetchone()
    if not document:
        raise HTTPException(status_code=404, detail="document not found")
    if body.stage == "reviewed":
        if document["status"] != "approved":
            raise HTTPException(status_code=409, detail="all leaves must be effectively approved")
        await db.execute(
            """
            UPDATE documents SET signoff_stage = 'reviewed', signoff_reviewed_by = ?,
                                 signoff_legal_by = NULL WHERE id = ?
            """,
            (actor, document_id),
        )
    elif body.stage == "legal_approved":
        if document["signoff_stage"] != "reviewed" or not document["signoff_reviewed_by"]:
            raise HTTPException(status_code=409, detail="reviewed sign-off is required first")
        if document["signoff_reviewed_by"] == actor:
            raise HTTPException(status_code=409, detail="legal approval requires a different declared name")
        await db.execute(
            "UPDATE documents SET signoff_stage = 'legal_approved', signoff_legal_by = ? WHERE id = ?",
            (actor, document_id),
        )
    else:
        raise HTTPException(status_code=400, detail="stage must be reviewed or legal_approved")
    await events.record(
        db,
        actor=actor,
        action="document_signoff",
        document_id=document_id,
        from_value=document["signoff_stage"],
        to_value=body.stage,
        detail={"identity_assurance": "self_asserted"},
    )
    await db.commit()
    return {
        "document_id": document_id,
        "stage": body.stage,
        "identity_assurance": "self_asserted",
        "declared_name": actor,
    }


@router.get("/documents/{document_id}/signoff")
async def signoff_status(document_id: str, db: DatabaseConnection = Depends(get_db)):
    async with db.execute(
        """
        SELECT signoff_stage, signoff_reviewed_by, signoff_legal_by,
               identity_status, row_revision FROM documents WHERE id = ?
        """,
        (document_id,),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="document not found")
    return {**dict(row), "identity_assurance": "self_asserted"}


@router.post("/documents/{document_id}/evidence", status_code=202)
async def request_evidence(
    document_id: str,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    async with db.execute("SELECT row_revision FROM documents WHERE id = ?", (document_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="document not found")
    job = await jobs.enqueue(
        db,
        "export",
        payload={"document_id": document_id},
        actor=actor,
        idempotency_key=f"evidence:{document_id}:{row['row_revision']}",
    )
    await db.commit()
    return {"job_id": job["id"], "state": job["state"]}
