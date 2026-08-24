"""An evidence bundle has to stand on its own, and sign-off has to be earned.

A reviewer's conclusion is only defensible if the package says which PDF and which parse
it was reached against, and includes the findings that were dismissed and the ones that
were orphaned by a reparse — not just the tidy ones.
"""

import json
import zipfile

import pytest

from backend.database import database_connection
from backend.services import blob_store, evidence, review_state
from backend.tests.conftest import (
    ADMIN_EMAIL,
    add_annotation,
    add_finding,
    seed_document,
)

DOCUMENT_ID = "doc-evidence"
SECTION_ID = "sec-evidence"


async def _reviewed_document(db):
    await seed_document(
        db,
        DOCUMENT_ID,
        name="Evidence Act, 2001",
        section_ids=(SECTION_ID,),
        with_active_version=True,
    )
    await db.execute(
        """
        INSERT INTO footnotes (id, section_id, marker, "text", review_status)
        VALUES ('fn-evidence', ?, '1', 'A footnote', 'approved')
        """,
        (SECTION_ID,),
    )
    resolved = await add_annotation(db, SECTION_ID, status="resolved")
    orphan = await add_finding(db, SECTION_ID, DOCUMENT_ID, detector="glyph_split")
    dismissed = await add_finding(db, SECTION_ID, DOCUMENT_ID, detector="wall_of_text")
    await db.execute("UPDATE findings SET orphaned = TRUE WHERE id = ?", (orphan,))
    await db.execute("UPDATE findings SET triage = 'dismissed' WHERE id = ?", (dismissed,))
    await db.commit()
    return {"annotation": resolved, "orphan": orphan, "dismissed": dismissed}


def _manifest(result) -> dict:
    path = blob_store.blob_path(result["key"])
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read("manifest.json"))


async def test_a_bundle_names_its_sources_and_keeps_the_awkward_findings(runtime_sandbox):
    async with database_connection() as db:
        ids = await _reviewed_document(db)

        result = await evidence.build_document_bundle(db, DOCUMENT_ID)
        assert result["bytes"] > 0
        assert result["sha256"] == blob_store.sha256_file(blob_store.blob_path(result["key"]))
        assert result["download_url"] == f"/uploads/{result['key']}"

        manifest = _manifest(result)

    assert manifest["format"] == "crx-evidence-v1"
    assert manifest["document"]["id"] == DOCUMENT_ID
    assert manifest["source_blobs"].keys() == {"pdf", "active_json"}
    assert [version["version_no"] for version in manifest["versions"]] == [1]
    assert [section["id"] for section in manifest["sections"]] == [SECTION_ID]
    assert [note["id"] for note in manifest["footnotes"]] == ["fn-evidence"]
    assert [note["review_status"] for note in manifest["footnotes"]] == ["approved"]
    assert [row["id"] for row in manifest["annotations_including_orphans"]] == [ids["annotation"]]

    findings = {row["id"]: row for row in manifest["findings"]}
    assert findings[ids["orphan"]]["orphaned"] is True, "a finding a reparse orphaned still counts"
    assert findings[ids["dismissed"]]["triage"] == "dismissed", "so does one a reviewer dismissed"

    assert manifest["signoff"] == {
        "stage": "draft",
        "reviewed_by": None,
        "legal_approved_by": None,
    }
    assert manifest["identity_assurance"] == "self_asserted", (
        "the bundle must not imply an authenticated signatory it does not have"
    )


async def test_an_unknown_document_has_no_bundle(runtime_sandbox):
    async with database_connection() as db:
        with pytest.raises(KeyError):
            await evidence.build_document_bundle(db, "no-such-document")
        with pytest.raises(KeyError):
            await evidence.build_regression_bundle(db, 999999)


async def test_a_regression_bundle_carries_the_case_a_pipeline_fix_needs(runtime_sandbox):
    async with database_connection() as db:
        ids = await _reviewed_document(db)
        result = await evidence.build_regression_bundle(db, ids["orphan"])
        path = blob_store.blob_path(result["key"])

    with zipfile.ZipFile(path) as archive:
        case = json.loads(archive.read("finding.json"))
    assert case["id"] == ids["orphan"]
    assert case["detector"] == "glyph_split"
    assert case["section_code"] == "1"
    assert case["plain_text"], "the leaf text is what a regression test asserts against"
    assert case["pdf_filename"] and case["json_filename"]


async def test_signoff_needs_every_leaf_approved_then_a_second_name(
    runtime_sandbox, client, sign_in
):
    async with database_connection() as db:
        await _reviewed_document(db)

    too_early = await client.post(
        f"/api/v2/documents/{DOCUMENT_ID}/signoff", json={"stage": "reviewed"}
    )
    assert too_early.status_code == 409, "a pending leaf blocks sign-off"

    async with database_connection() as db:
        state = await review_state.set_verdict(db, SECTION_ID, "approved")
        await db.commit()
        assert state["document_status"] == "approved"

    reviewed = await client.post(
        f"/api/v2/documents/{DOCUMENT_ID}/signoff", json={"stage": "reviewed"}
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["identity_assurance"] == "self_asserted"

    same_person = await client.post(
        f"/api/v2/documents/{DOCUMENT_ID}/signoff", json={"stage": "legal_approved"}
    )
    assert same_person.status_code == 409, "one name cannot be both stages"

    counsel = await sign_in("reviewer")
    legal = await counsel.post(
        f"/api/v2/documents/{DOCUMENT_ID}/signoff", json={"stage": "legal_approved"}
    )
    assert legal.status_code == 200

    status = await client.get(f"/api/v2/documents/{DOCUMENT_ID}/signoff")
    assert status.json()["signoff_stage"] == "legal_approved"
    assert status.json()["signoff_reviewed_by"] == ADMIN_EMAIL
    assert status.json()["signoff_legal_by"] == "reviewer@crx.test"


async def test_legal_approval_cannot_skip_the_reviewed_stage(runtime_sandbox, sign_in):
    async with database_connection() as db:
        await _reviewed_document(db)
        await review_state.set_verdict(db, SECTION_ID, "approved")
        await db.commit()

    counsel = await sign_in("reviewer")
    skipped = await counsel.post(
        f"/api/v2/documents/{DOCUMENT_ID}/signoff", json={"stage": "legal_approved"}
    )
    assert skipped.status_code == 409


async def test_an_evidence_request_is_one_job_per_document_revision(runtime_sandbox, client):
    async with database_connection() as db:
        await _reviewed_document(db)

    first = await client.post(f"/api/v2/documents/{DOCUMENT_ID}/evidence")
    assert first.status_code == 202
    second = await client.post(f"/api/v2/documents/{DOCUMENT_ID}/evidence")
    assert second.json()["job_id"] == first.json()["job_id"], "same revision, same job"

    async with database_connection() as db:
        await review_state.revoke_document_approval(db, DOCUMENT_ID)
        await db.commit()

    after_change = await client.post(f"/api/v2/documents/{DOCUMENT_ID}/evidence")
    assert after_change.json()["job_id"] != first.json()["job_id"], (
        "content changed, so the old bundle no longer describes the document"
    )

    missing = await client.post("/api/v2/documents/no-such-document/evidence")
    assert missing.status_code == 404
