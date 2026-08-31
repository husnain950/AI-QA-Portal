"""Pipeline health, on a deployment that has no reports to read.

`acts_metrics.ingest` reads the suite's measurements off a reports DIRECTORY, and a
deployment does not have one -- the pipeline repositories are not on the server. So
production held zero `version_metrics` rows and the health badges the Library already
renders had nothing behind them. PR #37: "The UI already exists... Nothing feeds it."

Fixing the identity (#64) made the badges *matchable*. This is the wire that carries
the numbers.
"""

import pytest
from fastapi import HTTPException

from backend.models import VersionMetrics
from backend.routes.documents import put_version_metrics
from backend.tests.conftest import seed_document

DOCUMENT_ID = "metrics-doc"


def _metrics(**overrides):
    base = dict(
        invariants_passed=57, invariants_total=58, cases_passed=4, cases_total=4,
        body_conserved=99.997, body_missing=3, footnote_conserved=100.0,
        footnote_missing=0, gate_ok=False, measured_at="2026-08-31T10:00:00Z",
        failing_invariants=["section_carries_its_body"],
    )
    base.update(overrides)
    return VersionMetrics(**base)


async def _stored(db):
    async with db.execute(
        "SELECT m.* FROM version_metrics m JOIN document_versions v ON v.id = m.version_id "
        "WHERE v.document_id = ? AND v.is_active = TRUE",
        (DOCUMENT_ID,),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def test_measurements_reach_a_deployment_that_cannot_read_reports(db, runtime_sandbox):
    await seed_document(db, DOCUMENT_ID, section_ids=("s-1",), with_active_version=True)
    await put_version_metrics(DOCUMENT_ID, _metrics(), db=db, actor="push_corpus")

    stored = await _stored(db)
    assert stored["invariants_passed"] == 57
    assert stored["gate_ok"] is False
    assert stored["body_conserved"] == pytest.approx(99.997)
    assert "section_carries_its_body" in stored["detail_json"]


async def test_reposting_replaces_rather_than_accumulates(db, runtime_sandbox):
    """The same suite re-run must not leave two answers for one parse."""
    await seed_document(db, DOCUMENT_ID, section_ids=("s-1",), with_active_version=True)
    await put_version_metrics(DOCUMENT_ID, _metrics(), db=db, actor="push_corpus")
    await put_version_metrics(
        DOCUMENT_ID, _metrics(invariants_passed=58, gate_ok=True, failing_invariants=[]),
        db=db, actor="push_corpus",
    )

    async with db.execute("SELECT COUNT(*) AS n FROM version_metrics") as cursor:
        assert (await cursor.fetchone())["n"] == 1
    stored = await _stored(db)
    assert stored["invariants_passed"] == 58
    assert stored["gate_ok"] is True


async def test_the_document_reports_its_health_once_measured(db, client, runtime_sandbox):
    await seed_document(db, DOCUMENT_ID, section_ids=("s-1",), with_active_version=True)
    assert (await client.get(f"/api/documents/{DOCUMENT_ID}")).json()["health"] is None

    await put_version_metrics(DOCUMENT_ID, _metrics(), db=db, actor="push_corpus")

    health = (await client.get(f"/api/documents/{DOCUMENT_ID}")).json()["health"]
    assert health is not None, "measured, and the badge still has nothing behind it"
    assert health["invariants_passed"] == 57
    assert health["gate_ok"] is False
    assert health["failing_invariants"] == ["section_carries_its_body"]


async def test_a_document_with_no_active_version_is_refused(db, runtime_sandbox):
    """A measurement describes a parse. With no parse there is nothing to describe,
    and silently dropping it would leave a badge that never appears and never says
    why."""
    await seed_document(db, DOCUMENT_ID, section_ids=("s-1",))
    await db.execute("DELETE FROM document_versions WHERE document_id = ?", (DOCUMENT_ID,))
    await db.commit()

    with pytest.raises(HTTPException) as caught:
        await put_version_metrics(DOCUMENT_ID, _metrics(), db=db, actor="push_corpus")
    assert caught.value.status_code == 409


async def test_an_unknown_document_is_a_404(db, runtime_sandbox):
    with pytest.raises(HTTPException) as caught:
        await put_version_metrics("no-such-doc", _metrics(), db=db, actor="push_corpus")
    assert caught.value.status_code == 404


def test_writing_health_needs_an_admin():
    """It is a claim about the corpus, not a review action."""
    from backend.middleware.security import required_role

    assert required_role("POST", "/api/documents/abc/metrics") == "admin"
    assert required_role("GET", "/api/documents/abc") == "reader"
