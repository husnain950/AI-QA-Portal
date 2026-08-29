"""Cursor pagination for the library, section list, findings queue, and search.

The audit found 1,591 open findings behind an implicit 500-row cap, with the UI showing
no sign that a thousand were missing. These endpoints exist so a page can say
"showing 1-200 of 1,591" truthfully, and so a cursor cannot be replayed against a
different filter and quietly return the wrong slice.
"""

import json

from backend.database import database_connection
from backend.routes.v2.pagination import encode_cursor
from backend.tests.conftest import add_annotation, add_finding, seed_document


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


async def _lane_mix(db):
    """Three documents spanning stored-lane, heuristic-lane, and manual lanes."""
    await seed_document(db, "doc-0", name="Customs Act, 1969", section_ids=("s0",), with_active_version=True)
    await seed_document(db, "doc-1", name="Income Tax Rules 2002", section_ids=("s1",), with_active_version=True)
    await seed_document(db, "doc-2", name="My Upload", section_ids=("s2",), with_active_version=True)
    await db.execute(
        "UPDATE documents SET corpus_lane = 'customs', source_type = 'acts_corpus', "
        "provenance = ? WHERE id = 'doc-0'",
        (json.dumps({"source_kind": "native-digital", "tags": ["native-digital"]}),),
    )
    await db.execute(
        "UPDATE documents SET source_type = 'acts_corpus' WHERE id = 'doc-1'"
    )
    await db.execute(
        "UPDATE documents SET provenance = ? WHERE id = 'doc-2'",
        (json.dumps({"source_kind": "scanned-ocr", "tags": ["scanned-ocr", "ocr-needs-review"]}),),
    )
    await db.commit()


async def test_documents_page_filters_by_lane_including_heuristic_and_manual(runtime_sandbox, client):
    async with database_connection() as db:
        await _lane_mix(db)

        stored = await get(client, "/documents", lane="customs")
        assert [item["id"] for item in stored["items"]] == ["doc-0"]

        heuristic = await get(client, "/documents", lane="income_tax_rules")
        assert [item["id"] for item in heuristic["items"]] == ["doc-1"], \
            "acts_corpus rows without a stored lane fall back to the title heuristic"

        manual = await get(client, "/documents", lane="manual")
        assert [item["id"] for item in manual["items"]] == ["doc-2"], \
            "uploads browse under the manual lane"

        multi = await get(client, "/documents", lane="customs,manual")
        assert {item["id"] for item in multi["items"]} == {"doc-0", "doc-2"}
        assert multi["total"] == 2


async def test_documents_page_filters_by_source_kind_with_unknown_bucket(runtime_sandbox, client):
    async with database_connection() as db:
        await _lane_mix(db)

        scanned = await get(client, "/documents", kind="scanned-ocr")
        assert [item["id"] for item in scanned["items"]] == ["doc-2"]

        unknown = await get(client, "/documents", kind="unknown")
        assert [item["id"] for item in unknown["items"]] == ["doc-1"], \
            "doc-1 carries no provenance blob at all"

        multi = await get(client, "/documents", kind="native-digital,unknown")
        assert {item["id"] for item in multi["items"]} == {"doc-0", "doc-1"}


async def test_documents_page_filters_by_flags(runtime_sandbox, client):
    async with database_connection() as db:
        await _lane_mix(db)
        await db.execute("UPDATE sections SET review_status = 'has_issues' WHERE id = 's2'")
        await add_annotation(db, "s2")
        await db.commit()

        flagged = await get(client, "/documents", flagged="1")
        assert [item["id"] for item in flagged["items"]] == ["doc-2"]

        annotated = await get(client, "/documents", annotations="1")
        assert [item["id"] for item in annotated["items"]] == ["doc-2"]

        resolved = await get(client, "/documents", annotations="1", q="Customs")
        assert resolved["total"] == 0


async def test_documents_page_filters_by_provenance_tags(runtime_sandbox, client):
    async with database_connection() as db:
        await _lane_mix(db)

        needs_review = await get(client, "/documents", tag="ocr-needs-review")
        assert [item["id"] for item in needs_review["items"]] == ["doc-2"]

        either = await get(client, "/documents", tag="ocr-needs-review,native-digital")
        assert {item["id"] for item in either["items"]} == {"doc-0", "doc-2"}

        response = await client.get("/api/v2/documents", params={"tag": "Not A Slug"})
        assert response.status_code == 422


