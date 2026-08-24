import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

from backend.database import database_connection
from backend.routes.documents import list_documents
from backend.sync_acts import discover_acts_repo, discover_pairs, run_sync
from backend.tests.conftest import add_annotation, sample_document, write_pair


def test_pair_discovery_rejects_ambiguous_and_symbolic_sources(tmp_path):
    ambiguous = tmp_path / "Ambiguous"
    ambiguous.mkdir()
    (ambiguous / "one.pdf").write_bytes(b"%PDF")
    (ambiguous / "two.pdf").write_bytes(b"%PDF")
    (ambiguous / "one.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="expected one PDF and one JSON"):
        discover_pairs(tmp_path)

    for child in ambiguous.iterdir():
        child.unlink()
    ambiguous.rmdir()
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "Linked Act").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic-link directories"):
        discover_pairs(tmp_path)


async def test_sync_is_idempotent_and_keeps_fts_and_api_consistent(
    runtime_sandbox,
):
    source = runtime_sandbox["root"] / "export"
    write_pair(source)

    first = await run_sync(source)
    second = await run_sync(source)

    assert first["added"] == 1
    assert first["failed"] == 0
    assert second["skipped"] == 1
    assert second["added"] == second["updated"] == second["failed"] == 0

    async with database_connection() as db:
        documents = await list_documents(db)
        assert len(documents) == 1
        assert documents[0].source_type == "acts_corpus"
        assert documents[0].source_key == "Test Act"
        async with db.execute("SELECT COUNT(*) FROM sections") as cursor:
            section_count = (await cursor.fetchone())[0]
        # The GIN expression index replaced the SQLite FTS shadow table: every
        # synced section must be reachable through the same match search uses.
        async with db.execute(
            """
            SELECT COUNT(*) FROM sections s
            WHERE to_tsvector('simple', coalesce(s.section_code,'') || ' ' ||
                                        coalesce(s.section_heading,'') || ' ' ||
                                        coalesce(s.plain_text,''))
                  @@ plainto_tsquery('simple', 'section')
            """
        ) as cursor:
            searchable = (await cursor.fetchone())[0]

    assert section_count == searchable == 2
    assert len(list(Path(runtime_sandbox["upload_dir"]).iterdir())) == 2


async def test_sync_replaces_empty_upload_stub(
    runtime_sandbox,
):
    source = runtime_sandbox["root"] / "export"
    write_pair(source)
    first = await run_sync(source)
    assert first["added"] == 1

    upload_dir = Path(runtime_sandbox["upload_dir"])
    pdfs = list(upload_dir.glob("pdf/*.pdf"))
    assert len(pdfs) == 1
    pdfs[0].write_bytes(b"")

    # Unchanged source_hash would previously skip forever while leaving a 0-byte stub.
    repaired = await run_sync(source)
    assert repaired["failed"] == 0
    assert repaired["skipped"] == 0
    assert repaired["updated"] == 1
    assert pdfs[0].stat().st_size > 0


async def test_strict_mode_refuses_to_supersede_an_annotated_leaf(runtime_sandbox):
    """--strict keeps the pre-versioning contract: refuse, roll back, change nothing."""
    source = runtime_sandbox["root"] / "export"
    pair_directory = write_pair(source)
    assert (await run_sync(source))["added"] == 1

    async with database_connection() as db:
        async with db.execute(
            """
            SELECT d.id AS document_id, d.source_hash, s.id AS section_id
            FROM documents d JOIN sections s ON s.document_id = d.id
            ORDER BY s.sort_order LIMIT 1
            """
        ) as cursor:
            before = dict(await cursor.fetchone())
        await add_annotation(
            db, before["section_id"], annotation_id="annotation-1",
            highlighted_text="First",
        )
        await db.commit()

    payload = json.loads(sample_document())
    payload["chapters"][0]["sections"][0]["plain_text"] = "Changed first section"
    payload["chapters"][0]["sections"][0]["html"] = "<p>Changed first section</p>"
    (pair_directory / "act.json").write_text(json.dumps(payload), encoding="utf-8")

    result = await run_sync(source, strict=True)
    assert result["failed"] == 1

    async with database_connection() as db:
        async with db.execute(
            "SELECT source_hash FROM documents WHERE id = ?",
            (before["document_id"],),
        ) as cursor:
            after_hash = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM annotations") as cursor:
            annotation_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM document_versions") as cursor:
            version_count = (await cursor.fetchone())[0]
    assert after_hash == before["source_hash"]
    assert annotation_count == 1
    assert version_count == 1, "a refused sync must not leave a version behind"


