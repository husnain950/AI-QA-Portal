"""The orphan sweep behind DELETE /api/corpus/orphans.

Deleting a document cascades only where a real foreign key exists. `findings`,
`section_overlays` and `jobs` name a document by bare text and `review_assignments`
names a finding, so those rows outlive the document. The first test proves that
outliving actually happens -- without it, the sweep could be a no-op and still pass.
"""

from __future__ import annotations

import pytest

from .conftest import add_finding, seed_document

DOOMED = "doomed-doc"
KEPT = "kept-doc"


async def _finding_ids(db) -> set[int]:
    async with db.execute("SELECT id FROM findings") as cursor:
        return {int(row["id"]) for row in await cursor.fetchall()}


async def _jobs(db) -> set[str]:
    async with db.execute("SELECT id FROM jobs") as cursor:
        return {row["id"] for row in await cursor.fetchall()}


@pytest.fixture
async def two_documents(db):
    """One document to delete and one to leave alone, each carrying a finding."""
    await seed_document(db, DOOMED, name="Doomed Act, 2001", section_ids=("doomed-sec",))
    await seed_document(db, KEPT, name="Kept Act, 2001", section_ids=("kept-sec",))
    doomed_finding = await add_finding(db, "doomed-sec", DOOMED)
    kept_finding = await add_finding(db, "kept-sec", KEPT)
    for finding_id in (doomed_finding, kept_finding):
        await db.execute(
            "INSERT INTO review_assignments (finding_id, actor, client_session_id, "
            "claimed_at, expires_at) VALUES (?, 'someone', 'sess', '2026-01-01', '2099-01-01')",
            (finding_id,),
        )
    for job_id, document_id in (("job-doomed", DOOMED), ("job-kept", KEPT)):
        await db.execute(
            "INSERT INTO jobs (id, type, payload, available_at, actor, created_at, updated_at) "
            "VALUES (?, 'export', ?, '2026-01-01', 'someone', '2026-01-01', '2026-01-01')",
            (job_id, f'{{"document_id": "{document_id}"}}'),
        )
    await db.commit()
    return doomed_finding, kept_finding


async def test_delete_document_leaves_the_finding_behind(client, db, two_documents):
    """The gap this endpoint exists to close. If this ever fails, delete the endpoint."""
    doomed_finding, _ = two_documents

    response = await client.delete(f"/api/documents/{DOOMED}")
    assert response.status_code == 200, response.text

    async with db.execute("SELECT COUNT(*) AS n FROM sections WHERE document_id = ?", (DOOMED,)) as cursor:
        assert (await cursor.fetchone())["n"] == 0, "sections should cascade"
    assert doomed_finding in await _finding_ids(db), "finding should NOT cascade"


async def test_purge_removes_orphans_and_spares_live_rows(client, db, two_documents):
    doomed_finding, kept_finding = two_documents
    await client.delete(f"/api/documents/{DOOMED}")

    response = await client.delete("/api/corpus/orphans")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["deleted"]["findings"] == 1
    assert body["deleted"]["review_assignments"] == 1
    assert body["deleted"]["jobs"] == 1
    # Reported, never deleted: a DB trigger rejects DELETE on the audit log.
    assert "review_events" in body["retained"]

    remaining = await _finding_ids(db)
    assert doomed_finding not in remaining
    assert kept_finding in remaining, "a live document's finding must survive"
    assert await _jobs(db) == {"job-kept"}


async def test_purge_is_idempotent(client, db, two_documents):
    await client.delete(f"/api/documents/{DOOMED}")
    await client.delete("/api/corpus/orphans")

    response = await client.delete("/api/corpus/orphans")
    assert response.status_code == 200, response.text
    assert response.json()["deleted"] == {
        "findings": 0,
        "section_overlays": 0,
        "review_assignments": 0,
        "jobs": 0,
        "statute_families": 0,
    }


async def test_purge_requires_admin(sign_in, two_documents):
    reviewer = await sign_in("reviewer")
    response = await reviewer.delete("/api/corpus/orphans")
    assert response.status_code == 403, response.text


async def test_purge_rejects_anonymous(anonymous, two_documents):
    response = await anonymous.delete("/api/corpus/orphans")
    assert response.status_code == 401, response.text


async def test_bulk_delete_removes_every_named_document(client, db, two_documents):
    """One request, many documents -- the shape the HEAVY rate limit forces."""
    response = await client.request(
        "DELETE", "/api/documents", json={"ids": [DOOMED, KEPT]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["deleted"] == 2

    async with db.execute("SELECT COUNT(*) AS n FROM documents") as cursor:
        assert (await cursor.fetchone())["n"] == 0


async def test_bulk_delete_is_all_or_nothing_on_an_unknown_id(client, db, two_documents):
    """A typo in the id list must not delete the documents that did resolve."""
    response = await client.request(
        "DELETE", "/api/documents", json={"ids": [DOOMED, "no-such-document"]}
    )
    assert response.status_code == 404, response.text

    async with db.execute("SELECT COUNT(*) AS n FROM documents") as cursor:
        assert (await cursor.fetchone())["n"] == 2, "nothing should have been deleted"


@pytest.mark.parametrize("body", [{}, {"ids": []}, {"ids": "doc"}, {"ids": [1]}])
async def test_bulk_delete_rejects_a_malformed_body(client, body):
    response = await client.request("DELETE", "/api/documents", json=body)
    assert response.status_code == 400, response.text


async def test_bulk_delete_requires_admin(sign_in, two_documents):
    reviewer = await sign_in("reviewer")
    response = await reviewer.request("DELETE", "/api/documents", json={"ids": [DOOMED]})
    assert response.status_code == 403, response.text
