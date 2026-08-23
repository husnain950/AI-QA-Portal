"""The QA report export, in both formats.

`routes/export.py` had no test at all while it was a single 205-line function holding
two serializers and two copies of the filename rule. These pin the parts that a reader
of the export actually depends on -- the shape of the JSON, the CSV header, and the
download filename -- so the split into fetch + two serializers is checked rather than
assumed.
"""

from __future__ import annotations

import csv
import io

from backend.database import database_connection
from backend.tests.conftest import add_annotation, seed_document

DOCUMENT_ID = "doc-export"
SECTION_ID = "sec-export"


async def _seed():
    async with database_connection() as db:
        await seed_document(
            db, DOCUMENT_ID, name="Sales Tax Act, 1990", section_ids=(SECTION_ID,)
        )
        await add_annotation(db, SECTION_ID, highlighted_text="jammed words")
        await db.commit()


async def test_the_json_export_carries_the_document_sections_and_summary(
    runtime_sandbox, client
):
    await _seed()
    response = await client.get(f"/api/documents/{DOCUMENT_ID}/export?format=json")
    assert response.status_code == 200, response.text
    body = response.json()

    assert set(body) >= {"document", "sections", "footnotes", "summary"}
    assert body["document"]["name"] == "Sales Tax Act, 1990"
    assert body["summary"]["total_annotations"] == 1
    assert set(body["summary"]["by_severity"]) == {"error", "warning", "info"}
    # generated_at is offset-aware UTC; it used to come from the deprecated
    # datetime.utcnow(), which produced a naive value with a "Z" glued on.
    assert body["summary"]["generated_at"].endswith("Z")
    assert "+00:00" not in body["summary"]["generated_at"]


async def test_the_csv_export_has_its_header_and_one_row_per_annotation(
    runtime_sandbox, client
):
    await _seed()
    response = await client.get(f"/api/documents/{DOCUMENT_ID}/export?format=csv")
    assert response.status_code == 200, response.text

    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0][0] == "Section Code"
    assert rows[0][-1] == "Created At"
    assert len(rows[0]) == 10
    assert len(rows) == 2                      # header + the one annotation
    assert "jammed words" in rows[1]


async def test_both_formats_name_the_download_after_the_document(
    runtime_sandbox, client
):
    await _seed()
    for fmt, extension in (("json", "json"), ("csv", "csv")):
        response = await client.get(
            f"/api/documents/{DOCUMENT_ID}/export?format={fmt}"
        )
        disposition = response.headers["content-disposition"]
        # spaces become underscores and punctuation is dropped, so the filename is
        # safe to write to disk unquoted
        assert disposition == (
            f"attachment; filename=Sales_Tax_Act_1990_QA_Report.{extension}"
        ), disposition
