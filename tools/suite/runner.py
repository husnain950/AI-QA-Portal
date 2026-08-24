"""Run all global invariants + data-driven cases against a converted JSON.

One copy, parameterised by lane. There used to be three byte-identical copies of this
file (and of checks.py and loader.py) under tools/<lane>/suite/, because the lane was
carried by *which* `suite` package sys.path happened to find. The lane now arrives as
arguments instead: an invariants module, a cases file and an exemptions file.
"""

from __future__ import annotations

import importlib
import json
import os
from types import ModuleType

from . import checks

CASES_DIR = os.path.join(os.path.dirname(__file__), "cases")
EXEMPTIONS_DIR = os.path.join(os.path.dirname(__file__), "exemptions")


def invariants_for(lane: str) -> ModuleType:
    return importlib.import_module(f"{__package__}.invariants.{lane}")


def cases_path_for(lane: str) -> str:
    return os.path.join(CASES_DIR, f"{lane}.json")


def exemptions_path_for(lane: str) -> str:
    """A lane with nothing to exempt has no file; a missing path means no exemptions."""
    return os.path.join(EXEMPTIONS_DIR, f"{lane}.json")


def _exempt_reasons(exemptions_path: str | None, filename: str) -> dict[str, str]:
    """Invariant name -> reason, for the exemptions scoped to THIS document.

    Scoping is `applies_to` as a substring of ``metadata.filename`` -- the same rule
    cases already use, rather than a second convention for the same job.
    """
    if not exemptions_path or not os.path.exists(exemptions_path):
        return {}
    with open(exemptions_path, encoding="utf-8") as fh:
        entries = json.load(fh).get("exemptions", [])
    return {e["invariant"]: e.get("reason", "")
            for e in entries if e.get("applies_to", "") in filename}


def run(doc: dict, invariants: ModuleType, cases_path: str,
        exemptions_path: str | None = None) -> dict:
    results = {"invariants": [], "cases": [], "known_gaps": [], "skipped": [],
               "exempt_invariants": []}
    filename = (doc.get("metadata") or {}).get("filename", "")

    # 1) global invariants
    #
    # An exempted invariant still RUNS and its failures are still counted and printed;
    # it just does not fail the build for the one document named in the exemption. That
    # keeps the rest of the lane gating instead of the whole lane being red -- and it
    # means an exemption that has become stale announces itself, because a *passing*
    # exempt invariant is reported as such rather than silently ignored.
    exempt = _exempt_reasons(exemptions_path, filename)
    for name, fn in invariants.ALL_INVARIANTS:
        failures = fn(doc)
        entry = {
            "name": name,
            "passed": not failures,
            "failures": failures[:20],
            "n_failures": len(failures),
        }
        if name in exempt:
            entry["reason"] = exempt[name]
            results["exempt_invariants"].append(entry)
        else:
            results["invariants"].append(entry)

    # 2) data-driven cases
    with open(cases_path, encoding="utf-8") as fh:
        cases = json.load(fh).get("cases", [])
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

    exempt = results.get("exempt_invariants", [])
    if exempt:
        lines.append("")
        lines.append("EXEMPT INVARIANTS (documented for this document -- not gating)")
        for i in exempt:
            mark = "no longer failing" if i["passed"] else f"{i['n_failures']} hit(s)"
            lines.append(f"  [{mark}] {i['name']}")
            if i["passed"]:
                lines.append("              exemption is now stale -- delete the entry")
            else:
                lines.append(f"              {i.get('reason', '')}")

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
        f"exempt {len(exempt)} ({sum(i['n_failures'] for i in exempt)} hits) | "
        f"skipped (other edition) {n_skipped}")
    lines.append("=" * 66)
    return "\n".join(lines), ok
