"""Cursor pagination for the library, section list, findings queue, and search.

The audit found 1,591 open findings behind an implicit 500-row cap, with the UI showing
no sign that a thousand were missing. These endpoints exist so a page can say
"showing 1-200 of 1,591" truthfully, and so a cursor cannot be replayed against a
different filter and quietly return the wrong slice.
"""

import pytest

from backend.database import database_connection
from backend.routes.v2.pagination import encode_cursor
from backend.tests.conftest import add_finding, seed_document


async def get(client, path, **params):
    """A v2 GET that must succeed, returning the decoded page."""
    response = await client.get(f"/api/v2{path}", params={
        key: value for key, value in params.items() if value is not None
    })
    assert response.status_code == 200, response.text
    return response.json()


async def _corpus(db, documents=3, sections_each=2):
    ids = []
    for index in range(documents):
        document_id = f"doc-{index}"
        section_ids = tuple(f"sec-{index}-{n}" for n in range(sections_each))
        await seed_document(
            db,
            document_id,
            name=f"Paginated Act, {2001 + index}",
            section_ids=section_ids,
            with_active_version=True,
        )
        ids.append((document_id, section_ids))
    return ids


@pytest.mark.asyncio
async def test_documents_page_reports_the_true_total_behind_a_small_page(runtime_sandbox, client):
    async with database_connection() as db:
        await _corpus(db, documents=5, sections_each=1)

        first = await get(client, "/documents", limit=2)
        assert len(first["items"]) == 2
        assert first["total"] == 5, "the count is of the filter, not of the page"
        assert first["next_cursor"]
        assert first["refreshed_at"]

        second = await get(client, "/documents", cursor=first["next_cursor"], limit=2)
        third = await get(client, "/documents", cursor=second["next_cursor"], limit=2)
        assert third["next_cursor"] is None, "the last page closes the cursor"

        seen = [item["id"] for page in (first, second, third) for item in page["items"]]
        assert len(seen) == len(set(seen)) == 5, "every document appears exactly once"


@pytest.mark.asyncio
async def test_a_cursor_minted_under_another_filter_is_rejected(runtime_sandbox, client):
    """Otherwise page 2 of one search silently returns rows from a different one."""
    async with database_connection() as db:
        await _corpus(db, documents=4, sections_each=1)
        page = await get(client, "/documents", limit=2)

        for bad in (
            {"cursor": page["next_cursor"], "limit": 2, "q": "Paginated"},
            {"cursor": "not-base64-at-all"},
            {"cursor": encode_cursor(-1, "whatever")},
        ):
            response = await client.get("/api/v2/documents", params=bad)
            assert response.status_code == 400, bad


@pytest.mark.asyncio
async def test_documents_page_filters_and_sorts(runtime_sandbox, client):
    async with database_connection() as db:
        await _corpus(db, documents=3, sections_each=1)
        await db.execute("UPDATE documents SET status = 'blocked' WHERE id = 'doc-2'")
        await db.commit()

        filtered = await get(client, "/documents", status="blocked")
        assert [item["id"] for item in filtered["items"]] == ["doc-2"]
        assert filtered["total"] == 1

        by_risk = await get(client, "/documents", sort="risk")
        assert by_risk["items"][0]["id"] == "doc-2", "blocked documents come first"

        searched = await get(client, "/documents", q="2003")
        assert [item["id"] for item in searched["items"]] == ["doc-2"]


@pytest.mark.asyncio
async def test_sections_page_paginates_within_one_document(runtime_sandbox, client):
    async with database_connection() as db:
        await _corpus(db, documents=2, sections_each=4)

        first = await get(client, "/documents/doc-0/sections", limit=3)
        assert first["total"] == 4, "only this document's sections are counted"
        assert len(first["items"]) == 3
        rest = await get(client, "/documents/doc-0/sections", cursor=first["next_cursor"], limit=3)
        assert len(rest["items"]) == 1
        assert rest["next_cursor"] is None
        assert all(item["document_id"] == "doc-0" for item in first["items"] + rest["items"])
        assert [item["sort_order"] for item in first["items"]] == [1, 2, 3], "stable order"


@pytest.mark.asyncio
async def test_sections_page_can_narrow_to_a_pdf_page(runtime_sandbox, client):
    async with database_connection() as db:
        await _corpus(db, documents=1, sections_each=3)
        await db.execute("UPDATE sections SET end_page = start_page")
        await db.commit()

        page_two = await get(client, "/documents/doc-0/sections", page=2)
        assert [item["section_code"] for item in page_two["items"]] == ["2"]


@pytest.mark.asyncio
async def test_findings_page_carries_queue_stats_and_a_stable_slice(runtime_sandbox, client):
    async with database_connection() as db:
        documents = await _corpus(db, documents=2, sections_each=2)
        for document_id, section_ids in documents:
            for section_id in section_ids:
                await add_finding(db, section_id, document_id, score=float(len(section_id)))
        await db.commit()

        first = await get(client, "/findings", limit=3)
        assert first["total"] == 4
        assert len(first["items"]) == 3
        assert first["stats"] == {
            "total": 4,
            "done": 0,
            "left": 4,
            "by_triage": {"new": 4},
        }
        assert first["items"][0]["summary"], "detail_json is unpacked for the UI"
        assert first["items"][0]["blast_radius"] >= 1

        second = await get(client, "/findings", cursor=first["next_cursor"], limit=3)
        assert len(second["items"]) == 1
        assert second["next_cursor"] is None
        ids = [item["id"] for page in (first, second) for item in page["items"]]
        assert len(set(ids)) == 4


@pytest.mark.asyncio
async def test_findings_page_filters_by_triage_detector_and_text(runtime_sandbox, client):
    async with database_connection() as db:
        (document_id, section_ids), *_ = await _corpus(db, documents=1, sections_each=2)
        await add_finding(db, section_ids[0], document_id, detector="glyph_split")
        await add_finding(db, section_ids[1], document_id, detector="missing_table")
        await db.execute("UPDATE findings SET triage = 'parse_bug' WHERE detector = 'missing_table'")
        await db.commit()

        new_only = await get(client, "/findings")
        assert [item["detector"] for item in new_only["items"]] == ["glyph_split"]
        assert new_only["stats"]["left"] == 1
        assert new_only["stats"]["done"] == 1, "triaged findings count as done"

        by_detector = await get(client, "/findings", triage="", detector="missing_table")
        assert by_detector["total"] == 1

        by_text = await get(client, "/findings", triage="", q="glyph")
        assert [item["detector"] for item in by_text["items"]] == ["glyph_split"]

        nothing = await get(client, "/findings", triage="", q="does-not-occur")
        assert nothing["items"] == [] and nothing["total"] == 0


@pytest.mark.asyncio
async def test_findings_page_orders_errors_before_warnings(runtime_sandbox, client):
    async with database_connection() as db:
        (document_id, section_ids), *_ = await _corpus(db, documents=1, sections_each=2)
        await add_finding(db, section_ids[0], document_id, detector="low", severity="warning", score=99)
        await add_finding(db, section_ids[1], document_id, detector="high", severity="error", score=1)
        await db.commit()

        by_risk = await get(client, "/findings", sort="risk")
        assert [item["detector"] for item in by_risk["items"]] == ["high", "low"]

        by_score = await get(client, "/findings", sort="score")
        assert [item["detector"] for item in by_score["items"]] == ["low", "high"]
