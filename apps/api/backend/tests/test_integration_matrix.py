"""The pipeline -> portal seam, driven end to end, against every state QA can reach.

This is the harness the project did not have. `data/corpora/` is gitignored, so all
three lane suites SKIP on CI and `convert_all` / `sync_corpus` appear in zero workflow
files -- everything between "a parser fix merged" and "a reviewer sees it" was
enforced by prose. On the day this work started that gap was not theoretical: the
corpus on disk was four parser rounds ahead of `main` and no automated check could
have noticed.

`tools/fixture_corpus.build()` generates a real corpus -- real PDFs with a real text
layer, contract-stamped JSON -- into a temp directory, so these run anywhere the API
tests run, CI included, with no private data.

Every case is a state a reviewer or an operator can actually produce. Where a case is
already covered at unit level (leaf identity in `test_node_key_identity`, withdrawal
in `test_withdrawal`), this drives it through `run_sync` instead, because the unit
tests can only prove the pieces agree with themselves.
"""

import asyncio
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
import fixture_corpus  # noqa: E402
from backend.database import database_connection  # noqa: E402
from backend.services import versions  # noqa: E402
from backend.services.corpus_sync import reconcile_corpus  # noqa: E402
from backend.sync_acts import run_sync  # noqa: E402

FIRST = "Fixture Finance Act 2024"


@pytest.fixture
def corpus(tmp_path):
    """A freshly generated corpus root, one per test."""
    dest = tmp_path / "acts"
    fixture_corpus.build(dest)
    return dest


async def _sync(corpus, **kwargs):
    return await run_sync(
        corpus, acts_repo=True, pdf_dir=corpus / "Acts", corpus_origin="acts", **kwargs
    )


def _json_path(corpus, name=FIRST):
    return corpus / "output" / f"{name}.json"


def _load(corpus, name=FIRST):
    return json.loads(_json_path(corpus, name).read_text(encoding="utf-8"))


def _save(corpus, doc, name=FIRST):
    from legal_contract import stamp_document

    stamp_document(doc)
    _json_path(corpus, name).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


async def _counts(db):
    async with db.execute(
        "SELECT (SELECT COUNT(*) FROM documents) AS documents,"
        " (SELECT COUNT(*) FROM sections) AS sections,"
        " (SELECT COUNT(*) FROM document_versions) AS versions,"
        " (SELECT COUNT(*) FROM sections WHERE review_status = 'approved') AS approved"
    ) as cursor:
        return dict(await cursor.fetchone())


# --- the ordinary path --------------------------------------------------------


async def test_first_ingest(corpus, runtime_sandbox):
    summary = await _sync(corpus)
    assert summary["added"] == 3
    assert summary["failed"] == 0
    assert summary["unmatched"] == 0
    async with database_connection() as db:
        counts = await _counts(db)
    assert counts["documents"] == 3
    assert counts["sections"] > 0
    assert counts["versions"] == 3


async def test_identical_reprocessing_writes_nothing(corpus, runtime_sandbox):
    await _sync(corpus)
    async with database_connection() as db:
        before = await _counts(db)
        async with db.execute("SELECT id, row_revision FROM documents ORDER BY id") as c:
            revisions = {r["id"]: r["row_revision"] for r in await c.fetchall()}

    summary = await _sync(corpus)
    assert summary["skipped"] == 3
    assert summary["added"] == 0 and summary["updated"] == 0

    async with database_connection() as db:
        assert await _counts(db) == before, "a no-op sync changed rows"
        async with db.execute("SELECT id, row_revision FROM documents ORDER BY id") as c:
            assert {r["id"]: r["row_revision"] for r in await c.fetchall()} == revisions


async def test_a_leaf_edit_resets_only_that_leaf(corpus, runtime_sandbox):
    await _sync(corpus)
    async with database_connection() as db:
        await db.execute("UPDATE sections SET review_status = 'approved'")
        await db.commit()

    doc = _load(corpus)
    doc["chapters"][0]["sections"][0]["plain_text"] += " As corrected."
    doc["chapters"][0]["sections"][0]["html"] += "<p>As corrected.</p>"
    _save(corpus, doc)
    await _sync(corpus)

    async with database_connection() as db:
        async with db.execute(
            "SELECT s.section_code, s.review_status FROM sections s "
            "JOIN documents d ON d.id = s.document_id WHERE d.name = ? "
            "ORDER BY s.sort_order",
            (FIRST,),
        ) as cursor:
            rows = [dict(r) for r in await cursor.fetchall()]
    assert rows[0]["review_status"] == "pending", rows
    assert all(r["review_status"] == "approved" for r in rows[1:]), rows


