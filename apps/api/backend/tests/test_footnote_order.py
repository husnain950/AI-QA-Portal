"""Footnotes come back in the order the document prints them, not row order.

The query that reads them carried no ORDER BY, so Postgres returned physical row
order.  On the 30.06.2025 Customs Act that served s.2's fifty notes ending
45, 49, 50, 46, 47, 48 while the pipeline JSON had them in order, and QA logged
it against the parser.  The rows below are inserted deliberately shuffled: the
test fails without the sort and cannot pass by accident of insertion order.
"""

from backend.tests.conftest import seed_document

DOCUMENT_ID = "doc-footnote-order"
SECTION_ID = "sec-footnote-order"

# printed order last, insertion order first -- "7.10" before "7.2" is what a
# plain string ORDER BY would also get wrong, so it is in here on purpose
SHUFFLED = ("9.49", "7.10", "9.46", "7.1a", "9.50", "7.2", "9.45", "7.1", "9.48", "9.47")
PRINTED = ("7.1", "7.1a", "7.2", "7.10", "9.45", "9.46", "9.47", "9.48", "9.49", "9.50")


def _page_of(marker: str) -> int:
    head = marker.split(".")[0]
    return int(head) if head.isdigit() else 1


async def _seed_footnotes(db, markers=SHUFFLED):
    await seed_document(db, DOCUMENT_ID, section_ids=(SECTION_ID,))
    # by-page matches on a start..end range; the seed helper sets only start_page
    await db.execute("UPDATE sections SET start_page = 1, end_page = 9 WHERE id = ?",
                     (SECTION_ID,))
    for i, marker in enumerate(markers):
        await db.execute(
            """
            INSERT INTO footnotes (id, section_id, marker, page, text, html_content,
                                   review_status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """,
            (f"fn-{i}", SECTION_ID, marker, _page_of(marker),
             f"note {marker}", f"<p>note {marker}</p>"),
        )
    await db.commit()


async def test_section_detail_returns_footnotes_in_printed_order(db, client):
    await _seed_footnotes(db)

    r = await client.get(f"/api/documents/{DOCUMENT_ID}/sections/{SECTION_ID}")
    assert r.status_code == 200, r.text
    assert tuple(fn["marker"] for fn in r.json()["footnotes"]) == PRINTED


async def test_by_page_returns_footnotes_in_printed_order(db, client):
    await _seed_footnotes(db)

    r = await client.get(f"/api/documents/{DOCUMENT_ID}/sections/by-page/1")
    assert r.status_code == 200, r.text
    sections = [s for s in r.json() if s["id"] == SECTION_ID]
    assert sections, r.text
    assert tuple(fn["marker"] for fn in sections[0]["footnotes"]) == PRINTED


async def test_an_unparseable_marker_sorts_last_and_is_never_dropped(db, client):
    """A marker shape nobody anticipated must still come back."""
    await _seed_footnotes(db, markers=("9.2", "odd-one", "9.1"))

    r = await client.get(f"/api/documents/{DOCUMENT_ID}/sections/{SECTION_ID}")
    assert r.status_code == 200, r.text
    assert tuple(fn["marker"] for fn in r.json()["footnotes"]) == ("9.1", "9.2", "odd-one")
