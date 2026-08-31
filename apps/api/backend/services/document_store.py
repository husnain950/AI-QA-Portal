import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from backend.database import DatabaseConnection
from backend.services import anchoring
from backend.services.parse_quality import (
    has_critical_flags,
    serialize_quality_flags,
)

SUPERSEDE = "supersede"
STRICT = "strict"


@dataclass
class ReviewConflict(Exception):
    details: List[str]

    def __str__(self) -> str:
        return "; ".join(self.details)


@dataclass
class Carryover:
    """What happened to human QA state when a new parse replaced the old one.

    This is the report that replaced the old refusal. Ingesting a pipeline fix must
    always be possible; what it cost in review state is recorded here, stored on the
    version, and shown to the reviewer -- never silently dropped.
    """

    sections_added: int = 0
    sections_removed: int = 0
    sections_changed: int = 0
    footnotes_removed: int = 0
    reanchored: int = 0
    needs_recheck: int = 0
    orphaned: int = 0
    approvals_reset: int = 0
    approvals_lost: int = 0
    inherited_revoked: int = 0
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "sections_added": self.sections_added,
            "sections_removed": self.sections_removed,
            "sections_changed": self.sections_changed,
            "footnotes_removed": self.footnotes_removed,
            "reanchored": self.reanchored,
            "needs_recheck": self.needs_recheck,
            "orphaned": self.orphaned,
            "approvals_reset": self.approvals_reset,
            "approvals_lost": self.approvals_lost,
            "inherited_revoked": self.inherited_revoked,
            "notes": self.notes[:50],
        }


def _legacy_section_key(section: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        section.get("sort_order"),
        section.get("chapter_code") or "",
        section.get("part_code") or "",
        section.get("division_code") or "",
        section.get("section_code") or "",
    )


def _carries_human_qa_state(row) -> bool:
    """True when dropping this row would discard something a PERSON did.

    ``has_issues`` cannot count. `parse_json_document` assigns it on every parse from
    `assess_section_quality`, so treating it as QA state means an upstream structural
    fix can never be ingested: re-syncing the corrected Acts-Discovery corpus refused
    64 of 93 documents on rows the parser itself had flagged moments earlier, which
    would have left reviewers permanently on the defective parse.

    Human intent is an explicit approval (including inherited), or an annotation.
    Both are still protected.
    """
    return row["review_status"] in ("approved", "approved_inherited") or bool(
        row["annotation_count"]
    )

async def _load_annotations(
    db: DatabaseConnection, document_id: str
) -> Tuple[Dict[str, List[dict]], Dict[str, List[dict]]]:
    """Live annotations for a document, grouped by section and by footnote.

    Footnote-scoped offsets index the footnote's own rendered text, not the section's,
    so the two groups are re-anchored against different strings.
    """
    async with db.execute(
        """
        SELECT id, section_id, footnote_id, highlighted_text, start_offset,
               end_offset, context_before, context_after, anchor_status, status
        FROM annotations
        WHERE document_id = ? AND section_id IS NOT NULL
        """,
        (document_id,),
    ) as cursor:
        rows = [dict(row) for row in await cursor.fetchall()]

    by_section: Dict[str, List[dict]] = {}
    by_footnote: Dict[str, List[dict]] = {}
    for row in rows:
        if row["footnote_id"]:
            by_footnote.setdefault(row["footnote_id"], []).append(row)
        else:
            by_section.setdefault(row["section_id"], []).append(row)
    return by_section, by_footnote


async def _reanchor_all(
    db: DatabaseConnection,
    annotations: List[dict],
    new_text: str,
    report: Carryover,
    label: str,
) -> None:
    for row in annotations:
        anchor = anchoring.reanchor(
            new_text,
            highlighted_text=row["highlighted_text"],
            start_offset=row["start_offset"],
            end_offset=row["end_offset"],
            context_before=row["context_before"],
            context_after=row["context_after"],
        )
        await db.execute(
            """
            UPDATE annotations
            SET start_offset = ?, end_offset = ?, anchor_status = ?
            WHERE id = ?
            """,
            (anchor.start, anchor.end, anchor.status, row["id"]),
        )
        if anchor.status == anchoring.ANCHORED:
            report.reanchored += 1
        else:
            report.needs_recheck += 1
            report.notes.append(f"{label}: {anchor.reason}")


