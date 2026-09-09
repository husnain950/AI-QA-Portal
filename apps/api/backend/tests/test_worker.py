"""The worker: handler wiring, and who actually runs the queue.

Nothing here existed, which is how production came to run with no executor at all:
`POST /api/v2/jobs/ai_proposal` wrote a row, `/health/worker` said 503, and the review
UI spun on "Sending the section JSON and PDF pages to the model" for thirty minutes.
The service-level AI fix tests all passed the whole time, because they call
``create_proposal`` directly and never touch the queue.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import timedelta

from backend import worker
from backend.database import database_connection
from backend.services import jobs
from backend.tests.conftest import (
    FIXED_TEXT,
    open_connection,
    synced_document,
)


async def _heartbeat_rows() -> list[dict]:
    async with database_connection() as db:
        async with db.execute("SELECT * FROM worker_heartbeats") as cur:
            return [dict(row) for row in await cur.fetchall()]


async def _wait_for_heartbeat(*, timeout: float = 10.0) -> list[dict]:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        rows = await _heartbeat_rows()
        if rows:
            return rows
        await asyncio.sleep(0.1)
    return []


@asynccontextmanager
async def _running_api():
    """The app's lifespan, which is what starts the in-process queue."""
    from backend.main import app, lifespan

    async with lifespan(app):
        yield


async def test_every_job_type_has_a_handler(runtime_sandbox):
    """An enqueueable type with no handler is a job that fails after three attempts."""
    assert set(jobs.JOB_TYPES) == set(worker._HANDLERS)


async def test_ai_proposal_runs_through_the_worker(runtime_sandbox, gateway):
    """The path the review UI actually uses: enqueue, claim, execute, succeed."""
    db, document_id, section_id = await synced_document(runtime_sandbox)
    try:
        job = await jobs.enqueue(
            db,
            "ai_proposal",
            payload={
                "document_id": document_id,
                "section_id": section_id,
                "instructions": "The body text is garbled.",
            },
            actor="tester",
        )
        await db.commit()
        assert job["state"] == "queued"
    finally:
        await db.close()

    async with database_connection() as claim_db:
        claimed = await jobs.claim(claim_db, "test-worker")
    assert claimed is not None and claimed["type"] == "ai_proposal"

    result = await worker._execute(claimed)
    async with database_connection() as done_db:
        await jobs.succeed(done_db, claimed["id"], result)
        await done_db.commit()
        settled = await jobs.get(done_db, claimed["id"])

    assert settled["state"] == "succeeded"
    assert settled["result"]["status"] == "proposed"

    db = await open_connection()
    try:
        async with db.execute(
            "SELECT * FROM fix_proposals WHERE id = ?", (result["proposal_id"],)
        ) as cur:
            proposal = dict(await cur.fetchone())
    finally:
        await db.close()
    assert proposal["section_id"] == section_id
    assert json.loads(proposal["proposed_json"])["plain_text"] == FIXED_TEXT


async def test_a_missing_payload_key_fails_without_retrying(runtime_sandbox):
    """KeyError is classified non-transient, so a malformed payload settles at once."""
    async with database_connection() as db:
        job = await jobs.enqueue(db, "ai_proposal", payload={}, actor="tester")
        await db.commit()
        claimed = await jobs.claim(db, "test-worker")

    try:
        await worker._execute(claimed)
        raise AssertionError("a payload with no document_id should not execute")
    except KeyError as exc:
        async with database_connection() as db:
            await jobs.fail(
                db,
                claimed,
                {"type": type(exc).__name__, "message": str(exc)},
                transient=not isinstance(exc, (ValueError, KeyError)),
            )
            settled = await jobs.get(db, job["id"])
    assert settled["state"] == "failed"
    assert settled["attempts"] == 1, "no retry budget spent on a permanent error"


async def test_the_api_process_runs_the_queue_by_default(runtime_sandbox):
    """The regression guard for the outage: booting the API starts an executor."""
    assert await _heartbeat_rows() == []
    async with _running_api():
        beats = await _wait_for_heartbeat()
        assert beats, "no worker heartbeat after the API booted"
        async with database_connection() as db:
            assert await jobs.worker_online(db) is True
        last = beats[0]["heartbeat_at"]

    # And it stops when the app does. The loop used to swallow the cancellation and
    # keep claiming work, which outlived the shutdown that asked it to stop.
    await asyncio.sleep(1.5)
    assert (await _heartbeat_rows())[0]["heartbeat_at"] == last, "the worker kept beating"


async def test_the_in_process_queue_can_be_switched_off(runtime_sandbox, monkeypatch):
    """Compose and the Northflank template set this, because they run a real worker."""
    monkeypatch.setenv("WORKER_IN_PROCESS", "0")
    async with _running_api():
        await asyncio.sleep(0.5)
        assert await _heartbeat_rows() == []


async def test_worker_online_follows_the_heartbeat(runtime_sandbox):
    async with database_connection() as db:
        assert await jobs.worker_online(db) is False, "no heartbeat has ever been written"

    await worker._beat("idle")
    async with database_connection() as db:
        assert await jobs.worker_online(db) is True

        stale = (jobs.now() - timedelta(seconds=jobs.HEARTBEAT_STALE_SECONDS * 2)).isoformat()
        await db.execute("UPDATE worker_heartbeats SET heartbeat_at = ?", (stale,))
        await db.commit()
        assert await jobs.worker_online(db) is False


async def test_enqueue_is_refused_while_no_worker_is_running(client, runtime_sandbox):
    """A 503 the reviewer can read, instead of a job that polls until it times out."""
    response = await client.post(
        "/api/v2/jobs/ai_proposal",
        json={"document_id": "d", "section_id": "s", "instructions": "fix"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "worker_offline"

    async with database_connection() as db:
        async with db.execute("SELECT COUNT(*) AS n FROM jobs") as cur:
            assert (await cur.fetchone())["n"] == 0, "nothing was queued"

    await worker._beat("idle")
    accepted = await client.post(
        "/api/v2/jobs/ai_proposal",
        json={"document_id": "d", "section_id": "s", "instructions": "fix"},
    )
    assert accepted.status_code == 202
    assert accepted.json()["state"] == "queued"
