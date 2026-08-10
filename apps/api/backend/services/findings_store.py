"""Findings store — upsert and lifecycle management for detector findings."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

from backend.services.detectors import DETECTOR_VERSION, Finding
from backend.services.disposition import normalize_finding_triage

logger = logging.getLogger(__name__)


async def upsert_findings(
    db: aiosqlite.Connection,
    findings: List[Tuple[str, str, Finding]],
    *,
    run_started_at: Optional[str] = None,
) -> Dict[str, int]:
    """Upsert findings without touching triage columns on existing rows.

    Returns counts of inserted and refreshed rows.
    """
    now = run_started_at or datetime.now(timezone.utc).isoformat()
    inserted = 0
    refreshed = 0

    for section_id, document_id, finding in findings:
        detail_json = json.dumps(finding.detail, ensure_ascii=False) if finding.detail else None
        async with db.execute(
            """
            SELECT id, triage FROM findings
            WHERE section_id = ? AND detector = ? AND fingerprint = ?
            """,
            (section_id, finding.code, finding.fingerprint),
        ) as cursor:
            existing = await cursor.fetchone()

        if existing:
            await db.execute(
                """
                UPDATE findings
                SET last_seen_at = ?, score = ?, severity = ?,
                    detector_version = ?, detail_json = ?
                WHERE id = ?
                """,
                (now, finding.score, finding.severity, DETECTOR_VERSION, detail_json, existing["id"]),
            )
            refreshed += 1
        else:
            await db.execute(
                """
                INSERT INTO findings
                    (section_id, document_id, detector, detector_version,
                     fingerprint, severity, score, triage,
                     first_seen_at, last_seen_at, detail_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?)
                """,
                (
                    section_id, document_id, finding.code, DETECTOR_VERSION,
                    finding.fingerprint, finding.severity, finding.score,
                    now, now, detail_json,
                ),
            )
            inserted += 1

    return {"inserted": inserted, "refreshed": refreshed}


async def close_stale(
    db: aiosqlite.Connection,
    run_started_at: str,
    *,
    detector: Optional[str] = None,
) -> int:
    """Mark findings not seen in the latest run as fixed.

    Only closes findings with triage='new' (human-triaged findings are preserved).
    """
    query = """
        UPDATE findings
        SET triage = 'fixed'
        WHERE triage = 'new' AND last_seen_at < ?
    """
    params: List[Any] = [run_started_at]
    if detector:
        query += " AND detector = ?"
        params.append(detector)

    async with db.execute(query, params) as cursor:
        return cursor.rowcount


async def triage_finding(
    db: aiosqlite.Connection,
    finding_id: int,
    *,
    triage: str,
    note: Optional[str] = None,
    actor: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Set triage status on a finding."""
    triage = normalize_finding_triage(triage)
    now = datetime.now(timezone.utc).isoformat()

    async with db.execute(
        "SELECT * FROM findings WHERE id = ?", (finding_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if not row:
        return None

    await db.execute(
        """
        UPDATE findings
        SET triage = ?, triage_note = ?, triaged_by = ?, triaged_at = ?
        WHERE id = ?
        """,
        (triage, note, actor, now, finding_id),
    )
    return {"id": finding_id, "triage": triage}


async def list_findings(
    db: aiosqlite.Connection,
    *,
    triage: Optional[str] = None,
    detector: Optional[str] = None,
    document_id: Optional[str] = None,
    section_id: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Query findings with filters."""
    query = """
        SELECT f.*, s.section_code, s.section_heading, d.name AS doc_name
        FROM findings f
        JOIN sections s ON s.id = f.section_id
        JOIN documents d ON d.id = f.document_id
    """
    conditions: List[str] = []
    params: List[Any] = []

    if triage:
        conditions.append("f.triage = ?")
        params.append(triage)
    if detector:
        conditions.append("f.detector = ?")
        params.append(detector)
    if document_id:
        conditions.append("f.document_id = ?")
        params.append(document_id)
    if section_id:
        conditions.append("f.section_id = ?")
        params.append(section_id)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY f.score DESC, f.first_seen_at DESC"
    query += f" LIMIT {limit} OFFSET {offset}"

    async with db.execute(query, params) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def seed_from_quality_flags(db: aiosqlite.Connection) -> Dict[str, int]:
    """Create findings from existing quality_flags on sections."""
    now = datetime.now(timezone.utc).isoformat()
    async with db.execute(
        "SELECT id, document_id, section_code, quality_flags FROM sections WHERE quality_flags IS NOT NULL AND quality_flags != '[]'"
    ) as cursor:
        rows = await cursor.fetchall()

    inserted = 0
    for row in rows:
        try:
            flags = json.loads(row["quality_flags"]) if row["quality_flags"] else []
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(flags, list):
            continue
        for flag in flags:
            if isinstance(flag, str):
                code = flag
                payload = {"code": flag}
            else:
                code = (flag or {}).get("code", "unknown")
                payload = flag
            fingerprint = f"quality_flag:{row['id']}:{code}"
            async with db.execute(
                "SELECT 1 FROM findings WHERE section_id = ? AND detector = ? AND fingerprint = ?",
                (row["id"], f"quality_{code}", fingerprint),
            ) as cursor2:
                if await cursor2.fetchone():
                    continue
            await db.execute(
                """
                INSERT INTO findings
                    (section_id, document_id, detector, detector_version,
                     fingerprint, severity, score, triage,
                     first_seen_at, last_seen_at, detail_json)
                VALUES (?, ?, ?, ?, ?, 'warning', 0.5, 'new', ?, ?, ?)
                """,
                (
                    row["id"], row["document_id"], f"quality_{code}",
                    "seed", fingerprint, now, now,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            inserted += 1

    return {"seeded": inserted}


async def run_detectors_and_store(
    db: aiosqlite.Connection, *, seed_flags: bool = True
) -> Dict[str, Any]:
    """Run corpus detectors, upsert findings, close stale, optionally seed flags."""
    from backend.services.detectors import run_all

    started = datetime.now(timezone.utc).isoformat()
    findings = await run_all(db)
    stats = await upsert_findings(db, findings, run_started_at=started)
    closed = await close_stale(db, started)
    seeded = {"seeded": 0}
    if seed_flags:
        seeded = await seed_from_quality_flags(db)
    return {
        "emitted": len(findings),
        "run_started_at": started,
        "closed": closed,
        **stats,
        **seeded,
    }


# Back-compat alias used by routes
async def set_triage(
    db: aiosqlite.Connection,
    finding_id: int,
    triage: str,
    *,
    actor: str,
    note: str = "",
) -> Dict[str, Any]:
    row = await triage_finding(
        db, finding_id, triage=triage, note=note or None, actor=actor
    )
    if row is None:
        raise KeyError(finding_id)
    async with db.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)) as cur:
        full = await cur.fetchone()
    return dict(full) if full else row
