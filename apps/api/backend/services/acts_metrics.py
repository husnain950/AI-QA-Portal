"""Ingest the Acts pipeline's own QA measurements against the active version.

The portal does not recompute any of this. The pipeline owns its gate; these are its
numbers, read from the reports it already knows how to write:

``qa-invariants.json``
    ``python scripts/run_tests.py --json reports/qa-invariants.json`` (no code change
    needed upstream). Shape: ``{json_path: {"invariants": [{name, passed, failures,
    n_failures}], "cases": [...], "known_gaps": [...], "skipped": [...]}}``. When a
    single target is tested the runner writes the bare results dict instead, so both
    shapes are accepted.

``qa-conservation.json``
    ``python scripts/audit_all.py --json reports/qa-conservation.json``. Shape:
    ``{"gates": {"body": 99.99, "footnote": 100.0},
       "editions": [{"json": "<stem>.json", "body_conserved": float,
                     "body_missing": int, "footnote_conserved": float,
                     "footnote_missing": int, "passed": bool}]}``

Both are optional. A missing report is a skip, never an error -- conservation re-reads
every source PDF, so it is run occasionally and by hand.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import aiosqlite

INVARIANTS_REPORT = "qa-invariants.json"
CONSERVATION_REPORT = "qa-conservation.json"


def _stem(name: str) -> str:
    return os.path.splitext(os.path.basename(name))[0]


def _load(path: Path) -> Optional[Any]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def read_invariants(report: Path) -> Dict[str, Dict[str, Any]]:
    """Per-edition invariant and case totals, keyed by JSON stem."""
    payload = _load(report)
    if payload is None:
        return {}
    if isinstance(payload, dict) and "invariants" in payload:
        # Single-target report: the runner drops the outer path key.
        payload = {report.name: payload}
    if not isinstance(payload, dict):
        return {}

    parsed: Dict[str, Dict[str, Any]] = {}
    for json_path, results in payload.items():
        if not isinstance(results, dict):
            continue
        invariants = results.get("invariants") or []
        cases = results.get("cases") or []
        failing = [item.get("name") for item in invariants if not item.get("passed")]
        parsed[_stem(json_path)] = {
            "invariants_total": len(invariants),
            "invariants_passed": sum(1 for item in invariants if item.get("passed")),
            "cases_total": len(cases),
            "cases_passed": sum(1 for item in cases if item.get("passed")),
            "failing_invariants": [name for name in failing if name],
            "failures": {
                item.get("name"): (item.get("failures") or [])[:5]
                for item in invariants
                if not item.get("passed")
            },
        }
    return parsed


def read_conservation(report: Path) -> Dict[str, Dict[str, Any]]:
    """Per-edition body/footnote conservation, keyed by JSON stem."""
    payload = _load(report)
    if not isinstance(payload, dict):
        return {}
    parsed: Dict[str, Dict[str, Any]] = {}
    for edition in payload.get("editions") or []:
        name = edition.get("json") or edition.get("name")
        if not name:
            continue
        parsed[_stem(name)] = {
            "body_conserved": edition.get("body_conserved"),
            "body_missing": edition.get("body_missing"),
            "footnote_conserved": edition.get("footnote_conserved"),
            "footnote_missing": edition.get("footnote_missing"),
            "gate_ok": edition.get("passed"),
        }
    return parsed


async def ingest(db: aiosqlite.Connection, reports_dir: Path) -> Dict[str, Any]:
    """Attach whatever measurements exist to each document's active version."""
    reports_dir = Path(reports_dir).expanduser()
    invariants = read_invariants(reports_dir / INVARIANTS_REPORT)
    conservation = read_conservation(reports_dir / CONSERVATION_REPORT)
    if not invariants and not conservation:
        return {
            "status": "skipped",
            "reason": f"no {INVARIANTS_REPORT} or {CONSERVATION_REPORT} in {reports_dir}",
        }

    async with db.execute(
        """
        SELECT d.source_key, v.id AS version_id
        FROM documents d
        JOIN document_versions v ON v.document_id = d.id AND v.is_active = 1
        WHERE d.source_key IS NOT NULL
        """
    ) as cursor:
        targets = {row["source_key"]: row["version_id"] for row in await cursor.fetchall()}

    measured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    written, unmatched = 0, []
    for stem in sorted(set(invariants) | set(conservation)):
        version_id = targets.get(stem)
        if version_id is None:
            unmatched.append(stem)
            continue
        inv = invariants.get(stem, {})
        con = conservation.get(stem, {})
        gate_ok = con.get("gate_ok")
        if gate_ok is not None and inv:
            # The pipeline's gate is conservation AND invariants; report the conjunction
            # so a green badge in the portal means what it means upstream.
            gate_ok = bool(gate_ok) and inv["invariants_passed"] == inv["invariants_total"]
        detail = {
            "failing_invariants": inv.get("failing_invariants", []),
            "failures": inv.get("failures", {}),
        }
        await db.execute(
            """
            INSERT INTO version_metrics (
                version_id, invariants_passed, invariants_total,
                cases_passed, cases_total, body_conserved, body_missing,
                footnote_conserved, footnote_missing, gate_ok, measured_at, detail_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(version_id) DO UPDATE SET
                invariants_passed = excluded.invariants_passed,
                invariants_total = excluded.invariants_total,
                cases_passed = excluded.cases_passed,
                cases_total = excluded.cases_total,
                body_conserved = excluded.body_conserved,
                body_missing = excluded.body_missing,
                footnote_conserved = excluded.footnote_conserved,
                footnote_missing = excluded.footnote_missing,
                gate_ok = excluded.gate_ok,
                measured_at = excluded.measured_at,
                detail_json = excluded.detail_json
            """,
            (
                version_id,
                inv.get("invariants_passed"),
                inv.get("invariants_total"),
                inv.get("cases_passed"),
                inv.get("cases_total"),
                con.get("body_conserved"),
                con.get("body_missing"),
                con.get("footnote_conserved"),
                con.get("footnote_missing"),
                None if gate_ok is None else int(bool(gate_ok)),
                measured_at,
                json.dumps(detail, ensure_ascii=False),
            ),
        )
        written += 1

    return {
        "status": "ok",
        "invariant_editions": len(invariants),
        "conservation_editions": len(conservation),
        "versions_updated": written,
        "unmatched": unmatched[:20],
    }


