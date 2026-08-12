"""AI fix loop endpoints — propose, inspect, approve, reject.

A proposal is synchronous for v1: the request holds while the gateway answers.
Nothing is ever applied without an explicit human approval.
"""

from __future__ import annotations

import json

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from backend.database import get_db
from backend.deps import require_reviewer
from backend.models import (
    FixApprovalResponse,
    FixModelsResponse,
    FixProposalCreate,
    FixProposalResponse,
)
from backend.services import ai_fix, events, llm_client

router = APIRouter(tags=["ai-fixes"])

_NOT_CONFIGURED = (
    "AI fixes are not configured. Set OPENPATHS_API_KEY, "
    "OPENPATHS_BASE_URL and OPENPATHS_MODELS on the API."
)


@router.get("/ai-fixes/models", response_model=FixModelsResponse)
async def list_models():
    """The configured model allow-list for the review UI's dropdown."""
    if not llm_client.configured():
        raise HTTPException(status_code=503, detail=_NOT_CONFIGURED)
    models = llm_client.available_models()
    return FixModelsResponse(models=models, default=models[0])


def _loads(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None


def _response(row) -> FixProposalResponse:
    return FixProposalResponse(
        id=row["id"],
        document_id=row["document_id"],
        section_id=row["section_id"],
        source_key=row["source_key"],
        instructions=row["instructions"],
        model_name=row["model"],
        status=row["status"],
        error=row["error"],
        created_at=row["created_at"],
        created_by=row["created_by"],
        resolved_at=row["resolved_at"] if "resolved_at" in row.keys() else None,
        resolved_by=row["resolved_by"] if "resolved_by" in row.keys() else None,
        proposed=_loads(row["proposed_json"]),
        validation=_loads(row["validation_json"]) or [],
        diff=_loads(row["diff_json"]),
    )


async def _get_proposal(db: aiosqlite.Connection, proposal_id: str):
    async with db.execute(
        "SELECT * FROM fix_proposals WHERE id = ?", (proposal_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return row


@router.post(
    "/documents/{document_id}/sections/{section_id}/ai-fix",
    response_model=FixProposalResponse,
)
async def request_ai_fix(
    document_id: str,
    section_id: str,
    body: FixProposalCreate,
    db: aiosqlite.Connection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    if not llm_client.configured():
        raise HTTPException(status_code=503, detail=_NOT_CONFIGURED)
    instructions = (body.instructions or "").strip()
    if not instructions:
        raise HTTPException(status_code=400, detail="Instructions are required")

    try:
        row = await ai_fix.create_proposal(
            db,
            document_id,
            section_id,
            instructions,
            actor=actor,
            model=body.model_name,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    await events.record(
        db,
        actor=actor,
        action="ai_fix_proposed",
        document_id=document_id,
        section_id=section_id,
        version_id=await events.active_version_id(db, document_id),
        to_value=row["status"],
        detail={"proposal_id": row["id"]},
    )
    await db.commit()
    return _response(row)


@router.get(
    "/documents/{document_id}/ai-fixes",
    response_model=list[FixProposalResponse],
)
async def list_ai_fixes(
    document_id: str,
    section_id: str | None = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    query = "SELECT * FROM fix_proposals WHERE document_id = ?"
    params: list = [document_id]
    if section_id:
        query += " AND section_id = ?"
        params.append(section_id)
    query += " ORDER BY created_at DESC"
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()
    return [_response(row) for row in rows]


@router.get("/ai-fixes/{proposal_id}", response_model=FixProposalResponse)
async def get_ai_fix(
    proposal_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    return _response(await _get_proposal(db, proposal_id))


@router.post("/ai-fixes/{proposal_id}/approve", response_model=FixApprovalResponse)
async def approve_ai_fix(
    proposal_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    proposal = await _get_proposal(db, proposal_id)
    try:
        result = await ai_fix.approve_proposal(db, proposal, actor=actor)
    except LookupError as error:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(error))

    await events.record(
        db,
        actor=actor,
        action="ai_fix_approved",
        document_id=proposal["document_id"],
        section_id=proposal["section_id"],
        version_id=await events.active_version_id(db, proposal["document_id"]),
        to_value="approved",
        detail=result,
    )
    await db.commit()
    return FixApprovalResponse(**result)


@router.post("/ai-fixes/{proposal_id}/reject", response_model=FixProposalResponse)
async def reject_ai_fix(
    proposal_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    proposal = await _get_proposal(db, proposal_id)
    try:
        await ai_fix.reject_proposal(db, proposal, actor=actor)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))

    await events.record(
        db,
        actor=actor,
        action="ai_fix_rejected",
        document_id=proposal["document_id"],
        section_id=proposal["section_id"],
        to_value="rejected",
        detail={"proposal_id": proposal_id},
    )
    await db.commit()
    return _response(await _get_proposal(db, proposal_id))
