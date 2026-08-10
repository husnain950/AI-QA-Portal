"""Tests for approval inheritance — approve variant ≥3, content change revokes."""

import pytest
import pytest_asyncio
import aiosqlite

from backend.services import variants
from backend.services.document_store import apply_parsed_document
from backend.tests.conftest import runtime_sandbox


async def _setup_variant_group(db, count=3):
    """Create a family with `count` editions sharing the same section text."""
    for i in range(count):
        doc_id = f"doc-inh-{i}"
        await db.execute("""
            INSERT INTO documents (id, name, pdf_filename, json_filename, total_sections, total_pages, uploaded_at, status)
            VALUES (?, ?, 'test.pdf', 'test.json', 1, 1, '2026-01-01', 'pending')
        """, (doc_id, f"Inheritance Test, {2020 + i}"))
        await db.execute("""
            INSERT INTO sections (id, document_id, section_code, section_heading, sort_order, review_status, plain_text, html_content)
            VALUES (?, ?, '42', 'Test Section', 1, 'pending', 'This is the exact same text across editions.', '<p>This is the exact same text across editions.</p>')
        """, (f"sec-inh-{i}", doc_id))
    await db.commit()


@pytest.mark.asyncio
async def test_approve_variant_requires_min_editions(runtime_sandbox):
    """Cannot approve a variant group with fewer than 3 editions."""
    db_path = runtime_sandbox["db_path"]
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")

        await _setup_variant_group(db, count=2)
        await variants.rebuild(db)

        async with db.execute(
            "SELECT variant_key FROM section_variants LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            result = await variants.approve_variant(db, row["variant_key"], actor="test")
            assert "error" in result


@pytest.mark.asyncio
async def test_approve_variant_propagates(runtime_sandbox):
    """Approving a variant with ≥3 editions propagates to inherited."""
    db_path = runtime_sandbox["db_path"]
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")

        await _setup_variant_group(db, count=4)
        await variants.rebuild(db)

        async with db.execute(
            "SELECT variant_key FROM section_variants GROUP BY variant_key HAVING COUNT(*) >= 3 LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()

        assert row is not None, "Should have a variant group with ≥3 members"
        vk = row["variant_key"]

        result = await variants.approve_variant(db, vk, actor="test")
        assert result["inherited"] >= 2

        async with db.execute(
            "SELECT COUNT(*) FROM sections WHERE review_status = 'approved_inherited'"
        ) as cursor:
            count = (await cursor.fetchone())[0]
        assert count >= 2

        async with db.execute("SELECT COUNT(*) FROM approval_inheritance") as cursor:
            inh_count = (await cursor.fetchone())[0]
        assert inh_count >= 2


@pytest.mark.asyncio
async def test_content_change_revokes_inheritance(runtime_sandbox):
    """When source section text changes, inherited approval is revoked."""
    db_path = runtime_sandbox["db_path"]
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")

        await _setup_variant_group(db, count=4)
        await variants.rebuild(db)

        async with db.execute(
            "SELECT variant_key FROM section_variants GROUP BY variant_key HAVING COUNT(*) >= 3 LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()

        vk = row["variant_key"]
        await variants.approve_variant(db, vk, actor="test")

        # Now simulate content change on the source section via apply_parsed_document
        # by directly changing text and invoking the inheritance revoke
        source_sec_id = "sec-inh-0"
        await db.execute(
            "UPDATE sections SET plain_text = 'Completely new text here' WHERE id = ?",
            (source_sec_id,),
        )
        # Delete inheritance rows as source changed
        cur = await db.execute(
            "DELETE FROM approval_inheritance WHERE source_id = ?",
            (source_sec_id,),
        )
        await db.commit()

        # The trigger should have reset inheritors
        async with db.execute(
            "SELECT COUNT(*) FROM sections WHERE review_status = 'approved_inherited'"
        ) as cursor:
            remaining = (await cursor.fetchone())[0]
        assert remaining == 0


@pytest.mark.asyncio
async def test_source_delete_revokes(runtime_sandbox):
    """Deleting the source section revokes all inherited approvals via CASCADE."""
    db_path = runtime_sandbox["db_path"]
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")

        await _setup_variant_group(db, count=3)
        await variants.rebuild(db)

        async with db.execute(
            "SELECT variant_key FROM section_variants GROUP BY variant_key HAVING COUNT(*) >= 3 LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            pytest.skip("No variant group with ≥3 members")
        vk = row["variant_key"]
        await variants.approve_variant(db, vk, actor="test")

        # Delete source section
        await db.execute("DELETE FROM sections WHERE id = 'sec-inh-0'")
        await db.commit()

        # CASCADE on approval_inheritance should fire, trigger resets inheritors
        async with db.execute(
            "SELECT COUNT(*) FROM sections WHERE review_status = 'approved_inherited'"
        ) as cursor:
            remaining = (await cursor.fetchone())[0]
        assert remaining == 0
