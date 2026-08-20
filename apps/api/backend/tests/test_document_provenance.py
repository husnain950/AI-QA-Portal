import io
import json

import pytest
from fastapi import UploadFile
from pypdf import PdfWriter

from backend.database import database_connection
from backend.routes.documents import list_documents, upload_document
from backend.services.document_provenance import (
    SOURCE_KIND_MIXED,
    SOURCE_KIND_NATIVE,
    SOURCE_KIND_SCANNED,
    TAG_NEEDS_REVIEW,
    TAG_PDF_INFERRED,
    TAG_PROVISIONAL,
    backfill_provenance_row,
    derive_from_json_content,
    derive_from_metadata,
    deserialize_provenance,
    section_intersects_ocr,
)
from backend.tests.conftest import sample_document


def test_native_when_no_ocr():
    provenance = derive_from_metadata({"total_pages": 100}, total_pages=100)
    assert provenance.source_kind == SOURCE_KIND_NATIVE
    assert provenance.tags == [SOURCE_KIND_NATIVE]
    assert provenance.ocr_pages is None
    assert provenance.pages_ocred == []


def test_scanned_when_ocr_covers_most_pages():
    provenance = derive_from_metadata(
        {
            "total_pages": 30,
            "ocr": {
                "pages": 30,
                "pages_ocred": list(range(1, 31)),
                "mean_agreement": 92.5,
                "floor": "admitted",
                "needs_review_tokens": 0,
            },
        },
        total_pages=30,
    )
    assert provenance.source_kind == SOURCE_KIND_SCANNED
    assert SOURCE_KIND_SCANNED in provenance.tags
    assert TAG_PROVISIONAL not in provenance.tags
    assert provenance.ocr_pages == 30
    assert provenance.mean_agreement == 92.5
    assert provenance.floor == "admitted"


def test_mixed_when_few_pages_ocred():
    provenance = derive_from_metadata(
        {
            "total_pages": 952,
            "ocr": {
                "pages": 1,
                "pages_ocred": [1],
                "mean_agreement": 88.0,
                "floor": "admitted",
                "needs_review_tokens": 3,
            },
        },
        total_pages=952,
    )
    assert provenance.source_kind == SOURCE_KIND_MIXED
    assert TAG_NEEDS_REVIEW in provenance.tags
    assert provenance.pages_ocred == [1]


def test_provisional_additive_tag():
    provenance = derive_from_metadata(
        {
            "total_pages": 10,
            "ocr": {
                "pages": 10,
                "pages_ocred": list(range(1, 11)),
                "floor": "provisional",
                "provisional": True,
                "needs_review_tokens": 0,
            },
        },
        total_pages=10,
    )
    assert provenance.source_kind == SOURCE_KIND_SCANNED
    assert TAG_PROVISIONAL in provenance.tags


def test_explicit_source_kind_honoured():
    provenance = derive_from_metadata(
        {"source_kind": "native-digital", "total_pages": 5},
        total_pages=5,
    )
    assert provenance.source_kind == SOURCE_KIND_NATIVE


def test_derive_from_json_content():
    payload = json.dumps(
        {
            "metadata": {
                "total_pages": 20,
                "ocr": {"pages": 2, "pages_ocred": [1, 2], "needs_review_tokens": 0},
            },
            "chapters": [],
        }
    )
    provenance = derive_from_json_content(payload, total_pages=20)
    assert provenance.source_kind == SOURCE_KIND_MIXED


def test_section_intersects_ocr():
    assert section_intersects_ocr(2, 4, [1, 3, 9]) is True
    assert section_intersects_ocr(5, 6, [1, 3, 9]) is False
    assert section_intersects_ocr(None, None, [1]) is False


def _pdf_bytes(pages: int = 3) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _pdf_path_from_bytes(pdf_bytes: bytes, *, suffix: str = ".pdf"):
    import tempfile

    tf = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tf.write(pdf_bytes)
    tf.close()
    return tf.name


def test_pdf_fallback_infers_scanned_when_no_ocr(monkeypatch):
    # Force the scan heuristic to consider every sampled page as scan-heavy.
    import acts_ingest.pagemodel as pagemodel

    monkeypatch.setattr(pagemodel, "_page_is_scan", lambda page, **_: True)

    pdf_path = _pdf_path_from_bytes(_pdf_bytes(pages=3))
    try:
        payload = json.dumps({"metadata": {"total_pages": 3}, "chapters": []})
        provenance = derive_from_json_content(payload, total_pages=3, pdf_path=pdf_path)
        assert provenance.source_kind == SOURCE_KIND_SCANNED
        assert TAG_PDF_INFERRED in provenance.tags
        assert provenance.pages_ocred == [1, 2, 3]
    finally:
        import os

        os.unlink(pdf_path)