async def test_documents_page_filters_by_health_and_review(runtime_sandbox, client):
    async with database_connection() as db:
        await _lane_mix(db)
        await db.execute(
            "INSERT INTO version_metrics (version_id, gate_ok, measured_at) "
            "VALUES ('ver-doc-0', TRUE, '2026-01-02')"
        )
        await db.execute(
            "INSERT INTO version_metrics (version_id, gate_ok, measured_at) "
            "VALUES ('ver-doc-1', FALSE, '2026-01-02')"
        )
        await db.execute("UPDATE sections SET review_status = 'approved' WHERE id = 's0'")
        await db.commit()
        # doc-0: within gate + complete; doc-1: outside gate + untouched; doc-2: unmeasured.

        within = await get(client, "/documents", health="within_gate")
        assert [item["id"] for item in within["items"]] == ["doc-0"]

        outside_or_unmeasured = await get(client, "/documents", health="outside_gate,unmeasured")
        assert {item["id"] for item in outside_or_unmeasured["items"]} == {"doc-1", "doc-2"}

        complete = await get(client, "/documents", review="complete")
        assert [item["id"] for item in complete["items"]] == ["doc-0"]

        untouched = await get(client, "/documents", review="untouched")
        assert {item["id"] for item in untouched["items"]} == {"doc-1", "doc-2"}


async def test_documents_page_filters_by_year_added_pages_and_ids(runtime_sandbox, client):
    async with database_connection() as db:
        await _lane_mix(db)
        await db.execute(
            "UPDATE documents SET edition_date = '1969', total_pages = 5, "
            "uploaded_at = '2026-06-15T10:00:00Z' WHERE id = 'doc-0'"
        )
        await db.execute("UPDATE documents SET total_pages = 500 WHERE id = 'doc-2'")
        await db.commit()
        # doc-1 keeps uploaded_at 2026-01-01, total_pages 1, year from name (2002).

        by_year = await get(client, "/documents", year=1969)
        assert [item["id"] for item in by_year["items"]] == ["doc-0"]

        multi_year = await get(client, "/documents", year="1969,2002")
        assert {item["id"] for item in multi_year["items"]} == {"doc-0", "doc-1"}

        year_range = await get(client, "/documents", year_from=2000, year_to=2010)
        assert [item["id"] for item in year_range["items"]] == ["doc-1"], \
            "the name-derived year is the fallback when edition_date is missing"

        added = await get(client, "/documents", added_after="2026-06-01")
        assert [item["id"] for item in added["items"]] == ["doc-0"]

        before = await get(client, "/documents", added_before="2026-01-01")
        assert {item["id"] for item in before["items"]} == {"doc-1", "doc-2"}

        pages = await get(client, "/documents", pages_min=10)
        assert [item["id"] for item in pages["items"]] == ["doc-2"]

        by_ids = await get(client, "/documents", ids="doc-2,doc-0", sort="name")
        assert [item["id"] for item in by_ids["items"]] == ["doc-0", "doc-2"]


async def test_documents_page_sorts_by_size_year_update_and_completion(runtime_sandbox, client):
    async with database_connection() as db:
        await _lane_mix(db)
        await db.execute("UPDATE documents SET total_pages = 500 WHERE id = 'doc-2'")
        await db.execute(
            "UPDATE document_versions SET created_at = '2026-05-01' WHERE document_id = 'doc-1'"
        )
        await db.execute("UPDATE sections SET review_status = 'approved' WHERE id = 's1'")
        await db.commit()
        # years: doc-0 1969 (edition_date), doc-1 2002 (name), doc-2 none.

        by_pages = await get(client, "/documents", sort="pages")
        assert [item["id"] for item in by_pages["items"]] == ["doc-2", "doc-0", "doc-1"]

        by_year = await get(client, "/documents", sort="year")
        assert [item["id"] for item in by_year["items"]][:2] == ["doc-1", "doc-0"]
        assert by_year["items"][-1]["id"] == "doc-2", "unknown years sort last"

        by_updated = await get(client, "/documents", sort="updated")
        assert by_updated["items"][0]["id"] == "doc-1"
        assert by_updated["items"][0]["last_version_at"] == "2026-05-01"

        by_completion = await get(client, "/documents", sort="completion")
        assert by_completion["items"][0]["id"] == "doc-1", "the one reviewed document leads"

        z_to_a = await get(client, "/documents", sort="name_desc")
        assert z_to_a["items"][0]["id"] == "doc-2", "My Upload sorts after the statutes"


