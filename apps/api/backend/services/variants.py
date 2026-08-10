"""Section variant tracking across editions.

variant_key = sha256(family_key | section_code | norm_text | html_shape)
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Dict, List, Optional

import aiosqlite

from backend.services.detectors import edition_date, family_key


def _norm_text(text: str) -> str:
    """NFKC + whitespace collapse, no casefolding."""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def _html_shape(html: str) -> str:
    """SHA256 of ordered block-tag sequence."""
    tags = re.findall(
        r"<(/?(?:p|div|table|tr|td|th|ul|ol|li|h[1-6]|blockquote|pre|section|article|aside|nav|header|footer|figure|figcaption|details|summary|dl|dt|dd))\b",
        html or "",
        re.IGNORECASE,
    )
    shape_str = "|".join(t.lower() for t in tags)
    return hashlib.sha256(shape_str.encode()).hexdigest()


def compute_variant_key(
    fam_key: str,
    section_code: str,
    plain_text: str,
    html_content: str,
) -> str:
    norm = _norm_text(plain_text)
    shape = _html_shape(html_content)
    raw = f"{fam_key}|{section_code}|{norm}|{shape}"
    return hashlib.sha256(raw.encode()).hexdigest()


def text_sha(plain_text: str) -> str:
    return hashlib.sha256(_norm_text(plain_text).encode()).hexdigest()


async def rebuild(db: aiosqlite.Connection) -> Dict[str, Any]:
    """Rebuild section_variants from current sections + documents."""
    await db.execute("DELETE FROM section_variants;")

    async with db.execute(
        """
        SELECT s.id, s.document_id, s.section_code, s.plain_text, s.html_content,
               d.name AS doc_name
        FROM sections s
        JOIN documents d ON d.id = s.document_id
        """
    ) as cursor:
        rows = await cursor.fetchall()

    inserted = 0
    for row in rows:
        fk = family_key(row["doc_name"])
        ed = edition_date(row["doc_name"])
        plain = row["plain_text"] or ""
        html = row["html_content"] or ""

        vk = compute_variant_key(fk, row["section_code"], plain, html)
        t_sha = text_sha(plain)
        h_shape = _html_shape(html)

        await db.execute(
            """
            INSERT OR IGNORE INTO section_variants
                (variant_key, section_id, document_id, family_key, section_code,
                 edition_date, text_sha, html_shape)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (vk, row["id"], row["document_id"], fk, row["section_code"],
             ed, t_sha, h_shape),
        )
        inserted += 1

    await db.commit()
    return {"inserted": inserted}


async def get_variants(
    db: aiosqlite.Connection,
    *,
    family: Optional[str] = None,
    section_code: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """List variant groups with optional family/code filter."""
    query = """
        SELECT variant_key, family_key, section_code,
               COUNT(*) AS edition_count,
               MIN(edition_date) AS first_edition,
               MAX(edition_date) AS last_edition
        FROM section_variants
    """
    conditions: List[str] = []
    params: List[Any] = []
    if family:
        conditions.append("family_key = ?")
        params.append(family.lower())
    if section_code:
        conditions.append("section_code = ?")
        params.append(section_code)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " GROUP BY variant_key ORDER BY family_key, section_code"
    query += f" LIMIT {limit} OFFSET {offset}"

    async with db.execute(query, params) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_variant_detail(
    db: aiosqlite.Connection, variant_key: str
) -> List[Dict[str, Any]]:
    """All sections sharing a variant_key."""
    async with db.execute(
        """
        SELECT sv.*, s.section_heading, s.review_status, d.name AS doc_name
        FROM section_variants sv
        JOIN sections s ON s.id = sv.section_id
        JOIN documents d ON d.id = sv.document_id
        WHERE sv.variant_key = ?
        ORDER BY sv.edition_date
        """,
        (variant_key,),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def approve_variant(
    db: aiosqlite.Connection,
    variant_key: str,
    *,
    actor: str,
    min_editions: int = 3,
) -> Dict[str, Any]:
    """Approve a variant group: source gets 'approved', others get 'approved_inherited'."""
    members = await get_variant_detail(db, variant_key)
    if len(members) < min_editions:
        return {"error": f"need >= {min_editions} editions, got {len(members)}"}

    source = None
    for m in members:
        if m["review_status"] == "approved":
            source = m
            break
    if not source:
        source = members[0]
        await db.execute(
            "UPDATE sections SET review_status = 'approved' WHERE id = ?",
            (source["section_id"],),
        )

    inherited_count = 0
    for m in members:
        if m["section_id"] == source["section_id"]:
            continue
        await db.execute(
            "UPDATE sections SET review_status = 'approved_inherited' WHERE id = ?",
            (m["section_id"],),
        )
        await db.execute(
            """
            INSERT OR REPLACE INTO approval_inheritance
                (source_id, inheritor_id, variant_key)
            VALUES (?, ?, ?)
            """,
            (source["section_id"], m["section_id"], variant_key),
        )
        inherited_count += 1

    await db.commit()
    return {"source_id": source["section_id"], "inherited": inherited_count}


async def revoke_variant_approval(
    db: aiosqlite.Connection, variant_key: str
) -> Dict[str, Any]:
    """Remove inheritance for a variant group."""
    async with db.execute(
        "SELECT inheritor_id FROM approval_inheritance WHERE variant_key = ?",
        (variant_key,),
    ) as cursor:
        rows = await cursor.fetchall()

    revoked = 0
    for row in rows:
        await db.execute(
            "DELETE FROM approval_inheritance WHERE variant_key = ? AND inheritor_id = ?",
            (variant_key, row["inheritor_id"]),
        )
        revoked += 1

    await db.commit()
    return {"revoked": revoked}


async def timeline(
    db: aiosqlite.Connection,
    *,
    family: str,
    section_code: str,
) -> List[Dict[str, Any]]:
    """Chronological timeline of a section across editions."""
    async with db.execute(
        """
        SELECT sv.variant_key, sv.section_id, sv.document_id, sv.edition_date,
               sv.text_sha, sv.html_shape,
               s.section_heading, s.review_status, s.plain_text,
               d.name AS doc_name
        FROM section_variants sv
        JOIN sections s ON s.id = sv.section_id
        JOIN documents d ON d.id = sv.document_id
        WHERE sv.family_key = ? AND sv.section_code = ?
        ORDER BY sv.edition_date
        """,
        (family.lower(), section_code),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]
