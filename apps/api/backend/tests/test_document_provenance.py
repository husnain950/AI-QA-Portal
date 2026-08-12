import io
import json

import aiosqlite
import pytest
from fastapi import UploadFile
from pypdf import PdfWriter

from backend.routes.documents import list_documents, upload_document
from backend.services.document_provenance import (
    SOURCE_KIND_MIXED,
    SOURCE_KIND_NATIVE,
    SOURCE_KIND_SCANNED,
    TAG_NEEDS_REVIEW,
    TAG_PROVISIONAL,
    derive_from_json_content,
    derive_from_metadata,
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

    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
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
