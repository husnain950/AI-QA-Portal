"""Approval inheritance — propagate QA verdicts across identical variants."""

from __future__ import annotations

import aiosqlite

VERSION = 6


async def upgrade(db: aiosqlite.Connection) -> None:
    await db.execute("""
    CREATE TABLE IF NOT EXISTS approval_inheritance (
        id            INTEGER PRIMARY KEY,
        source_id     TEXT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
        inheritor_id  TEXT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
        variant_key   TEXT NOT NULL,
        inherited_at  TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(source_id, inheritor_id)
    );
    """)

    await db.execute("""
    CREATE INDEX IF NOT EXISTS idx_inheritance_inheritor
    ON approval_inheritance(inheritor_id);
    """)

    await db.execute("""
    CREATE INDEX IF NOT EXISTS idx_inheritance_source
    ON approval_inheritance(source_id);
    """)

    # When an inheritance row is deleted, reset the inheritor to pending
    # (unless it was independently approved).
    await db.execute("""
    CREATE TRIGGER IF NOT EXISTS inheritance_revoke_on_delete
    AFTER DELETE ON approval_inheritance
    BEGIN
        UPDATE sections
        SET review_status = 'pending'
        WHERE id = OLD.inheritor_id
          AND review_status = 'approved_inherited';
    END;
    """)

    await db.commit()
