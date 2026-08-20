"""Persisted statute-family and edition identity."""

from __future__ import annotations

import json
import uuid

from backend.database import DatabaseConnection
from backend.services.editions import (
    edition_date_from_name,
    family_key_from_name,
    family_title_from_key,
)


def family_id_for_slug(slug: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"crx:statute-family:{slug}"))


async def persist_inferred_identity(
    db: DatabaseConnection,
    document_id: str,
    name: str,
) -> str:
    slug = family_key_from_name(name)
    family_id = family_id_for_slug(slug)
    edition = edition_date_from_name(name)
    await db.execute(
        """
        INSERT INTO statute_families
            (id, canonical_title, canonical_slug, aliases, created_at)
        VALUES (?, ?, ?, CAST(? AS jsonb), CURRENT_TIMESTAMP::text)
        ON CONFLICT (id) DO UPDATE SET
            aliases = CASE
                WHEN statute_families.aliases @> excluded.aliases THEN statute_families.aliases
                ELSE statute_families.aliases || excluded.aliases
            END
        """,
        (family_id, family_title_from_key(slug), slug, json.dumps([name])),
    )
    await db.execute(
        """
        UPDATE documents SET statute_family_id = ?, display_title = ?, edition_date = ?,
                             identity_status = COALESCE(identity_status, 'inferred')
        WHERE id = ?
        """,
        (family_id, name, str(edition["year"]) if edition["year"] else None, document_id),
    )
    return family_id


async def confirm_identity(
    db: DatabaseConnection,
    document_id: str,
    *,
    family_id: str,
    display_title: str,
    edition_date: str | None,
    amendment_through_date: str | None,
    actor: str,
) -> None:
    async with db.execute("SELECT 1 FROM statute_families WHERE id = ?", (family_id,)) as cur:
        if not await cur.fetchone():
            raise KeyError(family_id)
    await db.execute(
        """
        UPDATE documents SET statute_family_id = ?, display_title = ?, edition_date = ?,
                             amendment_through_date = ?, identity_status = 'confirmed'
        WHERE id = ?
        """,
        (family_id, display_title, edition_date, amendment_through_date, document_id),
    )
    await db.execute(
        "UPDATE statute_families SET confirmed_at = CURRENT_TIMESTAMP::text, confirmed_by = ? WHERE id = ?",
        (actor, family_id),
    )
