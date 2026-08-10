"""Section variants — track the same legal section across editions."""

from __future__ import annotations

import aiosqlite

VERSION = 5


async def upgrade(db: aiosqlite.Connection) -> None:
    await db.execute("""
    CREATE TABLE IF NOT EXISTS section_variants (
        id           INTEGER PRIMARY KEY,
        variant_key  TEXT NOT NULL,
        section_id   TEXT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
        document_id  TEXT NOT NULL,
        family_key   TEXT NOT NULL,
        section_code TEXT NOT NULL,
        edition_date TEXT,
        text_sha     TEXT NOT NULL,
        html_shape   TEXT NOT NULL,
        created_at   TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(variant_key, section_id)
    );
    """)

    await db.execute("""
    CREATE INDEX IF NOT EXISTS idx_variants_key
    ON section_variants(variant_key);
    """)

    await db.execute("""
    CREATE INDEX IF NOT EXISTS idx_variants_family
    ON section_variants(family_key, section_code);
    """)

    await db.commit()
