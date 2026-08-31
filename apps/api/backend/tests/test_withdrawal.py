"""A document that leaves `output/` leaves the portal -- without losing its evidence.

Nothing used to remove a `documents` row when its JSON stopped being produced. Phase 2
moved two acts editions to `output/_refused/` and holds nine in `_provisional/`; every
one of them kept its rows, its stale parse and its "approved" badges, and a reviewer
had no way to tell a current document from an abandoned one.

Withdrawal is a timestamp, never a delete: the annotations and exported evidence
pointing at the document are the audit trail for a legally binding corpus.
"""

import json

import pytest

from backend.services.corpus_sync import reconcile_corpus
from backend.services.library_query import LibraryFilters, build_where
from backend.tests.conftest import seed_document


async def _origin(db, document_id, origin, source_key):
    await db.execute(
        "UPDATE documents SET corpus_origin = ?, source_key = ?, source_type = ? "
        "WHERE id = ?",
        (origin, source_key, "acts_corpus", document_id),
    )
    await db.commit()


async def _withdrawn(db):
    async with db.execute(
        "SELECT source_key, withdrawn_at FROM documents ORDER BY source_key"
    ) as cursor:
        return {r["source_key"]: r["withdrawn_at"] for r in await cursor.fetchall()}


async def test_a_document_the_corpus_no_longer_holds_is_withdrawn(db, runtime_sandbox):
    await seed_document(db, "doc-kept", section_ids=("s-kept",))
    await seed_document(db, "doc-gone", section_ids=("s-gone",))
    await _origin(db, "doc-kept", "acts", "Kept Act")
    await _origin(db, "doc-gone", "acts", "Gone Act")

    result = await reconcile_corpus("acts", ["Kept Act"])
    assert result == {"withdrawn": ["Gone Act"], "restored": []}

    state = await _withdrawn(db)
    assert state["Kept Act"] is None
    assert state["Gone Act"] is not None

    # The rows are still there. Withdrawal is not a delete.
    async with db.execute("SELECT COUNT(*) AS n FROM sections") as cursor:
        assert (await cursor.fetchone())["n"] == 2


async def test_a_document_that_comes_back_is_restored(db, runtime_sandbox):
    await seed_document(db, "doc-flap", section_ids=("s-flap",))
    await _origin(db, "doc-flap", "acts", "Flapping Act")

    await reconcile_corpus("acts", [])
    assert (await _withdrawn(db))["Flapping Act"] is not None

    result = await reconcile_corpus("acts", ["Flapping Act"])
    assert result == {"withdrawn": [], "restored": ["Flapping Act"]}
    assert (await _withdrawn(db))["Flapping Act"] is None


async def test_reconciliation_is_idempotent(db, runtime_sandbox):
    await seed_document(db, "doc-gone", section_ids=("s-gone",))
    await _origin(db, "doc-gone", "acts", "Gone Act")

    first = await reconcile_corpus("acts", [])
    stamp = (await _withdrawn(db))["Gone Act"]
    second = await reconcile_corpus("acts", [])

    assert first["withdrawn"] == ["Gone Act"]
    assert second == {"withdrawn": [], "restored": []}
    # ...and the original timestamp is not overwritten, so "withdrawn since" is real.
    assert (await _withdrawn(db))["Gone Act"] == stamp


async def test_syncing_one_corpus_never_withdraws_another(db, runtime_sandbox):
    """The reason `corpus_origin` exists rather than reusing `corpus_lane`.

    `corpus_lane` is the Library's browse facet and says nothing about which corpus
    root a file came from. Without the origin, `--only rules` would compute
    "everything not in the rules corpus" and withdraw all 80 acts documents.
    """
    await seed_document(db, "doc-acts", section_ids=("s-acts",))
    await seed_document(db, "doc-rules", section_ids=("s-rules",))
    await _origin(db, "doc-acts", "acts", "An Act")
    await _origin(db, "doc-rules", "rules", "Some Rules")

    result = await reconcile_corpus("rules", ["Some Rules"])

    assert result == {"withdrawn": [], "restored": []}
    state = await _withdrawn(db)
    assert state["An Act"] is None, "an acts document was withdrawn by a rules sync"
    assert state["Some Rules"] is None


async def test_a_row_with_no_origin_is_never_a_candidate(db, runtime_sandbox):
    """Rows that predate the column. The next sync gives them one; until then the
    safe direction is to leave them alone."""
    await seed_document(db, "doc-legacy", section_ids=("s-legacy",))
    await db.execute(
        "UPDATE documents SET corpus_origin = NULL, source_key = ?, source_type = ? "
        "WHERE id = ?",
        ("Legacy Act", "acts_corpus", "doc-legacy"),
    )
    await db.commit()

    assert await reconcile_corpus("acts", []) == {"withdrawn": [], "restored": []}
    assert (await _withdrawn(db))["Legacy Act"] is None


@pytest.mark.parametrize(
    "include_withdrawn, expects_clause",
    [(False, True), (True, False)],
)
def test_the_library_hides_withdrawn_documents_by_default(
    include_withdrawn, expects_clause
):
    where, _ = build_where(LibraryFilters(include_withdrawn=include_withdrawn))
    assert ("d.withdrawn_at IS NULL" in where) is expects_clause


def test_the_withdrawn_filter_survives_facet_exclusion():
    """Facet counts drop one dimension at a time to stay consistent with the page.

    The withdrawn filter must not be one of them, or a facet would count documents
    the page it labels cannot show.
    """
    for dimension in ("lane", "kind", "health", "review", "year", "tags", "ids"):
        where, _ = build_where(LibraryFilters(), exclude=dimension)
        assert "d.withdrawn_at IS NULL" in where, dimension


async def test_the_api_reports_withdrawal(db, client, runtime_sandbox):
    await seed_document(db, "doc-gone", section_ids=("s-gone",))
    await _origin(db, "doc-gone", "acts", "Gone Act")
    await reconcile_corpus("acts", [])

    response = await client.get("/api/documents/doc-gone")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["withdrawn_at"], "the reviewer is never told the parse was retired"
    assert json.loads(response.text)["id"] == "doc-gone"
