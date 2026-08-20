"""Stable source-page and leaf-occurrence identity across version revisions."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from backend.database import DatabaseConnection


def _id(*parts: object) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "crx:" + ":".join(str(part) for part in parts)))


async def record_version_revisions(
    db: DatabaseConnection,
    document_id: str,
    version_id: str,
) -> dict[str, int]:
    async with db.execute(
        "SELECT total_pages FROM documents WHERE id = ?", (document_id,)
    ) as cur:
        total_pages = int((await cur.fetchone())[0] or 0)
    for page in range(1, total_pages + 1):
        await db.execute(
            """
            INSERT INTO source_pages (id, document_id, page_number)
            VALUES (?, ?, ?) ON CONFLICT (document_id, page_number) DO NOTHING
            """,
            (_id("page", document_id, page), document_id, page),
        )

    async with db.execute(
        """
        SELECT id, source_key, plain_text, html_content, start_page, end_page, sort_order
        FROM sections WHERE document_id = ? ORDER BY sort_order
        """,
        (document_id,),
    ) as cur:
        sections = await cur.fetchall()
    created = matched = ambiguous = 0
    timestamp = datetime.now(timezone.utc).isoformat()
    for section in sections:
        digest = hashlib.sha256(
            ((section["plain_text"] or "") + "\0" + (section["html_content"] or "")).encode()
        ).hexdigest()
        occurrence_id = None
        if section["source_key"]:
            async with db.execute(
                """
                SELECT id FROM leaf_occurrences
                WHERE document_id = ? AND source_key = ? AND retired_at IS NULL
                """,
                (document_id, section["source_key"]),
            ) as cur:
                existing = await cur.fetchall()
            if len(existing) == 1:
                occurrence_id = existing[0]["id"]
                matched += 1
        if occurrence_id is None:
            async with db.execute(
                """
                SELECT DISTINCT lr.occurrence_id
                FROM leaf_revisions lr
                JOIN leaf_occurrences lo ON lo.id = lr.occurrence_id
                WHERE lo.document_id = ? AND lr.start_page IS NOT DISTINCT FROM ?
                  AND lr.end_page IS NOT DISTINCT FROM ? AND lr.content_sha256 = ?
                  AND lr.sort_order BETWEEN ? AND ?
                """,
                (
                    document_id,
                    section["start_page"],
                    section["end_page"],
                    digest,
                    max(0, section["sort_order"] - 1),
                    section["sort_order"] + 1,
                ),
            ) as cur:
                candidates = await cur.fetchall()
            if len(candidates) == 1:
                occurrence_id = candidates[0]["occurrence_id"]
                matched += 1
            else:
                ambiguous += int(len(candidates) > 1)
                occurrence_id = str(uuid.uuid4())
                await db.execute(
                    """
                    INSERT INTO leaf_occurrences (id, document_id, source_key, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (occurrence_id, document_id, section["source_key"], timestamp),
                )
                created += 1
        await db.execute(
            "UPDATE sections SET occurrence_id = ? WHERE id = ?",
            (occurrence_id, section["id"]),
        )
        await db.execute(
            """
            INSERT INTO leaf_revisions
                (id, occurrence_id, version_id, section_id, content_sha256,
                 start_page, end_page, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (occurrence_id, version_id) DO NOTHING
            """,
            (
                _id("revision", occurrence_id, version_id),
                occurrence_id,
                version_id,
                section["id"],
                digest,
                section["start_page"],
                section["end_page"],
                section["sort_order"],
            ),
        )
    return {"created": created, "matched": matched, "ambiguous": ambiguous}
