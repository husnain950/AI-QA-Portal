"""Atomic bulk triage, review sessions that survive a reload, and review leases.

Bulk triage used to be a sequential PATCH per row: interrupt it and the queue was left
half-applied with no record of where it stopped. A session exists so a reviewer can walk
the queue from Review and come back to the same place; a lease exists so two reviewers
do not work the same finding.
"""

import json
from datetime import datetime, timezone

from backend.database import database_connection
from backend.tests.conftest import ADMIN_EMAIL, add_finding, seed_document

DOCUMENT_ID = "doc-queue"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _queue(db, count=3):
    section_ids = tuple(f"sec-queue-{index}" for index in range(count))
    await seed_document(db, DOCUMENT_ID, section_ids=section_ids, with_active_version=True)
    ids = []
    for index, section_id in enumerate(section_ids):
        ids.append(
            await add_finding(
                db,
                section_id,
                DOCUMENT_ID,
                detector=f"detector_{index}",
                severity="error" if index == 0 else "warning",
                score=100 - index,
            )
        )
    await db.commit()
    return ids


async def _triages(db, ids):
    placeholders = ",".join("?" for _ in ids)
    async with db.execute(
        f"SELECT id, triage FROM findings WHERE id IN ({placeholders}) ORDER BY id", ids
    ) as cursor:
        return {row["id"]: row["triage"] for row in await cursor.fetchall()}


def _bulk(ids, triage="parse_bug", prior="new"):
    return {"items": [{"id": i, "triage": triage, "expected_prior": prior, "note": ""} for i in ids]}


# --------------------------------------------------------------------- bulk triage


