#!/usr/bin/env python3
"""Import a QA-review report into the regression case registry (tools/suite/cases/ordinance.json).

Point it at any QA report JSON (the reviewer export) and it turns each annotation
into a regression case, so review findings become permanent, re-runnable checks.

    python scripts/import_qa_report.py QA_Report.json            # append new cases
    python scripts/import_qa_report.py QA_Report.json --dry-run   # show what it would add

Design notes -- annotations vary in how reliably they can be auto-checked:

  * page-number / glyph removals ("inheritance. 157", the U+F0D8 asterisk) carry
    concrete flagged text -> a precise check, imported as **active** (must pass).
  * everything else (missing text, "format as per PDF", bullet/indent/line-break
    requests) can't be verified reliably from free text -> imported as
    **needs_review** (tracked, non-failing) with a suggested check for a human to
    confirm and promote to 'active'.

IDs are a stable hash of (section, highlighted text, issue), so re-importing the
same report adds nothing and a newer report only contributes its new findings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

# Make tools/ importable so this works from any working directory. `CASES` used to
# point at a `tools/suite/cases/ordinance.json` that has never existed in this repo, so every run
# ended in FileNotFoundError.
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from suite.runner import cases_path_for  # noqa: E402

#: This importer reads Ordinance QA reports, so it writes the Ordinance case file.
CASES = cases_path_for("ordinance")

_REMOVE_HINTS = ("remove", "removed", "should be removed", "there is no",
                 "no need", "there should no", "should no", "is no ")


def _has_pua(s: str) -> bool:
    return any(0xE000 <= ord(c) <= 0xF8FF for c in s)


def _stable_id(code: str, hl: str, desc: str) -> str:
    h = hashlib.md5(f"{code}|{hl}|{desc}".encode("utf-8")).hexdigest()[:8]
    safe = re.sub(r"[^A-Za-z0-9]+", "", str(code))[:8] or "x"
    return f"qa_{safe}_{h}"


def classify(hl: str, desc: str, severity: str) -> dict:
    """Return {check, arg, status} for an annotation (best-effort)."""
    hl = (hl or "").strip()
    d = (desc or "").lower()

    # 1) private-use glyph -> precise PUA-range regex (no literal glyph needed)
    if _has_pua(hl):
        return {"check": "html_not_matches", "arg": "[\\ue000-\\uf8ff]",
                "status": "active"}

    # 2) page-number removal: the flag must carry a real 2-4 digit page number
    #    AND removal/page context.  This deliberately excludes "there is no (4)"
    #    (a *missing* item, not a page number) and bare/short flags like "31".
    has_pagenum = bool(re.search(r"\d{2,4}", hl))
    removal_ctx = ("remove" in d or "page" in d or bool(re.search(r"no\s+\d", d)))
    if has_pagenum and removal_ctx and len(hl) >= 6:
        return {"check": "plain_not_contains", "arg": hl, "status": "active"}

    # 3) "missing X" -> guess the phrase, but a human confirms before it's active
    if "missing" in d:
        m = re.search(r"missing\s+(.+?)(?:\s+as per|\s+in the|$)", desc, re.I)
        return {"check": "plain_contains", "arg": (m.group(1).strip() if m else ""),
                "status": "needs_review"}

    # 4) everything else (formatting, "as per PDF", bare flags) -> review.
    #    Suggest a not_contains on the flagged text as a starting point.
    return {"check": "plain_not_contains", "arg": hl, "status": "needs_review"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Import a QA report into the Ordinance regression cases")
    ap.add_argument("qa_report", help="path to the QA report JSON")
    ap.add_argument("--dry-run", action="store_true", help="print, don't write")
    args = ap.parse_args(argv)

    with open(args.qa_report, encoding="utf-8") as fh:
        qa = json.load(fh)
    with open(CASES, encoding="utf-8") as fh:
        reg = json.load(fh)
    existing = {c["id"] for c in reg["cases"]}

    added, skipped, by_status = [], 0, {"active": 0, "needs_review": 0}
    for sec in qa.get("sections", []):
        code = sec.get("code")
        for a in sec.get("annotations", []):
            hl = a.get("highlighted_text", "") or ""
            desc = a.get("issue_description", "") or ""
            cid = _stable_id(code, hl, desc)
            if cid in existing:
                skipped += 1
                continue
            spec = classify(hl, desc, a.get("severity", ""))
            case = {
                "id": cid,
                "source": "QA_Report:" + qa.get("document", {}).get("name", "")[:30],
                "description": f"Sec {code}: {desc} [flagged: {hl[:40]!r}]",
                "target": {"kind": "section", "code": str(code)},
                "check": spec["check"],
                "arg": spec["arg"],
                "status": spec["status"],
                "severity": a.get("severity"),
            }
            reg["cases"].append(case)
            existing.add(cid)
            added.append(case)
            by_status[spec["status"]] = by_status.get(spec["status"], 0) + 1

    print(f"QA report: {args.qa_report}")
    print(f"  new cases:     {len(added)}  (active={by_status.get('active',0)}, "
          f"needs_review={by_status.get('needs_review',0)})")
    print(f"  already known: {skipped}")
    for c in added:
        print(f"    + [{c['status']:>12}] {c['id']}  {c['check']}({c['arg'][:24]!r})")

    if args.dry_run:
        print("\n(dry-run: tools/suite/cases/ordinance.json not modified)")
        return 0
    with open(CASES, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2)
    print(f"\nwrote {len(added)} new case(s) to {CASES}")
    print("next: python tools/run_suite.py ordinance   (review 'needs_review' items and promote to 'active')")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