def demo() -> None:
    """Self-check the report readers against the runner's real output shape."""
    import tempfile

    with tempfile.TemporaryDirectory() as root:
        reports = Path(root)
        (reports / INVARIANTS_REPORT).write_text(
            json.dumps(
                {
                    "/x/output/Customs Act, 1969.json": {
                        "invariants": [
                            {"name": "a", "passed": True, "failures": [], "n_failures": 0},
                            {"name": "b", "passed": False, "failures": ["s.9"], "n_failures": 3},
                        ],
                        "cases": [{"id": "c1", "passed": True}],
                        "known_gaps": [],
                        "skipped": [{"id": "c2", "applies_to": "other"}],
                    }
                }
            ),
            encoding="utf-8",
        )
        parsed = read_invariants(reports / INVARIANTS_REPORT)
        assert set(parsed) == {"Customs Act, 1969"}, parsed
        row = parsed["Customs Act, 1969"]
        assert (row["invariants_passed"], row["invariants_total"]) == (1, 2), row
        assert row["cases_passed"] == 1 and row["cases_total"] == 1
        assert row["failing_invariants"] == ["b"], row
        assert row["failures"]["b"] == ["s.9"], row

        # A single-target run writes the bare results dict.
        single = reports / "single.json"
        single.write_text(json.dumps({"invariants": [], "cases": []}), encoding="utf-8")
        assert read_invariants(single) == {
            "single": {
                "invariants_total": 0,
                "invariants_passed": 0,
                "cases_total": 0,
                "cases_passed": 0,
                "failing_invariants": [],
                "failures": {},
            }
        }

        (reports / CONSERVATION_REPORT).write_text(
            json.dumps(
                {
                    "gates": {"body": 99.99, "footnote": 100.0},
                    "editions": [
                        {
                            "json": "Finance Act, 2022.json",
                            "body_conserved": 100.0,
                            "body_missing": 0,
                            "footnote_conserved": 99.843,
                            "footnote_missing": 135,
                            "passed": False,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        con = read_conservation(reports / CONSERVATION_REPORT)
        assert con["Finance Act, 2022"]["footnote_missing"] == 135, con
        assert con["Finance Act, 2022"]["gate_ok"] is False, con

        # Missing reports are a skip, not a crash.
        assert read_invariants(reports / "nope.json") == {}
        assert read_conservation(reports / "nope.json") == {}
    print("acts_metrics: ok")


if __name__ == "__main__":
    demo()