async def test_bulk_triage_applies_the_whole_batch_once(runtime_sandbox, client):
    async with database_connection() as db:
        ids = await _queue(db)

    response = await client.post(
        "/api/v2/findings/bulk-triage",
        json=_bulk(ids),
        headers={"Idempotency-Key": "batch-1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 3
    assert body["updated"][0] == {"id": ids[0], "from": "new", "to": "parse_bug"}

    async with database_connection() as db:
        assert set((await _triages(db, ids)).values()) == {"parse_bug"}
        async with db.execute(
            "SELECT action, detail_json FROM review_events "
            "WHERE action = 'bulk_finding_triage'"
        ) as cursor:
            events = [dict(row) for row in await cursor.fetchall()]
    assert len(events) == 1, "one audit event for the batch, not one per row"
    detail = events[0]["detail_json"]
    detail = detail if isinstance(detail, dict) else json.loads(detail)
    assert len(detail["changes"]) == 3


async def test_one_stale_row_fails_the_batch_and_writes_nothing(runtime_sandbox, client):
    """The point of the endpoint: no partially applied bulk action."""
    async with database_connection() as db:
        ids = await _queue(db)
        await db.execute(
            "UPDATE findings SET triage = 'dismissed' WHERE id = ?", (ids[1],)
        )
        await db.commit()

    response = await client.post(
        "/api/v2/findings/bulk-triage",
        json=_bulk(ids),
        headers={"Idempotency-Key": "batch-conflict"},
    )
    assert response.status_code == 409
    conflicts = response.json()["detail"]["conflicts"]
    assert conflicts == [{"id": ids[1], "expected": "new", "current": "dismissed"}]

    async with database_connection() as db:
        assert await _triages(db, ids) == {
            ids[0]: "new",
            ids[1]: "dismissed",
            ids[2]: "new",
        }


async def test_an_unknown_id_fails_the_batch(runtime_sandbox, client):
    async with database_connection() as db:
        ids = await _queue(db)

    response = await client.post(
        "/api/v2/findings/bulk-triage",
        json=_bulk([ids[0], 999999]),
        headers={"Idempotency-Key": "batch-missing"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["conflicts"] == [
        {"id": 999999, "expected": "new", "current": None}
    ]
    async with database_connection() as db:
        assert (await _triages(db, [ids[0]]))[ids[0]] == "new"


async def test_replaying_the_same_key_returns_the_first_answer(runtime_sandbox, client):
    """A retried request after a dropped response must not triage twice."""
    async with database_connection() as db:
        ids = await _queue(db)

    first = await client.post(
        "/api/v2/findings/bulk-triage",
        json=_bulk(ids),
        headers={"Idempotency-Key": "batch-retry"},
    )
    second = await client.post(
        "/api/v2/findings/bulk-triage",
        json=_bulk(ids),
        headers={"Idempotency-Key": "batch-retry"},
    )
    assert second.status_code == 200
    assert second.json() == first.json()

    async with database_connection() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM review_events WHERE action = 'bulk_finding_triage'"
        ) as cursor:
            assert (await cursor.fetchone())[0] == 1


async def test_reusing_a_key_for_a_different_batch_is_refused(runtime_sandbox, client):
    async with database_connection() as db:
        ids = await _queue(db)

    await client.post(
        "/api/v2/findings/bulk-triage",
        json=_bulk(ids[:1]),
        headers={"Idempotency-Key": "batch-shared"},
    )
    response = await client.post(
        "/api/v2/findings/bulk-triage",
        json=_bulk(ids[1:]),
        headers={"Idempotency-Key": "batch-shared"},
    )
    assert response.status_code == 409
    assert "another request" in response.json()["detail"]


async def test_a_batch_needs_a_key_unique_ids_and_at_least_one_item(runtime_sandbox, client):
    async with database_connection() as db:
        ids = await _queue(db)

    missing_key = await client.post("/api/v2/findings/bulk-triage", json=_bulk(ids))
    assert missing_key.status_code == 422

    duplicate = await client.post(
        "/api/v2/findings/bulk-triage",
        json=_bulk([ids[0], ids[0]]),
        headers={"Idempotency-Key": "batch-dupe"},
    )
    assert duplicate.status_code == 400

    empty = await client.post(
        "/api/v2/findings/bulk-triage",
        json={"items": []},
        headers={"Idempotency-Key": "batch-empty"},
    )
    assert empty.status_code == 422


# ------------------------------------------------------------------ review sessions


async def test_a_session_starts_on_the_highest_risk_finding(runtime_sandbox, client):
    async with database_connection() as db:
        ids = await _queue(db)

    created = await client.post(
        "/api/v2/review-sessions", json={"client_session_id": "tab-1", "filters": {}}
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["current_finding_id"] == ids[0], "the error outranks the warnings"
    assert body["current"]["document_id"] == DOCUMENT_ID
    assert body["snapshot_at"]


async def test_a_session_can_be_resumed_and_walked_forwards_and_back(runtime_sandbox, client):
    async with database_connection() as db:
        ids = await _queue(db)

    session_id = (
        await client.post(
            "/api/v2/review-sessions", json={"client_session_id": "tab-1", "filters": {}}
        )
    ).json()["id"]

    resumed = await client.get(f"/api/v2/review-sessions/{session_id}")
    assert resumed.status_code == 200
    assert resumed.json()["current_finding_id"] == ids[0]

    advanced = await client.post(
        f"/api/v2/review-sessions/{session_id}/advance",
        json={"finding_id": ids[0], "triage": "parse_bug", "expected_prior": "new"},
    )
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["previous_finding_id"] == ids[0]
    assert advanced.json()["current_finding_id"] == ids[1], "triaged findings drop out"

    skipped = await client.post(f"/api/v2/review-sessions/{session_id}/next")
    assert skipped.json()["current_finding_id"] == ids[2]

    back = await client.post(f"/api/v2/review-sessions/{session_id}/back")
    assert back.json()["current_finding_id"] == ids[1], "skipping is reversible"

    # And the disposition really landed.
    async with database_connection() as db:
        assert (await _triages(db, [ids[0]]))[ids[0]] == "parse_bug"


async def test_a_session_ignores_findings_that_arrived_after_its_snapshot(runtime_sandbox, client):
    """A queue that grows under the reviewer must not reshuffle mid-session."""
    async with database_connection() as db:
        ids = await _queue(db, count=1)

    session_id = (
        await client.post(
            "/api/v2/review-sessions", json={"client_session_id": "tab-1", "filters": {}}
        )
    ).json()["id"]

    async with database_connection() as db:
        await seed_document(db, "doc-later", section_ids=("sec-later",))
        late = await add_finding(db, "sec-later", "doc-later", detector="late", severity="error")
        await db.execute(
            "UPDATE findings SET first_seen_at = '2099-01-01' WHERE id = ?", (late,)
        )
        await db.commit()

    advanced = await client.post(
        f"/api/v2/review-sessions/{session_id}/advance",
        json={"finding_id": ids[0], "triage": "dismissed", "expected_prior": "new"},
    )
    assert advanced.json()["current_finding_id"] is None, "the late finding is out of scope"


async def test_advancing_a_finding_someone_else_changed_is_a_conflict(runtime_sandbox, client):
    async with database_connection() as db:
        ids = await _queue(db)

    session_id = (
        await client.post(
            "/api/v2/review-sessions", json={"client_session_id": "tab-1", "filters": {}}
        )
    ).json()["id"]

    async with database_connection() as db:
        await db.execute("UPDATE findings SET triage = 'dismissed' WHERE id = ?", (ids[0],))
        await db.commit()

    response = await client.post(
        f"/api/v2/review-sessions/{session_id}/advance",
        json={"finding_id": ids[0], "triage": "parse_bug", "expected_prior": "new"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "stale_finding"


async def test_another_reviewer_cannot_drive_someone_elses_session(
    runtime_sandbox, client, sign_in
):
    async with database_connection() as db:
        ids = await _queue(db)

    session_id = (
        await client.post(
            "/api/v2/review-sessions", json={"client_session_id": "tab-1", "filters": {}}
        )
    ).json()["id"]

    other = await sign_in("reviewer")
    response = await other.post(
        f"/api/v2/review-sessions/{session_id}/advance",
        json={"finding_id": ids[0], "triage": "parse_bug", "expected_prior": "new"},
    )
    assert response.status_code == 409


async def test_an_unknown_session_is_404(runtime_sandbox, client):
    response = await client.get("/api/v2/review-sessions/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


async def test_a_session_filter_narrows_the_queue(runtime_sandbox, client):
    async with database_connection() as db:
        ids = await _queue(db)

    created = await client.post(
        "/api/v2/review-sessions",
        json={"client_session_id": "tab-1", "filters": {"detector": "detector_2"}},
    )
    assert created.json()["current_finding_id"] == ids[2]


# ------------------------------------------------------------------- review leases


async def test_a_lease_stops_a_second_reviewer_but_not_a_renewal(
    runtime_sandbox, client, sign_in
):
    async with database_connection() as db:
        ids = await _queue(db)

    claimed = await client.post(
        f"/api/v2/review-assignments/{ids[0]}", json={"client_session_id": "tab-1"}
    )
    assert claimed.status_code == 200
    assert claimed.json()["actor"] == ADMIN_EMAIL
    assert claimed.json()["expires_at"] > _now_iso()

    renewed = await client.post(
        f"/api/v2/review-assignments/{ids[0]}", json={"client_session_id": "tab-1"}
    )
    assert renewed.status_code == 200, "the holder can renew its own lease"
    assert renewed.json()["expires_at"] >= claimed.json()["expires_at"]

    other = await sign_in("reviewer")
    taken = await other.post(
        f"/api/v2/review-assignments/{ids[0]}", json={"client_session_id": "tab-2"}
    )
    assert taken.status_code == 409
    assert taken.json()["detail"]["code"] == "finding_leased"
    assert taken.json()["detail"]["actor"] == ADMIN_EMAIL


async def test_an_expired_lease_can_be_taken_over(runtime_sandbox, client, sign_in):
    async with database_connection() as db:
        ids = await _queue(db)

    await client.post(f"/api/v2/review-assignments/{ids[0]}", json={"client_session_id": "tab-1"})
    async with database_connection() as db:
        await db.execute(
            "UPDATE review_assignments SET expires_at = '2020-01-01T00:00:00+00:00' "
            "WHERE finding_id = ?",
            (ids[0],),
        )
        await db.commit()

    other = await sign_in("reviewer")
    taken = await other.post(
        f"/api/v2/review-assignments/{ids[0]}", json={"client_session_id": "tab-2"}
    )
    assert taken.status_code == 200
    assert taken.json()["actor"] == "reviewer@crx.test"
