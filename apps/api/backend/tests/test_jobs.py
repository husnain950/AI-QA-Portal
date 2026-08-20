"""The durable job queue: exclusive claims, lease recovery, retries, cancellation.

Corpus sync, detectors, exports, PDF renders, and AI proposals all run through this, so
a lost lease or a double-claimed job means duplicated paid work or a sync that silently
stops halfway.
"""

import asyncio
from datetime import timedelta

import pytest

from backend.database import database_connection
from backend.services import jobs
from backend.tests.conftest import open_connection


async def _shift_heartbeat(db, job_id: str, *, seconds: int):
    """Age a running job's heartbeat, as a crashed worker would."""
    stale = (jobs.now() - timedelta(seconds=seconds)).isoformat()
    await db.execute(
        "UPDATE jobs SET heartbeat_at = ? WHERE id = ?", (stale, job_id)
    )
    await db.commit()


@pytest.mark.asyncio
async def test_an_unknown_job_type_is_refused(runtime_sandbox):
    async with database_connection() as db:
        with pytest.raises(ValueError, match="unsupported job type"):
            await jobs.enqueue(db, "mine_bitcoin", payload={}, actor="tester")


@pytest.mark.asyncio
async def test_enqueue_starts_queued_and_carries_its_payload(runtime_sandbox):
    async with database_connection() as db:
        job = await jobs.enqueue(
            db, "detectors", payload={"seed_flags": False}, actor="tester"
        )
        await db.commit()
        assert job["state"] == "queued"
        assert job["payload"] == {"seed_flags": False}
        assert job["attempts"] == 0
        assert job["cancel_requested"] is False
        assert (await jobs.get(db, job["id"]))["actor"] == "tester"


@pytest.mark.asyncio
async def test_the_idempotency_key_makes_a_replay_a_no_op(runtime_sandbox):
    async with database_connection() as db:
        first = await jobs.enqueue(
            db, "corpus_sync", payload={}, actor="tester", idempotency_key="nightly-1"
        )
        await db.commit()
        second = await jobs.enqueue(
            db, "corpus_sync", payload={}, actor="someone-else", idempotency_key="nightly-1"
        )
        await db.commit()

        assert second["id"] == first["id"]
        async with db.execute("SELECT COUNT(*) FROM jobs") as cursor:
            assert (await cursor.fetchone())[0] == 1

        # The key is scoped to the type, so a different job with the same key still runs.
        other = await jobs.enqueue(
            db, "detectors", payload={}, actor="tester", idempotency_key="nightly-1"
        )
        await db.commit()
        assert other["id"] != first["id"]


@pytest.mark.asyncio
async def test_two_workers_racing_for_one_job_produce_one_winner(runtime_sandbox):
    """FOR UPDATE SKIP LOCKED is the whole reason a second worker is safe to run."""
    async with database_connection() as db:
        job = await jobs.enqueue(db, "detectors", payload={}, actor="tester")
        await db.commit()

    first, second = await open_connection(), await open_connection()
    claims = await asyncio.gather(
        jobs.claim(first, "worker-a"), jobs.claim(second, "worker-b")
    )
    won = [claim for claim in claims if claim]
    assert len(won) == 1, "the same job must not be handed to two workers"
    assert won[0]["id"] == job["id"]
    assert won[0]["state"] == "running"
    assert won[0]["attempts"] == 1


@pytest.mark.asyncio
async def test_a_claim_on_an_empty_queue_is_none(runtime_sandbox):
    async with database_connection() as db:
        assert await jobs.claim(db, "worker-a") is None


@pytest.mark.asyncio
async def test_a_crashed_worker_lease_is_requeued_then_finally_failed(runtime_sandbox):
    async with database_connection() as db:
        job = await jobs.enqueue(db, "detectors", payload={}, actor="tester")
        await db.commit()

        claimed = await jobs.claim(db, "worker-a")
        assert claimed["attempts"] == 1
        await _shift_heartbeat(db, job["id"], seconds=jobs.LEASE_SECONDS * 2)

        # A worker with attempts left gets the job back.
        reclaimed = await jobs.claim(db, "worker-b")
        assert reclaimed["id"] == job["id"]
        assert reclaimed["attempts"] == 2
        assert reclaimed["lease_owner"] == "worker-b"

        # Exhaust the attempts, then a stale lease is a failure, not an endless retry.
        await db.execute(
            "UPDATE jobs SET attempts = max_attempts WHERE id = ?", (job["id"],)
        )
        await _shift_heartbeat(db, job["id"], seconds=jobs.LEASE_SECONDS * 2)
        assert await jobs.claim(db, "worker-c") is None
        dead = await jobs.get(db, job["id"])
        assert dead["state"] == "failed"
        assert dead["error"]["type"] == "LeaseExpired"


