from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from backend.database import DatabaseConnection, get_db
from backend.deps import require_reviewer
from backend.services import jobs

router = APIRouter(prefix="/jobs", tags=["v2-jobs"])


@router.post("/{job_type}", status_code=202)
async def create_job(
    job_type: str,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    try:
        job = await jobs.enqueue(
            db,
            job_type,
            payload=payload or {},
            actor=actor,
            idempotency_key=idempotency_key,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"job_id": job["id"], "state": job["state"]}


@router.get("/{job_id}")
async def get_job(job_id: str, db: DatabaseConnection = Depends(get_db)):
    job = await jobs.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/{job_id}/cancel", status_code=202)
async def cancel_job(
    job_id: str,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    del actor
    job = await jobs.cancel(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job_id": job_id, "state": job["state"], "cancel_requested": job["cancel_requested"]}
