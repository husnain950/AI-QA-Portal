"""Tests for review_events table: append-only triggers and record helper."""

import pytest
from sqlalchemy.exc import DatabaseError

from backend.database import database_connection
from backend.services import events


@pytest.mark.asyncio
async def test_review_events_append_only(runtime_sandbox):
    """Triggers prevent UPDATE and DELETE on review_events."""
    async with database_connection() as db:

        row_id = await events.record(
            db,
            actor="tester",
            action="test_action",
            document_id="doc-1",
        )
        await db.commit()
        assert row_id is not None

        with pytest.raises(DatabaseError):
            await db.execute(
                "UPDATE review_events SET actor = 'hacker' WHERE id = ?",
                (row_id,),
            )

        with pytest.raises(DatabaseError):
            await db.execute(
                "DELETE FROM review_events WHERE id = ?", (row_id,)
            )


@pytest.mark.asyncio
async def test_record_on_approve(runtime_sandbox):
    """Event is recorded with from/to values."""
    async with database_connection() as db:

        await events.record(
            db,
            actor="reviewer-A",
            action="section_status",
            document_id="doc-1",
            section_id="sec-1",
            version_id="ver-1",
            from_value="pending",
            to_value="approved",
        )
        await db.commit()

        async with db.execute(
            "SELECT * FROM review_events WHERE action = 'section_status'"
        ) as cursor:
            row = await cursor.fetchone()

        assert row is not None
        assert row["actor"] == "reviewer-A"
        assert row["from_value"] == "pending"
        assert row["to_value"] == "approved"
        assert row["document_id"] == "doc-1"
        assert row["section_id"] == "sec-1"
        assert row["version_id"] == "ver-1"


@pytest.mark.asyncio
async def test_record_with_detail(runtime_sandbox):
    """detail_json round-trips correctly."""
    async with database_connection() as db:

        import json
        detail = {"disposition": "source_defect", "note": "PDF is garbled"}
        await events.record(
            db,
            actor="reviewer-B",
            action="annotation_update",
            detail=detail,
        )
        await db.commit()

        async with db.execute(
            "SELECT detail_json FROM review_events WHERE actor = 'reviewer-B'"
        ) as cursor:
            row = await cursor.fetchone()

        assert row is not None
        parsed = json.loads(row["detail_json"])
        assert parsed["disposition"] == "source_defect"
