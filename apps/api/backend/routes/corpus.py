"""Corpus sync status and trigger endpoints for the portal dashboard."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.database import DatabaseConnection, get_db
from backend.deps import require_reviewer
from backend.services import jobs
from backend.services.corpus_sync import (
    corpus_root_configured,
    default_acts_path,
    default_ordinance_path,
)

router = APIRouter(prefix="/corpus", tags=["corpus"])

class CorpusStatus(BaseModel):
    ordinance_path: str
    acts_path: str
    # Pipeline-mount health (dir + output/*.json), not document count.
    ordinance_configured: bool
    acts_configured: bool
    last_sync_at: Optional[str] = None
    last_status: Optional[str] = None
    ordinance_docs: int = 0
    acts_docs: int = 0
    total_documents: int = 0
    sync_running: bool = False
    last_summary: Optional[Dict[str, Any]] = None


class SyncRequest(BaseModel):
    dry_run: bool = False
    metrics: bool = True
    ordinance_only: bool = False
    acts_only: bool = False


@router.get("/status", response_model=CorpusStatus)
async def corpus_status(db: DatabaseConnection = Depends(get_db)):
    ordinance = default_ordinance_path()
    acts = default_acts_path()
    last_sync_at = last_status = None
    last_summary = None
    ordinance_docs = acts_docs = 0
    try:
        async with db.execute(
            "SELECT last_sync_at, last_status, last_summary, ordinance_docs, acts_docs "
            "FROM corpus_sync_state WHERE id = 1"
        ) as cur:
            row = await cur.fetchone()
        if row:
            last_sync_at = row[0]
            last_status = row[1]
            if row[2]:
                try:
                    last_summary = json.loads(row[2])
                except json.JSONDecodeError:
                    last_summary = None
            ordinance_docs = int(row[3] or 0)
            acts_docs = int(row[4] or 0)
    except Exception:
        pass

    async with db.execute("SELECT COUNT(*) FROM documents") as cur:
        total = (await cur.fetchone())[0]
    async with db.execute(
        "SELECT COUNT(*) FROM jobs WHERE type = 'corpus_sync' AND state IN ('queued','running')"
    ) as cur:
        sync_running = bool((await cur.fetchone())[0])

    return CorpusStatus(
        ordinance_path=str(ordinance),
        acts_path=str(acts),
        ordinance_configured=corpus_root_configured(ordinance),
        acts_configured=corpus_root_configured(acts),
        last_sync_at=last_sync_at,
        last_status=last_status,
        ordinance_docs=ordinance_docs,
        acts_docs=acts_docs,
        total_documents=int(total or 0),
        sync_running=sync_running,
        last_summary=last_summary,
    )


@router.post("/sync", status_code=202)
async def trigger_sync(
    body: SyncRequest = SyncRequest(),
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    ordinance = default_ordinance_path()
    acts = default_acts_path()
    if not body.acts_only and not corpus_root_configured(ordinance):
        raise HTTPException(
            status_code=400,
            detail=(
                "Ordinance pipeline mount not on this host "
                f"(need output/*.json at {ordinance})"
            ),
        )
    if not body.ordinance_only and not corpus_root_configured(acts):
        raise HTTPException(
            status_code=400,
            detail=(
                "Acts pipeline mount not on this host "
                f"(need output/*.json at {acts})"
            ),
        )

    job = await jobs.enqueue(
        db,
        "corpus_sync",
        payload=body.model_dump(),
        actor=actor,
    )
    await db.commit()
    return {"job_id": job["id"], "state": job["state"]}
