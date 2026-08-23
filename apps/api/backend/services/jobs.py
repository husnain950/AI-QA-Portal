"""Durable PostgreSQL job queue with leases, retries, and cancellation."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

from backend.database import DatabaseConnection
from backend.services.clock import utc_now as now

JOB_TYPES = frozenset(
    {
        "corpus_sync",
        "detectors",
        "provenance_scan",
        "export",
        "render_pdf",
        "regression_bundle",
        "ai_proposal",
    }
)
LEASE_SECONDS = 60




async def enqueue(
    db: DatabaseConnection,
    job_type: str,
    *,
    payload: dict[str, Any],
    actor: str,
    queue: str = "default",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    if job_type not in JOB_TYPES:
        raise ValueError(f"unsupported job type: {job_type}")
    if idempotency_key:
        async with db.execute(
            "SELECT * FROM jobs WHERE type = ? AND idempotency_key = ?",
            (job_type, idempotency_key),
        ) as cur:
            existing = await cur.fetchone()
        if existing:
            return dict(existing)
    timestamp = now().isoformat()
    job_id = str(uuid.uuid4())
    await db.execute(
        """
        INSERT INTO jobs
            (id, type, queue, state, idempotency_key, payload, progress_current,
             attempts, max_attempts, available_at, cancel_requested, actor,
             created_at, updated_at)
        VALUES (?, ?, ?, 'queued', ?, CAST(? AS jsonb), 0, 0, 3, ?, FALSE, ?, ?, ?)
        """,
        (
            job_id,
            job_type,
            queue,
            idempotency_key,
            json.dumps(payload),
            timestamp,
            actor,
            timestamp,
            timestamp,
        ),
    )
    async with db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cur:
        return dict(await cur.fetchone())


async def get(db: DatabaseConnection, job_id: str) -> dict[str, Any] | None:
    async with db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def claim(db: DatabaseConnection, worker_id: str, queue: str = "default") -> dict[str, Any] | None:
    timestamp = now()
    expired = (timestamp - timedelta(seconds=LEASE_SECONDS)).isoformat()
    await db.execute(
        """
        UPDATE jobs SET state = 'failed', lease_owner = NULL, leased_at = NULL,
                        heartbeat_at = NULL, finished_at = ?, updated_at = ?,
                        error = CAST(? AS jsonb)
        WHERE state = 'running' AND heartbeat_at < ? AND attempts >= max_attempts
        """,
        (
            timestamp.isoformat(),
            timestamp.isoformat(),
            json.dumps({"type": "LeaseExpired", "message": "maximum attempts exhausted"}),
            expired,
        ),
    )
    await db.execute(
        """
        UPDATE jobs SET state = 'queued', lease_owner = NULL, leased_at = NULL,
                        heartbeat_at = NULL, updated_at = ?
        WHERE state = 'running' AND heartbeat_at < ? AND attempts < max_attempts
        """,
        (timestamp.isoformat(), expired),
    )
    async with db.execute(
        """
        SELECT id FROM jobs
        WHERE queue = ? AND state = 'queued' AND available_at <= ?
          AND cancel_requested = FALSE
        ORDER BY created_at, id
        FOR UPDATE SKIP LOCKED LIMIT 1
        """,
        (queue, timestamp.isoformat()),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        await db.commit()
        return None
    await db.execute(
        """
        UPDATE jobs SET state = 'running', lease_owner = ?, leased_at = ?,
                        heartbeat_at = ?, attempts = attempts + 1, updated_at = ?
        WHERE id = ?
        """,
        (worker_id, timestamp.isoformat(), timestamp.isoformat(), timestamp.isoformat(), row["id"]),
    )
    await db.commit()
    return await get(db, row["id"])


async def heartbeat(
    db: DatabaseConnection,
    job_id: str,
    worker_id: str,
    *,
    current: int | None = None,
    total: int | None = None,
) -> bool:
    timestamp = now().isoformat()
    await db.execute(
        """
        UPDATE jobs SET heartbeat_at = ?, updated_at = ?,
                        progress_current = COALESCE(?, progress_current),
                        progress_total = COALESCE(?, progress_total)
        WHERE id = ? AND state = 'running' AND lease_owner = ?
        """,
        (timestamp, timestamp, current, total, job_id, worker_id),
    )
    await db.commit()
    row = await get(db, job_id)
    return bool(row and row["cancel_requested"])


async def succeed(db: DatabaseConnection, job_id: str, result: dict[str, Any]) -> None:
    timestamp = now().isoformat()
    await db.execute(
        """
        UPDATE jobs SET state = 'succeeded', result = CAST(? AS jsonb),
                        progress_current = COALESCE(progress_total, progress_current),
                        finished_at = ?, updated_at = ?, heartbeat_at = ?
        WHERE id = ?
        """,
        (json.dumps(result), timestamp, timestamp, timestamp, job_id),
    )
    await db.commit()


async def fail(db: DatabaseConnection, job: dict[str, Any], error: dict[str, Any], *, transient: bool) -> None:
    timestamp = now()
    retry = transient and int(job["attempts"]) < int(job["max_attempts"])
    state = "queued" if retry else "failed"
    delay = min(60, 2 ** max(0, int(job["attempts"])))
    available = timestamp + timedelta(seconds=delay)
    await db.execute(
        """
        UPDATE jobs SET state = ?, error = CAST(? AS jsonb), available_at = ?,
                        lease_owner = NULL, leased_at = NULL, heartbeat_at = NULL,
                        finished_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            state,
            json.dumps(error),
            available.isoformat(),
            None if retry else timestamp.isoformat(),
            timestamp.isoformat(),
            job["id"],
        ),
    )
    await db.commit()


async def cancel(db: DatabaseConnection, job_id: str) -> dict[str, Any] | None:
    timestamp = now().isoformat()
    await db.execute(
        """
        UPDATE jobs SET cancel_requested = TRUE,
                        state = CASE WHEN state = 'queued' THEN 'cancelled' ELSE state END,
                        finished_at = CASE WHEN state = 'queued' THEN ? ELSE finished_at END,
                        updated_at = ?
        WHERE id = ? AND state IN ('queued','running')
        """,
        (timestamp, timestamp, job_id),
    )
    await db.commit()
    return await get(db, job_id)


async def mark_cancelled(db: DatabaseConnection, job_id: str) -> None:
    timestamp = now().isoformat()
    await db.execute(
        "UPDATE jobs SET state = 'cancelled', finished_at = ?, updated_at = ? WHERE id = ?",
        (timestamp, timestamp, job_id),
    )
    await db.commit()
