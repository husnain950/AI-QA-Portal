"""Persistent leaf overlays — approved AI fixes that outlive a re-sync.

An overlay says: "for the PDF with this content hash, the leaf at this
``source_key`` should read like *this* instead of what the pipeline produced".
It is keyed by the PDF hash, not the document row, because a corpus re-sync can
drop and recreate documents while the PDF bytes never change.

``original_leaf_fingerprint`` is the canonical hash of the pipeline leaf the fix
replaced. On every sync the incoming leaf is compared against it:

* matches            -> the pipeline still produces the flawed parse; re-apply.
* matches the fix    -> the parser caught up; the overlay is ``superseded``.
* anything else      -> the parser changed that leaf on its own; applying an old
                        AI fix would clobber a genuine improvement, so the
                        overlay goes ``stale`` and the section is re-flagged for
                        human review.

Callers own the transaction: nothing here commits.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from backend.database import DatabaseConnection, DatabaseRow
from backend.services.clock import iso_now_z as _now

_LEAF_SEGMENTS = {"chapters", "schedules", "parts", "divisions", "sections"}




def leaf_fingerprint(leaf: Dict[str, Any]) -> str:
    """Canonical content hash of a leaf node (key order independent)."""
    canonical = json.dumps(leaf, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def pdf_digest_from_filename(pdf_filename: str) -> Optional[str]:
    """Extract the sha256 from a blob-store name like ``pdf/<sha256>.pdf``."""
    name = pdf_filename or ""
    if name.startswith("pdf/") and name.endswith(".pdf"):
        digest = name[len("pdf/"):-len(".pdf")]
        if len(digest) == 64:
            return digest
    return None


def get_leaf(data: Dict[str, Any], source_key: str) -> Optional[Dict[str, Any]]:
    """Resolve a ``source_key`` path (e.g. ``/chapters/0/sections/3``) to its node."""
    if source_key == "/preamble":
        node = data.get("preamble")
        return node if isinstance(node, dict) else None
    segments = _walk(source_key)
    if not segments:
        return None  # a malformed key must not resolve to the document root
    node: Any = data
    for name, index in segments:
        if not isinstance(node, dict):
            return None
        collection = node.get(name)
        if not isinstance(collection, list) or index >= len(collection):
            return None
        node = collection[index]
    return node if isinstance(node, dict) else None


def set_leaf(data: Dict[str, Any], source_key: str, leaf: Dict[str, Any]) -> bool:
    """Replace the node at ``source_key`` in place. False when the path is gone."""
    if source_key == "/preamble":
        if not isinstance(data.get("preamble"), dict):
            return False
        data["preamble"] = leaf
        return True
    segments = list(_walk(source_key))
    if not segments:
        return False
    node: Any = data
    for name, index in segments[:-1]:
        if not isinstance(node, dict):
            return False
        collection = node.get(name)
        if not isinstance(collection, list) or index >= len(collection):
            return False
        node = collection[index]
    name, index = segments[-1]
    if not isinstance(node, dict):
        return False
    collection = node.get(name)
    if not isinstance(collection, list) or index >= len(collection):
        return False
    collection[index] = leaf
    return True


def _walk(source_key: str) -> List[Tuple[str, int]]:
    parts = [part for part in (source_key or "").split("/") if part]
    if len(parts) % 2 != 0:
        return []
    pairs: List[Tuple[str, int]] = []
    for name, raw_index in zip(parts[0::2], parts[1::2]):
        if name not in _LEAF_SEGMENTS or not raw_index.isdigit():
            return []
        pairs.append((name, int(raw_index)))
    return pairs


async def upsert_overlay(
    db: DatabaseConnection,
    *,
    pdf_sha256: str,
    section_source_key: str,
    replacement: Dict[str, Any],
    original_fingerprint: str,
    proposal_id: Optional[str] = None,
    created_by: Optional[str] = None,
) -> str:
    """Store an approved fix, revoking any previous overlay for the same leaf."""
    await db.execute(
        """
        UPDATE section_overlays
        SET status = 'revoked', status_changed_at = ?,
            status_reason = 'replaced by a newer approved fix'
        WHERE pdf_sha256 = ? AND section_source_key = ? AND status = 'active'
        """,
        (_now(), pdf_sha256, section_source_key),
    )
    overlay_id = str(uuid.uuid4())
    await db.execute(
        """
        INSERT INTO section_overlays (
            id, pdf_sha256, section_source_key, replacement_json,
            original_leaf_fingerprint, proposal_id, status, created_at, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """,
        (
            overlay_id,
            pdf_sha256,
            section_source_key,
            json.dumps(replacement, ensure_ascii=False),
            original_fingerprint,
            proposal_id,
            _now(),
            created_by,
        ),
    )
    return overlay_id


async def active_overlays(
    db: DatabaseConnection, pdf_sha256: str
) -> List[DatabaseRow]:
    async with db.execute(
        """
        SELECT * FROM section_overlays
        WHERE pdf_sha256 = ? AND status = 'active'
        ORDER BY section_source_key
        """,
        (pdf_sha256,),
    ) as cursor:
        return list(await cursor.fetchall())


@dataclass
class OverlayReport:
    applied: List[str] = field(default_factory=list)
    superseded: List[str] = field(default_factory=list)
    stale: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "applied": self.applied,
            "superseded": self.superseded,
            "stale": self.stale,
        }


async def apply_overlays(
    db: DatabaseConnection,
    pdf_sha256: str,
    json_bytes: bytes,
) -> Tuple[bytes, OverlayReport]:
    """Re-apply every active overlay on top of a fresh pipeline JSON.

    Returns the (possibly rewritten) bytes plus a report. Stale/superseded
    overlays have their status rows updated here; flagging the affected
    sections is the caller's job because the section rows only exist after
    the version is applied.
    """
    report = OverlayReport()
    rows = await active_overlays(db, pdf_sha256)
    if not rows:
        return json_bytes, report

    data = json.loads(json_bytes.decode("utf-8"))
    changed = False
    for row in rows:
        source_key = row["section_source_key"]
        replacement = json.loads(row["replacement_json"])
        incoming = get_leaf(data, source_key)

        if incoming is None:
            await _mark(db, row["id"], "stale", "leaf no longer exists in pipeline output")
            report.stale.append(source_key)
            continue

        incoming_print = leaf_fingerprint(incoming)
        if incoming_print == leaf_fingerprint(replacement):
            await _mark(db, row["id"], "superseded", "pipeline output now matches the fix")
            report.superseded.append(source_key)
            continue
        if incoming_print != row["original_leaf_fingerprint"]:
            await _mark(
                db,
                row["id"],
                "stale",
                "pipeline output changed since the fix was approved",
            )
            report.stale.append(source_key)
            continue

        set_leaf(data, source_key, replacement)
        changed = True
        report.applied.append(source_key)

    if changed:
        json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    return json_bytes, report


async def _mark(
    db: DatabaseConnection, overlay_id: str, status: str, reason: str
) -> None:
    await db.execute(
        """
        UPDATE section_overlays
        SET status = ?, status_changed_at = ?, status_reason = ?
        WHERE id = ?
        """,
        (status, _now(), reason, overlay_id),
    )


async def flag_stale_sections(
    db: DatabaseConnection, document_id: str, source_keys: List[str]
) -> int:
    """Re-flag sections whose overlay went stale, but never clobber a human verdict."""
    flagged = 0
    for source_key in source_keys:
        cursor = await db.execute(
            """
            UPDATE sections
            SET review_status = 'has_issues'
            WHERE document_id = ? AND source_key = ? AND review_status = 'pending'
            """,
            (document_id, source_key),
        )
        flagged += int(cursor.rowcount or 0)
    return flagged
