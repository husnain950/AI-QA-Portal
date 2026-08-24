"""One place decides what a section's review state is.

The audit found four ways this used to go wrong: a section could be approved over an
open annotation, stay flagged after its footnote was cleared, drop to pending while a
quality flag was still live, and a document with every section flagged was reported
"completed". Each of those is a test here.
"""

import json

import pytest

from backend.database import database_connection
from backend.services import review_state
from backend.tests.conftest import add_annotation, seed_document

DOCUMENT_ID = "doc-state"
SECTION_ID = "sec-state"
OTHER_SECTION_ID = "sec-state-2"


async def _document(db, *, sections=(SECTION_ID,)):
    await seed_document(
        db, DOCUMENT_ID, name="Review State Act, 2001", section_ids=tuple(sections)
    )


async def test_a_clean_section_is_pending_and_approves_on_a_verdict(runtime_sandbox):
    async with database_connection() as db:
        await _document(db)

        state = await review_state.refresh_section(db, SECTION_ID)
        assert state == {
            "section_id": SECTION_ID,
            "reviewer_verdict": "pending",
            "effective_status": "pending",
            "review_status": "pending",
            "blockers": [],
            "document_status": "pending",
        }

        approved = await review_state.set_verdict(db, SECTION_ID, "approved")
        assert approved["effective_status"] == "approved"
        assert approved["document_status"] == "approved"


async def test_an_unknown_verdict_is_refused(runtime_sandbox):
    async with database_connection() as db:
        await _document(db)
        with pytest.raises(ValueError, match="reviewer verdict"):
            await review_state.set_verdict(db, SECTION_ID, "looks-fine-to-me")


async def test_needs_work_blocks_without_any_other_signal(runtime_sandbox):
    async with database_connection() as db:
        await _document(db)
        state = await review_state.set_verdict(db, SECTION_ID, "needs_work")
        assert state["effective_status"] == "blocked"
        assert state["review_status"] == "has_issues", "legacy column stays in step"


@pytest.mark.parametrize(
    "reason",
    ["blocking_quality_flag", "open_annotation", "annotation_recheck", "flagged_footnote",
     "unresolved_error_finding"],
)
async def test_each_blocker_holds_an_approved_verdict(runtime_sandbox, reason):
    """An approved verdict must never win over a live blocker."""
    async with database_connection() as db:
        await _document(db)
        await review_state.set_verdict(db, SECTION_ID, "approved")

        if reason == "blocking_quality_flag":
            await db.execute(
                "UPDATE sections SET quality_flags = ? WHERE id = ?",
                (json.dumps([{"code": "missing_table", "reason": "table lost"}]), SECTION_ID),
            )
        elif reason == "open_annotation":
            await add_annotation(db, SECTION_ID, status="open")
        elif reason == "annotation_recheck":
            annotation_id = await add_annotation(db, SECTION_ID, status="resolved")
            await db.execute(
                "UPDATE annotations SET anchor_status = 'orphaned' WHERE id = ?",
                (annotation_id,),
            )
        elif reason == "flagged_footnote":
            await db.execute(
                """
                INSERT INTO footnotes (id, section_id, marker, "text", review_status)
                VALUES ('fn-1', ?, '1', 'note', 'has_issues')
                """,
                (SECTION_ID,),
            )
        else:
            await db.execute(
                """
                INSERT INTO findings (section_id, document_id, detector, detector_version,
                                      fingerprint, severity, score, triage,
                                      first_seen_at, last_seen_at)
                VALUES (?, ?, 'glyph_split', '1', 'fp-1', 'error', 10, 'new',
                        '2026-01-01', '2026-01-01')
                """,
                (SECTION_ID, DOCUMENT_ID),
            )

        state = await review_state.refresh_section(db, SECTION_ID)
        assert state["blockers"] == [reason]
        assert state["effective_status"] == "blocked"
        assert state["reviewer_verdict"] == "approved", (
            "the verdict is remembered, not erased, so clearing the blocker restores it"
        )
        assert state["document_status"] == "blocked"


async def test_clearing_the_last_blocker_restores_the_verdict_not_pending(runtime_sandbox):
    """Resolving the last annotation used to reset the section to pending outright."""
    async with database_connection() as db:
        await _document(db)
        annotation_id = await add_annotation(db, SECTION_ID, status="open")
        await review_state.set_verdict(db, SECTION_ID, "approved")
        assert (await review_state.refresh_section(db, SECTION_ID))["effective_status"] == "blocked"

        await db.execute(
            "UPDATE annotations SET status = 'resolved' WHERE id = ?", (annotation_id,)
        )
        state = await review_state.refresh_section(db, SECTION_ID)
        assert state["blockers"] == []
        assert state["effective_status"] == "approved"


async def test_a_document_with_a_blocked_section_is_never_reported_complete(runtime_sandbox):
    """The exact bug: status was derived from "nothing pending", so all-flagged read done."""
    async with database_connection() as db:
        await _document(db, sections=(SECTION_ID, OTHER_SECTION_ID))

        await review_state.set_verdict(db, SECTION_ID, "approved")
        assert (await review_state.refresh_document(db, DOCUMENT_ID)) == "in_progress"

        await review_state.set_verdict(db, OTHER_SECTION_ID, "needs_work")
        assert (await review_state.refresh_document(db, DOCUMENT_ID)) == "blocked"

        await review_state.set_verdict(db, OTHER_SECTION_ID, "approved")
        assert (await review_state.refresh_document(db, DOCUMENT_ID)) == "approved"


async def test_a_missing_section_is_a_key_error_not_a_silent_pass(runtime_sandbox):
    async with database_connection() as db:
        with pytest.raises(KeyError):
            await review_state.refresh_section(db, "no-such-section")


async def test_a_content_change_revokes_approval_and_signoff(runtime_sandbox):
    async with database_connection() as db:
        await _document(db, sections=(SECTION_ID, OTHER_SECTION_ID))
        await review_state.set_verdict(db, SECTION_ID, "approved")
        await review_state.set_verdict(db, OTHER_SECTION_ID, "approved")
        await db.execute(
            "UPDATE documents SET signoff_stage = 'legal_approved', "
            "signoff_reviewed_by = 'r', signoff_legal_by = 'l' WHERE id = ?",
            (DOCUMENT_ID,),
        )

        await review_state.revoke_document_approval(db, DOCUMENT_ID)

        async with db.execute(
            "SELECT status, signoff_stage, signoff_reviewed_by, signoff_legal_by, row_revision "
            "FROM documents WHERE id = ?",
            (DOCUMENT_ID,),
        ) as cursor:
            document = dict(await cursor.fetchone())
        assert document["status"] == "pending"
        assert document["signoff_stage"] == "draft"
        assert document["signoff_reviewed_by"] is None
        assert document["signoff_legal_by"] is None
        assert document["row_revision"] >= 1, "the revision moves so stale writes 409"

        async with db.execute(
            "SELECT DISTINCT reviewer_verdict, effective_status FROM sections WHERE document_id = ?",
            (DOCUMENT_ID,),
        ) as cursor:
            rows = [dict(row) for row in await cursor.fetchall()]
        assert rows == [{"reviewer_verdict": "pending", "effective_status": "pending"}]
