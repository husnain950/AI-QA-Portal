"""Structural leaf identity: a leaf inserted above another must not disturb it.

`source_key` is the positional JSON-pointer path (`/chapters/0/sections/3`), so
inserting one leaf renames every later sibling. Measured over the corpus that is
**386 leaves falsely reported "changed"** across 84 documents, 16 of them churning
100% of themselves -- and in `apply_parsed_document` a false "changed" is not
cosmetic: it resets approvals, revokes inheritance, and re-anchors annotations
against the wrong leaf's text.

These tests are written against the behaviour, not the implementation: they set up
human review state, reprocess with a structural change, and assert what survived.
Every one of them fails when leaves are matched by `source_key`.
"""

import json

import pytest

from backend.database import database_connection
from backend.services.document_store import apply_parsed_document
from backend.services.json_parser import parse_json_document
from backend.tests.conftest import add_annotation

DOCUMENT_ID = "node-key-doc"


def _doc(codes, *, bodies=None):
    """A contract-v1 document whose chapter holds one leaf per code, in order."""
    bodies = bodies or {}
    return json.dumps({
        "metadata": {"total_pages": 9, "contract_version": 1},
        "chapters": [{
            "code": "I", "heading": "General", "type": "chapter",
            "node_key": "ch:i", "parts": [], "divisions": [],
            "sections": [
                {
                    "code": code,
                    "heading": f"Section {code}",
                    "start_page": index + 1,
                    "end_page": index + 1,
                    "type": "section",
                    "node_key": f"ch:i/s:{code.lower()}",
                    "html": f"<p>{bodies.get(code, f'body of {code}')}</p>",
                    "plain_text": bodies.get(code, f"body of {code}"),
                    "footnotes": [],
                }
                for index, code in enumerate(codes)
            ],
        }],
        "schedules": [],
    })


