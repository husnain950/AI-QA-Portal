"""Static PDFs, JSON version history, and carrying QA state across a re-parse."""

import io
import json
from pathlib import Path

import aiosqlite
import pytest
from fastapi import HTTPException, UploadFile
from pypdf import PdfWriter

import backend.database as database
from backend.migrate_blobs import migrate
from backend.routes.documents import (
    _require_document,
    activate_document_version,
    diff_document_version,
    list_document_versions,
    upload_document,
)
from backend.services import anchoring, blob_store, versions
from backend.services.document_store import apply_parsed_document
from backend.services.json_parser import parse_json_document
from backend.tests.conftest import add_annotation, sample_document


def _pdf_bytes(pages: int = 3) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _upload(pdf: bytes, payload: str, name: str = "doc"):
    return dict(
        pdf=UploadFile(filename=f"{name}.pdf", file=io.BytesIO(pdf)),
        json_file=UploadFile(filename=f"{name}.json", file=io.BytesIO(payload.encode())),
        name=name,
    )


# --------------------------------------------------------------------------- blobs


def test_blob_store_dedupes_and_uses_relative_names(runtime_sandbox):
    first = blob_store.store_bytes(b"%PDF-1.4 same", "pdf")
    second = blob_store.store_bytes(b"%PDF-1.4 same", "pdf")
    assert first == second
    assert blob_store.is_blob_name(first)
    # Stored under UPLOAD_DIR/pdf/, which is what the /uploads static mount serves.
    assert Path(blob_store.blob_path(first)).relative_to(
        runtime_sandbox["upload_dir"]
    ) == Path(first)
    assert len(list(Path(runtime_sandbox["upload_dir"]).glob("pdf/*.pdf"))) == 1


def test_blob_store_rejects_unknown_kind(runtime_sandbox):
    with pytest.raises(ValueError):
        blob_store.store_bytes(b"x", "docx")


