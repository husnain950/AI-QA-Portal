"""AI fix loop — model-proposed leaf corrections and their persistent overlays.

``fix_proposals`` is the audit trail: every request to the model and what came
back, whether or not it was ever applied. ``section_overlays`` is the durable
part: an approved replacement leaf, keyed by the PDF's content hash + the leaf's
``source_key`` so it survives the document row being dropped and re-synced.
``original_leaf_fingerprint`` is the hash of the pipeline leaf the fix replaced;
a future sync whose leaf no longer matches it must NOT be overwritten silently
(the parser itself changed), so the overlay goes ``stale`` instead.
"""

from __future__ import annotations

import aiosqlite

VERSION = 7


async def upgrade(db: aiosqlite.Connection) -> None:
    await db.execute("""
    CREATE TABLE IF NOT EXISTS fix_proposals (
        id                TEXT PRIMARY KEY,
        document_id       TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        section_id        TEXT REFERENCES sections(id) ON DELETE SET NULL,
        source_key        TEXT NOT NULL,
        -- fingerprint of the active leaf when the proposal was made; approval
        -- refuses to apply onto a leaf that has since changed under it
        original_fingerprint TEXT,
        instructions      TEXT NOT NULL,
        model             TEXT,
        proposed_json     TEXT,
        validation_json   TEXT,
        diff_json         TEXT,
        status            TEXT NOT NULL DEFAULT 'proposed',
        -- proposed | approved | rejected | failed
        error             TEXT,
        created_at        TEXT NOT NULL,
        created_by        TEXT,
        resolved_at       TEXT,
        resolved_by       TEXT
    );
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS section_overlays (
        id                        TEXT PRIMARY KEY,
        pdf_sha256                TEXT NOT NULL,
        section_source_key        TEXT NOT NULL,
        replacement_json          TEXT NOT NULL,
        original_leaf_fingerprint TEXT NOT NULL,
        proposal_id               TEXT REFERENCES fix_proposals(id) ON DELETE SET NULL,
        status                    TEXT NOT NULL DEFAULT 'active',
        -- active | stale | superseded | revoked
        created_at                TEXT NOT NULL,
        created_by                TEXT,
        status_changed_at         TEXT,
        status_reason             TEXT
    );
    """)

    await db.execute("""
    CREATE INDEX IF NOT EXISTS idx_fix_proposals_document
    ON fix_proposals(document_id, created_at DESC);
    """)

    await db.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_overlays_active
    ON section_overlays(pdf_sha256, section_source_key)
    WHERE status = 'active';
    """)

    await db.execute("""
    CREATE INDEX IF NOT EXISTS idx_overlays_pdf
    ON section_overlays(pdf_sha256);
    """)

    await db.commit()
