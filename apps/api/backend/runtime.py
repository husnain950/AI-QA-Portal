import os
import shutil

import aiosqlite

from backend.database import DB_PATH, init_db

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(BACKEND_DIR, "uploads"))
SEED_DB_PATH = os.path.join(BACKEND_DIR, "seed_data", "qa_portal.db")
SEED_UPLOAD_DIR = os.path.join(BACKEND_DIR, "seed_uploads")


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


async def bootstrap_runtime() -> None:
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