@pytest.mark.asyncio
async def test_migrate_blobs_moves_legacy_uploads_and_is_idempotent(runtime_sandbox):
    upload_dir = Path(runtime_sandbox["upload_dir"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    pdf = _pdf_bytes()
    payload = sample_document()

    # Two documents that were given the identical PDF under the old flat scheme.
    for index in (1, 2):
        (upload_dir / f"doc{index}_act.pdf").write_bytes(pdf)
        (upload_dir / f"doc{index}_act.json").write_text(payload, encoding="utf-8")
    (upload_dir / "unreferenced_leftover.pdf").write_bytes(b"%PDF-1.4 nobody")

    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        for index in (1, 2):
            await db.execute(
                """
                INSERT INTO documents (
                    id, name, pdf_filename, json_filename, total_sections,
                    total_pages, uploaded_at, status, source_type
                ) VALUES (?, ?, ?, ?, 2, 3, 'now', 'pending', 'upload')
                """,
                (
                    f"doc{index}",
                    f"Act {index}",
                    f"doc{index}_act.pdf",
                    f"doc{index}_act.json",
                ),
            )
        await db.commit()
    # A fresh init_db turns those rows into version 1, as it will on the live database.
    await database.init_db()

    preview = await migrate(dry_run=True)
    assert preview["moved"] == 2, preview  # one PDF + one JSON, both shared
    assert preview["deduped"] == 2, preview
    assert (upload_dir / "doc1_act.pdf").exists(), "dry run must not write"

    report = await migrate()
    assert report["moved"] == 2 and report["deduped"] == 2
    assert not (upload_dir / "doc1_act.pdf").exists()
    assert len(list(upload_dir.glob("pdf/*.pdf"))) == 1, "identical PDFs collapse to one"
    assert len(list(upload_dir.glob("json/*.json"))) == 1
    assert "unreferenced_leftover.pdf" in report["orphans"]

    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT pdf_filename, json_filename FROM documents") as cur:
            names = [dict(row) for row in await cur.fetchall()]
        async with db.execute(
            "SELECT json_filename, json_sha256 FROM document_versions"
        ) as cur:
            version_rows = [dict(row) for row in await cur.fetchall()]

    assert all(blob_store.is_blob_name(row["pdf_filename"]) for row in names)
    assert all(blob_store.usable(blob_store.blob_path(row["pdf_filename"])) for row in names)
    assert all(row["json_sha256"] for row in version_rows), "backfilled hash must be filled"

    again = await migrate()
    assert again["moved"] == 0 and again["already_addressed"] == 6


# ------------------------------------------------------------------------ versions


@pytest.mark.asyncio
async def test_upload_creates_version_one_and_further_versions_stack(runtime_sandbox):
    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        created = await upload_document(**_upload(_pdf_bytes(), sample_document()), db=db)
        rows = await list_document_versions(created.id, db)

    assert len(rows) == 1
    assert rows[0].version_no == 1 and rows[0].is_active
    assert blob_store.is_blob_name(created.pdf_filename)
    assert blob_store.is_blob_name(created.json_filename)
    assert created.total_sections == 2


@pytest.mark.asyncio
async def test_identical_json_is_not_a_new_version(runtime_sandbox):
    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        created = await upload_document(**_upload(_pdf_bytes(), sample_document()), db=db)
        row, outcome = await versions.create_version(
            db, created.id, sample_document().encode()
        )
        await db.commit()
    assert outcome["status"] == "unchanged"
    assert row["version_no"] == 1


@pytest.mark.asyncio
async def test_activate_rolls_back_to_the_previous_parse(runtime_sandbox):
    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        created = await upload_document(**_upload(_pdf_bytes(), sample_document()), db=db)
        await versions.create_version(
            db,
            created.id,
            sample_document(second_text="Corrected second section").encode(),
            note="pipeline fix",
        )
        await db.commit()

        async with db.execute(
            "SELECT plain_text FROM sections ORDER BY sort_order DESC LIMIT 1"
        ) as cursor:
            assert (await cursor.fetchone())["plain_text"] == "Corrected second section"

        rows = await list_document_versions(created.id, db)
        assert [row.version_no for row in rows] == [2, 1]
        first = next(row for row in rows if row.version_no == 1)

        await activate_document_version(created.id, first.id, db)
        async with db.execute(
            "SELECT plain_text FROM sections ORDER BY sort_order DESC LIMIT 1"
        ) as cursor:
            assert (await cursor.fetchone())["plain_text"] == "Second section"
        async with db.execute(
            "SELECT COUNT(*) FROM document_versions WHERE document_id = ? AND is_active = 1",
            (created.id,),
        ) as cursor:
            assert (await cursor.fetchone())[0] == 1, "exactly one active version"


@pytest.mark.asyncio
async def test_only_one_version_can_be_active(runtime_sandbox):
    """The partial unique index, not convention, is what enforces this."""
    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        created = await upload_document(**_upload(_pdf_bytes(), sample_document()), db=db)
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                """
                INSERT INTO document_versions (
                    id, document_id, version_no, json_filename, json_sha256,
                    created_at, total_sections, is_active
                ) VALUES ('rogue', ?, 99, 'json/x.json', 'x', 'now', 0, 1)
                """,
                (created.id,),
            )
        await db.rollback()


@pytest.mark.asyncio
async def test_version_diff_reports_changed_added_and_removed_leaves(runtime_sandbox):
    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        created = await upload_document(**_upload(_pdf_bytes(), sample_document()), db=db)

        payload = json.loads(sample_document())
        payload["chapters"][0]["sections"][1]["plain_text"] = "Corrected second section"
        payload["chapters"][0]["sections"][1]["html"] = "<p>Corrected second section</p>"
        row, _ = await versions.create_version(
            db, created.id, json.dumps(payload).encode(), note="fix"
        )
        await db.commit()

        result = await diff_document_version(created.id, row["id"], None, db)

    assert result["summary"]["changed"] == 1
    assert result["summary"]["unchanged"] == 1
    assert result["summary"]["added"] == result["summary"]["removed"] == 0
    body = "\n".join(line for item in result["sections"] for line in item["diff"])
    assert "-Second section" in body and "+Corrected second section" in body


@pytest.mark.asyncio
async def test_diff_of_the_first_version_is_empty_not_an_error(runtime_sandbox):
    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        created = await upload_document(**_upload(_pdf_bytes(), sample_document()), db=db)
        rows = await list_document_versions(created.id, db)
        result = await diff_document_version(created.id, rows[0].id, None, db)
    assert result["base"] is None
    assert result["sections"] == []


@pytest.mark.asyncio
async def test_unknown_version_activation_is_404(runtime_sandbox):
    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        created = await upload_document(**_upload(_pdf_bytes(), sample_document()), db=db)
        with pytest.raises(HTTPException) as error:
            await activate_document_version(created.id, "no-such-version", db)
    assert error.value.status_code == 404


# ----------------------------------------------------------------------- anchoring


@pytest.mark.asyncio
async def test_annotation_survives_a_reparse_and_is_flagged_when_unfindable(
    runtime_sandbox,
):
    document_id = "anchor-doc"
    sections, footnotes = parse_json_document(sample_document(), document_id=document_id)
    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            INSERT INTO documents (
                id, name, pdf_filename, json_filename, total_sections,
                total_pages, uploaded_at, status, source_type
            ) VALUES (?, 'Act', 'pdf/a.pdf', '', 2, 3, 'now', 'pending', 'upload')
            """,
            (document_id,),
        )
        await apply_parsed_document(db, document_id, sections, footnotes)

        keeper = sections[0]["id"]
        loser = sections[1]["id"]
        await add_annotation(
            db, keeper, annotation_id="keeps", highlighted_text="First section",
            start=0, end=13,
        )
        await add_annotation(
            db, loser, annotation_id="loses", highlighted_text="Second section",
            start=0, end=14,
        )
        await db.commit()

        changed, changed_footnotes = parse_json_document(
            sample_document(second_text="Entirely rewritten"), document_id=document_id
        )
        changed[0]["html_content"] = "<p>Preamble. First section</p>"
        changed[0]["plain_text"] = "Preamble. First section"
        stats = await apply_parsed_document(db, document_id, changed, changed_footnotes)
        await db.commit()

        async with db.execute(
            "SELECT id, anchor_status, start_offset, end_offset FROM annotations"
        ) as cursor:
            found = {row["id"]: dict(row) for row in await cursor.fetchall()}
        async with db.execute(
            "SELECT html_content FROM sections WHERE id = ?", (keeper,)
        ) as cursor:
            html = (await cursor.fetchone())["html_content"]

    carryover = stats["carryover"]
    assert carryover["reanchored"] == 1 and carryover["needs_recheck"] == 1

    moved = found["keeps"]
    assert moved["anchor_status"] == "anchored"
    text = anchoring.container_text(html)
    assert text[moved["start_offset"]:moved["end_offset"]] == "First section"

    # The text it pointed at is simply gone: flag it, do not guess, do not delete it.
    assert found["loses"]["anchor_status"] == "needs_recheck"
    assert found["loses"]["start_offset"] == 0


@pytest.mark.asyncio
async def test_container_text_matches_the_pipelines_real_markup():
    """Offsets index the rendered container's textContent, not the raw html."""
    html = (
        '<h4 class="section-heading">1. Short title.&#8212;</h4>\n'
        '<ol class="subsection"><li>(1) Called the Tax Laws &amp; Act.</li></ol>'
    )
    text = anchoring.container_text(html)
    assert "<" not in text and "class=" not in text
    assert "—" in text and " & " in text
    assert text.index("1. Short title") == 0


# ------------------------------------------------------------------ the whole story


@pytest.mark.asyncio
async def test_the_workflow_this_all_exists_for(runtime_sandbox):
    """Upload once, annotate, fix the pipeline, push JSON only, see and undo the change.

    This is the end-to-end shape of the change: the PDF is sent once and never again,
    a reviewer's finding survives the corrected parse instead of blocking it, and the
    difference between the two parses is inspectable and reversible.
    """
    pdf = _pdf_bytes()

    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row

        # 1. Upload the pair once.
        created = await upload_document(**_upload(pdf, sample_document()), db=db)
        pdf_name = created.pdf_filename
        upload_dir = Path(runtime_sandbox["upload_dir"])
        assert len(list(upload_dir.glob("pdf/*.pdf"))) == 1

        # 2. A reviewer approves one leaf and flags a problem in the other.
        async with db.execute(
            "SELECT id, plain_text FROM sections ORDER BY sort_order"
        ) as cursor:
            first, second = [dict(row) for row in await cursor.fetchall()]
        await db.execute(
            "UPDATE sections SET review_status = 'approved' WHERE id = ?", (first["id"],)
        )
        await add_annotation(
            db,
            second["id"],
            annotation_id="finding-1",
            highlighted_text="Second section",
            start=0,
            end=14,
            context_after="",
        )
        await db.commit()

        # 3. The pipeline is fixed. Only the JSON is sent -- no PDF in the request.
        payload = json.loads(sample_document())
        payload["chapters"][0]["sections"][1]["plain_text"] = "Corrected. Second section"
        payload["chapters"][0]["sections"][1]["html"] = "<p>Corrected. Second section</p>"
        version_row, outcome = await versions.create_version(
            db,
            created.id,
            json.dumps(payload).encode(),
            note="fixed the heading bleed",
            created_by="pipeline",
        )
        await db.commit()

        assert outcome["status"] == "created"
        # The PDF was never touched, and is still stored exactly once.
        assert (await _require_document(db, created.id))["pdf_filename"] == pdf_name
        assert len(list(upload_dir.glob("pdf/*.pdf"))) == 1
        # Two JSON blobs now: the old parse is retained, not overwritten.
        assert len(list(upload_dir.glob("json/*.json"))) == 2

        # 4. The fix landed, and the finding came with it.
        carryover = outcome["stats"]["carryover"]
        assert carryover["sections_changed"] == 1
        assert carryover["reanchored"] == 1
        assert carryover["orphaned"] == 0

        async with db.execute(
            "SELECT anchor_status, start_offset, end_offset FROM annotations "
            "WHERE id = 'finding-1'"
        ) as cursor:
            annotation = dict(await cursor.fetchone())
        async with db.execute(
            "SELECT html_content, review_status FROM sections WHERE id = ?",
            (second["id"],),
        ) as cursor:
            changed = dict(await cursor.fetchone())

        assert annotation["anchor_status"] == "anchored"
        text = anchoring.container_text(changed["html_content"])
        assert (
            text[annotation["start_offset"]:annotation["end_offset"]] == "Second section"
        )
        # An open finding keeps the leaf flagged rather than silently going pending.
        assert changed["review_status"] == "has_issues"

        # The untouched leaf keeps its approval; only changed text loses it.
        async with db.execute(
            "SELECT review_status FROM sections WHERE id = ?", (first["id"],)
        ) as cursor:
            assert (await cursor.fetchone())["review_status"] == "approved"

        # 5. The change is inspectable.
        diff = await diff_document_version(created.id, version_row["id"], None, db)
        assert diff["summary"] == {
            "added": 0,
            "removed": 0,
            "changed": 1,
            "unchanged": 1,
        }
        body = "\n".join(line for item in diff["sections"] for line in item["diff"])
        assert "+Corrected. Second section" in body

        # 6. And reversible.
        rows = await list_document_versions(created.id, db)
        first_version = next(row for row in rows if row.version_no == 1)
        await activate_document_version(created.id, first_version.id, db)

        async with db.execute(
            "SELECT plain_text FROM sections WHERE id = ?", (second["id"],)
        ) as cursor:
            assert (await cursor.fetchone())["plain_text"] == "Second section"
        async with db.execute("SELECT COUNT(*) FROM annotations") as cursor:
            assert (await cursor.fetchone())[0] == 1, "rollback must not drop findings"


@pytest.mark.asyncio
async def test_upload_is_streamed_not_buffered(runtime_sandbox):
    """A large PDF must never be held in memory in one piece.

    Buffering it took the 256 MB deployment down mid-import, so this pins the read
    size: the store must pull the file in chunks, and still land on the same content
    address as an equivalent in-memory write.
    """
    payload = _pdf_bytes(40)

    class CountingUpload:
        def __init__(self, data):
            self._buffer = io.BytesIO(data)
            self.reads = []

        async def read(self, size=-1):
            chunk = self._buffer.read(size)
            self.reads.append(size)
            return chunk

    upload = CountingUpload(payload)
    name = await blob_store.store_upload(upload, "pdf")

    assert all(size == blob_store._CHUNK for size in upload.reads), upload.reads
    assert len(upload.reads) >= 1
    assert name == blob_store.store_bytes(payload, "pdf"), "same bytes, same address"
    with open(blob_store.blob_path(name), "rb") as stored:
        assert stored.read() == payload
    # No partial file is left behind under the kind directory.
    leftovers = list(Path(runtime_sandbox["upload_dir"]).glob("pdf/.incoming.*"))
    assert leftovers == [], leftovers


@pytest.mark.asyncio
async def test_failed_stream_leaves_no_partial_blob(runtime_sandbox):
    class ExplodingUpload:
        def __init__(self):
            self.calls = 0

        async def read(self, size=-1):
            self.calls += 1
            if self.calls == 1:
                return b"%PDF-1.4 partial"
            raise OSError("connection dropped")

    with pytest.raises(OSError):
        await blob_store.store_upload(ExplodingUpload(), "pdf")

    upload_dir = Path(runtime_sandbox["upload_dir"])
    assert list(upload_dir.glob("pdf/*")) == []
