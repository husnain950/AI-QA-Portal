"""Section variant tracking across editions.

variant_key = sha256(family_key | section_code | norm_text | html_shape)
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from backend.database import DatabaseConnection, DatabaseRow
from backend.services import review_state
from backend.services.clock import iso_now as _now
from backend.services.detectors import edition_date, family_key
from backend.services.textnorm import html_shape as _html_shape
from backend.services.textnorm import norm_text as _norm_text


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


def _raw_sha(value: str) -> str:
    return hashlib.sha256((value or "").encode()).hexdigest()


async def _footnote_sha(db: DatabaseConnection, section_id: str) -> str:
    async with db.execute(
        """
        SELECT marker, page, text, html_content FROM footnotes
        WHERE section_id = ? ORDER BY page NULLS LAST, marker, id
        """,
        (section_id,),
    ) as cursor:
        rows = [dict(row) for row in await cursor.fetchall()]
    return _raw_sha(json.dumps(rows, sort_keys=True, ensure_ascii=False))


async def _section_rows(
    db: DatabaseConnection,
    document_id: Optional[str] = None,
) -> List[DatabaseRow]:
    query = """
        SELECT s.id, s.document_id, s.section_code, s.plain_text, s.html_content,
               d.name AS doc_name
        FROM sections s
        JOIN documents d ON d.id = s.document_id
    """
    params: List[Any] = []
    if document_id:
        query += " WHERE s.document_id = ?"
        params.append(document_id)
    async with db.execute(query, params) as cursor:
        return await cursor.fetchall()


async def _insert_variant(db: DatabaseConnection, row: DatabaseRow) -> None:
    fk = family_key(row["doc_name"])
    ed = edition_date(row["doc_name"])
    plain = row["plain_text"] or ""
    html = row["html_content"] or ""
    vk = compute_variant_key(fk, row["section_code"], plain, html)
    await db.execute(
        """
        INSERT INTO section_variants
            (variant_key, section_id, document_id, family_key, section_code,
             edition_date, text_sha, html_sha, html_shape, footnote_sha, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (variant_key, section_id) DO NOTHING
        """,
        (
            vk,
            row["id"],
            row["document_id"],
            fk,
            row["section_code"],
            ed,
            text_sha(plain),
            _raw_sha(html),
            _html_shape(html),
            await _footnote_sha(db, row["id"]),
            _now(),
        ),
    )


async def rebuild_document(
    db: DatabaseConnection, document_id: str
) -> Dict[str, Any]:
    """Reindex one document's variant rows. Does not commit — callers own the txn."""
    await db.execute(
        "DELETE FROM section_variants WHERE document_id = ?",
        (document_id,),
    )
    rows = await _section_rows(db, document_id)
    for row in rows:
        await _insert_variant(db, row)
    return {"inserted": len(rows)}


async def rebuild(db: DatabaseConnection) -> Dict[str, Any]:
    """Rebuild section_variants from current sections + documents."""
    await db.execute("DELETE FROM section_variants;")
    rows = await _section_rows(db)
    for row in rows:
        await _insert_variant(db, row)
    await db.commit()
    return {"inserted": len(rows)}


async def rebuild_if_empty(db: DatabaseConnection) -> Optional[Dict[str, Any]]:
    """Full rebuild when sections exist but the variants table was never filled."""
    async with db.execute("SELECT COUNT(*) FROM sections") as cursor:
        n_sections = int((await cursor.fetchone())[0])
    async with db.execute("SELECT COUNT(*) FROM section_variants") as cursor:
        n_variants = int((await cursor.fetchone())[0])
    if n_sections > 0 and n_variants == 0:
        return await rebuild(db)
    return None


async def get_variants(
    db: DatabaseConnection,
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
    db: DatabaseConnection, variant_key: str
) -> List[Dict[str, Any]]:
    """All sections sharing a variant_key."""
    async with db.execute(
        """
        SELECT sv.*, s.section_heading, s.review_status, s.reviewer_verdict,
               s.effective_status, d.name AS doc_name
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
    db: DatabaseConnection,
    variant_key: str,
    *,
    actor: str,
    min_editions: int = 2,
) -> Dict[str, Any]:
    """Inherit approval only from an explicitly approved, exact-match source."""
    members = await get_variant_detail(db, variant_key)
    if len(members) < min_editions:
        return {"error": f"need >= {min_editions} editions, got {len(members)}"}

    source = next(
        (
            m
            for m in members
            if m["reviewer_verdict"] == "approved" and m["effective_status"] == "approved"
        ),
        None,
    )
    if not source:
        return {"error": "variant requires an explicitly human-approved source"}

    exact_hashes = {
        (m["text_sha"], m["html_sha"], m["footnote_sha"] or "") for m in members
    }
    if len(exact_hashes) != 1:
        return {"error": "variant members do not have identical text, HTML, and footnote hashes"}
    for member in members:
        blockers = await review_state.blocker_reasons(db, member["section_id"])
        # A reviewer verdict of needs_work leaves no blocker row behind, so it has to be
        # read directly — otherwise "this one is wrong" still receives inherited approval.
        if member["reviewer_verdict"] == "needs_work" or member["effective_status"] == "blocked":
            blockers = blockers or ["reviewer_marked_needs_work"]
        if blockers:
            return {
                "error": "variant member has blockers",
                "section_id": member["section_id"],
                "blockers": blockers,
            }

    document_ids = [member["document_id"] for member in members]
    placeholders = ",".join("?" for _ in document_ids)
    async with db.execute(
        f"""
        SELECT d.id AS document_id, v.id AS version_id, v.json_sha256
        FROM documents d
        JOIN document_versions v ON v.document_id = d.id AND v.is_active = TRUE
        WHERE d.id IN ({placeholders})
        """,
        document_ids,
    ) as cursor:
        versions = [dict(row) for row in await cursor.fetchall()]
    if len(versions) != len(set(document_ids)):
        return {"error": "every variant member must have an active version hash"}

    evidence = {
        "policy_version": "v2",
        "variant_key": variant_key,
        "hashes": {
            "text": source["text_sha"],
            "html": source["html_sha"],
            "footnotes": source["footnote_sha"] or "",
        },
        "source_section_id": source["section_id"],
        "recipient_section_ids": [
            m["section_id"] for m in members if m["section_id"] != source["section_id"]
        ],
        "active_versions": versions,
        "approved_by": actor,
    }

    inherited_count = 0
    for m in members:
        if m["section_id"] == source["section_id"]:
            continue
        await db.execute(
            """
            UPDATE sections SET review_status = 'approved_inherited',
                                effective_status = 'approved_inherited',
                                reviewer_verdict = 'pending'
            WHERE id = ?
            """,
            (m["section_id"],),
        )
        await db.execute(
            """
            INSERT INTO approval_inheritance
                (source_id, inheritor_id, variant_key, inherited_at, policy_version, evidence)
            VALUES (?, ?, ?, ?, 'v2', CAST(? AS jsonb))
            ON CONFLICT (source_id, inheritor_id) DO UPDATE
            SET variant_key = excluded.variant_key,
                inherited_at = excluded.inherited_at,
                policy_version = excluded.policy_version,
                evidence = excluded.evidence
            """,
            (
                source["section_id"],
                m["section_id"],
                variant_key,
                _now(),
                json.dumps(evidence, ensure_ascii=False),
            ),
        )
        inherited_count += 1

    for document_id in sorted(set(document_ids)):
        await review_state.refresh_document(db, document_id)
    await db.commit()
    return {
        "source_id": source["section_id"],
        "inherited": inherited_count,
        "policy_version": "v2",
        "evidence": evidence,
    }


async def revoke_variant_approval(
    db: DatabaseConnection, variant_key: str
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
    db: DatabaseConnection,
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
