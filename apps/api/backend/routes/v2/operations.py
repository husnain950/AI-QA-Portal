"""Private operator visibility and server metadata."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from backend.database import DatabaseConnection, get_db
from backend.deps import require_reviewer
from backend.services import jobs
from backend.services.detectors import DETECTOR_VERSION

router = APIRouter(tags=["v2-operations"])


def _operator(token: str | None) -> None:
    expected = os.environ.get("METRICS_TOKEN", "")
    if not expected or token != expected:
        raise HTTPException(status_code=404, detail="not found")


@router.get("/system")
async def system_info(db: DatabaseConnection = Depends(get_db)):
    async with db.execute(
        """
        SELECT (SELECT COUNT(*) FROM documents) AS documents,
               (SELECT COUNT(*) FROM sections) AS sections,
               (SELECT COUNT(*) FROM footnotes) AS footnotes,
               (SELECT COUNT(*) FROM findings) AS findings,
               (SELECT MAX(last_seen_at) FROM findings) AS findings_refreshed_at,
               (SELECT last_sync_at FROM corpus_sync_state WHERE id = 1) AS corpus_refreshed_at
        """
    ) as cur:
        totals = dict(await cur.fetchone())
    return {
        "server_version": os.environ.get("CRX_VERSION", "dev"),
        "detector_version": DETECTOR_VERSION,
        "totals": totals,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/csp-reports", status_code=204)
async def csp_report(request: Request):
    body = await request.body()
    logging.getLogger("crx.csp").warning(
        "csp_violation",
        extra={"report": body[:16_384].decode("utf-8", errors="replace")},
    )


@router.get("/detectors/status")
async def detector_status(db: DatabaseConnection = Depends(get_db)):
    async with db.execute(
        """
        SELECT id, state, created_at, finished_at, result, error, actor
        FROM jobs WHERE type = 'detectors'
        ORDER BY created_at DESC LIMIT 1
        """
    ) as cur:
        latest = await cur.fetchone()
    async with db.execute(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE orphaned = TRUE) AS stale,
               COUNT(DISTINCT document_id) AS documents,
               MAX(last_seen_at) AS last_seen_at
        FROM findings
        """
    ) as cur:
        coverage = dict(await cur.fetchone())
    return {
        "version": DETECTOR_VERSION,
        "coverage": coverage,
        "last_run": dict(latest) if latest else None,
        "authorization": "self_asserted_attribution",
    }


@router.post("/detectors/run", status_code=202)
async def run_detectors(
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    job = await jobs.enqueue(
        db,
        "detectors",
        payload={"seed_flags": True},
        actor=actor,
    )
    await db.commit()
    return {"job_id": job["id"], "state": job["state"]}


@router.get("/operator/audit-events")
async def audit_events(
    limit: int = Query(100, ge=1, le=1000),
    x_metrics_token: str | None = Header(None, alias="X-Metrics-Token"),
    db: DatabaseConnection = Depends(get_db),
):
    _operator(x_metrics_token)
    async with db.execute(
        "SELECT * FROM review_events ORDER BY id DESC LIMIT ?", (limit,)
    ) as cur:
        return {"items": [dict(row) for row in await cur.fetchall()]}


@router.get("/operator/backups")
async def backup_status(
    x_metrics_token: str | None = Header(None, alias="X-Metrics-Token"),
    db: DatabaseConnection = Depends(get_db),
):
    _operator(x_metrics_token)
    async with db.execute("SELECT * FROM backup_runs ORDER BY started_at DESC LIMIT 100") as cur:
        return {"items": [dict(row) for row in await cur.fetchall()]}


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics(
    x_metrics_token: str | None = Header(None, alias="X-Metrics-Token"),
    db: DatabaseConnection = Depends(get_db),
):
    _operator(x_metrics_token)
    async with db.execute("SELECT state, COUNT(*) AS count FROM jobs GROUP BY state") as cur:
        jobs = {row["state"]: int(row["count"]) for row in await cur.fetchall()}
    async with db.execute("SELECT status, COUNT(*) AS count FROM documents GROUP BY status") as cur:
        documents = {row["status"]: int(row["count"]) for row in await cur.fetchall()}
    lines = [f'crx_jobs{{state="{state}"}} {count}' for state, count in sorted(jobs.items())]
    lines.extend(f'crx_documents{{status="{state}"}} {count}' for state, count in sorted(documents.items()))
    return "\n".join(lines) + "\n"
