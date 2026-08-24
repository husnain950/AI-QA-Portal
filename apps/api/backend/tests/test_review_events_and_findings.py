"""review_events append-only + fingerprint dismissal survival."""

from __future__ import annotations

import pytest

from backend.database import database_connection
from backend.services import events
from backend.services.detectors import DETECTOR_VERSION, Finding
from backend.services.findings_store import upsert_findings
from backend.sync_acts import run_sync
from backend.tests.conftest import write_pair


async def test_review_events_append_only_after_a_sync(runtime_sandbox):
    source = runtime_sandbox["root"] / "export"
    write_pair(source)
    await run_sync(source)

    async with database_connection() as db:
        eid = await events.record(
            db,
            actor="tester",
            action="section_status",
            document_id="d1",
            section_id="s1",
            version_id="v1",
            from_value="pending",
            to_value="approved",
        )
        await db.commit()
        assert eid > 0

        with pytest.raises(Exception):
            await db.execute("UPDATE review_events SET actor = 'x' WHERE id = ?", (eid,))
            await db.commit()
        await db.rollback()

        with pytest.raises(Exception):
            await db.execute("DELETE FROM review_events WHERE id = ?", (eid,))
            await db.commit()
        await db.rollback()


async def test_finding_dismissal_survives_score_bump(runtime_sandbox):
    source = runtime_sandbox["root"] / "export"
    write_pair(source)
    await run_sync(source)

    async with database_connection() as db:
        async with db.execute(
            "SELECT id, document_id, source_key FROM sections LIMIT 1"
        ) as cur:
            sec = await cur.fetchone()

        f = Finding(
            code="heading_only_body",
            severity="warning",
            score=10.0,
            fingerprint=f"heading_only_body:{sec['source_key']}",
            detail={"assertion": "test"},
        )
        await upsert_findings(
            db, [(sec["id"], sec["document_id"], f)], run_started_at="2026-01-01T00:00:00Z"
        )
        await db.execute(
            "UPDATE findings SET triage='not_a_defect', triage_note='nope' "
            "WHERE fingerprint=?",
            (f.fingerprint,),
        )
        await db.commit()

        f2 = Finding(
            code="heading_only_body",
            severity="error",
            score=99.0,
            fingerprint=f.fingerprint,
            detail={"assertion": "retuned"},
        )
        await upsert_findings(
            db, [(sec["id"], sec["document_id"], f2)], run_started_at="2026-01-02T00:00:00Z"
        )
        await db.commit()

        async with db.execute(
            "SELECT triage, score, detector_version FROM findings WHERE fingerprint=?",
            (f.fingerprint,),
        ) as cur:
            row = await cur.fetchone()
        assert row["triage"] == "not_a_defect"
        assert float(row["score"]) == 99.0
        assert str(row["detector_version"]) == str(DETECTOR_VERSION)
