"""Initial schema — ported from the pre-migration database.py DDL.

Idempotent: CREATE IF NOT EXISTS, guarded ALTER for legacy DBs, FTS rebuild.
"""

from __future__ import annotations

import os
import uuid

import aiosqlite

VERSION = 1


async def _columns(db: aiosqlite.Connection, table: str) -> set[str]:
    async with db.execute(f"PRAGMA table_info({table});") as cursor:
        return {row[1] for row in await cursor.fetchall()}


async def _scalar(db: aiosqlite.Connection, sql: str, params=()) -> int:
    async with db.execute(sql, params) as cursor:
        row = await cursor.fetchone()
    return int((row[0] if row else 0) or 0)


async def _rebuild_annotations_if_legacy(db: aiosqlite.Connection) -> None:
    if "document_id" in await _columns(db, "annotations"):
        return

    before = await _scalar(db, "SELECT COUNT(*) FROM annotations;")
    await db.execute("PRAGMA foreign_keys = OFF;")
    try:
        await db.execute("""
        CREATE TABLE annotations_rebuilt (
            id            TEXT PRIMARY KEY,
            document_id   TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            section_id    TEXT REFERENCES sections(id) ON DELETE SET NULL,
            footnote_id   TEXT REFERENCES footnotes(id) ON DELETE SET NULL,
            highlighted_text TEXT NOT NULL,
            context_before TEXT,
            context_after TEXT,
            start_offset  INTEGER NOT NULL,
            end_offset    INTEGER NOT NULL,
            issue_description TEXT,
            severity      TEXT NOT NULL DEFAULT 'error',
            created_at    TEXT NOT NULL,
            reviewer_name TEXT,
            status        TEXT NOT NULL DEFAULT 'open',
            anchor_status TEXT NOT NULL DEFAULT 'anchored',
            created_version_id TEXT,
            orphan_context TEXT
        );
        """)
        await db.execute("""
            INSERT INTO annotations_rebuilt (
                id, document_id, section_id, footnote_id, highlighted_text,
                start_offset, end_offset, issue_description, severity,
                created_at, reviewer_name, status
            )
            SELECT a.id, s.document_id, a.section_id, a.footnote_id,
                   a.highlighted_text, a.start_offset, a.end_offset,
                   a.issue_description, a.severity, a.created_at,
                   a.reviewer_name, a.status
            FROM annotations a
            JOIN sections s ON s.id = a.section_id
        """)
        after = await _scalar(db, "SELECT COUNT(*) FROM annotations_rebuilt;")
        if after != before:
            raise RuntimeError(
                f"annotations migration would lose {before - after} row(s); aborted"
            )
        await db.execute("DROP TABLE annotations;")
        await db.execute("ALTER TABLE annotations_rebuilt RENAME TO annotations;")
        await db.commit()
    except Exception:
        await db.rollback()
        await db.execute("DROP TABLE IF EXISTS annotations_rebuilt;")
        await db.commit()
        raise
    finally:
        await db.execute("PRAGMA foreign_keys = ON;")


async def _backfill_initial_versions(db: aiosqlite.Connection) -> None:
    if await _scalar(db, "SELECT COUNT(*) FROM document_versions;"):
        return
    async with db.execute(
        """
        SELECT id, json_filename, total_sections, uploaded_at
        FROM documents
        WHERE json_filename IS NOT NULL AND json_filename != ''
        """
    ) as cursor:
        rows = await cursor.fetchall()
    for row in rows:
        await db.execute(
            """
            INSERT INTO document_versions (
                id, document_id, version_no, json_filename, json_sha256,
                source_name, created_at, created_by, note, total_sections,
                is_active, stats_json
            ) VALUES (?, ?, 1, ?, '', ?, ?, NULL, ?, ?, 1, NULL)
            """,
            (
                str(uuid.uuid5(uuid.NAMESPACE_URL, f"pdf-qa-portal:version:{row[0]}:1")),
                row[0],
                row[1],
                os.path.basename(row[1]),
                row[3],
                "Initial version, recorded when version history was introduced.",
                row[2] or 0,
            ),
        )
    if rows:
        await db.commit()


async def _add_column_if_missing(
    db: aiosqlite.Connection, table: str, column: str, ddl: str
) -> None:
    if column in await _columns(db, table):
        return
    try:
        await db.execute(ddl)
    except Exception as migrate_err:
        print(f"Migration error ({table}.{column}): {migrate_err}")


