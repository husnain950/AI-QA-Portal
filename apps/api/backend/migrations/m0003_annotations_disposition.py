"""Add disposition column to annotations for unified triage vocabulary."""

from __future__ import annotations

import aiosqlite

VERSION = 3


async def _columns(db: aiosqlite.Connection, table: str) -> set[str]:
    async with db.execute(f"PRAGMA table_info({table});") as cursor:
        return {row[1] for row in await cursor.fetchall()}


async def upgrade(db: aiosqlite.Connection) -> None:
    if "disposition" not in await _columns(db, "annotations"):
        await db.execute(
            "ALTER TABLE annotations ADD COLUMN disposition TEXT NOT NULL DEFAULT 'open';"
        )
    await db.commit()