async def test_documents_page_relevance_prefers_prefix_then_position(runtime_sandbox, client):
    async with database_connection() as db:
        await seed_document(db, "doc-a", name="Sales Tax Act, 1990", section_ids=("sa",), with_active_version=True)
        await seed_document(db, "doc-b", name="The Sales Tax (Appeals) Rules", section_ids=("sb",), with_active_version=True)
        await seed_document(db, "doc-c", name="Unrelated Act", section_ids=("sc",), with_active_version=True)
        await db.commit()

        ranked = await get(client, "/documents", q="sales", sort="relevance")
        assert [item["id"] for item in ranked["items"]] == ["doc-a", "doc-b"], \
            "prefix match first, then earliest position; non-matches excluded by the filter"


async def test_documents_facets_respect_other_filters_but_not_their_own(runtime_sandbox, client):
    async with database_connection() as db:
        await _lane_mix(db)
        await db.execute(
            "INSERT INTO version_metrics (version_id, gate_ok, measured_at) "
            "VALUES ('ver-doc-0', TRUE, '2026-01-02')"
        )
        await db.commit()

        facets = await get(client, "/documents/facets", lane="customs")
        assert facets["lanes"] == {"customs": 1, "income_tax_rules": 1, "manual": 1}, \
            "lane counts ignore the lane filter itself, so multi-select stays useful"
        assert facets["kinds"] == {"native-digital": 1}, \
            "kind counts do respect the active lane filter"
        assert facets["totals"]["documents"] == 1
        assert facets["library_total"] == 3
        assert facets["health"] == {"within_gate": 1}
        assert facets["years"] == [{"year": 1969, "count": 1}]

        everything = await get(client, "/documents/facets")
        assert everything["totals"] == {"documents": 3, "flagged": 0, "annotated": 0, "complete": 0}
        assert everything["library"] == {"documents": 3, "flagged": 0, "complete": 0}
        tag_counts = {row["tag"]: row["count"] for row in everything["tags"]}
        assert tag_counts["ocr-needs-review"] == 1


async def test_documents_page_rejects_unknown_facet_values(runtime_sandbox, client):
    async with database_connection() as db:
        await _lane_mix(db)

        for bad in (
            {"lane": "bogus"},
            {"kind": "pdf"},
            {"health": "sick"},
            {"review": "done"},
            {"sort": "bogus"},
            {"added_after": "last-week"},
        ):
            response = await client.get("/api/v2/documents", params=bad)
            assert response.status_code == 422, bad


async def test_new_filters_invalidate_a_cursor(runtime_sandbox, client):
    async with database_connection() as db:
        await _corpus(db, documents=4, sections_each=1)
        page = await get(client, "/documents", limit=2, lane="manual")

        response = await client.get(
            "/api/v2/documents",
            params={"cursor": page["next_cursor"], "limit": 2, "lane": "other_acts"},
        )
        assert response.status_code == 400, "a cursor is bound to the full filter set"


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


async def test_sections_page_can_narrow_to_a_pdf_page(runtime_sandbox, client):
    async with database_connection() as db:
        await _corpus(db, documents=1, sections_each=3)
        await db.execute("UPDATE sections SET end_page = start_page")
        await db.commit()

        page_two = await get(client, "/documents/doc-0/sections", page=2)
        assert [item["section_code"] for item in page_two["items"]] == ["2"]


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


async def test_count_from_skips_section_scans_until_a_stat_filter_needs_them(runtime_sandbox):
    """Unfiltered Library COUNT used to LATERAL-scan every section of every
    document just to return a number, which is what timed the page out."""
    from backend.services import library_query as lq

    light = lq.count_from(lq.LibraryFilters())
    assert "LATERAL" not in light
    assert "LATERAL" not in lq.count_from(lq.LibraryFilters(q="customs"))
    assert "LATERAL" not in lq.count_from(lq.LibraryFilters(lanes=("customs",)))
    assert "LATERAL" in lq.count_from(lq.LibraryFilters(flagged=True))
    assert "LATERAL" in lq.count_from(lq.LibraryFilters(review=("complete",)))
    assert "LATERAL" in lq.count_from(lq.LibraryFilters(health=("within_gate",)))
    assert "LATERAL" not in lq.count_from(lq.LibraryFilters(flagged=True), exclude="flags")
