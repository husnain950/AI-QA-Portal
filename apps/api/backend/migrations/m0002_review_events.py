"""Append-only review audit trail.

actor is the X-Reviewer header value — a display name, not authentication.
Triggers prevent mutation after the fact.
"""

from __future__ import annotations

import aiosqlite

VERSION = 2


async def upgrade(db: aiosqlite.Connection) -> None:
    await db.execute("""
    CREATE TABLE IF NOT EXISTS review_events (
        id          INTEGER PRIMARY KEY,
        at          TEXT NOT NULL,
        actor       TEXT NOT NULL,
        action      TEXT NOT NULL,
        document_id TEXT,
        section_id  TEXT,
        version_id  TEXT,
        from_value  TEXT,
        to_value    TEXT,
        detail_json TEXT
    );
    """)

    await db.execute("""
    CREATE TRIGGER IF NOT EXISTS review_events_no_update
    BEFORE UPDATE ON review_events
    BEGIN
        SELECT RAISE(ABORT, 'review_events is append-only');
    END;
    """)

    await db.execute("""
    CREATE TRIGGER IF NOT EXISTS review_events_no_delete
    BEFORE DELETE ON review_events
    BEGIN
        SELECT RAISE(ABORT, 'review_events is append-only');
    END;
    """)

    await db.commit()
