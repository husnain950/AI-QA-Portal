import os
import shutil
from pathlib import Path

import aiosqlite

from backend.database import DB_PATH, init_db

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(BACKEND_DIR, "uploads"))
SEED_DB_PATH = os.path.join(BACKEND_DIR, "seed_data", "qa_portal.db")
SEED_UPLOAD_DIR = os.path.join(BACKEND_DIR, "seed_uploads")

SEED_CORPUS_ORDINANCE = Path(
    os.environ.get("SEED_CORPUS_ORDINANCE", "/seed/corpus/ordinance")
)
SEED_CORPUS_ACTS = Path(os.environ.get("SEED_CORPUS_ACTS", "/seed/corpus/acts"))


def seed_runtime_files() -> None:
    """Populate ignored runtime storage without overwriting user QA state.

    ``seed_uploads`` is no longer carried in git -- source PDFs are static and were
    163 MB of repository. It is still honoured when an operator drops files there, but
    a deployment normally populates ``uploads/`` from the server volume or by running
    ``backend.sync_acts``. See "Seeding storage" in the README.
    """

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    if not os.path.exists(DB_PATH) and os.path.exists(SEED_DB_PATH):
        shutil.copy2(SEED_DB_PATH, DB_PATH)

    current_uploads = [
        name for name in os.listdir(UPLOAD_DIR) if name != ".gitkeep"
    ]
    if not current_uploads and os.path.isdir(SEED_UPLOAD_DIR):
        for name in os.listdir(SEED_UPLOAD_DIR):
            source = os.path.join(SEED_UPLOAD_DIR, name)
            destination = os.path.join(UPLOAD_DIR, name)
            if name != ".gitkeep" and os.path.isfile(source):
                shutil.copy2(source, destination)


async def merge_seed_footnote_html() -> None:
    if (
        not os.path.exists(DB_PATH)
        or not os.path.exists(SEED_DB_PATH)
        or os.path.abspath(DB_PATH) == os.path.abspath(SEED_DB_PATH)
    ):
        return

    async with aiosqlite.connect(DB_PATH) as destination:
        await destination.execute("PRAGMA foreign_keys = ON;")
        await destination.execute(
            "ATTACH DATABASE ? AS seed_db;",
            (SEED_DB_PATH,),
        )
        await destination.execute(
            """
            UPDATE footnotes
            SET html_content = (
                SELECT sf.html_content
                FROM seed_db.footnotes sf
                JOIN seed_db.sections ss ON sf.section_id = ss.id
                JOIN sections s ON footnotes.section_id = s.id
                WHERE s.document_id = ss.document_id
                  AND COALESCE(s.chapter_code, '') = COALESCE(ss.chapter_code, '')
                  AND COALESCE(s.part_code, '') = COALESCE(ss.part_code, '')
                  AND COALESCE(s.division_code, '') = COALESCE(ss.division_code, '')
                  AND COALESCE(s.section_code, '') = COALESCE(ss.section_code, '')
                  AND s.sort_order = ss.sort_order
                  AND sf.marker = footnotes.marker
            )
            WHERE (html_content IS NULL OR html_content = '')
              AND EXISTS (
                SELECT 1
                FROM seed_db.footnotes sf
                JOIN seed_db.sections ss ON sf.section_id = ss.id
                JOIN sections s ON footnotes.section_id = s.id
                WHERE s.document_id = ss.document_id
                  AND COALESCE(s.chapter_code, '') = COALESCE(ss.chapter_code, '')
                  AND COALESCE(s.part_code, '') = COALESCE(ss.part_code, '')
                  AND COALESCE(s.division_code, '') = COALESCE(ss.division_code, '')
                  AND COALESCE(s.section_code, '') = COALESCE(ss.section_code, '')
                  AND s.sort_order = ss.sort_order
                  AND sf.marker = footnotes.marker
                  AND COALESCE(sf.html_content, '') != ''
              );
            """
        )
        await destination.commit()


_BOOTSTRAP_DONE = False


def _find_seed_path(label: str) -> Path | None:
    """Locate usable corpus for auto-seeding (baked image path, then mounted volume)."""
    candidates = [
        SEED_CORPUS_ORDINANCE if label == "ordinance" else SEED_CORPUS_ACTS,
        Path(os.environ.get("CORPUS_ORDINANCE", ""))
        if label == "ordinance"
        else Path(os.environ.get("CORPUS_ACTS", "")),
    ]
    for path in candidates:
        if path and path.is_dir() and (path / "output").is_dir():
            if any(path.glob("output/*.json")):
                return path
    return None


async def _auto_seed_if_empty() -> None:
    """Seed corpus on first boot when DB has no documents.

    Checks two locations in priority order:
      1. Baked seed inside image (/seed/corpus/{ordinance,acts})
      2. Mounted corpus volumes (CORPUS_ORDINANCE / CORPUS_ACTS env vars)

    Either source works — the first available one with output/*.json wins.
    """
    ordinance_path = _find_seed_path("ordinance")
    acts_path = _find_seed_path("acts")

    if not ordinance_path and not acts_path:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM documents") as cur:
            count = (await cur.fetchone())[0]

    if count > 0:
        return

    print("[runtime] empty database detected — auto-seeding from corpus...")

    from backend.services.corpus_sync import _record_sync, sync_one

    combined = {"ordinance": {}, "acts": {}, "failed": 0, "unmatched": 0}

    if ordinance_path:
        print(f"[runtime]   ordinance source: {ordinance_path}")
        part = await sync_one(
            "ordinance",
            ordinance_path,
            dry_run=False,
            force=False,
            strict=False,
            metrics=True,
            pdf_dir=None,
        )
        combined["ordinance"] = part
        combined["failed"] += int(part.get("failed", 0) or 0)
        added = int(part.get("added", 0) or 0) + int(part.get("updated", 0) or 0)
        print(f"[runtime]   ordinance: {added} documents synced")

    if acts_path:
        print(f"[runtime]   acts source: {acts_path}")
        part = await sync_one(
            "acts",
            acts_path,
            dry_run=False,
            force=False,
            strict=False,
            metrics=True,
            pdf_dir=None,
        )
        combined["acts"] = part
        combined["failed"] += int(part.get("failed", 0) or 0)
        added = int(part.get("added", 0) or 0) + int(part.get("updated", 0) or 0)
        print(f"[runtime]   acts: {added} documents synced")

    status = "ok" if combined["failed"] == 0 else "failed"
    await _record_sync(combined, status)
    print(f"[runtime] auto-seed complete (status={status})")


async def bootstrap_runtime() -> None:
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    _BOOTSTRAP_DONE = True

    seed_runtime_files()
    await init_db()
    await merge_seed_footnote_html()

    # A seeded database still carries the pre-versioning flat upload names. Addressing
    # them is idempotent and costs two queries once everything is already addressed, so
    # it runs on boot rather than being a step someone has to remember on every deploy.
    # Imported here, not at module scope: blob_store imports this module.
    from backend.migrate_blobs import migrate

    report = await migrate()
    if report["moved"] or report["missing"]:
        print(
            f"[runtime] blob migration: moved {report['moved']}, "
            f"deduped {report['deduped']}, missing {len(report['missing'])}"
        )

    await _auto_seed_if_empty()