def test_pdf_fallback_infers_mixed_when_partial_scan(monkeypatch):
    # Mark the first 2/3 pages as scan-heavy => 0.66 ratio => mixed-ocr.
    import acts_ingest.pagemodel as pagemodel

    def infer(page, **_):
        return page.page_number <= 2

    monkeypatch.setattr(pagemodel, "_page_is_scan", infer)

    pdf_path = _pdf_path_from_bytes(_pdf_bytes(pages=3))
    try:
        payload = json.dumps({"metadata": {"total_pages": 3}, "chapters": []})
        provenance = derive_from_json_content(payload, total_pages=3, pdf_path=pdf_path)
        assert provenance.source_kind == SOURCE_KIND_MIXED
        assert TAG_PDF_INFERRED in provenance.tags
        assert provenance.pages_ocred == [1, 2]
    finally:
        import os

        os.unlink(pdf_path)


def test_json_ocr_block_wins_over_pdf_inference(monkeypatch):
    import acts_ingest.pagemodel as pagemodel

    monkeypatch.setattr(pagemodel, "_page_is_scan", lambda page, **_: True)

    pdf_path = _pdf_path_from_bytes(_pdf_bytes(pages=3))
    try:
        payload = json.dumps(
            {
                "metadata": {
                    "total_pages": 3,
                    # OCR block present but says "no OCR pages" => native-digital.
                    "ocr": {"pages": 0, "pages_ocred": [], "needs_review_tokens": 0},
                },
                "chapters": [],
            }
        )
        provenance = derive_from_json_content(payload, total_pages=3, pdf_path=pdf_path)
        assert provenance.source_kind == SOURCE_KIND_NATIVE
        assert TAG_PDF_INFERRED not in provenance.tags
    finally:
        import os

        os.unlink(pdf_path)


@pytest.mark.asyncio
async def test_list_documents_includes_provenance(runtime_sandbox):
    payload = json.loads(sample_document())
    payload["metadata"] = {
        "total_pages": 3,
        "ocr": {
            "pages": 1,
            "pages_ocred": [1],
            "mean_agreement": 90.0,
            "floor": "admitted",
            "needs_review_tokens": 2,
        },
        "source_kind": "mixed-ocr",
    }
    json_text = json.dumps(payload)

    async with database_connection() as db:
        created = await upload_document(
            pdf=UploadFile(filename="act.pdf", file=io.BytesIO(_pdf_bytes())),
            json_file=UploadFile(
                filename="act.json", file=io.BytesIO(json_text.encode())
            ),
            name="OCR Act",
            db=db,
        )
        assert created.provenance is not None
        assert created.provenance.source_kind == SOURCE_KIND_MIXED
        assert TAG_NEEDS_REVIEW in created.provenance.tags

        listed = await list_documents(db)
        match = next(doc for doc in listed if doc.id == created.id)
        assert match.provenance is not None
        assert match.provenance.source_kind == SOURCE_KIND_MIXED
        assert match.provenance.pages_ocred == [1]


@pytest.mark.asyncio
async def test_upload_document_uses_pdf_fallback_provenance(runtime_sandbox, monkeypatch):
    import acts_ingest.pagemodel as pagemodel

    monkeypatch.setattr(pagemodel, "_page_is_scan", lambda page, **_: True)

    json_text = sample_document()

    async with database_connection() as db:
        created = await upload_document(
            pdf=UploadFile(filename="act.pdf", file=io.BytesIO(_pdf_bytes(pages=3))),
            json_file=UploadFile(filename="act.json", file=io.BytesIO(json_text.encode())),
            name="OCR Act",
            db=db,
        )
        assert created.provenance is not None
        assert created.provenance.source_kind == SOURCE_KIND_SCANNED
        assert TAG_PDF_INFERRED in created.provenance.tags


