import pytest

from backend.database import database_connection
from backend.services.document_store import ReviewConflict, apply_parsed_document
from backend.services.json_parser import parse_json_document
from backend.tests.conftest import add_annotation, sample_document


@pytest.mark.asyncio
async def test_store_preserves_state_and_rejects_annotated_content_changes_in_strict_mode(
    runtime_sandbox,
):
    document_id = "store-document"
    sections, footnotes = parse_json_document(
        sample_document(),
        document_id=document_id,
    )
    async with database_connection() as db:
        await db.execute(
            """
            INSERT INTO documents (
                id, name, pdf_filename, json_filename, total_sections,
                total_pages, uploaded_at, status, source_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                "Store Act",
                "act.pdf",
                "act.json",
                2,
                3,
                "2026-07-29T00:00:00Z",
                "pending",
                "upload",
            ),
        )
        await apply_parsed_document(db, document_id, sections, footnotes)
        first_id = sections[0]["id"]
        second_id = sections[1]["id"]
        await db.execute(
            "UPDATE sections SET review_status = 'approved' WHERE id IN (?, ?)",
            (first_id, second_id),
        )
        await add_annotation(db, first_id, highlighted_text="First")
        await db.commit()

        identical_stats = await apply_parsed_document(
            db,
            document_id,
            sections,
            footnotes,
        )
        assert identical_stats["approved"] == 2

        changed_sections, changed_footnotes = parse_json_document(
            sample_document(second_text="Corrected second section"),
            document_id=document_id,
        )
        changed_sections[0]["plain_text"] = "Changed annotated content"
        with pytest.raises(ReviewConflict, match="changed with 1 annotation"):
            await apply_parsed_document(
                db,
                document_id,
                changed_sections,
                changed_footnotes,
                mode="strict",
            )
        await db.rollback()

        changed_sections[0] = sections[0]
        stats = await apply_parsed_document(
            db,
            document_id,
            changed_sections,
            changed_footnotes,
        )
        await db.commit()
        assert stats["approved"] == 1
        assert stats["pending"] == 1
        async with db.execute(
            "SELECT review_status FROM sections WHERE id = ?",
            (second_id,),
        ) as cursor:
            assert (await cursor.fetchone())[0] == "pending"


@pytest.mark.asyncio
async def test_store_strict_mode_rejects_removing_reviewed_evidence(runtime_sandbox):
    document_id = "remove-document"
    sections, footnotes = parse_json_document(
        sample_document(),
        document_id=document_id,
    )
    async with database_connection() as db:
        await db.execute(
            """
            INSERT INTO documents (
                id, name, pdf_filename, json_filename, total_sections,
                total_pages, uploaded_at, status, source_type
            ) VALUES (?, 'Act', 'a.pdf', 'a.json', 2, 3, 'now', 'pending', 'upload')
            """,
            (document_id,),
        )
        await apply_parsed_document(db, document_id, sections, footnotes)
        await db.execute(
            "UPDATE sections SET review_status = 'approved' WHERE id = ?",
            (sections[1]["id"],),
        )
        await db.commit()

        with pytest.raises(ReviewConflict, match="was removed with QA state"):
            await apply_parsed_document(
                db,
                document_id,
                sections[:1],
                footnotes,
                mode="strict",
            )
        await db.rollback()


@pytest.mark.asyncio
async def test_store_strict_mode_rejects_reviewed_footnote_removal(
    runtime_sandbox,
):
    document_id = "footnote-remove-document"
    sections, footnotes = parse_json_document(
        sample_document(),
        document_id=document_id,
    )
    async with database_connection() as db:
        await db.execute(
            """
            INSERT INTO documents (
                id, name, pdf_filename, json_filename, total_sections,
                total_pages, uploaded_at, status, source_type
            ) VALUES (?, 'Act', 'a.pdf', 'a.json', 2, 3, 'now', 'pending', 'upload')
            """,
            (document_id,),
        )
        await apply_parsed_document(db, document_id, sections, footnotes)
        await db.execute(
            "UPDATE footnotes SET review_status = 'approved' WHERE id = ?",
            (footnotes[0]["id"],),
        )
        await db.commit()

        with pytest.raises(ReviewConflict, match="footnote 1 was removed"):
            await apply_parsed_document(
                db,
                document_id,
                sections[1:],
                [],
                mode="strict",
            )
        await db.rollback()


@pytest.mark.asyncio
async def test_parser_autoflag_does_not_block_an_upstream_fix(tmp_path):
    """`has_issues` is machine-assigned, so it must not veto a corrected parse.

    The guard used to treat any non-pending status as QA state. Because
    `parse_json_document` stamps `has_issues` on every parse, re-syncing a corrected
    corpus refused 64 of 93 documents on rows the parser had flagged itself — leaving
    reviewers stuck on the defective structure for good.
    """
    from backend.services.document_store import _carries_human_qa_state

    auto_flagged = {"review_status": "has_issues", "annotation_count": 0}
    assert not _carries_human_qa_state(auto_flagged)

    # Human intent is still protected.
    assert _carries_human_qa_state({"review_status": "approved", "annotation_count": 0})
    assert _carries_human_qa_state(
        {"review_status": "approved_inherited", "annotation_count": 0}
    )
    assert _carries_human_qa_state({"review_status": "pending", "annotation_count": 1})
    assert _carries_human_qa_state({"review_status": "has_issues", "annotation_count": 2})
    assert not _carries_human_qa_state({"review_status": "pending", "annotation_count": 0})