async def test_pipeline_fix_lands_and_carries_the_annotation_forward(runtime_sandbox):
    """The whole point of versioning: an annotated leaf no longer blocks the fix."""
    source = runtime_sandbox["root"] / "export"
    pair_directory = write_pair(source)
    assert (await run_sync(source))["added"] == 1

    async with database_connection() as db:
        async with db.execute(
            "SELECT id FROM sections ORDER BY sort_order LIMIT 1"
        ) as cursor:
            section_id = (await cursor.fetchone())["id"]
        # "First section" survives the edit below, so the finding can be re-found.
        await add_annotation(
            db, section_id, annotation_id="annotation-1",
            highlighted_text="First section", start=0, end=13,
        )
        await db.commit()

    payload = json.loads(sample_document())
    payload["chapters"][0]["sections"][0]["plain_text"] = "Corrected. First section"
    payload["chapters"][0]["sections"][0]["html"] = "<p>Corrected. First section</p>"
    (pair_directory / "act.json").write_text(json.dumps(payload), encoding="utf-8")

    result = await run_sync(source)
    assert result["failed"] == 0
    assert result["updated"] == 1

    async with database_connection() as db:
        async with db.execute(
            "SELECT * FROM annotations WHERE id = 'annotation-1'"
        ) as cursor:
            annotation = dict(await cursor.fetchone())
        async with db.execute(
            "SELECT version_no, is_active, stats_json FROM document_versions "
            "ORDER BY version_no"
        ) as cursor:
            all_versions = [dict(row) for row in await cursor.fetchall()]
        async with db.execute("SELECT plain_text FROM sections WHERE id = ?",
                              (section_id,)) as cursor:
            text = (await cursor.fetchone())["plain_text"]

    assert text == "Corrected. First section", "the fix must actually land"
    assert [v["version_no"] for v in all_versions] == [1, 2]
    assert [v["is_active"] for v in all_versions] == [0, 1]
    # Re-anchored, not lost and not left pointing at the old offsets.
    assert annotation["anchor_status"] == "anchored"
    assert text[annotation["start_offset"]:annotation["end_offset"]] == "First section"
    carryover = json.loads(all_versions[1]["stats_json"])
    assert carryover["reanchored"] == 1 and carryover["sections_changed"] == 1


async def test_removed_leaf_keeps_its_finding_as_an_orphan(runtime_sandbox):
    source = runtime_sandbox["root"] / "export"
    pair_directory = write_pair(source)
    await run_sync(source)

    async with database_connection() as db:
        async with db.execute(
            "SELECT id FROM sections ORDER BY sort_order DESC LIMIT 1"
        ) as cursor:
            doomed = (await cursor.fetchone())["id"]
        await add_annotation(db, doomed, annotation_id="doomed-1",
                             highlighted_text="Second")
        await db.commit()

    payload = json.loads(sample_document())
    del payload["chapters"][0]["sections"][1]
    (pair_directory / "act.json").write_text(json.dumps(payload), encoding="utf-8")

    assert (await run_sync(source))["failed"] == 0

    async with database_connection() as db:
        async with db.execute(
            "SELECT * FROM annotations WHERE id = 'doomed-1'"
        ) as cursor:
            annotation = dict(await cursor.fetchone())
        async with db.execute("SELECT COUNT(*) FROM sections") as cursor:
            remaining = (await cursor.fetchone())[0]

    assert remaining == 1, "the removed leaf really is gone"
    assert annotation["section_id"] is None
    assert annotation["anchor_status"] == "orphaned"
    context = json.loads(annotation["orphan_context"])
    assert context["section_heading"] == "Repeated code", context
    assert "Second section" in context["plain_text"], context