@pytest.mark.asyncio
async def test_backfill_provenance_reinferences_native_when_json_has_no_ocr(
    runtime_sandbox, monkeypatch
):
    import acts_ingest.pagemodel as pagemodel
    from backend.models import DocumentProvenance
    from backend.services import blob_store
    from backend.services.document_provenance import serialize_provenance

    monkeypatch.setattr(pagemodel, "_page_is_scan", lambda page, **_: True)

    pdf_name = blob_store.store_bytes(_pdf_bytes(pages=3), "pdf")
    json_content = json.dumps({"metadata": {"total_pages": 3}, "chapters": []}).encode(
        "utf-8"
    )
    json_name = blob_store.store_bytes(json_content, "json")

    doc_id = "backfill-doc"
    existing = DocumentProvenance(
        source_kind=SOURCE_KIND_NATIVE,
        tags=[SOURCE_KIND_NATIVE],
        ocr_pages=None,
        ocr_total_pages=3,
        mean_agreement=None,
        floor=None,
        pages_ocred=[],
    )
    existing_raw = serialize_provenance(existing)

    async with database_connection() as db:
        await db.execute(
            """
            INSERT INTO documents (
                id, name, pdf_filename, json_filename, total_sections, total_pages,
                uploaded_at, status, provenance
            )
            VALUES (?, ?, ?, ?, ?, ?, '2026-01-01', 'pending', ?)
            """,
            (doc_id, "Backfill Doc", pdf_name, json_name, 1, 3, existing_raw),
        )
        await db.commit()

        pdf_path = blob_store.blob_path(pdf_name)
        proven = await backfill_provenance_row(
            db,
            document_id=doc_id,
            json_filename=json_name,
            total_pages=3,
            existing_raw=existing_raw,
            pdf_path=pdf_path,
            force_native_reinfer=True,
        )
        assert proven is not None
        assert proven.source_kind == SOURCE_KIND_SCANNED
        assert proven.pages_ocred == [1, 2, 3]


@pytest.mark.asyncio
async def test_reinfer_provenance_route_pages_and_is_idempotent(
    runtime_sandbox, monkeypatch
):
    """The route is the only way a *deployment* can reach the PDF fallback.

    ``tools/backfill_provenance.py`` needs local access to the database and blobs, and a
    deployment's are inside its container, so without this the fallback is unreachable
    in production and every scanned act stays labelled native-digital.

    Paging is the part worth pinning: sampling every PDF takes minutes against one
    uvicorn worker, so the route hands back a cursor instead of running the whole
    corpus in one request. A short page must end the walk, and a second pass must
    change nothing.
    """
    import acts_ingest.pagemodel as pagemodel
    from backend.routes.documents import reinfer_provenance
    from backend.services import blob_store

    monkeypatch.setattr(pagemodel, "_page_is_scan", lambda page, **_: True)

    payload = json.dumps({"metadata": {"total_pages": 3}, "chapters": []}).encode("utf-8")
    json_name = blob_store.store_bytes(payload, "json")

    # One document carries real pipeline OCR provenance; the heuristic must not touch it.
    ocr_payload = json.dumps(
        {
            "metadata": {
                "total_pages": 3,
                "ocr": {"pages": 3, "pages_ocred": [1, 2, 3], "mean_agreement": 0.97},
            },
            "chapters": [],
        }
    ).encode("utf-8")
    ocr_json_name = blob_store.store_bytes(ocr_payload, "json")

    async with database_connection() as db:
        for index in range(3):
            await db.execute(
                """
                INSERT INTO documents (
                    id, name, pdf_filename, json_filename, total_sections, total_pages,
                    uploaded_at, status, source_type
                ) VALUES (?, ?, ?, ?, 0, 3, '2026-01-01T00:00:00Z', 'pending', 'upload')
                """,
                (
                    f"doc-{index}",
                    f"Act {index}",
                    blob_store.store_bytes(_pdf_bytes(pages=3), "pdf"),
                    ocr_json_name if index == 2 else json_name,
                ),
            )
        await db.commit()

        # limit=2 over 3 rows: a full page returns a cursor, the short page ends it.
        first = await reinfer_provenance(limit=2, after=None, db=db)
        assert first["processed"] == 2
        assert first["next"] == "doc-1", "a full page must hand back a cursor"
        assert [c["to"] for c in first["changed"]] == [
            SOURCE_KIND_SCANNED,
            SOURCE_KIND_SCANNED,
        ]

        second = await reinfer_provenance(limit=2, after=first["next"], db=db)
        assert second["processed"] == 1
        assert second["next"] is None, "a short page must end the walk"
        # doc-2 had no stored provenance, so filling it in counts as a change -- but the
        # verdict has to come from its JSON OCR block, not the PDF heuristic. The tag
        # and the agreement figure below are what tell those two apart.
        assert second["changed"] == [
            {"id": "doc-2", "from": None, "to": SOURCE_KIND_SCANNED}
        ]

        async with db.execute(
            "SELECT id, provenance FROM documents ORDER BY id"
        ) as cursor:
            stored = {r["id"]: deserialize_provenance(r["provenance"]) for r in await cursor.fetchall()}
        assert stored["doc-0"].source_kind == SOURCE_KIND_SCANNED
        assert TAG_PDF_INFERRED in stored["doc-0"].tags
        # The pipeline's own verdict keeps its evidence and gains no inferred tag.
        assert stored["doc-2"].mean_agreement == 0.97
        assert TAG_PDF_INFERRED not in stored["doc-2"].tags

        again = await reinfer_provenance(limit=100, after=None, db=db)
        assert again["changed"] == [], "re-running must be a no-op"