@pytest.mark.parametrize("position", [0, 1, "end"])
async def test_inserting_a_leaf_keeps_every_other_approval(position, corpus, runtime_sandbox):
    await _sync(corpus)
    async with database_connection() as db:
        await db.execute("UPDATE sections SET review_status = 'approved'")
        await db.commit()
        before = await _counts(db)

    doc = _load(corpus)
    sections = doc["chapters"][0]["sections"]
    new = {
        "code": "0A", "heading": "Recovered", "start_page": 1, "end_page": 1,
        "html": "<p>recovered</p>", "plain_text": "recovered", "footnotes": [],
    }
    sections.insert(len(sections) if position == "end" else position, new)
    doc["metadata"]["sections_count"] += 1
    _save(corpus, doc)
    await _sync(corpus)

    async with database_connection() as db:
        after = await _counts(db)
    assert after["sections"] == before["sections"] + 1
    assert after["approved"] == before["approved"], (
        "an insertion reset an approval on a leaf that did not change"
    )


async def test_deleting_a_leaf_removes_exactly_it(corpus, runtime_sandbox):
    await _sync(corpus)
    async with database_connection() as db:
        await db.execute("UPDATE sections SET review_status = 'approved'")
        await db.commit()
        before = await _counts(db)

    doc = _load(corpus)
    doc["chapters"][0]["sections"].pop(0)
    doc["metadata"]["sections_count"] -= 1
    _save(corpus, doc)
    await _sync(corpus)

    async with database_connection() as db:
        after = await _counts(db)
    assert after["sections"] == before["sections"] - 1
    assert after["approved"] == before["approved"] - 1


async def test_a_chapter_rename_rekeys_only_its_own_leaves(corpus, runtime_sandbox):
    """`node_key` is the ancestor chain by code, so renaming a chapter is a real
    structural change for its children and for nothing else."""
    await _sync(corpus)
    async with database_connection() as db:
        async with db.execute(
            "SELECT node_key FROM sections WHERE node_key LIKE 'ch:ii/%'"
        ) as cursor:
            untouched = {r["node_key"] for r in await cursor.fetchall()}

    doc = _load(corpus)
    doc["chapters"][0]["code"] = "I-A"
    _save(corpus, doc)
    await _sync(corpus)

    async with database_connection() as db:
        async with db.execute("SELECT node_key FROM sections") as cursor:
            keys = {r["node_key"] for r in await cursor.fetchall()}
    assert any(k and k.startswith("ch:i-a/") for k in keys), keys
    assert untouched <= keys, "renaming one chapter re-keyed another's leaves"


# --- malformed and hostile input ----------------------------------------------


async def test_malformed_json_fails_that_document_alone(corpus, runtime_sandbox):
    _json_path(corpus).write_text("{not json at all", encoding="utf-8")
    summary = await _sync(corpus)
    assert summary["unmatched"] == 1, summary
    assert summary["added"] == 2, "one bad document held the others hostage"
    async with database_connection() as db:
        assert (await _counts(db))["documents"] == 2


