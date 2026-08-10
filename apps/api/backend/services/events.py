"""Append-only review event recorder.

Callers own the transaction — this module only inserts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite


async def active_version_id(db: aiosqlite.Connection, document_id: str) -> Optional[str]:
    """Fetch the active version id for a document, or None."""
    async with db.execute(
        "SELECT id FROM document_versions WHERE document_id = ? AND is_active = 1",
        (document_id,),
    ) as cursor:
        row = await cursor.fetchone()
    return row["id"] if row else None


async def record(
    db: aiosqlite.Connection,
    *,
    actor: str,
    action: str,
    document_id: Optional[str] = None,
    section_id: Optional[str] = None,
    version_id: Optional[str] = None,
    from_value: Optional[str] = None,
    to_value: Optional[str] = None,
    detail: Optional[Any] = None,
) -> int:
    """Insert a single review event. Returns the new row id."""
    actor_s = (actor or "").strip()
    if not actor_s:
        raise ValueError("actor is required")
    at = datetime.now(timezone.utc).isoformat()
    detail_json = json.dumps(detail, ensure_ascii=False) if detail is not None else None
    cursor = await db.execute(
        """
        INSERT INTO review_events (at, actor, action, document_id, section_id, version_id, from_value, to_value, detail_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (at, actor_s, action, document_id, section_id, version_id, from_value, to_value, detail_json),
    )
    return int(cursor.lastrowid)
