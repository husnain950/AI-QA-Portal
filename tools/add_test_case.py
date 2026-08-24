#!/usr/bin/env python3
"""Capture a regression case by pointing at an issue.

Workflow you described: point at the problem, inspect what the output *currently*
is, decide the expected behaviour, and log it as a test case that future runs
must keep satisfying.

Examples:
    # See what section 4 currently produces (helps you decide the assertion)
    python scripts/add_test_case.py inspect --section 4

    # Log a case: section 3's text must never contain a trailing "31"
    python scripts/add_test_case.py add --id qa_sec3_no_page_31 \\
        --section 3 --check plain_not_matches --arg "\\b31\\s*$" \\
        --desc "Sec 3: page number 31 must not bleed into text"

    # Log a case against a schedule leaf
    python scripts/add_test_case.py add --id fifteenth_is_table \\
        --schedule FIFTEENTH --check has_fbr_table --arg "" \\
        --desc "Fifteenth Schedule renders as a table"

Available checks: plain_contains, plain_not_contains, plain_not_matches,
html_contains, html_not_contains, html_matches, has_fbr_table,
has_subsection_li, footnote_text_nonempty, footnote_html_has_table,
body_not_starts_with.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

# Make tools/ importable so this works from any working directory. It used to say
# `from tests import checks, loader`, a package that has not existed since the suite
# moved to tools/suite/ -- so this script could not even start.
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Relies on the sys.path bootstrap above; corpus_paths also adds packages/.
from corpus_paths import LABELS, get  # noqa: E402
from suite import checks, loader  # noqa: E402
from suite.runner import cases_path_for  # noqa: E402


def _default_json(lane):
    hits = sorted(glob.glob(os.path.join(str(get(lane).output_path()), "*.json")))
    return hits[0] if hits else None


def _target(args):
    if args.section is not None:
        return {"kind": "section", "code": args.section}
    if args.schedule is not None:
        return {"kind": "schedule_leaf", "code": args.schedule}
    raise SystemExit("specify --section CODE or --schedule NAME")


def cmd_inspect(args):
    doc = loader.load(args.data or _default_json(args.lane))
    tgt = _target(args)
    leaf = loader.find_leaf(doc, tgt["kind"], tgt["code"])
    if leaf is None:
        print("target not found:", tgt)
        return 1
    print("=== code:", leaf.get("code"), "| heading:", leaf.get("heading"))
    print("--- plain_text (first 600) ---")
    print(leaf.get("plain_text", "")[:600])
    print("--- html (first 900) ---")
    print(leaf.get("html", "")[:900])
    print("--- footnotes ---")
    for fn in leaf.get("footnotes", [])[:12]:
        print(f"  {fn.get('ref')}: {fn.get('text','')[:60]}")
    return 0


def cmd_add(args):
    case = {
        "id": args.id,
        "source": args.source,
        "description": args.desc,
        "target": _target(args),
        "check": args.check,
        "arg": args.arg,
        "status": "known_gap" if args.known_gap else "active",
    }
    if args.applies_to:
        case["applies_to"] = args.applies_to
    if args.check not in checks.REGISTRY:
        raise SystemExit(f"unknown check {args.check!r}; see --help")

    # verify the case runs against the current output before saving
    data = args.data or _default_json(args.lane)
    if data and os.path.exists(data):
        doc = loader.load(data)
        msg = checks.run_case(doc, case)
        status = "PASSES now" if msg is None else f"FAILS now -> {msg}"
        print(f"[check against current output] {status}")

    cases = cases_path_for(args.lane)
    with open(cases, encoding="utf-8") as fh:
        reg = json.load(fh)
    if any(c["id"] == args.id for c in reg["cases"]):
        raise SystemExit(f"case id {args.id!r} already exists")
    reg["cases"].append(case)
    with open(cases, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2)
    print(f"added case {args.id!r} to {cases}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("lane", choices=LABELS,
                       help="which corpus's case file to inspect or append to")
        p.add_argument("--section", help="section code, e.g. 4 or 109A")
        p.add_argument("--schedule", help="schedule name fragment, e.g. FIFTEENTH")
        p.add_argument("--data", help="JSON to inspect/verify against (default: output/*.json)")

    pi = sub.add_parser("inspect", help="show a section/schedule's current output")
    common(pi)

    pa = sub.add_parser("add", help="log a new regression case")
    common(pa)
    pa.add_argument("--id", required=True)
    pa.add_argument("--check", required=True)
    pa.add_argument("--arg", default="")
    pa.add_argument("--desc", required=True)
    pa.add_argument("--source", default="manual")
    pa.add_argument("--applies-to", dest="applies_to",
                    help="scope to one edition: substring of metadata.filename "
                         "(e.g. '30.06.2024'); omit to run on every document")
    pa.add_argument("--known-gap", action="store_true",
                    help="track but don't count as a regression yet")

    args = ap.parse_args(argv)
    return {"inspect": cmd_inspect, "add": cmd_add}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
