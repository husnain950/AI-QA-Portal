import io
import json

import aiosqlite
import pytest
from fastapi import UploadFile

from backend.models import FootnoteStatusUpdate
from backend.routes.documents import replace_json
from backend.routes.footnotes import update_footnote_status
from backend.sync_acts import run_sync
from backend.tests.conftest import sample_document, write_pair


@pytest.mark.asyncio
async def test_footnote_revert_restores_document_pending_status(runtime_sandbox):
    source = runtime_sandbox["root"] / "export"
    write_pair(source)
    await run_sync(source)

    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT f.id AS footnote_id, d.id AS document_id
            FROM footnotes f
            JOIN sections s ON s.id = f.section_id
            JOIN documents d ON d.id = s.document_id
            LIMIT 1
            """
        ) as cursor:
            row = await cursor.fetchone()

        await update_footnote_status(
            row["footnote_id"],
            FootnoteStatusUpdate(review_status="approved"),
            db,
            actor="tester",
        )
        async with db.execute(
            "SELECT status FROM documents WHERE id = ?",
            (row["document_id"],),
        ) as cursor:
            assert (await cursor.fetchone())["status"] == "in_progress"

        await update_footnote_status(
            row["footnote_id"],
            FootnoteStatusUpdate(review_status="pending"),
            db,
            actor="tester",
        )
        async with db.execute(
            "SELECT status FROM documents WHERE id = ?",
            (row["document_id"],),
        ) as cursor:
            assert (await cursor.fetchone())["status"] == "pending"


@pytest.mark.asyncio
async def test_act_corpus_json_can_be_replaced_and_becomes_a_new_version(
    runtime_sandbox,
):
    """ACT-corpus documents used to 409 here.

    That guard existed because a replacement overwrote the parse in place with no way
    back. Versions make it reversible, so the reviewer can push a corrected JSON without
    waiting for a corpus sync -- and the sync still reconciles by content hash.
    """
    source = runtime_sandbox["root"] / "export"
    write_pair(source)
    await run_sync(source)

    payload = json.loads(sample_document())
    payload["chapters"][0]["sections"][0]["plain_text"] = "Corrected first section"
    payload["chapters"][0]["sections"][0]["html"] = "<p>Corrected first section</p>"

    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id FROM documents LIMIT 1") as cursor:
            document_id = (await cursor.fetchone())["id"]

        replacement = UploadFile(
            filename="replacement.json",
            file=io.BytesIO(json.dumps(payload).encode()),
        )
        response = await replace_json(
            document_id, replacement, note="fixed table parsing", db=db
        )
        assert response.id == document_id

        async with db.execute(
            "SELECT version_no, note, is_active FROM document_versions "
            "WHERE document_id = ? ORDER BY version_no",
            (document_id,),
        ) as cursor:
            rows = [dict(row) for row in await cursor.fetchall()]
        async with db.execute(
            "SELECT plain_text FROM sections ORDER BY sort_order LIMIT 1"
        ) as cursor:
            text = (await cursor.fetchone())["plain_text"]

    assert [row["version_no"] for row in rows] == [1, 2]
    assert rows[1]["is_active"] == 1 and rows[0]["is_active"] == 0
    assert rows[1]["note"] == "fixed table parsing"
    assert text == "Corrected first section"


@pytest.mark.asyncio
async def test_replacing_with_identical_json_creates_no_version(runtime_sandbox):
    source = runtime_sandbox["root"] / "export"
    write_pair(source)
    await run_sync(source)

    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id FROM documents LIMIT 1") as cursor:
            document_id = (await cursor.fetchone())["id"]
        await replace_json(
            document_id,
            UploadFile(
                filename="same.json", file=io.BytesIO(sample_document().encode())
            ),
            db=db,
        )
        async with db.execute(
            "SELECT COUNT(*) FROM document_versions WHERE document_id = ?",
            (document_id,),
        ) as cursor:
            count = (await cursor.fetchone())[0]

    assert count == 1, "identical bytes must not manufacture an empty version"
