"""Upload validation happens once, up front, and says what is wrong.

The old flow told the reviewer "JSON Schema holds valid structure" after only checking
that the file parsed, then failed later with a generic message. Preflight stages both
files, checks them against each other, and only then hands back a token to commit.
"""

import io
import json

import pytest
from pypdf import PdfWriter

from backend.database import database_connection
from backend.services import blob_store
from backend.tests.conftest import ADMIN_EMAIL, sample_document


def _pdf(pages=3) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _files(pdf_bytes=None, json_text=None):
    return {
        "pdf": ("source.pdf", pdf_bytes if pdf_bytes is not None else _pdf(), "application/pdf"),
        "json_file": (
            "structure.json",
            (json_text if json_text is not None else sample_document()).encode(),
            "application/json",
        ),
    }


async def _preflight(client, **kwargs):
    return await client.post("/api/v2/uploads/preflight", files=_files(**kwargs))


@pytest.mark.asyncio
async def test_preflight_reports_what_it_actually_counted(runtime_sandbox, client):
    response = await _preflight(client)
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["errors"] == [] and body["warnings"] == []
    assert body["pages"] == 3, "read from the PDF, not from the JSON's claim"
    assert body["sections"] == 2
    assert body["footnotes"] == 1
    assert body["pdf_bytes"] > 0 and body["json_bytes"] > 0
    assert body["token"] and body["expires_at"]

    async with database_connection() as db:
        async with db.execute(
            "SELECT pdf_key, json_key, created_by, committed_at FROM upload_staging WHERE token = ?",
            (body["token"],),
        ) as cursor:
            staged = dict(await cursor.fetchone())
    assert staged["created_by"] == ADMIN_EMAIL
    assert staged["committed_at"] is None
    storage = blob_store.get_storage()
    assert storage.exists(staged["pdf_key"]) and storage.exists(staged["json_key"])


@pytest.mark.asyncio
async def test_a_renamed_non_pdf_is_caught_by_its_bytes(runtime_sandbox, client):
    response = await _preflight(client, pdf_bytes=b"GIF89a not a pdf at all")
    assert response.status_code == 400
    assert response.json()["detail"]["errors"][0]["code"] == "invalid_magic"


@pytest.mark.asyncio
async def test_broken_json_points_at_the_line(runtime_sandbox, client):
    response = await _preflight(client, json_text='{"chapters": [')
    assert response.status_code == 400
    error = response.json()["detail"]["errors"][0]
    assert error["code"] == "invalid_json"
    assert "line" in error["message"], "a reviewer needs the position, not just 'invalid'"


@pytest.mark.asyncio
async def test_a_json_with_nothing_to_review_is_refused(runtime_sandbox, client):
    response = await _preflight(client, json_text=json.dumps({"chapters": [], "schedules": []}))
    assert response.status_code == 422
    codes = {error["code"] for error in response.json()["detail"]["errors"]}
    assert "zero_sections" in codes


@pytest.mark.asyncio
async def test_page_spans_are_checked_against_the_real_pdf(runtime_sandbox, client):
    payload = json.loads(sample_document())
    payload["chapters"][0]["sections"][0]["end_page"] = 99

    response = await _preflight(client, json_text=json.dumps(payload))
    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    codes = {error["code"] for error in errors}
    assert "invalid_page_span" in codes
    assert any("1-3" in error["message"] for error in errors), "say what the PDF actually has"


@pytest.mark.asyncio
async def test_a_declared_page_count_that_disagrees_is_reported(runtime_sandbox, client):
    payload = json.loads(sample_document())
    payload["metadata"]["total_pages"] = 7

    response = await _preflight(client, json_text=json.dumps(payload))
    assert response.status_code == 422
    errors = {error["code"]: error for error in response.json()["detail"]["errors"]}
    assert errors["page_count_mismatch"]["pointer"] == "/metadata/total_pages"


@pytest.mark.asyncio
async def test_commit_creates_the_document_and_burns_the_token(runtime_sandbox, client):
    token = (await _preflight(client)).json()["token"]

    created = await client.post(
        "/api/v2/documents", json={"token": token, "name": "Committed Act, 2001"}
    )
    assert created.status_code == 201, created.text
    document = created.json()
    assert document["name"] == "Committed Act, 2001"
    assert document["total_pages"] == 3

    async with database_connection() as db:
        async with db.execute(
            "SELECT version_no, is_active, created_by FROM document_versions WHERE document_id = ?",
            (document["id"],),
        ) as cursor:
            versions = [dict(row) for row in await cursor.fetchall()]
        async with db.execute(
            "SELECT pdf_key, json_key FROM upload_staging WHERE token = ?", (token,)
        ) as cursor:
            staged = dict(await cursor.fetchone())
    assert versions == [{"version_no": 1, "is_active": True, "created_by": ADMIN_EMAIL}]

    storage = blob_store.get_storage()
    assert not storage.exists(staged["pdf_key"]), "staging is cleaned up after the commit"
    assert not storage.exists(staged["json_key"])

    replay = await client.post(
        "/api/v2/documents", json={"token": token, "name": "Committed Again"}
    )
    assert replay.status_code == 409, "a token commits once"


@pytest.mark.asyncio
async def test_committing_an_unknown_or_expired_token_fails_clearly(runtime_sandbox, client):
    unknown = await client.post(
        "/api/v2/documents", json={"token": "00000000-0000-0000-0000-000000000000", "name": "x"}
    )
    assert unknown.status_code == 404

    token = (await _preflight(client)).json()["token"]
    async with database_connection() as db:
        await db.execute(
            "UPDATE upload_staging SET expires_at = '2020-01-01T00:00:00+00:00' WHERE token = ?",
            (token,),
        )
        await db.commit()

    expired = await client.post("/api/v2/documents", json={"token": token, "name": "x"})
    assert expired.status_code == 410


@pytest.mark.asyncio
async def test_uploading_needs_a_session_and_the_admin_role(
    runtime_sandbox, anonymous, sign_in
):
    unauthenticated = await anonymous.post("/api/v2/uploads/preflight", files=_files())
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["code"] == "unauthenticated"

    reviewer = await sign_in("reviewer")
    forbidden = await reviewer.post("/api/v2/uploads/preflight", files=_files())
    assert forbidden.status_code == 403
    assert forbidden.json()["required_role"] == "admin"
