"""Tests for findings upsert — dismissal survives score/version bump."""

import aiosqlite
import pytest

from backend.services import findings_store
from backend.services.detectors import Finding


@pytest.mark.asyncio
async def test_upsert_inserts_new_finding(runtime_sandbox):
    db_path = runtime_sandbox["db_path"]
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")

        await db.execute("""
            INSERT INTO documents (id, name, pdf_filename, json_filename, total_sections, total_pages, uploaded_at, status)
            VALUES ('doc-f', 'Finding Test', 'f.pdf', 'f.json', 1, 1, '2026-01-01', 'pending')
        """)
        await db.execute("""
            INSERT INTO sections (id, document_id, section_code, section_heading, sort_order, review_status)
            VALUES ('sec-f', 'doc-f', '1', 'Test', 1, 'pending')
        """)
        await db.commit()

        finding = Finding(
            code="heading_only_body",
            severity="warning",
            score=0.9,
            fingerprint="heading_only:sec-f",
            detail={"text_len": 10, "expected_len": 10},
        )

        result = await findings_store.upsert_findings(db, [("sec-f", "doc-f", finding)])
        await db.commit()

        assert result["inserted"] == 1
        assert result["refreshed"] == 0


@pytest.mark.asyncio
async def test_dismissal_survives_score_bump(runtime_sandbox):
    """A human triage must not be overwritten by a detector re-run."""
    db_path = runtime_sandbox["db_path"]
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")

        await db.execute("""
            INSERT INTO documents (id, name, pdf_filename, json_filename, total_sections, total_pages, uploaded_at, status)
            VALUES ('doc-f2', 'Finding Test 2', 'f.pdf', 'f.json', 1, 1, '2026-01-01', 'pending')
        """)
        await db.execute("""
            INSERT INTO sections (id, document_id, section_code, section_heading, sort_order, review_status)
            VALUES ('sec-f2', 'doc-f2', '1', 'Test', 1, 'pending')
        """)
        await db.commit()

        finding = Finding(
            code="short_vs_siblings",
            severity="warning",
            score=0.8,
            fingerprint="short_sibling:sec-f2",
            detail={"length": 10, "median": 100, "n": 5},
        )

        await findings_store.upsert_findings(db, [("sec-f2", "doc-f2", finding)])
        await db.commit()

        # Human triages as not_a_defect
        async with db.execute(
            "SELECT id FROM findings WHERE fingerprint = 'short_sibling:sec-f2'"
        ) as cursor:
            row = await cursor.fetchone()
        finding_id = row["id"]

        await findings_store.triage_finding(
            db, finding_id, triage="not_a_defect", note="false positive", actor="human"
        )
        await db.commit()

        # Re-run detector with different score
        finding_v2 = Finding(
            code="short_vs_siblings",
            severity="warning",
            score=0.95,
            fingerprint="short_sibling:sec-f2",
            detail={"length": 5, "median": 100, "n": 5},
        )
        result = await findings_store.upsert_findings(db, [("sec-f2", "doc-f2", finding_v2)])
        await db.commit()

        assert result["refreshed"] == 1
        assert result["inserted"] == 0

        # Triage must still be not_a_defect
        async with db.execute(
            "SELECT triage, score FROM findings WHERE id = ?", (finding_id,)
        ) as cursor:
            row = await cursor.fetchone()
        assert row["triage"] == "not_a_defect"
        assert row["score"] == 0.95  # score updated


@pytest.mark.asyncio
async def test_close_stale_only_closes_new(runtime_sandbox):
    """close_stale only closes triage='new', not human-triaged findings."""
    db_path = runtime_sandbox["db_path"]
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")

        await db.execute("""
            INSERT INTO documents (id, name, pdf_filename, json_filename, total_sections, total_pages, uploaded_at, status)
            VALUES ('doc-f3', 'Test', 'f.pdf', 'f.json', 1, 1, '2026-01-01', 'pending')
        """)
        await db.execute("""
            INSERT INTO sections (id, document_id, section_code, section_heading, sort_order, review_status)
            VALUES ('sec-f3', 'doc-f3', '1', 'Test', 1, 'pending')
        """)
        await db.execute("""
            INSERT INTO findings (section_id, document_id, detector, detector_version, fingerprint, severity, score, triage, first_seen_at, last_seen_at)
            VALUES ('sec-f3', 'doc-f3', 'test_det', '1', 'fp_new', 'warning', 0.5, 'new', '2026-01-01T00:00:00', '2026-01-01T00:00:00')
        """)
        await db.execute("""
            INSERT INTO findings (section_id, document_id, detector, detector_version, fingerprint, severity, score, triage, first_seen_at, last_seen_at)
            VALUES ('sec-f3', 'doc-f3', 'test_det', '1', 'fp_triaged', 'warning', 0.5, 'source_defect', '2026-01-01T00:00:00', '2026-01-01T00:00:00')
        """)
        await db.commit()

        closed = await findings_store.close_stale(db, "2026-08-01T00:00:00")
        await db.commit()

        assert closed == 1

        async with db.execute(
            "SELECT triage FROM findings WHERE fingerprint = 'fp_triaged'"
        ) as cursor:
            row = await cursor.fetchone()
        assert row["triage"] == "source_defect"