@pytest.mark.asyncio
async def test_a_permanent_failure_does_not_retry(runtime_sandbox):
    async with database_connection() as db:
        await jobs.enqueue(db, "export", payload={"document_id": "nope"}, actor="tester")
        await db.commit()
        job = await jobs.claim(db, "worker-a")

        await jobs.fail(db, job, {"type": "KeyError", "message": "nope"}, transient=False)
        settled = await jobs.get(db, job["id"])
        assert settled["state"] == "failed"
        assert settled["finished_at"] is not None
        assert await jobs.claim(db, "worker-a") is None, "a failed job is not re-served"


@pytest.mark.asyncio
async def test_a_transient_failure_is_requeued_with_a_backoff(runtime_sandbox):
    async with database_connection() as db:
        await jobs.enqueue(db, "render_pdf", payload={"page": 1}, actor="tester")
        await db.commit()
        job = await jobs.claim(db, "worker-a")

        await jobs.fail(db, job, {"type": "TimeoutError", "message": "slow"}, transient=True)
        requeued = await jobs.get(db, job["id"])
        assert requeued["state"] == "queued"
        assert requeued["finished_at"] is None
        assert requeued["available_at"] > jobs.now().isoformat(), "backoff delays the retry"
        assert await jobs.claim(db, "worker-a") is None, "not available until the backoff ends"


@pytest.mark.asyncio
async def test_success_records_the_result_and_completes_progress(runtime_sandbox):
    async with database_connection() as db:
        await jobs.enqueue(db, "detectors", payload={}, actor="tester")
        await db.commit()
        job = await jobs.claim(db, "worker-a")

        assert await jobs.heartbeat(db, job["id"], "worker-a", current=3, total=10) is False
        progressing = await jobs.get(db, job["id"])
        assert (progressing["progress_current"], progressing["progress_total"]) == (3, 10)

        await jobs.succeed(db, job["id"], {"findings": 7})
        done = await jobs.get(db, job["id"])
        assert done["state"] == "succeeded"
        assert done["result"] == {"findings": 7}
        assert done["progress_current"] == 10, "a finished job does not sit at 3/10"


@pytest.mark.asyncio
async def test_a_heartbeat_from_the_wrong_worker_changes_nothing(runtime_sandbox):
    async with database_connection() as db:
        await jobs.enqueue(db, "detectors", payload={}, actor="tester")
        await db.commit()
        job = await jobs.claim(db, "worker-a")

        await jobs.heartbeat(db, job["id"], "worker-b", current=99, total=99)
        assert (await jobs.get(db, job["id"]))["progress_current"] == 0


@pytest.mark.asyncio
async def test_cancelling_a_queued_job_is_immediate(runtime_sandbox):
    async with database_connection() as db:
        job = await jobs.enqueue(db, "corpus_sync", payload={}, actor="tester")
        await db.commit()

        cancelled = await jobs.cancel(db, job["id"])
        assert cancelled["state"] == "cancelled"
        assert cancelled["finished_at"] is not None
        assert await jobs.claim(db, "worker-a") is None


@pytest.mark.asyncio
async def test_cancelling_a_running_job_asks_it_to_stop(runtime_sandbox):
    """A running job cannot be yanked; it learns from its next heartbeat."""
    async with database_connection() as db:
        await jobs.enqueue(db, "corpus_sync", payload={}, actor="tester")
        await db.commit()
        job = await jobs.claim(db, "worker-a")

        requested = await jobs.cancel(db, job["id"])
        assert requested["state"] == "running"
        assert requested["cancel_requested"] is True
        assert await jobs.heartbeat(db, job["id"], "worker-a") is True

        await jobs.mark_cancelled(db, job["id"])
        assert (await jobs.get(db, job["id"]))["state"] == "cancelled"


@pytest.mark.asyncio
async def test_cancelling_a_finished_job_is_ignored(runtime_sandbox):
    async with database_connection() as db:
        await jobs.enqueue(db, "detectors", payload={}, actor="tester")
        await db.commit()
        job = await jobs.claim(db, "worker-a")
        await jobs.succeed(db, job["id"], {})

        assert (await jobs.cancel(db, job["id"]))["state"] == "succeeded"


@pytest.mark.asyncio
async def test_queues_are_independent(runtime_sandbox):
    async with database_connection() as db:
        await jobs.enqueue(db, "detectors", payload={}, actor="tester", queue="slow")
        await db.commit()
        assert await jobs.claim(db, "worker-a", queue="default") is None
        assert (await jobs.claim(db, "worker-a", queue="slow"))["queue"] == "slow"
