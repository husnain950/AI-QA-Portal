"""Cross-edition quality detectors.

Each detector operates on the full corpus in the database and produces
Finding namedtuples with a stable fingerprint for upsert-safe storage.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from backend.database import DatabaseConnection
from backend.services.textnorm import html_shape as _html_shape
from backend.services.textnorm import norm_text as _norm_text

DETECTOR_VERSION = "1"


class Finding(NamedTuple):
    code: str
    severity: str
    score: float
    fingerprint: str
    detail: Dict[str, Any]


DETECTORS: Tuple[str, ...] = (
    "regression_vs_previous_edition",
    "heading_only_body",
    "short_vs_siblings",
    "glyph_split",
    "markup_only_drift",
)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

_YEAR_RE = re.compile(r"((?:19|20)\d{2})")
_FAMILY_STRIP = re.compile(r",?\s*(19|20)\d{2}.*$")


def family_key(document_name: str) -> str:
    """Normalize a document name to a family identifier (edition-independent)."""
    name = document_name.strip()
    name = _FAMILY_STRIP.sub("", name)
    return name.strip().lower()


def edition_date(document_name: str) -> Optional[str]:
    """Extract the first 4-digit year from a document name, or None."""
    match = _YEAR_RE.search(document_name)
    return match.group(1) if match else None


def _text_len(plain_text: Optional[str]) -> int:
    return len((plain_text or "").strip())




# ---------------------------------------------------------------------------
# Detector implementations
# ---------------------------------------------------------------------------

_OMIT_RE = re.compile(r"\b(omitted|repealed)\b", re.IGNORECASE)


async def _detect_regression(db: DatabaseConnection) -> List[Tuple[str, str, Finding]]:
    """Sections >=300 chars in edition N-1 that dropped to <25% in edition N."""
    async with db.execute(
        """
        SELECT s.id, s.document_id, s.section_code, s.plain_text,
               d.name AS doc_name
        FROM sections s
        JOIN documents d ON d.id = s.document_id
        ORDER BY d.name, s.section_code, s.sort_order
        """
    ) as cursor:
        rows = [dict(row) for row in await cursor.fetchall()]

    by_family_code: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        fk = family_key(row["doc_name"])
        key = f"{fk}|{row['section_code']}"
        by_family_code[key].append(row)

    findings: List[Tuple[str, str, Finding]] = []
    for _key, editions in by_family_code.items():
        editions.sort(key=lambda r: edition_date(r["doc_name"]) or "0000")
        for i in range(1, len(editions)):
            prev, curr = editions[i - 1], editions[i]
            prev_len = _text_len(prev["plain_text"])
            curr_len = _text_len(curr["plain_text"])
            if prev_len < 300:
                continue
            if curr_len >= prev_len * 0.25:
                continue
            if _OMIT_RE.search(curr["plain_text"] or ""):
                continue
            fp = f"regression:{prev['id']}:{curr['id']}"
            findings.append((
                curr["id"],
                curr["document_id"],
                Finding(
                    code="regression_vs_previous_edition",
                    severity="error",
                    score=round(1.0 - curr_len / max(prev_len, 1), 3),
                    fingerprint=fp,
                    detail={
                        "prev_doc": prev["doc_name"],
                        "prev_len": prev_len,
                        "curr_len": curr_len,
                        "assertion": f"{prev_len}→{curr_len} chars vs previous edition; not Omitted/Repealed",
                    },
                ),
            ))
    return findings


async def _detect_heading_only(db: DatabaseConnection) -> List[Tuple[str, str, Finding]]:
    """Sections whose body is basically just the code+heading."""
    async with db.execute(
        """
        SELECT s.id, s.document_id, s.section_code, s.section_heading, s.plain_text
        FROM sections s
        """
    ) as cursor:
        rows = await cursor.fetchall()

    findings: List[Tuple[str, str, Finding]] = []
    for row in rows:
        text = (row["plain_text"] or "").strip()
        if not text:
            continue
        if _OMIT_RE.search(text):
            continue
        expected = f"{row['section_code'] or ''} {row['section_heading'] or ''}".strip()
        if abs(len(text) - len(expected)) <= 12:
            fp = f"heading_only:{row['id']}"
            findings.append((
                row["id"],
                row["document_id"],
                Finding(
                    code="heading_only_body",
                    severity="warning",
                    score=0.9,
                    fingerprint=fp,
                    detail={"text_len": len(text), "expected_len": len(expected)},
                ),
            ))
    return findings


async def _detect_short_vs_siblings(db: DatabaseConnection) -> List[Tuple[str, str, Finding]]:
    """Sections <20% of the median length among siblings in same family+code group."""
    async with db.execute(
        """
        SELECT s.id, s.document_id, s.section_code, s.plain_text,
               d.name AS doc_name
        FROM sections s
        JOIN documents d ON d.id = s.document_id
        """
    ) as cursor:
        rows = [dict(row) for row in await cursor.fetchall()]

    by_group: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        fk = family_key(row["doc_name"])
        key = f"{fk}|{row['section_code']}"
        by_group[key].append(row)

    findings: List[Tuple[str, str, Finding]] = []
    for _key, siblings in by_group.items():
        if len(siblings) < 3:
            continue
        lengths = sorted(_text_len(s["plain_text"]) for s in siblings)
        median = lengths[len(lengths) // 2]
        if median < 50:
            continue
        threshold = median * 0.2
        for sib in siblings:
            sib_len = _text_len(sib["plain_text"])
            if sib_len < threshold:
                fp = f"short_sibling:{sib['id']}"
                findings.append((
                    sib["id"],
                    sib["document_id"],
                    Finding(
                        code="short_vs_siblings",
                        severity="warning",
                        score=round(1.0 - sib_len / max(median, 1), 3),
                        fingerprint=fp,
                        detail={"length": sib_len, "median": median, "n": len(siblings)},
                    ),
                ))
    return findings


_GLYPH_SPLIT_RE = re.compile(
    r"(?:(?<!\w)[A-Z]\s+[A-Z](?:\s+[A-Z])+(?!\w))"  # A O mitted
    r"|(?:CHAP\s+TER)"
    r"|(?:SCHED\s+ULE)"
    r"|(?:SECT\s+ION)"
    r"|(?:\bO\s+mitted\b)"
    r"|(?:\bR\s+epealed\b)",
    re.IGNORECASE,
)


async def _detect_glyph_split(db: DatabaseConnection) -> List[Tuple[str, str, Finding]]:
    """OCR artifacts where letters are isolated by spaces."""
    async with db.execute(
        "SELECT s.id, s.document_id, s.plain_text FROM sections s"
    ) as cursor:
        rows = await cursor.fetchall()

    findings: List[Tuple[str, str, Finding]] = []
    for row in rows:
        text = row["plain_text"] or ""
        matches = _GLYPH_SPLIT_RE.findall(text)
        if not matches:
            continue
        for i, match in enumerate(matches[:5]):
            fp = f"glyph_split:{row['id']}:{i}"
            findings.append((
                row["id"],
                row["document_id"],
                Finding(
                    code="glyph_split",
                    severity="warning",
                    score=0.7,
                    fingerprint=fp,
                    detail={"fragment": match.strip()[:80]},
                ),
            ))
    return findings




async def _detect_markup_drift(db: DatabaseConnection) -> List[Tuple[str, str, Finding]]:
    """Same normalized text across editions but different HTML structure."""
    async with db.execute(
        """
        SELECT s.id, s.document_id, s.section_code, s.plain_text, s.html_content,
               d.name AS doc_name
        FROM sections s
        JOIN documents d ON d.id = s.document_id
        """
    ) as cursor:
        rows = [dict(row) for row in await cursor.fetchall()]

    by_family_code: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        fk = family_key(row["doc_name"])
        key = f"{fk}|{row['section_code']}"
        row["_text_sha"] = hashlib.sha256(
            _norm_text(row["plain_text"] or "").encode()
        ).hexdigest()
        row["_html_shape"] = _html_shape(row["html_content"] or "")
        by_family_code[key].append(row)

    findings: List[Tuple[str, str, Finding]] = []
    for _key, editions in by_family_code.items():
        if len(editions) < 2:
            continue
        by_text_sha: Dict[str, List[dict]] = defaultdict(list)
        for ed in editions:
            by_text_sha[ed["_text_sha"]].append(ed)
        for _sha, group in by_text_sha.items():
            if len(group) < 2:
                continue
            shapes = set(g["_html_shape"] for g in group)
            if len(shapes) <= 1:
                continue
            for item in group:
                fp = f"markup_drift:{item['id']}"
                findings.append((
                    item["id"],
                    item["document_id"],
                    Finding(
                        code="markup_only_drift",
                        severity="info",
                        score=0.4,
                        fingerprint=fp,
                        detail={
                            "html_shape": item["_html_shape"][:16],
                            "n_shapes": len(shapes),
                        },
                    ),
                ))
    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_DETECTOR_FNS = {
    "regression_vs_previous_edition": _detect_regression,
    "heading_only_body": _detect_heading_only,
    "short_vs_siblings": _detect_short_vs_siblings,
    "glyph_split": _detect_glyph_split,
    "markup_only_drift": _detect_markup_drift,
}


async def run_all(db: DatabaseConnection) -> List[Tuple[str, str, Finding]]:
    """Run every detector and return (section_id, document_id, Finding) triples."""
    all_findings: List[Tuple[str, str, Finding]] = []
    for name in DETECTORS:
        fn = _DETECTOR_FNS[name]
        all_findings.extend(await fn(db))
    return all_findings
