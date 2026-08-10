"""Findings table — automated detector output with stable identity."""

from __future__ import annotations

import aiosqlite

VERSION = 4


async def upgrade(db: aiosqlite.Connection) -> None:
    await db.execute("""
    CREATE TABLE IF NOT EXISTS findings (
        id              INTEGER PRIMARY KEY,
        section_id      TEXT NOT NULL,
        document_id     TEXT NOT NULL,
        detector        TEXT NOT NULL,
        detector_version TEXT NOT NULL,
        fingerprint     TEXT NOT NULL,
        severity        TEXT NOT NULL DEFAULT 'warning',
        score           REAL,
        triage          TEXT NOT NULL DEFAULT 'new',
        triage_note     TEXT,
        triaged_by      TEXT,
        triaged_at      TEXT,
        first_seen_at   TEXT NOT NULL,
        last_seen_at    TEXT NOT NULL,
        detail_json     TEXT,
        UNIQUE(section_id, detector, fingerprint)
    );
    """)

    await db.execute("""
    CREATE INDEX IF NOT EXISTS idx_findings_queue
    ON findings(triage, detector, severity);
    """)

    await db.execute("""
    CREATE INDEX IF NOT EXISTS idx_findings_section
    ON findings(section_id);
    """)

    await db.execute("""
    CREATE INDEX IF NOT EXISTS idx_findings_document
    ON findings(document_id);
    """)

    await db.commit()