async def _orphan_annotations(
    db: DatabaseConnection,
    annotations: List[dict],
    context: Dict[str, Any],
    report: Carryover,
) -> None:
    """Detach findings from a row the new parse dropped, keeping the evidence."""
    for row in annotations:
        await db.execute(
            """
            UPDATE annotations
            SET section_id = NULL, footnote_id = NULL,
                anchor_status = ?, orphan_context = ?
            WHERE id = ?
            """,
            (anchoring.ORPHANED, json.dumps(context, ensure_ascii=False), row["id"]),
        )
        report.orphaned += 1
    if annotations:
        report.notes.append(
            f"{context.get('label', 'row')} was removed; "
            f"{len(annotations)} finding(s) kept as orphaned"
        )


async def apply_parsed_document(
    db: DatabaseConnection,
    document_id: str,
    sections: List[Dict[str, Any]],
    footnotes: List[Dict[str, Any]],
    *,
    mode: str = SUPERSEDE,
) -> Dict[str, Any]:
    """Upsert parsed content while preserving valid QA state.

    Stable source keys are the primary identity. Existing databases are
    backfilled once through a unique sort-order/hierarchy fallback.

    ``mode='supersede'`` (the default) always ingests: annotations on changed leaves are
    re-anchored, annotations on dropped leaves are orphaned with a snapshot, and the
    cost is returned under ``carryover``. ``mode='strict'`` keeps the original
    behaviour and raises :class:`ReviewConflict` instead -- it is for CI and for
    ``sync_acts --strict``, where refusing is the point.
    """
    if mode not in (SUPERSEDE, STRICT):
        raise ValueError(f"unknown mode: {mode}")
    report = Carryover()
    ann_by_section, ann_by_footnote = await _load_annotations(db, document_id)

    async with db.execute(
        """
        SELECT
            s.*,
            COUNT(a.id) AS annotation_count
        FROM sections s
        LEFT JOIN annotations a ON a.section_id = s.id
        WHERE s.document_id = ?
        GROUP BY s.id
        """,
        (document_id,),
    ) as cursor:
        existing_sections = [dict(row) for row in await cursor.fetchall()]

    # Identity, most structural first. `node_key` survives a leaf being inserted
    # above it; `source_key` is positional and does not; the legacy tuple is the
    # one-time backfill for rows that predate `source_key` entirely.
    by_node_key = {
        row["node_key"]: row
        for row in existing_sections
        if row.get("node_key")
    }
    by_source_key = {
        row["source_key"]: row
        for row in existing_sections
        if row.get("source_key")
    }
    by_legacy_key = {
        _legacy_section_key(row): row for row in existing_sections
    }
    existing_section_ids = {row["id"] for row in existing_sections}

    resolved_sections: List[Tuple[Dict[str, Any], str, str, bool]] = []
    parsed_to_final: Dict[str, str] = {}
    used_section_ids = set()
    conflicts: List[str] = []
    reset_sections = 0
    inheritance_revoke_ids: List[str] = []

    # One identity scheme per document, never a mix.
    #
    # The positional fallback is a MIGRATION affordance, not a second chance: while no
    # stored row carries a `node_key` yet, matching by `source_key` is what lets the
    # first ingest after the column landed recognise its own rows and backfill them
    # without re-minting a single id. The moment any row has one, falling back is
    # actively wrong -- a genuinely new leaf inserted at position 0 would match the
    # row of the leaf that used to be there and inherit its approval, while that leaf
    # was written as new. Measured on a three-leaf fixture: the inserted leaf took
    # section 2's row, section 2 became a fresh row, and one approval moved to the
    # wrong provision.
    migrating = not by_node_key
    for section in sections:
        existing = None
        node_key = section.get("node_key")
        if node_key:
            existing = by_node_key.get(node_key)
        if existing is None and (migrating or not node_key):
            # A leaf with no `node_key` is either the synthesised preamble or a
            # document converted before the contract; `source_key` is all it has.
            existing = by_source_key.get(section["source_key"])
            if existing is None:
                existing = by_legacy_key.get(_legacy_section_key(section))
        # Two lookups can still land on one row -- during the migration ingest a
        # leaf can match by node_key while another matches the same row by
        # source_key. The second claimant is new, or both would be written to one id
        # and the first would simply vanish.
        if existing is not None and existing["id"] in used_section_ids:
            existing = None

        final_id = existing["id"] if existing else section["id"]
        review_status = existing["review_status"] if existing else "pending"
        content_changed = False

        if existing:
            content_changed = (
                (existing.get("html_content") or "")
                != (section.get("html_content") or "")
                or (existing.get("plain_text") or "")
                != (section.get("plain_text") or "")
            )
            if content_changed:
                report.sections_changed += 1
            if content_changed and existing["annotation_count"] and mode == STRICT:
                conflicts.append(
                    f"{section['source_key']} changed with "
                    f"{existing['annotation_count']} annotation(s)"
                )
            elif content_changed and review_status != "pending":
                # The text this judgement was made about no longer exists.
                if review_status in ("approved", "approved_inherited"):
                    report.approvals_reset += 1
                review_status = "pending"
                reset_sections += 1
                inheritance_revoke_ids.append(existing["id"])
        else:
            # Fresh insert: respect parser auto-flag (pending → has_issues).
            review_status = section.get("review_status") or "pending"
            report.sections_added += 1

        # Critical parse-quality flags elevate pending only — never clobber
        # approved / has_issues / annotated leaves' review status.
        if has_critical_flags(section.get("quality_flags")) and review_status == "pending":
            review_status = "has_issues"

        # A leaf that still carries an open finding stays flagged, whatever else changed.
        if review_status == "pending" and any(
            row["status"] == "open" for row in ann_by_section.get(final_id, ())
        ):
            review_status = "has_issues"

        parsed_to_final[section["id"]] = final_id
        used_section_ids.add(final_id)
        resolved_sections.append((section, final_id, review_status, content_changed))

    # Revoke inheritance for changed leaves (as inheritor or as source).
    for sid in inheritance_revoke_ids:
        cur = await db.execute(
            "DELETE FROM approval_inheritance WHERE inheritor_id = ? OR source_id = ?",
            (sid, sid),
        )
        if cur.rowcount and cur.rowcount > 0:
            report.inherited_revoked += int(cur.rowcount)

    removed_sections = [
        row for row in existing_sections if row["id"] not in used_section_ids
    ]
    report.sections_removed = len(removed_sections)
    for row in removed_sections:
        if _carries_human_qa_state(row) and mode == STRICT:
            conflicts.append(
                f"{row.get('source_key') or row['id']} was removed with QA state"
            )
        elif row["review_status"] in ("approved", "approved_inherited"):
            report.approvals_lost += 1
            if row["review_status"] == "approved_inherited":
                report.inherited_revoked += 1

    async with db.execute(
        """
        SELECT
            f.*,
            COUNT(a.id) AS annotation_count
        FROM footnotes f
        JOIN sections s ON s.id = f.section_id
        LEFT JOIN annotations a ON a.footnote_id = f.id
        WHERE s.document_id = ?
        GROUP BY f.id
        """,
        (document_id,),
    ) as cursor:
        existing_footnotes = [dict(row) for row in await cursor.fetchall()]

    footnotes_by_key = {
        (row["section_id"], row["marker"]): row
        for row in existing_footnotes
    }
    resolved_footnotes: List[Tuple[Dict[str, Any], str, str, str, bool]] = []
    used_footnote_ids = set()

    for footnote in footnotes:
        final_section_id = parsed_to_final.get(footnote["section_id"])
        if not final_section_id:
            continue
        existing = footnotes_by_key.get(
            (final_section_id, footnote["marker"])
        )
        final_id = existing["id"] if existing else footnote["id"]
        review_status = existing["review_status"] if existing else "pending"
        content_changed = False

        if existing:
            content_changed = (
                (existing.get("text") or "") != (footnote.get("text") or "")
                or (existing.get("html_content") or "")
                != (footnote.get("html_content") or "")
            )
            if content_changed and existing["annotation_count"] and mode == STRICT:
                conflicts.append(
                    f"footnote {footnote['marker']} changed with annotation(s)"
                )
            elif content_changed and review_status != "pending":
                review_status = "pending"

        used_footnote_ids.add(final_id)
        resolved_footnotes.append(
            (footnote, final_id, final_section_id, review_status, content_changed)
        )

    removed_footnotes = [
        row
        for row in existing_footnotes
        if row["id"] not in used_footnote_ids
    ]
    report.footnotes_removed = len(removed_footnotes)
    for row in removed_footnotes:
        if _carries_human_qa_state(row) and mode == STRICT:
            conflicts.append(
                f"footnote {row['marker']} was removed with QA state"
            )

    if conflicts:
        raise ReviewConflict(conflicts)

    # Carry findings across before the rows they point at are rewritten or dropped.
    for section, final_id, _status, changed in resolved_sections:
        if changed and ann_by_section.get(final_id):
            await _reanchor_all(
                db,
                ann_by_section[final_id],
                anchoring.container_text(section.get("html_content")),
                report,
                f"section {section.get('section_code') or section['source_key']}",
            )
    for footnote, final_id, _sid, _status, changed in resolved_footnotes:
        if changed and ann_by_footnote.get(final_id):
            await _reanchor_all(
                db,
                ann_by_footnote[final_id],
                anchoring.container_text(footnote.get("html_content"))
                or (footnote.get("text") or ""),
                report,
                f"footnote {footnote['marker']}",
            )
    for row in removed_sections:
        await _orphan_annotations(
            db,
            ann_by_section.get(row["id"], []),
            {
                "label": f"section {row.get('section_code') or ''}".strip(),
                "source_key": row.get("source_key"),
                "section_code": row.get("section_code"),
                "section_heading": row.get("section_heading"),
                "plain_text": (row.get("plain_text") or "")[:4000],
            },
            report,
        )
    for row in removed_footnotes:
        await _orphan_annotations(
            db,
            ann_by_footnote.get(row["id"], []),
            {
                "label": f"footnote {row.get('marker')}",
                "marker": row.get("marker"),
                "page": row.get("page"),
                "plain_text": (row.get("text") or "")[:4000],
            },
            report,
        )

    # Release both identity keys before rewriting any of them.
    #
    # `uq_sections_source` and `uq_sections_node_key` are unique per document, and the
    # rows are updated one at a time. Once leaves are matched STRUCTURALLY, a leaf that
    # kept its identity can still move position, so its new `source_key` is one that
    # the row beside it is still holding -- the update collides with an index entry
    # that is about to be rewritten anyway. Inserting a single leaf at the top of a
    # chapter reproduced it (IntegrityError on `uq_sections_source`).
    #
    # A Postgres unique INDEX cannot be deferred and a partial unique CONSTRAINT does
    # not exist, so the keys are cleared first and written back below, inside the same
    # transaction. A rollback restores them with everything else.
    await db.execute(
        "UPDATE sections SET source_key = NULL, node_key = NULL WHERE document_id = ?",
        (document_id,),
    )

    for section, final_id, review_status, changed in resolved_sections:
        quality_flags_json = serialize_quality_flags(section.get("quality_flags"))
        effective_status = "blocked" if review_status == "has_issues" else review_status
        reviewer_verdict = "pending"
        if not changed and final_id in existing_section_ids:
            existing_row = next(row for row in existing_sections if row["id"] == final_id)
            reviewer_verdict = existing_row.get("reviewer_verdict") or (
                "approved" if review_status == "approved" else "pending"
            )
        diagnostics_json = json.dumps(section.get("sanitizer_diagnostics") or [])
        if final_id in existing_section_ids:
            await db.execute(
                """
                UPDATE sections SET
                    chapter_code = ?, chapter_heading = ?,
                    part_code = ?, part_heading = ?,
                    division_code = ?, division_heading = ?,
                    section_code = ?, section_heading = ?,
                    start_page = ?, end_page = ?,
                    html_content = ?, plain_text = ?,
                    sort_order = ?, review_status = ?, source_key = ?,
                    node_key = ?,
                    quality_flags = ?, hierarchy_kind = ?, reviewer_verdict = ?,
                    effective_status = ?, sanitizer_version = ?, sanitized_changed = ?,
                    sanitizer_diagnostics = CAST(? AS jsonb)
                WHERE id = ?
                """,
                (
                    section["chapter_code"],
                    section["chapter_heading"],
                    section["part_code"],
                    section["part_heading"],
                    section["division_code"],
                    section["division_heading"],
                    section["section_code"],
                    section["section_heading"],
                    section["start_page"],
                    section["end_page"],
                    section["html_content"],
                    section["plain_text"],
                    section["sort_order"],
                    review_status,
                    section["source_key"],
                    # Backfilled here on the first ingest after the column landed:
                    # the row was matched by source_key and now carries the key the
                    # NEXT ingest will match it by.
                    section.get("node_key"),
                    quality_flags_json,
                    section.get("hierarchy_kind"),
                    reviewer_verdict,
                    effective_status,
                    section.get("sanitizer_version"),
                    bool(section.get("sanitized_changed")),
                    diagnostics_json,
                    final_id,
                ),
            )
        else:
            await db.execute(
                """
                INSERT INTO sections (
                    id, document_id, chapter_code, chapter_heading,
                    part_code, part_heading, division_code, division_heading,
                    section_code, section_heading, start_page, end_page,
                    html_content, plain_text, sort_order, review_status,
                    source_key, node_key, quality_flags, hierarchy_kind,
                    reviewer_verdict,
                    effective_status, sanitizer_version, sanitized_changed,
                    sanitizer_diagnostics
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, CAST(? AS jsonb))
                """,
                (
                    final_id,
                    document_id,
                    section["chapter_code"],
                    section["chapter_heading"],
                    section["part_code"],
                    section["part_heading"],
                    section["division_code"],
                    section["division_heading"],
                    section["section_code"],
                    section["section_heading"],
                    section["start_page"],
                    section["end_page"],
                    section["html_content"],
                    section["plain_text"],
                    section["sort_order"],
                    review_status,
                    section["source_key"],
                    section.get("node_key"),
                    quality_flags_json,
                    section.get("hierarchy_kind"),
                    reviewer_verdict,
                    effective_status,
                    section.get("sanitizer_version"),
                    bool(section.get("sanitized_changed")),
                    diagnostics_json,
                ),
            )

    existing_footnote_ids = {row["id"] for row in existing_footnotes}
    for footnote, final_id, final_section_id, review_status, _changed in resolved_footnotes:
        footnote_diagnostics = json.dumps(footnote.get("sanitizer_diagnostics") or [])
        if final_id in existing_footnote_ids:
            await db.execute(
                """
                UPDATE footnotes SET
                    section_id = ?, marker = ?, page = ?, text = ?,
                    html_content = ?, review_status = ?, sanitizer_version = ?,
                    sanitized_changed = ?, sanitizer_diagnostics = CAST(? AS jsonb)
                WHERE id = ?
                """,
                (
                    final_section_id,
                    footnote["marker"],
                    footnote["page"],
                    footnote["text"],
                    footnote.get("html_content", ""),
                    review_status,
                    footnote.get("sanitizer_version"),
                    bool(footnote.get("sanitized_changed")),
                    footnote_diagnostics,
                    final_id,
                ),
            )
        else:
            await db.execute(
                """
                INSERT INTO footnotes (
                    id, section_id, marker, page, text, html_content,
                    review_status, sanitizer_version, sanitized_changed,
                    sanitizer_diagnostics
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb))
                """,
                (
                    final_id,
                    final_section_id,
                    footnote["marker"],
                    footnote["page"],
                    footnote["text"],
                    footnote.get("html_content", ""),
                    review_status,
                    footnote.get("sanitizer_version"),
                    bool(footnote.get("sanitized_changed")),
                    footnote_diagnostics,
                ),
            )

    for row in removed_footnotes:
        await db.execute("DELETE FROM footnotes WHERE id = ?", (row["id"],))
    for row in removed_sections:
        await db.execute("DELETE FROM sections WHERE id = ?", (row["id"],))

    # Record audit events for status resets during sync
    if reset_sections:
        from backend.services import events

        await events.record(
            db,
            actor="sync_acts",
            action="sync_status_reset",
            document_id=document_id,
            detail={
                "reset_sections": reset_sections,
                "inherited_revoked": report.inherited_revoked,
            },
        )

    async with db.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN review_status = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN review_status = 'approved' THEN 1 ELSE 0 END) AS approved,
            SUM(CASE WHEN review_status = 'has_issues' THEN 1 ELSE 0 END) AS has_issues
        FROM sections
        WHERE document_id = ?
        """,
        (document_id,),
    ) as cursor:
        row = await cursor.fetchone()

    total = int(row["total"] or 0)
    pending = int(row["pending"] or 0)
    return {
        "total": total,
        "pending": pending,
        "approved": int(row["approved"] or 0),
        "has_issues": int(row["has_issues"] or 0),
        "reviewed": total - pending,
        "reset_sections": reset_sections,
        "carryover": report.as_dict(),
    }


def document_status(stats: Dict[str, int]) -> str:
    if stats["total"] == 0 or stats["pending"] == stats["total"]:
        return "pending"
    if stats.get("has_issues", 0):
        return "blocked"
    if stats["pending"] == 0:
        return "approved"
    return "in_progress"