async def upgrade(db: aiosqlite.Connection) -> None:
    await db.execute("PRAGMA foreign_keys = ON;")

    await db.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id            TEXT PRIMARY KEY,
        name          TEXT NOT NULL,
        pdf_filename  TEXT NOT NULL,
        json_filename TEXT NOT NULL,
        total_sections INTEGER NOT NULL,
        total_pages   INTEGER NOT NULL,
        uploaded_at   TEXT NOT NULL,
        status        TEXT NOT NULL DEFAULT 'pending',
        source_type   TEXT NOT NULL DEFAULT 'upload',
        source_key    TEXT,
        source_hash   TEXT,
        provenance    TEXT,
        corpus_lane   TEXT
    );
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS sections (
        id            TEXT PRIMARY KEY,
        document_id   TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        chapter_code  TEXT,
        chapter_heading TEXT,
        part_code     TEXT,
        part_heading  TEXT,
        division_code TEXT,
        division_heading TEXT,
        section_code  TEXT NOT NULL,
        section_heading TEXT NOT NULL,
        start_page    INTEGER,
        end_page      INTEGER,
        html_content  TEXT,
        plain_text    TEXT,
        sort_order    INTEGER NOT NULL,
        review_status TEXT NOT NULL DEFAULT 'pending',
        source_key    TEXT,
        quality_flags TEXT,
        hierarchy_kind TEXT
    );
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS footnotes (
        id            TEXT PRIMARY KEY,
        section_id    TEXT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
        marker        TEXT NOT NULL,
        page          INTEGER,
        text          TEXT NOT NULL,
        html_content  TEXT,
        review_status TEXT NOT NULL DEFAULT 'pending'
    );
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS annotations (
        id            TEXT PRIMARY KEY,
        document_id   TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        section_id    TEXT REFERENCES sections(id) ON DELETE SET NULL,
        footnote_id   TEXT REFERENCES footnotes(id) ON DELETE SET NULL,
        highlighted_text TEXT NOT NULL,
        context_before TEXT,
        context_after TEXT,
        start_offset  INTEGER NOT NULL,
        end_offset    INTEGER NOT NULL,
        issue_description TEXT,
        severity      TEXT NOT NULL DEFAULT 'error',
        created_at    TEXT NOT NULL,
        reviewer_name TEXT,
        status        TEXT NOT NULL DEFAULT 'open',
        anchor_status TEXT NOT NULL DEFAULT 'anchored',
        created_version_id TEXT,
        orphan_context TEXT
    );
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS document_versions (
        id             TEXT PRIMARY KEY,
        document_id    TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        version_no     INTEGER NOT NULL,
        json_filename  TEXT NOT NULL,
        json_sha256    TEXT NOT NULL,
        source_name    TEXT,
        created_at     TEXT NOT NULL,
        created_by     TEXT,
        note           TEXT,
        total_sections INTEGER NOT NULL DEFAULT 0,
        is_active      INTEGER NOT NULL DEFAULT 0,
        stats_json     TEXT,
        UNIQUE(document_id, version_no)
    );
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS version_metrics (
        version_id TEXT PRIMARY KEY
            REFERENCES document_versions(id) ON DELETE CASCADE,
        invariants_passed INTEGER,
        invariants_total  INTEGER,
        cases_passed      INTEGER,
        cases_total       INTEGER,
        body_conserved    REAL,
        body_missing      INTEGER,
        footnote_conserved REAL,
        footnote_missing  INTEGER,
        gate_ok           INTEGER,
        measured_at       TEXT,
        detail_json       TEXT
    );
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS corpus_sync_state (
        id            INTEGER PRIMARY KEY CHECK (id = 1),
        last_sync_at  TEXT,
        last_status   TEXT,
        last_summary  TEXT,
        ordinance_docs INTEGER DEFAULT 0,
        acts_docs      INTEGER DEFAULT 0
    );
    """)
    await db.execute(
        "INSERT OR IGNORE INTO corpus_sync_state (id) VALUES (1);"
    )

    # Legacy column upgrades for databases created before full CREATE DDL.
    await _add_column_if_missing(
        db,
        "annotations",
        "footnote_id",
        "ALTER TABLE annotations ADD COLUMN footnote_id TEXT REFERENCES footnotes(id) ON DELETE CASCADE;",
    )
    await _add_column_if_missing(
        db,
        "annotations",
        "status",
        "ALTER TABLE annotations ADD COLUMN status TEXT NOT NULL DEFAULT 'open';",
    )
    await _add_column_if_missing(
        db, "footnotes", "html_content", "ALTER TABLE footnotes ADD COLUMN html_content TEXT;"
    )
    for column, ddl in (
        (
            "source_type",
            "ALTER TABLE documents ADD COLUMN source_type TEXT NOT NULL DEFAULT 'upload';",
        ),
        ("source_key", "ALTER TABLE documents ADD COLUMN source_key TEXT;"),
        ("source_hash", "ALTER TABLE documents ADD COLUMN source_hash TEXT;"),
        (
            "provenance",
            "ALTER TABLE documents ADD COLUMN provenance TEXT;",
        ),
        (
            "corpus_lane",
            "ALTER TABLE documents ADD COLUMN corpus_lane TEXT;",
        ),
    ):
        await _add_column_if_missing(db, "documents", column, ddl)

    await _add_column_if_missing(
        db, "sections", "source_key", "ALTER TABLE sections ADD COLUMN source_key TEXT;"
    )
    await _add_column_if_missing(
        db, "sections", "quality_flags", "ALTER TABLE sections ADD COLUMN quality_flags TEXT;"
    )
    await _add_column_if_missing(
        db, "sections", "hierarchy_kind", "ALTER TABLE sections ADD COLUMN hierarchy_kind TEXT;"
    )

    # tables may exist from a partial legacy schema without annotations yet
    tables = set()
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table';"
    ) as cursor:
        tables = {row[0] for row in await cursor.fetchall()}
    if "annotations" in tables:
        await _rebuild_annotations_if_legacy(db)
    if "document_versions" in tables and "documents" in tables:
        await _backfill_initial_versions(db)

    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_sections_document ON sections(document_id);"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_versions_document "
        "ON document_versions(document_id, version_no DESC);"
    )
    await db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_versions_active
        ON document_versions(document_id) WHERE is_active = 1;
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_annotations_document "
        "ON annotations(document_id);"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_sections_pages ON sections(document_id, start_page, end_page);"
    )
    await db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_source
        ON documents(source_type, source_key)
        WHERE source_key IS NOT NULL;
        """
    )
    await db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sections_source
        ON sections(document_id, source_key)
        WHERE source_key IS NOT NULL;
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_footnotes_section ON footnotes(section_id);"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_annotations_section ON annotations(section_id);"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_annotations_footnote ON annotations(footnote_id);"
    )

    async with db.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE type = 'table' AND name = 'sections_fts'
        """
    ) as cursor:
        fts_row = await cursor.fetchone()
    if fts_row and "content=sections" in (fts_row[0] or "").replace(" ", ""):
        await db.execute("DROP TRIGGER IF EXISTS sections_ai;")
        await db.execute("DROP TRIGGER IF EXISTS sections_ad;")
        await db.execute("DROP TRIGGER IF EXISTS sections_au;")
        await db.execute("DROP TABLE sections_fts;")

    await db.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS sections_fts USING fts5(
        section_id,
        section_code,
        section_heading,
        chapter_code,
        plain_text
    );
    """)

    await db.execute("""
    CREATE TRIGGER IF NOT EXISTS sections_ai AFTER INSERT ON sections BEGIN
        INSERT INTO sections_fts(rowid, section_id, section_code, section_heading, chapter_code, plain_text)
        VALUES (new.rowid, new.id, new.section_code, new.section_heading, new.chapter_code, new.plain_text);
    END;
    """)

    await db.execute("""
    CREATE TRIGGER IF NOT EXISTS sections_ad AFTER DELETE ON sections BEGIN
        DELETE FROM sections_fts WHERE rowid = old.rowid;
    END;
    """)

    await db.execute("""
    CREATE TRIGGER IF NOT EXISTS sections_au AFTER UPDATE ON sections BEGIN
        DELETE FROM sections_fts WHERE rowid = old.rowid;
        INSERT INTO sections_fts(rowid, section_id, section_code, section_heading, chapter_code, plain_text)
        VALUES (new.rowid, new.id, new.section_code, new.section_heading, new.chapter_code, new.plain_text);
    END;
    """)

    async with db.execute("SELECT COUNT(*) FROM sections_fts;") as cursor:
        fts_count = (await cursor.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM sections;") as cursor:
        section_count = (await cursor.fetchone())[0]
    if fts_count != section_count:
        await db.execute("DELETE FROM sections_fts;")
        await db.execute(
            """
            INSERT INTO sections_fts(
                rowid, section_id, section_code, section_heading,
                chapter_code, plain_text
            )
            SELECT
                rowid, id, section_code, section_heading,
                chapter_code, plain_text
            FROM sections
            """
        )

    await db.commit()
