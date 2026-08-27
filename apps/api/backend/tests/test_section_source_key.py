"""Section list/detail expose the JSON-pointer source_key used by overlays."""

from backend.tests.conftest import seed_document

DOCUMENT_ID = "doc-leaf-path"
SECTION_ID = "sec-leaf-path"
SOURCE_KEY = "/chapters/4/sections/2"


async def test_section_list_and_detail_include_source_key(db, client):
    await seed_document(db, DOCUMENT_ID, section_ids=(SECTION_ID,))
    await db.execute(
        "UPDATE sections SET source_key = ? WHERE id = ?",
        (SOURCE_KEY, SECTION_ID),
    )
    await db.commit()

    listed = await client.get(f"/api/documents/{DOCUMENT_ID}/sections")
    assert listed.status_code == 200, listed.text
    items = listed.json()
    assert len(items) == 1
    assert items[0]["id"] == SECTION_ID
    assert items[0]["source_key"] == SOURCE_KEY

    detail = await client.get(f"/api/documents/{DOCUMENT_ID}/sections/{SECTION_ID}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["source_key"] == SOURCE_KEY
    assert body["id"] == SECTION_ID
