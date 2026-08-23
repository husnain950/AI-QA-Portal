"""Run all global invariants + data-driven cases against a converted JSON.

One copy, parameterised by lane. There used to be three byte-identical copies of this
file (and of checks.py and loader.py) under tools/<lane>/suite/, because the lane was
carried by *which* `suite` package sys.path happened to find. The lane now arrives as
arguments instead: an invariants module and a cases file.
"""

from __future__ import annotations

import importlib
import json
import os
from types import ModuleType

from . import checks

CASES_DIR = os.path.join(os.path.dirname(__file__), "cases")


def invariants_for(lane: str) -> ModuleType:
    return importlib.import_module(f"{__package__}.invariants.{lane}")


def cases_path_for(lane: str) -> str:
    return os.path.join(CASES_DIR, f"{lane}.json")


def run(doc: dict, invariants: ModuleType, cases_path: str) -> dict:
    results = {"invariants": [], "cases": [], "known_gaps": [], "skipped": []}

    # 1) global invariants
    for name, fn in invariants.ALL_INVARIANTS:
        failures = fn(doc)
        results["invariants"].append({
            "name": name,
            "passed": not failures,
            "failures": failures[:20],
            "n_failures": len(failures),
        })

    # 2) data-driven cases
    with open(cases_path, encoding="utf-8") as fh:
        cases = json.load(fh).get("cases", [])
    filename = (doc.get("metadata") or {}).get("filename", "")
    for case in cases:
        # a case may be scoped to one edition of the document family:
        # ``applies_to`` is a substring of metadata.filename (e.g. the
        # "amended upto" date).  Unscoped cases run against every document.
        scope = case.get("applies_to")
        if scope and scope not in filename:
            results["skipped"].append({"id": case.get("id"),
                                       "applies_to": scope})
            continue
        msg = checks.run_case(doc, case)
        entry = {"id": case.get("id"), "source": case.get("source"),
                 "status": case.get("status", "active"),
                 "description": case.get("description"), "passed": msg is None,
                 "message": msg}
        # only 'active' cases can fail the build; everything else is tracked
        bucket = "cases" if entry["status"] == "active" else "known_gaps"
        results[bucket].append(entry)
    return results


def summarize(results: dict) -> tuple[str, bool]:
    lines = []
    inv_fail = [i for i in results["invariants"] if not i["passed"]]
    case_fail = [c for c in results["cases"] if not c["passed"]]
    gap_fail = [c for c in results["known_gaps"] if not c["passed"]]

    lines.append("=" * 66)
    lines.append("GLOBAL INVARIANTS")
    for i in results["invariants"]:
        mark = "PASS" if i["passed"] else f"FAIL ({i['n_failures']})"
        lines.append(f"  [{mark:>9}] {i['name']}")
        for f in i["failures"][:6]:
            lines.append(f"              - {f}")
        if i["n_failures"] > 6:
            lines.append(f"              ... +{i['n_failures'] - 6} more")

    lines.append("")
    lines.append("REGRESSION CASES")
    for c in results["cases"]:
        mark = "PASS" if c["passed"] else "FAIL"
        lines.append(f"  [{mark:>4}] {c['id']}")
        if not c["passed"]:
            lines.append(f"           {c['description']}")
            lines.append(f"           -> {c['message']}")

    if results["known_gaps"]:
        lines.append("")
        lines.append("TRACKED (known_gap / needs_review -- not counted as regressions)")
        for c in results["known_gaps"]:
            mark = "ok" if c["passed"] else "open"
            lines.append(f"  [{mark:>4}] ({c.get('status')}) {c['id']}: {c['description']}")

    ok = not inv_fail and not case_fail
    n_skipped = len(results.get("skipped", []))
    lines.append("")
    lines.append("=" * 66)
    lines.append(
        f"RESULT: {'ALL PASS' if ok else 'FAILURES'} | "
        f"invariants {len(results['invariants']) - len(inv_fail)}/{len(results['invariants'])} | "
        f"cases {len(results['cases']) - len(case_fail)}/{len(results['cases'])} | "
        f"known gaps {len(gap_fail)}/{len(results['known_gaps'])} open | "
        f"skipped (other edition) {n_skipped}")
    lines.append("=" * 66)
    return "\n".join(lines), ok