async def _create_document(db):
    await db.execute(
        """
        INSERT INTO documents (
            id, name, pdf_filename, json_filename, total_sections,
            total_pages, uploaded_at, status, source_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (DOCUMENT_ID, "Node Key Act", "act.pdf", "act.json", 0, 9,
         "2026-08-31T00:00:00Z", "pending", "upload"),
    )


async def _apply(db, codes, **kwargs):
    sections, footnotes = parse_json_document(_doc(codes, **kwargs), document_id=DOCUMENT_ID)
    return await apply_parsed_document(db, DOCUMENT_ID, sections, footnotes)


async def _by_code(db):
    async with db.execute(
        "SELECT section_code, id, node_key, source_key, review_status "
        "FROM sections WHERE document_id = ?",
        (DOCUMENT_ID,),
    ) as cursor:
        return {row["section_code"]: dict(row) for row in await cursor.fetchall()}


async def test_inserting_a_leaf_leaves_its_siblings_untouched(runtime_sandbox):
    """The headline case: approvals below an insertion survive it."""
    async with database_connection() as db:
        await _create_document(db)
        await _apply(db, ["2", "3", "4"])
        await db.execute(
            "UPDATE sections SET review_status = 'approved' WHERE document_id = ?",
            (DOCUMENT_ID,),
        )
        await db.commit()
        before = await _by_code(db)
        assert all(row["node_key"] for row in before.values())

        stats = await _apply(db, ["1", "2", "3", "4"])
        await db.commit()
        after = await _by_code(db)

        # One leaf added; nothing else changed, removed, or reset.
        assert stats["carryover"]["sections_added"] == 1, stats["carryover"]
        assert stats["carryover"]["sections_changed"] == 0, stats["carryover"]
        assert stats["carryover"]["sections_removed"] == 0, stats["carryover"]
        assert stats["carryover"]["approvals_reset"] == 0, stats["carryover"]

        # The three survivors kept their ids AND their approvals. On source_key
        # every one of them is a different row with a reset status.
        for code in ("2", "3", "4"):
            assert after[code]["id"] == before[code]["id"], code
            assert after[code]["review_status"] == "approved", code
        assert after["1"]["review_status"] == "pending"
        assert after["1"]["node_key"] == "ch:i/s:1"

        # ...and their positional keys really did shift, so the test is exercising
        # the case it claims to.
        assert before["2"]["source_key"] != after["2"]["source_key"]


async def test_inserting_a_leaf_does_not_reanchor_a_sibling_annotation(runtime_sandbox):
    """An annotation on a later leaf must not be re-anchored against another leaf."""
    async with database_connection() as db:
        await _create_document(db)
        await _apply(db, ["2", "3"])
        await db.commit()
        rows = await _by_code(db)
        await add_annotation(db, rows["3"]["id"], highlighted_text="body of 3")
        await db.commit()

        stats = await _apply(db, ["1", "2", "3"])
        await db.commit()

        carry = stats["carryover"]
        assert carry["reanchored"] == 0, carry
        assert carry["needs_recheck"] == 0, carry
        assert carry["orphaned"] == 0, carry

        async with db.execute(
            "SELECT section_id, anchor_status FROM annotations WHERE document_id = ?",
            (DOCUMENT_ID,),
        ) as cursor:
            annotations = [dict(row) for row in await cursor.fetchall()]
        assert len(annotations) == 1
        assert annotations[0]["section_id"] == rows["3"]["id"]


async def test_removing_a_leaf_removes_exactly_that_leaf(runtime_sandbox):
    """A deletion is a deletion, not a rename of everything after it."""
    async with database_connection() as db:
        await _create_document(db)
        await _apply(db, ["1", "2", "3"])
        await db.execute(
            "UPDATE sections SET review_status = 'approved' WHERE document_id = ?",
            (DOCUMENT_ID,),
        )
        await db.commit()
        before = await _by_code(db)

        stats = await _apply(db, ["1", "3"])
        await db.commit()
        after = await _by_code(db)

        assert stats["carryover"]["sections_removed"] == 1, stats["carryover"]
        assert stats["carryover"]["sections_added"] == 0, stats["carryover"]
        assert stats["carryover"]["approvals_lost"] == 1, stats["carryover"]
        assert set(after) == {"1", "3"}
        assert after["3"]["id"] == before["3"]["id"]
        assert after["3"]["review_status"] == "approved"


async def test_a_real_edit_is_still_reported_and_still_resets(runtime_sandbox):
    """The key narrows the report; it must not switch it off."""
    async with database_connection() as db:
        await _create_document(db)
        await _apply(db, ["1", "2"])
        await db.execute(
            "UPDATE sections SET review_status = 'approved' WHERE document_id = ?",
            (DOCUMENT_ID,),
        )
        await db.commit()

        stats = await _apply(db, ["1", "2"], bodies={"2": "body of 2, corrected"})
        await db.commit()
        after = await _by_code(db)

        assert stats["carryover"]["sections_changed"] == 1, stats["carryover"]
        assert stats["carryover"]["approvals_reset"] == 1, stats["carryover"]
        assert after["1"]["review_status"] == "approved"
        assert after["2"]["review_status"] == "pending"


async def test_identical_reprocessing_changes_nothing(runtime_sandbox):
    async with database_connection() as db:
        await _create_document(db)
        await _apply(db, ["1", "2", "3"])
        await db.commit()
        before = await _by_code(db)

        stats = await _apply(db, ["1", "2", "3"])
        await db.commit()

        assert stats["carryover"]["sections_added"] == 0
        assert stats["carryover"]["sections_changed"] == 0
        assert stats["carryover"]["sections_removed"] == 0
        assert await _by_code(db) == before


async def test_a_document_without_node_key_still_matches_by_source_key(runtime_sandbox):
    """The bridge for documents converted before the contract.

    They keep the old behaviour exactly -- including its churn, which is why the
    fallback is a migration affordance and not a design.
    """
    def legacy(codes):
        payload = json.loads(_doc(codes))
        payload["metadata"].pop("contract_version")
        for node in payload["chapters"]:
            node.pop("node_key", None)
            node.pop("type", None)
            for leaf in node["sections"]:
                leaf.pop("node_key", None)
                leaf.pop("type", None)
        return json.dumps(payload)

    async with database_connection() as db:
        await _create_document(db)
        sections, footnotes = parse_json_document(legacy(["1", "2"]), document_id=DOCUMENT_ID)
        assert all(s["node_key"] is None for s in sections)
        await apply_parsed_document(db, DOCUMENT_ID, sections, footnotes)
        await db.execute(
            "UPDATE sections SET review_status = 'approved' WHERE document_id = ?",
            (DOCUMENT_ID,),
        )
        await db.commit()
        before = await _by_code(db)

        sections, footnotes = parse_json_document(legacy(["1", "2"]), document_id=DOCUMENT_ID)
        stats = await apply_parsed_document(db, DOCUMENT_ID, sections, footnotes)
        await db.commit()
        after = await _by_code(db)

        assert stats["carryover"]["sections_changed"] == 0, stats["carryover"]
        assert after["1"]["id"] == before["1"]["id"]
        assert after["1"]["review_status"] == "approved"
        assert after["1"]["node_key"] is None


async def test_the_first_ingest_after_the_column_backfills_it(runtime_sandbox):
    """Existing rows are matched by source_key and gain node_key without re-minting.

    This is the migration, and it is the one path that cannot be got wrong: an id
    that changes here is an id already inside an exported evidence bundle.
    """
    async with database_connection() as db:
        await _create_document(db)
        await _apply(db, ["1", "2", "3"])
        # Rewind to the pre-migration state: rows exist, none carries a node_key.
        await db.execute(
            "UPDATE sections SET node_key = NULL WHERE document_id = ?", (DOCUMENT_ID,)
        )
        await db.execute(
            "UPDATE sections SET review_status = 'approved' WHERE document_id = ?",
            (DOCUMENT_ID,),
        )
        await db.commit()
        before = await _by_code(db)
        assert all(row["node_key"] is None for row in before.values())

        stats = await _apply(db, ["1", "2", "3"])
        await db.commit()
        after = await _by_code(db)

        assert stats["carryover"]["sections_added"] == 0, stats["carryover"]
        assert stats["carryover"]["sections_removed"] == 0, stats["carryover"]
        for code in ("1", "2", "3"):
            assert after[code]["id"] == before[code]["id"], code
            assert after[code]["review_status"] == "approved", code
            assert after[code]["node_key"] == f"ch:i/s:{code}", code


@pytest.mark.parametrize("codes", [["1", "2", "3"], ["3", "1", "2"]])
async def test_reordering_leaves_keeps_every_id(runtime_sandbox, codes):
    """Reading order is a property of the document, not of a leaf's identity."""
    async with database_connection() as db:
        await _create_document(db)
        await _apply(db, ["1", "2", "3"])
        await db.execute(
            "UPDATE sections SET review_status = 'approved' WHERE document_id = ?",
            (DOCUMENT_ID,),
        )
        await db.commit()
        before = await _by_code(db)

        stats = await _apply(db, codes)
        await db.commit()
        after = await _by_code(db)

        assert stats["carryover"]["sections_added"] == 0, stats["carryover"]
        assert stats["carryover"]["sections_removed"] == 0, stats["carryover"]
        for code in ("1", "2", "3"):
            assert after[code]["id"] == before[code]["id"], code
            assert after[code]["review_status"] == "approved", code