async def test_a_truncated_json_is_a_failure_not_an_empty_document(corpus, runtime_sandbox):
    """The shape a killed converter used to leave behind, before the atomic write."""
    raw = _json_path(corpus).read_text(encoding="utf-8")
    _json_path(corpus).write_text(raw[: len(raw) // 2], encoding="utf-8")
    summary = await _sync(corpus)
    assert summary["unmatched"] == 1
    async with database_connection() as db:
        async with db.execute(
            "SELECT COUNT(*) AS n FROM documents WHERE name = ?", (FIRST,)
        ) as cursor:
            assert (await cursor.fetchone())["n"] == 0, "a half-file became a document"


async def test_a_document_with_no_leaves_is_refused(corpus, runtime_sandbox):
    doc = _load(corpus)
    doc["chapters"] = []
    doc["metadata"]["sections_count"] = 0
    _save(corpus, doc)
    summary = await _sync(corpus)
    assert summary["failed"] == 1, summary
    assert any("no reviewable sections" in p for p in summary["problems"]), summary["problems"]
    assert summary["added"] == 2


async def test_a_document_claiming_impossible_pages_is_flagged_not_dropped(
    corpus, runtime_sandbox
):
    doc = _load(corpus)
    doc["chapters"][0]["sections"][0]["end_page"] = 9999
    _save(corpus, doc)
    summary = await _sync(corpus)
    assert summary["flagged_pages"] >= 1, summary
    assert summary["added"] == 3, "a flagged page range must not lose the document"


async def test_a_large_document_ingests(corpus, runtime_sandbox):
    """Not a benchmark -- a check that nothing here is quadratic enough to hang, and
    that 2,000 leaves get 2,000 distinct keys."""
    doc = _load(corpus)
    template = doc["chapters"][0]["sections"][0]
    # One chapter, so the count is the count. The fixture ships two.
    doc["chapters"] = [{
        **doc["chapters"][0],
        "sections": [
            {**template, "code": str(index), "heading": f"Section {index}",
             "plain_text": f"body {index}", "html": f"<p>body {index}</p>"}
            for index in range(2000)
        ],
    }]
    doc["metadata"]["chapters_count"] = 1
    doc["metadata"]["sections_count"] = 2000
    _save(corpus, doc)
    await _sync(corpus)

    async with database_connection() as db:
        async with db.execute(
            "SELECT COUNT(*) AS n, COUNT(DISTINCT node_key) AS keys FROM sections s "
            "JOIN documents d ON d.id = s.document_id WHERE d.name = ?", (FIRST,)
        ) as cursor:
            row = dict(await cursor.fetchone())
    assert row["n"] == 2000
    assert row["keys"] == 2000, "2,000 leaves did not get 2,000 distinct keys"


# --- interruption, retry, concurrency -----------------------------------------


async def test_a_sync_interrupted_midway_resumes(corpus, runtime_sandbox):
    """The first run dies after one document; the second must finish the job and
    must not duplicate what the first wrote."""
    parked = corpus.parent / "parked"
    parked.mkdir()
    for name in ("Fixture Customs Act 1969", "Fixture Sales Tax Act 1990"):
        shutil.move(str(_json_path(corpus, name)), str(parked / f"{name}.json"))
    first = await _sync(corpus)
    assert first["added"] == 1

    for path in parked.iterdir():
        shutil.move(str(path), str(corpus / "output" / path.name))
    second = await _sync(corpus)
    assert second["added"] == 2
    assert second["skipped"] == 1, "the already-ingested document was rewritten"

    async with database_connection() as db:
        counts = await _counts(db)
    assert counts["documents"] == 3
    assert counts["versions"] == 3, "a resumed run manufactured extra versions"


async def test_two_syncs_of_one_corpus_do_not_collide(corpus, runtime_sandbox):
    """`sync_validated_pair` takes a transaction-scoped advisory lock per edition."""
    await asyncio.gather(_sync(corpus), _sync(corpus))
    async with database_connection() as db:
        counts = await _counts(db)
    assert counts["documents"] == 3, "concurrent syncs duplicated documents"
    assert counts["versions"] == 3, "concurrent syncs manufactured versions"


async def test_rolling_back_to_an_earlier_version_restores_its_text(corpus, runtime_sandbox):
    await _sync(corpus)
    async with database_connection() as db:
        async with db.execute(
            "SELECT id FROM documents WHERE name = ?", (FIRST,)
        ) as cursor:
            document_id = (await cursor.fetchone())["id"]
        original = await versions.active_version(db, document_id)

    doc = _load(corpus)
    doc["chapters"][0]["sections"][0]["plain_text"] = "rewritten"
    doc["chapters"][0]["sections"][0]["html"] = "<p>rewritten</p>"
    _save(corpus, doc)
    await _sync(corpus)

    async with database_connection() as db:
        async with db.execute(
            "SELECT plain_text FROM sections WHERE document_id = ? ORDER BY sort_order",
            (document_id,),
        ) as cursor:
            assert (await cursor.fetchone())["plain_text"] == "rewritten"

        result = await versions.activate_version(db, document_id, original["id"])
        await db.commit()
        assert result["status"] == "activated"
        async with db.execute(
            "SELECT plain_text FROM sections WHERE document_id = ? ORDER BY sort_order",
            (document_id,),
        ) as cursor:
            assert (await cursor.fetchone())["plain_text"] != "rewritten"


# --- withdrawal, through the real sync ----------------------------------------


async def test_withdrawal_and_return(corpus, runtime_sandbox):
    await _sync(corpus)
    async with database_connection() as db:
        before = await _counts(db)

    parked = corpus.parent / "parked"
    parked.mkdir()
    shutil.move(str(_json_path(corpus)), str(parked / f"{FIRST}.json"))
    await _sync(corpus)
    await reconcile_corpus("acts", [p.stem for p in (corpus / "output").glob("*.json")])

    async with database_connection() as db:
        async with db.execute(
            "SELECT withdrawn_at FROM documents WHERE name = ?", (FIRST,)
        ) as cursor:
            assert (await cursor.fetchone())["withdrawn_at"], "not withdrawn"
        assert (await _counts(db))["sections"] == before["sections"], (
            "withdrawal deleted rows; the evidence pointing at them is the audit trail"
        )

    shutil.move(str(parked / f"{FIRST}.json"), str(_json_path(corpus)))
    await _sync(corpus)
    async with database_connection() as db:
        async with db.execute(
            "SELECT withdrawn_at FROM documents WHERE name = ?", (FIRST,)
        ) as cursor:
            assert (await cursor.fetchone())["withdrawn_at"] is None


async def test_a_withdrawn_document_leaves_the_library_but_stays_addressable(
    corpus, runtime_sandbox, client, db
):
    await _sync(corpus)
    parked = corpus.parent / "parked"
    parked.mkdir()
    shutil.move(str(_json_path(corpus)), str(parked / f"{FIRST}.json"))
    await _sync(corpus)
    await reconcile_corpus("acts", [p.stem for p in (corpus / "output").glob("*.json")])

    async with db.execute("SELECT id FROM documents WHERE name = ?", (FIRST,)) as cursor:
        document_id = (await cursor.fetchone())["id"]

    library = (await client.get("/api/v2/documents")).json()
    names = [item["name"] for item in library["items"]]
    assert FIRST not in names, "a retired parse is still offered for review"

    detail = await client.get(f"/api/documents/{document_id}")
    assert detail.status_code == 200, "a withdrawn document must stay addressable"
    assert detail.json()["withdrawn_at"]
