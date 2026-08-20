"""Timeline lookup by section id and by the two family-key dialects."""

import json

import pytest

from backend.database import database_connection
from backend.routes.documents import upload_document
from backend.routes.timeline import timeline, timeline_query
from backend.services import variants
from backend.services.detectors import family_key
from backend.services.editions import family_key_from_name
from backend.tests.test_versions_and_blobs import _pdf_bytes, _upload

FOREIGN_ASSETS = "Foreign Assets (Declaration and Repatriation) Act, 2018"
FOREIGN_ASSETS_2017 = "Foreign Assets (Declaration and Repatriation) Act, 2017"
SECTION_14_TEXT = "A person shall declare foreign assets in the prescribed form."
SECTION_14_TEXT_2017 = "A person may declare foreign assets in the prescribed form."


def _fa_payload(text: str) -> str:
    return json.dumps(
        {
            "metadata": {"total_pages": 1},
            "chapters": [
                {
                    "code": "III",
                    "heading": "Declaration",
                    "sections": [
                        {
                            "code": "14",
                            "heading": "Declaration of foreign assets",
                            "start_page": 8,
                            "end_page": 8,
                            "html": f"<p>{text}</p>",
                            "plain_text": text,
                            "footnotes": [],
                        }
                    ],
                }
            ],
            "schedules": [],
        }
    )


async def _insert_edition(db, *, doc_id: str, name: str, section_id: str, text: str):
    await db.execute(
        """
        INSERT INTO documents (
            id, name, pdf_filename, json_filename, total_sections, total_pages,
            uploaded_at, status
        ) VALUES (?, ?, 'test.pdf', 'test.json', 1, 1, '2026-01-01', 'pending')
        """,
        (doc_id, name),
    )
    await db.execute(
        """
        INSERT INTO sections (
            id, document_id, section_code, section_heading, sort_order,
            review_status, plain_text, html_content
        ) VALUES (?, ?, '14', 'Declaration of foreign assets', 1, 'pending', ?, ?)
        """,
        (section_id, doc_id, text, f"<p>{text}</p>"),
    )


@pytest.mark.asyncio
async def test_foreign_assets_section_id_and_review_family_key(runtime_sandbox):
    """The Review-style key used to miss the stored detectors key for this act."""
    assert family_key(FOREIGN_ASSETS) == (
        "foreign assets (declaration and repatriation) act"
    )
    assert family_key_from_name(FOREIGN_ASSETS) == "foreign assets act, 2018"

    async with database_connection() as db:
        await _insert_edition(
            db,
            doc_id="fa-2017",
            name=FOREIGN_ASSETS_2017,
            section_id="fa-sec-2017",
            text=SECTION_14_TEXT_2017,
        )
        await _insert_edition(
            db,
            doc_id="fa-2018",
            name=FOREIGN_ASSETS,
            section_id="fa-sec-2018",
            text=SECTION_14_TEXT,
        )
        await db.commit()
        await variants.rebuild(db)

        by_section = await timeline_query(
            section_id="fa-sec-2018", family=None, section_code=None, db=db
        )
        assert by_section["section_code"] == "14"
        assert by_section["editions"] == 2
        assert [event["kind"] for event in by_section["events"]] == ["first", "changed"]
        assert by_section["events"][1]["section_id"] == "fa-sec-2018"

        by_review_key = await timeline_query(
            section_id=None,
            family="foreign assets act, 2018",
            section_code="14",
            db=db,
        )
        assert by_review_key["editions"] == 2
        assert by_review_key["family"] == family_key(FOREIGN_ASSETS)

        by_path = await timeline(
            family="foreign assets act, 2018", section_code="14", db=db
        )
        assert by_path["editions"] == 2


@pytest.mark.asyncio
async def test_upload_indexes_section_variants(runtime_sandbox):
    async with database_connection() as db:
        created = await upload_document(
            **_upload(_pdf_bytes(), _fa_payload(SECTION_14_TEXT), name=FOREIGN_ASSETS),
            db=db,
        )
        async with db.execute(
            "SELECT family_key, section_code FROM section_variants WHERE document_id = ?",
            (created.id,),
        ) as cursor:
            rows = [dict(row) for row in await cursor.fetchall()]
        assert rows
        assert rows[0]["section_code"] == "14"
        assert rows[0]["family_key"] == family_key(FOREIGN_ASSETS)

        payload = await timeline_query(
            section_id=None,
            family=None,
            section_code=None,
            db=db,
        )
        assert payload["events"] == []

        async with db.execute(
            "SELECT id FROM sections WHERE document_id = ? AND section_code = '14'",
            (created.id,),
        ) as cursor:
            section_id = (await cursor.fetchone())["id"]
        payload = await timeline_query(
            section_id=section_id, family=None, section_code=None, db=db
        )
        assert payload["editions"] == 1
        assert payload["events"][0]["kind"] == "first"


@pytest.mark.asyncio
async def test_rebuild_if_empty_heals_upload_only_db(runtime_sandbox):
    async with database_connection() as db:
        await _insert_edition(
            db,
            doc_id="fa-2018",
            name=FOREIGN_ASSETS,
            section_id="fa-sec-2018",
            text=SECTION_14_TEXT,
        )
        await db.commit()

        assert await variants.rebuild_if_empty(db) is not None
        async with db.execute("SELECT COUNT(*) FROM section_variants") as cursor:
            assert (await cursor.fetchone())[0] == 1
        assert await variants.rebuild_if_empty(db) is None
