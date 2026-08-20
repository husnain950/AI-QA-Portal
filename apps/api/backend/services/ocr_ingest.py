"""Parse OCR disagreement reports into findings.

Reports live under data/corpora/acts/reports/ocr-disagreements-*.md.
Each row is a token-level disagreement between OCR engines.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from backend.database import DatabaseConnection
from backend.services.detectors import family_key

logger = logging.getLogger(__name__)

_TABLE_ROW_RE = re.compile(
    r"\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|"
    r"\s*`?([^|`]*)`?\s*\|\s*([\d.]+)\s*\|"
    r"\s*`?([^|`]*)`?\s*\|\s*([\d.]+)\s*\|"
    r"\s*`?([^|`]*)`?\s*\|"
)

_SOURCE_RE = re.compile(r"Source:\s*`([^`]+)`", re.IGNORECASE)
_HEADER_RE = re.compile(r"^#\s*OCR disagreements\s*--\s*(.+)", re.IGNORECASE)


def parse_ocr_report(path: Path) -> Tuple[str, List[Dict[str, Any]]]:
    """Parse a single OCR disagreement report.

    Returns (source_pdf_name, list of disagreement dicts).
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    source_name = ""
    for line in lines[:10]:
        m = _HEADER_RE.match(line)
        if m:
            source_name = m.group(1).strip().rstrip(".pdf")
        m2 = _SOURCE_RE.search(line)
        if m2:
            source_name = source_name or Path(m2.group(1)).stem

    rows: List[Dict[str, Any]] = []
    for line in lines:
        m = _TABLE_ROW_RE.match(line)
        if not m:
            continue
        page, x0, top = int(m.group(1)), int(m.group(2)), int(m.group(3))
        tesseract, tess_conf = m.group(4).strip(), float(m.group(5))
        rapidocr, rapid_conf = m.group(6).strip(), float(m.group(7))
        accepted = m.group(8).strip()
        rows.append({
            "page": page,
            "x0": x0,
            "top": top,
            "tesseract": tesseract,
            "tess_conf": tess_conf,
            "rapidocr": rapidocr,
            "rapid_conf": rapid_conf,
            "accepted": accepted,
        })

    return source_name, rows


async def ingest_ocr_findings(
    db: DatabaseConnection,
    reports_dir: Path,
) -> Dict[str, Any]:
    """Parse all ocr-disagreements-*.md and insert as findings.

    Matches reports to documents via source_key/name patterns.
    """
    report_files = sorted(reports_dir.glob("ocr-disagreements-*.md"))
    if not report_files:
        return {"reports": 0, "findings": 0}

    total_findings = 0
    reports_processed = 0

    for report_path in report_files:
        source_name, rows = parse_ocr_report(report_path)
        if not rows:
            continue

        fk = family_key(source_name) if source_name else ""
        async with db.execute(
            """
            SELECT d.id, d.name FROM documents d
            WHERE LOWER(d.name) LIKE ? OR d.source_key LIKE ?
            LIMIT 1
            """,
            (f"%{fk}%", f"%{fk}%"),
        ) as cursor:
            doc_row = await cursor.fetchone()

        if not doc_row:
            logger.debug("No document match for OCR report: %s", report_path.name)
            continue

        document_id = doc_row["id"]
        reports_processed += 1

        for row in rows:
            fingerprint = f"ocr_disagree:{document_id}:p{row['page']}:{row['x0']}:{row['top']}"

            async with db.execute(
                "SELECT 1 FROM findings WHERE document_id = ? AND detector = ? AND fingerprint = ?",
                (document_id, "ocr_disagree", fingerprint),
            ) as cursor:
                if await cursor.fetchone():
                    continue

            section_id = None
            async with db.execute(
                "SELECT id FROM sections WHERE document_id = ? AND start_page <= ? AND end_page >= ? LIMIT 1",
                (document_id, row["page"], row["page"]),
            ) as cursor:
                sec_row = await cursor.fetchone()
            if sec_row:
                section_id = sec_row["id"]
            else:
                async with db.execute(
                    "SELECT id FROM sections WHERE document_id = ? ORDER BY sort_order LIMIT 1",
                    (document_id,),
                ) as cursor:
                    sec_row = await cursor.fetchone()
                if sec_row:
                    section_id = sec_row["id"]

            if not section_id:
                continue

            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()

            detail = {
                "page": row["page"],
                "x0": row["x0"],
                "top": row["top"],
                "tesseract": row["tesseract"],
                "rapidocr": row["rapidocr"],
                "accepted": row["accepted"],
            }

            import json
            await db.execute(
                """
                INSERT INTO findings
                    (section_id, document_id, detector, detector_version,
                     fingerprint, severity, score, triage,
                     first_seen_at, last_seen_at, detail_json)
                VALUES (?, ?, 'ocr_disagree', 'report', ?, 'info', 0.3, 'new', ?, ?, ?)
                ON CONFLICT (section_id, detector, fingerprint) DO NOTHING
                """,
                (section_id, document_id, fingerprint, now, now,
                 json.dumps(detail, ensure_ascii=False)),
            )
            total_findings += 1

    await db.commit()
    return {"reports": reports_processed, "findings": total_findings}
