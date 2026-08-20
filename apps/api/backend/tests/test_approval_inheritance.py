"""Approval inheritance is fail-closed.

A variant group can only inherit from a section a human explicitly approved, and only
while every member is byte-identical, unblocked, and backed by an active version hash.
The audit found the opposite: a one-member group could nominate its own first member as
the "approved" source, so unreviewed legal text acquired approval on its own.
"""

import pytest

from backend.database import database_connection
from backend.services import review_state, variants


async def _setup_variant_group(db, count=3, *, text="This is the exact same text."):
    """A family of `count` editions sharing one section, each with an active version."""
    for index in range(count):
        document_id = f"doc-inh-{index}"
        await db.execute(
            """
            INSERT INTO documents (id, name, pdf_filename, json_filename,
                                   total_sections, total_pages, uploaded_at, status)
            VALUES (?, ?, 'test.pdf', 'test.json', 1, 1, '2026-01-01', 'pending')
            """,
            (document_id, f"Inheritance Test, {2020 + index}"),
        )
        await db.execute(
            """
            INSERT INTO document_versions (id, document_id, version_no, json_filename,
                                           json_sha256, created_at, total_sections, is_active)
            VALUES (?, ?, 1, 'json/x.json', ?, '2026-01-01', 1, TRUE)
            """,
            (f"ver-inh-{index}", document_id, f"sha-{index}"),
        )
        await db.execute(
            """
            INSERT INTO sections (id, document_id, section_code, section_heading,
                                  sort_order, review_status, plain_text, html_content)
            VALUES (?, ?, '42', 'Test Section', 1, 'pending', ?, ?)
            """,
            (f"sec-inh-{index}", document_id, text, f"<p>{text}</p>"),
        )
    await db.commit()


async def _group_key(db, minimum=3):
    async with db.execute(
        "SELECT variant_key FROM section_variants "
        "GROUP BY variant_key HAVING COUNT(*) >= ? LIMIT 1",
        (minimum,),
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None, f"expected a variant group with >= {minimum} members"
    return row["variant_key"]


async def _approved_group(db, count=4):
    """A group whose first member carries a real human verdict."""
    await _setup_variant_group(db, count=count)
    await variants.rebuild(db)
    key = await _group_key(db)
    state = await review_state.set_verdict(db, "sec-inh-0", "approved")
    assert state["effective_status"] == "approved"
    return key


@pytest.mark.asyncio
async def test_approve_variant_requires_min_editions(runtime_sandbox):
    async with database_connection() as db:
        await _setup_variant_group(db, count=1)
        await variants.rebuild(db)
        key = await _group_key(db, minimum=1)
        result = await variants.approve_variant(db, key, actor="test")
        assert "error" in result and "editions" in result["error"]


@pytest.mark.asyncio
async def test_approve_variant_refuses_without_a_human_approved_source(runtime_sandbox):
    """The regression the audit named: nobody approved anything, so nothing inherits."""
    async with database_connection() as db:
        await _setup_variant_group(db, count=4)
        await variants.rebuild(db)
        key = await _group_key(db)

        result = await variants.approve_variant(db, key, actor="test")
        assert result["error"] == "variant requires an explicitly human-approved source"

        async with db.execute(
            "SELECT COUNT(*) FROM sections WHERE review_status = 'approved_inherited'"
        ) as cursor:
            assert (await cursor.fetchone())[0] == 0
        async with db.execute("SELECT COUNT(*) FROM approval_inheritance") as cursor:
            assert (await cursor.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_approve_variant_refuses_when_a_member_is_blocked(runtime_sandbox):
    async with database_connection() as db:
        key = await _approved_group(db)
        await db.execute(
            "UPDATE footnotes SET review_status = 'has_issues' WHERE FALSE"
        )  # no footnotes here; block through a verdict instead
        await review_state.set_verdict(db, "sec-inh-2", "needs_work")

        result = await variants.approve_variant(db, key, actor="test")
        assert result["error"] == "variant member has blockers"
        assert result["section_id"] == "sec-inh-2"


@pytest.mark.asyncio
async def test_approve_variant_refuses_when_the_text_is_not_identical(runtime_sandbox):
    async with database_connection() as db:
        key = await _approved_group(db)
        await db.execute(
            "UPDATE section_variants SET text_sha = 'different' WHERE section_id = ?",
            ("sec-inh-3",),
        )
        result = await variants.approve_variant(db, key, actor="test")
        assert "identical" in result["error"]


@pytest.mark.asyncio
async def test_approve_variant_propagates_from_the_human_source(runtime_sandbox):
    async with database_connection() as db:
        key = await _approved_group(db)

        result = await variants.approve_variant(db, key, actor="test")
        assert result.get("error") is None, result
        assert result["inherited"] == 3

        async with db.execute(
            "SELECT id, review_status, reviewer_verdict FROM sections ORDER BY id"
        ) as cursor:
            rows = {row["id"]: dict(row) for row in await cursor.fetchall()}
        assert rows["sec-inh-0"]["reviewer_verdict"] == "approved"
        for other in ("sec-inh-1", "sec-inh-2", "sec-inh-3"):
            assert rows[other]["review_status"] == "approved_inherited"
            assert rows[other]["reviewer_verdict"] == "pending", (
                "inherited confidence must never read as a human verdict"
            )

        async with db.execute(
            "SELECT source_id, inheritor_id, policy_version, evidence "
            "FROM approval_inheritance ORDER BY inheritor_id"
        ) as cursor:
            inheritance = [dict(row) for row in await cursor.fetchall()]
        assert len(inheritance) == 3
        assert {row["source_id"] for row in inheritance} == {"sec-inh-0"}
        evidence = inheritance[0]["evidence"]
        assert evidence["source_section_id"] == "sec-inh-0"
        assert evidence["approved_by"] == "test"
        assert len(evidence["active_versions"]) == 4, "each edition's version is recorded"


@pytest.mark.asyncio
async def test_source_delete_revokes_inherited_approval(runtime_sandbox):
    async with database_connection() as db:
        key = await _approved_group(db)
        assert (await variants.approve_variant(db, key, actor="test"))["inherited"] == 3

        await db.execute("DELETE FROM sections WHERE id = 'sec-inh-0'")
        await db.commit()

        async with db.execute("SELECT COUNT(*) FROM approval_inheritance") as cursor:
            assert (await cursor.fetchone())[0] == 0, "CASCADE removes the evidence"

        # With the evidence gone the inheritance no longer validates, so a refresh must
        # drop each recipient back to pending rather than leave it looking approved.
        for section_id in ("sec-inh-1", "sec-inh-2", "sec-inh-3"):
            state = await review_state.refresh_section(db, section_id)
            assert state["effective_status"] == "pending"
