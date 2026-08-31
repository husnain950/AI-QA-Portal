"""The server sends the values it derives, instead of leaving the client to guess.

`LANE_SQL`, `YEAR_SQL` and the statute family were all computed for the WHERE and
ORDER BY clauses and then withheld from the payload, so the client re-derived them
from copies that had drifted:

* filtering by Source = Customs returned a card badged "Other Acts", because
  `PAGE_SELECT` sent the raw NULL `corpus_lane` while `LANE_SQL` classified by title;
* "Edition - newest" produced an order contradicting the year on every card;
* the client's family key split 5 of 29 families on the real corpus, the 21-edition
  Income Tax Ordinance among them.
"""

from backend.tests.conftest import seed_document

DOCUMENT_ID = "derived-doc"
NAME = "Customs Act, 1969 as amended up to 30.06.2025"


async def _as_corpus(db, name=NAME):
    await db.execute(
        "UPDATE documents SET name = ?, source_type = 'acts_corpus', "
        "corpus_lane = NULL WHERE id = ?",
        (name, DOCUMENT_ID),
    )
    await db.commit()


async def test_the_lane_the_filter_uses_is_the_lane_the_payload_carries(db, client):
    await seed_document(db, DOCUMENT_ID, section_ids=("s-1",))
    await _as_corpus(db)

    async with db.execute(
        "SELECT corpus_lane FROM documents WHERE id = ?", (DOCUMENT_ID,)
    ) as cursor:
        assert (await cursor.fetchone())["corpus_lane"] is None, "stored column unset"

    body = (await client.get(f"/api/documents/{DOCUMENT_ID}")).json()
    assert body["lane"] == "customs", "the resolved lane is what the client needs"
    # ...and the field the client used to read agrees with it rather than
    # contradicting it, which is what the four parallel implementations allowed.
    assert body["corpus_lane"] == "customs"


async def test_the_year_the_sort_uses_is_the_year_the_payload_carries(db, client):
    await seed_document(db, DOCUMENT_ID, section_ids=("s-1",))
    await _as_corpus(db)

    body = (await client.get(f"/api/documents/{DOCUMENT_ID}")).json()
    # YEAR_SQL takes the FIRST 19xx/20xx in the name. Reading the name the client's
    # own way yields 2025, which is how the order and the labels came apart.
    assert body["edition_year"] == 1969


async def test_the_statute_family_is_named_on_the_document(db, client):
    await seed_document(db, DOCUMENT_ID, section_ids=("s-1",))
    await _as_corpus(db)
    from backend.services.identity import persist_inferred_identity

    await persist_inferred_identity(db, DOCUMENT_ID, NAME)
    await db.commit()

    body = (await client.get(f"/api/documents/{DOCUMENT_ID}")).json()
    assert body["family_key"] == "customs act, 1969"
    assert body["family_title"]


async def test_the_list_endpoint_carries_them_too(db, client):
    """The Library reads the list, not the detail -- a field on one and not the
    other is the same divergence in a smaller place."""
    await seed_document(db, DOCUMENT_ID, section_ids=("s-1",))
    await _as_corpus(db)

    listed = (await client.get("/api/documents")).json()
    row = next(d for d in listed if d["id"] == DOCUMENT_ID)
    assert row["lane"] == "customs"
    assert row["edition_year"] == 1969


async def test_a_manual_upload_resolves_to_the_manual_lane(db, client):
    await seed_document(db, DOCUMENT_ID, section_ids=("s-1",))
    body = (await client.get(f"/api/documents/{DOCUMENT_ID}")).json()
    assert body["lane"] == "manual"
