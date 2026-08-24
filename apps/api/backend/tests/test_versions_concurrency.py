"""Version numbers cannot collide, and a stale activation cannot win.

Two reviewers with the same document open used to be able to activate over each other
without either noticing, and two concurrent uploads computed the next version number as
MAX(version_no) + 1 with nothing serializing them.
"""

import asyncio
import io
import json

import pytest
from fastapi import UploadFile
from pypdf import PdfWriter

from backend.database import database_connection
from backend.routes.documents import upload_document
from backend.services import versions
from backend.tests.conftest import open_connection, sample_document


def _pdf() -> bytes:
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


async def _document(db):
    created = await upload_document(
        pdf=UploadFile(filename="act.pdf", file=io.BytesIO(_pdf())),
        json_file=UploadFile(filename="act.json", file=io.BytesIO(sample_document().encode())),
        name="Concurrency Act, 2001",
        db=db,
    )
    await db.commit()
    return created.id


def _variant(text: str) -> bytes:
    return sample_document(second_text=text).encode()


async def test_two_concurrent_version_creations_do_not_collide(runtime_sandbox):
    async with database_connection() as db:
        document_id = await _document(db)

    first, second = await open_connection(), await open_connection()

    async def create(db, text):
        row, outcome = await versions.create_version(
            db, document_id, _variant(text), created_by="racer"
        )
        await db.commit()
        return row["version_no"], outcome["status"]

    # The FOR UPDATE on the documents row is what serializes these; without it both
    # would read MAX(version_no) = 1 and both would try to insert version 2.
    results = await asyncio.gather(
        create(first, "First racer"), create(second, "Second racer")
    )
    assert sorted(number for number, _ in results) == [2, 3]

    async with database_connection() as db:
        async with db.execute(
            "SELECT version_no, is_active FROM document_versions "
            "WHERE document_id = ? ORDER BY version_no",
            (document_id,),
        ) as cursor:
            rows = [dict(row) for row in await cursor.fetchall()]
    assert [row["version_no"] for row in rows] == [1, 2, 3]
    assert [row["is_active"] for row in rows].count(True) == 1, "exactly one active version"


async def test_identical_bytes_are_not_a_new_version(runtime_sandbox):
    async with database_connection() as db:
        document_id = await _document(db)
        row, outcome = await versions.create_version(
            db, document_id, sample_document().encode(), created_by="tester"
        )
        assert outcome["status"] == "unchanged"
        assert row["version_no"] == 1


async def test_creating_a_version_against_a_stale_expectation_is_refused(runtime_sandbox):
    async with database_connection() as db:
        document_id = await _document(db)
        active = await versions.active_version(db, document_id)

        await versions.create_version(db, document_id, _variant("Moved on"), created_by="other")
        await db.commit()

        with pytest.raises(versions.StaleVersion) as error:
            await versions.create_version(
                db,
                document_id,
                _variant("Based on what I was looking at"),
                created_by="tester",
                expected_version_id=active["id"],
            )
        assert error.value.current_version_id != active["id"]
        await db.rollback()


async def test_replace_json_requires_an_if_match_and_rejects_a_stale_one(runtime_sandbox, client):
    async with database_connection() as db:
        document_id = await _document(db)
        active_id = (await versions.active_version(db, document_id))["id"]

    files = {"json_file": ("act.json", _variant("Replaced"), "application/json")}

    missing = await client.post(f"/api/documents/{document_id}/replace-json", files=files)
    assert missing.status_code == 428, "If-Match is required, not optional"
    assert missing.json()["detail"]["code"] == "if_match_required"

    stale = await client.post(
        f"/api/documents/{document_id}/replace-json",
        files={"json_file": ("act.json", _variant("Stale"), "application/json")},
        headers={"If-Match": '"version:not-the-active-one"'},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_version"

    accepted = await client.post(
        f"/api/documents/{document_id}/replace-json",
        files={"json_file": ("act.json", _variant("Accepted"), "application/json")},
        headers={"If-Match": f'W/"version:{active_id}"'},
    )
    assert accepted.status_code == 200, accepted.text

    # And the same If-Match cannot be replayed now that it is no longer active.
    replay = await client.post(
        f"/api/documents/{document_id}/replace-json",
        files={"json_file": ("act.json", _variant("Replayed"), "application/json")},
        headers={"If-Match": f'"version:{active_id}"'},
    )
    assert replay.status_code == 409


async def test_activating_over_someone_elses_change_is_refused(runtime_sandbox, client):
    async with database_connection() as db:
        document_id = await _document(db)
        first_id = (await versions.active_version(db, document_id))["id"]
        await versions.create_version(db, document_id, _variant("Second"), created_by="other")
        await db.commit()
        second_id = (await versions.active_version(db, document_id))["id"]

    missing = await client.post(
        f"/api/documents/{document_id}/versions/{first_id}/activate"
    )
    assert missing.status_code == 428, "If-Match is required to activate, too"
    assert missing.json()["detail"]["code"] == "if_match_required"

    stale = await client.post(
        f"/api/documents/{document_id}/versions/{first_id}/activate",
        headers={"If-Match": f'"version:{first_id}"'},
    )
    assert stale.status_code == 409, "the reviewer was looking at version 1, not version 2"
    assert stale.json()["detail"]["current_version"] == second_id

    rolled_back = await client.post(
        f"/api/documents/{document_id}/versions/{first_id}/activate",
        headers={"If-Match": f'"version:{second_id}"'},
    )
    assert rolled_back.status_code == 200

    async with database_connection() as db:
        async with db.execute(
            "SELECT id FROM document_versions WHERE document_id = ? AND is_active",
            (document_id,),
        ) as cursor:
            assert (await cursor.fetchone())["id"] == first_id
        async with db.execute(
            "SELECT plain_text FROM sections ORDER BY sort_order DESC LIMIT 1"
        ) as cursor:
            assert (await cursor.fetchone())["plain_text"] == "Second section", (
                "activation re-applies the parse, it does not just move a flag"
            )


async def test_the_active_version_is_advertised_for_the_next_write(runtime_sandbox, client):
    """A client cannot send If-Match unless the read told it what to send."""
    async with database_connection() as db:
        document_id = await _document(db)

    listed = await client.get(f"/api/documents/{document_id}/versions")
    assert listed.status_code == 200
    payload = listed.json()
    active = [version for version in payload if version["is_active"]]
    assert len(active) == 1
    assert active[0]["id"]
    assert json.dumps(payload), "response is serialisable as-is"
