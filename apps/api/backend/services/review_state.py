"""Single source of truth for reviewer verdicts and effective review state."""

from __future__ import annotations

from typing import Any

from backend.database import DatabaseConnection
from backend.services.parse_quality import deserialize_quality_flags, has_critical_flags

REVIEWER_VERDICTS = frozenset({"pending", "approved", "needs_work"})


async def blocker_reasons(db: DatabaseConnection, section_id: str) -> list[str]:
    reasons: list[str] = []
    async with db.execute(
        "SELECT quality_flags FROM sections WHERE id = ?", (section_id,)
    ) as cursor:
        section = await cursor.fetchone()
    if section is None:
        raise KeyError(section_id)
    if has_critical_flags(deserialize_quality_flags(section["quality_flags"])):
        reasons.append("blocking_quality_flag")

    async with db.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE status = 'open') AS open_count,
          COUNT(*) FILTER (WHERE anchor_status IN ('needs_recheck','orphaned')) AS recheck_count
        FROM annotations WHERE section_id = ?
        """,
        (section_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row["open_count"]:
        reasons.append("open_annotation")
    if row["recheck_count"]:
        reasons.append("annotation_recheck")

    async with db.execute(
        """
        SELECT COUNT(*) FROM footnotes
        WHERE section_id = ? AND review_status IN ('has_issues','needs_work')
        """,
        (section_id,),
    ) as cursor:
        if (await cursor.fetchone())[0]:
            reasons.append("flagged_footnote")

    async with db.execute(
        """
        SELECT COUNT(*) FROM findings
        WHERE section_id = ? AND severity = 'error'
          AND triage IN ('new','parse_bug','source_defect')
        """,
        (section_id,),
    ) as cursor:
        if (await cursor.fetchone())[0]:
            reasons.append("unresolved_error_finding")
    return reasons


async def _valid_inheritance(db: DatabaseConnection, section_id: str) -> bool:
    async with db.execute(
        """
        SELECT 1
        FROM approval_inheritance ai
        JOIN sections source ON source.id = ai.source_id
        JOIN section_variants source_variant
          ON source_variant.section_id = source.id
         AND source_variant.variant_key = ai.variant_key
        JOIN section_variants recipient_variant
          ON recipient_variant.section_id = ai.inheritor_id
         AND recipient_variant.variant_key = ai.variant_key
        WHERE ai.inheritor_id = ?
          AND source.reviewer_verdict = 'approved'
          AND source.effective_status = 'approved'
          AND source_variant.text_sha = recipient_variant.text_sha
          AND source_variant.html_shape = recipient_variant.html_shape
          AND coalesce(source_variant.footnote_sha, '') = coalesce(recipient_variant.footnote_sha, '')
        LIMIT 1
        """,
        (section_id,),
    ) as cursor:
        return await cursor.fetchone() is not None


async def refresh_section(db: DatabaseConnection, section_id: str) -> dict[str, Any]:
    async with db.execute(
        "SELECT document_id, reviewer_verdict, effective_status FROM sections WHERE id = ? FOR UPDATE",
        (section_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        raise KeyError(section_id)
    reasons = await blocker_reasons(db, section_id)
    verdict = row["reviewer_verdict"]
    if reasons or verdict == "needs_work":
        effective = "blocked"
    elif verdict == "approved":
        effective = "approved"
    elif row["effective_status"] == "approved_inherited" and await _valid_inheritance(db, section_id):
        effective = "approved_inherited"
    else:
        effective = "pending"
    legacy = "has_issues" if effective == "blocked" else effective
    await db.execute(
        "UPDATE sections SET effective_status = ?, review_status = ? WHERE id = ?",
        (effective, legacy, section_id),
    )
    document_status = await refresh_document(db, row["document_id"])
    return {
        "section_id": section_id,
        "reviewer_verdict": verdict,
        "effective_status": effective,
        "review_status": legacy,
        "blockers": reasons,
        "document_status": document_status,
    }


async def refresh_document(db: DatabaseConnection, document_id: str) -> str:
    async with db.execute(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE effective_status = 'pending') AS pending,
               COUNT(*) FILTER (WHERE effective_status = 'blocked') AS blocked,
               COUNT(*) FILTER (WHERE effective_status IN ('approved','approved_inherited')) AS approved
        FROM sections WHERE document_id = ?
        """,
        (document_id,),
    ) as cursor:
        row = await cursor.fetchone()
    total = int(row["total"] or 0)
    if row["blocked"]:
        status = "blocked"
    elif total and int(row["approved"] or 0) == total:
        status = "approved"
    elif row["approved"]:
        status = "in_progress"
    else:
        status = "pending"
    await db.execute("UPDATE documents SET status = ? WHERE id = ?", (status, document_id))
    return status


async def set_verdict(
    db: DatabaseConnection, section_id: str, verdict: str
) -> dict[str, Any]:
    if verdict not in REVIEWER_VERDICTS:
        raise ValueError(f"reviewer verdict must be one of {sorted(REVIEWER_VERDICTS)}")
    await db.execute(
        "UPDATE sections SET reviewer_verdict = ? WHERE id = ?", (verdict, section_id)
    )
    return await refresh_section(db, section_id)


async def revoke_document_approval(db: DatabaseConnection, document_id: str) -> None:
    """Content changes invalidate approval inheritance and attribution-only sign-off."""
    await db.execute(
        """
        UPDATE sections SET reviewer_verdict = 'pending', effective_status = 'pending',
                            review_status = 'pending'
        WHERE document_id = ?
        """,
        (document_id,),
    )
    await db.execute(
        "DELETE FROM approval_inheritance WHERE inheritor_id IN (SELECT id FROM sections WHERE document_id = ?)",
        (document_id,),
    )
    await db.execute(
        """
        UPDATE documents SET status = 'pending', signoff_stage = 'draft',
                             signoff_reviewed_by = NULL, signoff_legal_by = NULL,
                             row_revision = row_revision + 1
        WHERE id = ?
        """,
        (document_id,),
    )
