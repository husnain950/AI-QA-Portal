"""A document seeded over HTTP must be the same row a local sync would create.

A deployment has no source PDFs, so `sync_acts` cannot run there and `push_corpus`
re-uploads over the API instead. That produced a *different kind of row*:
`source_type='upload'`, `source_key=NULL`, a random uuid4 for an id. Three
consequences, all of them live in production:

* `acts_metrics.ingest` matches on `source_key`, so every pipeline-health row was
  unmatched and the badges the UI already renders had nothing to feed them.
* Identity was `documents.name`, a display string, so two documents sharing a name
  silently became one.
* A re-push created a second row rather than a new version -- which is why the
  Makefile warns that re-uploading resets every section to pending, and why a nightly
  GitHub Action exists to back up the review state it destroys.
"""

import io
import json

import pytest
from fastapi import HTTPException, UploadFile
from pypdf import PdfWriter

from backend.routes.documents import upload_document
from backend.sync_acts import deterministic_document_id
from backend.tests.conftest import sample_document


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


PDF_BYTES = _pdf_bytes()


def _upload(name="Test Corpus Act", json_text=None):
    return {
        "pdf": UploadFile(filename="act.pdf", file=io.BytesIO(PDF_BYTES)),
        "json_file": UploadFile(
            filename="act.json",
            file=io.BytesIO((json_text or sample_document()).encode()),
        ),
        "name": name,
    }


async def _row(db, document_id):
    async with db.execute(
        "SELECT id, source_type, source_key, corpus_origin, source_hash, withdrawn_at "
        "FROM documents WHERE id = ?",
        (document_id,),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def test_a_seeded_document_gets_the_id_a_local_sync_would_mint(db, runtime_sandbox):
    created = await upload_document(
        **_upload(), source_key="Test Corpus Act", corpus_origin="acts", db=db
    )
    assert created.id == deterministic_document_id("Test Corpus Act")
    assert created.source_type == "acts_corpus"
    assert created.source_key == "Test Corpus Act"

    row = await _row(db, created.id)
    assert row["corpus_origin"] == "acts"
    assert row["source_hash"], "no source_hash means every sync rewrites it"


async def test_pushing_twice_is_a_version_not_a_second_row(db, runtime_sandbox):
    """`make push-remote` twice in a row must cost nothing and destroy nothing."""
    first = await upload_document(
        **_upload(), source_key="Test Corpus Act", corpus_origin="acts", db=db
    )
    await db.execute(
        "UPDATE sections SET review_status = 'approved' WHERE document_id = ?",
        (first.id,),
    )
    await db.commit()

    second = await upload_document(
        **_upload(), source_key="Test Corpus Act", corpus_origin="acts", db=db
    )
    assert second.id == first.id

    async with db.execute("SELECT COUNT(*) AS n FROM documents") as cursor:
        assert (await cursor.fetchone())["n"] == 1, "a re-push created a second row"
    async with db.execute(
        "SELECT COUNT(*) AS n FROM document_versions WHERE document_id = ?", (first.id,)
    ) as cursor:
        assert (await cursor.fetchone())["n"] == 1, "identical bytes are not a version"
    async with db.execute(
        "SELECT COUNT(*) AS n FROM sections "
        "WHERE document_id = ? AND review_status = 'approved'",
        (first.id,),
    ) as cursor:
        assert (await cursor.fetchone())["n"] == 2, "a re-push reset the review state"


async def test_a_changed_push_is_a_new_version_that_carries_review_state(db, runtime_sandbox):
    first = await upload_document(
        **_upload(), source_key="Test Corpus Act", corpus_origin="acts", db=db
    )
    await db.execute(
        "UPDATE sections SET review_status = 'approved' WHERE document_id = ?",
        (first.id,),
    )
    await db.commit()

    await upload_document(
        **_upload(json_text=sample_document(second_text="Corrected second section")),
        source_key="Test Corpus Act",
        corpus_origin="acts",
        db=db,
    )

    async with db.execute(
        "SELECT COUNT(*) AS n FROM document_versions WHERE document_id = ?", (first.id,)
    ) as cursor:
        assert (await cursor.fetchone())["n"] == 2
    async with db.execute(
        "SELECT section_code, review_status FROM sections "
        "WHERE document_id = ? ORDER BY sort_order",
        (first.id,),
    ) as cursor:
        statuses = [dict(r) for r in await cursor.fetchall()]
    # The untouched leaf keeps its approval; only the corrected one is reset.
    assert [s["review_status"] for s in statuses] == ["approved", "pending"], statuses


async def test_a_seeded_document_is_visible_to_reconciliation(db, runtime_sandbox):
    """A pushed row with no `corpus_origin` could never be withdrawn, so a
    deployment would accumulate retired documents forever."""
    from backend.services.corpus_sync import reconcile_corpus

    created = await upload_document(
        **_upload(), source_key="Test Corpus Act", corpus_origin="acts", db=db
    )
    result = await reconcile_corpus("acts", [])
    assert result["withdrawn"] == ["Test Corpus Act"]
    assert (await _row(db, created.id))["withdrawn_at"]


async def test_pushing_it_back_clears_the_withdrawal(db, runtime_sandbox):
    from backend.services.corpus_sync import reconcile_corpus

    created = await upload_document(
        **_upload(), source_key="Test Corpus Act", corpus_origin="acts", db=db
    )
    await reconcile_corpus("acts", [])
    assert (await _row(db, created.id))["withdrawn_at"]

    await upload_document(
        **_upload(), source_key="Test Corpus Act", corpus_origin="acts", db=db
    )
    assert (await _row(db, created.id))["withdrawn_at"] is None


async def test_a_hand_upload_is_untouched(db, runtime_sandbox):
    """No `source_key` means the old behaviour, exactly: a uuid4 and an upload row."""
    created = await upload_document(**_upload(name="Hand Upload"), db=db)
    assert created.source_type == "upload"
    assert created.source_key is None
    row = await _row(db, created.id)
    assert row["corpus_origin"] is None
    assert row["source_hash"] is None


async def test_an_origin_without_a_key_is_refused(db, runtime_sandbox):
    """It would be a row reconciliation counts but can never match, so the next
    sync of that corpus would withdraw it immediately."""
    with pytest.raises(HTTPException) as caught:
        await upload_document(**_upload(), corpus_origin="acts", db=db)
    assert caught.value.status_code == 400
    assert "source_key" in str(caught.value.detail)


async def test_the_seeded_source_hash_matches_what_a_local_sync_computes(db, runtime_sandbox):
    """If the two disagreed, the first local sync would rewrite every pushed
    document and manufacture a version for each."""
    import hashlib

    from backend.services import blob_store

    body = sample_document().encode()
    created = await upload_document(
        **_upload(json_text=body.decode()),
        source_key="Test Corpus Act",
        corpus_origin="acts",
        db=db,
    )
    row = await _row(db, created.id)
    expected = hashlib.sha256(
        f"{blob_store.sha256_bytes(PDF_BYTES)}:{blob_store.sha256_bytes(body)}".encode("ascii")
    ).hexdigest()
    assert row["source_hash"] == expected, json.dumps(row, indent=2)