async def test_acts_repo_layout_is_discovered_and_page_ranges_are_flagged(
    runtime_sandbox, tmp_path
):
    """The Acts_fbr shape: flat output/*.json resolved to Acts/** by metadata.filename."""
    repo = tmp_path / "Acts_fbr"
    (repo / "output" / "_provisional").mkdir(parents=True)
    (repo / "Acts" / "Customs Act, 1969").mkdir(parents=True)

    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=612, height=792)
    # No .pdf suffix: six real corpus sources are like this, hence magic-byte detection.
    with (repo / "Acts" / "Customs Act, 1969" / "Customs Act 2025").open("wb") as fh:
        writer.write(fh)

    payload = json.loads(sample_document())
    payload["metadata"]["filename"] = "Customs Act 2025"
    # A year misread as a folio -- the real defect measured in the live corpus.
    payload["chapters"][0]["sections"][1]["start_page"] = 1995
    payload["chapters"][0]["sections"][1]["end_page"] = 1995
    (repo / "output" / "Customs Act 2025.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    # Neither of these may be picked up as corpus.
    (repo / "output" / "_provisional" / "Sub Floor.json").write_text("{}", encoding="utf-8")
    (repo / "output" / "Orphan Edition.json").write_text(
        json.dumps({"metadata": {"filename": "nothing.pdf"}, "chapters": []}),
        encoding="utf-8",
    )

    pairs, unmatched = discover_acts_repo(repo)
    assert [pair.source_key for pair in pairs] == ["Customs Act 2025"]
    assert len(unmatched) == 1 and "Orphan Edition.json" in unmatched[0]

    result = await run_sync(repo, acts_repo=True)
    assert result["added"] == 1
    assert result["failed"] == 0, "one bad leaf must not reject the edition"
    assert result["unmatched"] == 1
    assert result["flagged_pages"] == 1

    async with database_connection() as db:
        async with db.execute(
            "SELECT quality_flags, review_status FROM sections "
            "WHERE start_page = 1995"
        ) as cursor:
            flagged = dict(await cursor.fetchone())
    codes = [flag["code"] for flag in json.loads(flagged["quality_flags"])]
    assert "page_range_out_of_bounds" in codes, flagged


async def test_identical_pdf_across_documents_is_stored_once(runtime_sandbox):
    """Static PDFs: the same source bytes must never be written twice."""
    source = runtime_sandbox["root"] / "export"
    write_pair(source, name="Act One")
    write_pair(source, name="Act Two")

    result = await run_sync(source)
    assert result["added"] == 2

    upload_dir = Path(runtime_sandbox["upload_dir"])
    assert len(list(upload_dir.glob("pdf/*.pdf"))) == 1, "identical PDFs must dedupe"
    assert len(list(upload_dir.glob("json/*.json"))) == 1


def _write_edition(repo, pdf_dir_name, stem, pdf_name, pages=3):
    """A converted edition: JSON in output/, its PDF under an arbitrary folder."""
    (repo / "output").mkdir(parents=True, exist_ok=True)
    pdf_dir = repo / pdf_dir_name
    pdf_dir.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    with (pdf_dir / pdf_name).open("wb") as handle:
        writer.write(handle)
    payload = json.loads(sample_document())
    payload["metadata"]["filename"] = pdf_name
    (repo / "output" / f"{stem}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_discovery_finds_sources_outside_an_Acts_directory(tmp_path):
    """The Ordinance pipeline keeps its PDFs beside output/ under its own folder name.

    Hardcoding ``Acts/`` meant that whole corpus could not be synced at all.
    """
    repo = tmp_path / "CC-FBR"
    _write_edition(
        repo,
        "Income Tax Ordinance, 2001",
        "Income Tax Ordinance 2001 - amended upto 30.06.2024",
        "Income Tax Ordinance, 2001 Amended upto 30.06.2024.pdf",
    )

    pairs, unmatched = discover_acts_repo(repo)
    assert unmatched == []
    assert [p.source_key for p in pairs] == [
        "Income Tax Ordinance 2001 - amended upto 30.06.2024"
    ]
    assert pairs[0].pdf_path.parent.name == "Income Tax Ordinance, 2001"


def test_discovery_skips_output_and_nested_pipeline_repositories(tmp_path):
    """Scanning CC-FBR/ must not reach into CC-FBR/Acts_fbr/Acts/.

    A nested pipeline owns its own sources; pulling them in here would pair one
    corpus's JSON against another corpus's PDFs.
    """
    repo = tmp_path / "CC-FBR"
    _write_edition(repo, "Income Tax Ordinance, 2001", "Ordinance 2024", "Ordinance.pdf")

    # A nested repository, identified by having its own output/.
    nested = repo / "Acts_fbr"
    _write_edition(nested, "Acts", "Customs 2025", "Customs.pdf")

    # A decoy PDF inside output/ must never be treated as a source.
    (repo / "output" / "stray.pdf").write_bytes(b"%PDF-1.4 stray")

    pairs, unmatched = discover_acts_repo(repo)
    assert [p.source_key for p in pairs] == ["Ordinance 2024"]
    assert "Acts_fbr" not in str(pairs[0].pdf_path)
    assert unmatched == []

    # The nested repository still syncs perfectly well on its own.
    nested_pairs, _ = discover_acts_repo(nested)
    assert [p.source_key for p in nested_pairs] == ["Customs 2025"]


def test_explicit_pdf_dir_overrides_the_default_search(tmp_path):
    repo = tmp_path / "repo"
    _write_edition(repo, "sources", "Edition A", "A.pdf")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    pairs, _ = discover_acts_repo(repo, pdf_dir=repo / "sources")
    assert len(pairs) == 1

    # Pointed at a directory with no PDFs, nothing resolves -- and it says so.
    with pytest.raises(ValueError, match="No corpus JSON matched"):
        discover_acts_repo(repo, pdf_dir=elsewhere)

    with pytest.raises(ValueError, match="PDF directory does not exist"):
        discover_acts_repo(repo, pdf_dir=tmp_path / "nope")
