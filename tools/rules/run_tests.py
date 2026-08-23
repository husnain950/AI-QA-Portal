#!/usr/bin/env python3
"""Post-conversion regression test runner.

Runs global invariants + the data-driven case registry (tests/cases.json)
against a converted JSON, so that fixing one issue can't silently break another.

Usage:
    python scripts/run_tests.py                      # test EVERY JSON in ./output/
    python scripts/run_tests.py path/to/output.json  # test a specific JSON
    python scripts/run_tests.py --pdf INPUT.pdf      # (re)convert first, then test
    python scripts/run_tests.py --json out.json      # write full machine-readable report

Exit code is non-zero if any invariant or active case fails (CI-friendly).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

# This tool lives at tools/<pipeline>/; the repo root is two levels up. The suite is
# a sibling package, imported as ``suite`` rather than ``tests`` so it cannot collide
# with tools/tests (the deploy-script tests), which is a different package entirely.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _path in (_HERE, os.path.join(_ROOT, "tools")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Both rely on the sys.path bootstrap above; corpus_paths also puts packages/ there.
from suite import loader, runner  # noqa: E402

from corpus_paths import output_dir  # noqa: E402


def _default_jsons() -> list[str]:
    """Every JSON in the CORPUS_RULES corpus -- the bare command gates ALL editions.

    (It used to test only whichever file sorted first, which silently gated
    the 30.06.2024 edition and nothing else.)
    """
    return sorted(glob.glob(os.path.join(str(output_dir("rules")), "*.json")))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run post-conversion regression tests.")
    ap.add_argument("json_path", nargs="?", help="converted JSON to test")
    ap.add_argument("--pdf", help="convert this PDF first, then test its output")
    ap.add_argument("--json", dest="report", help="write full JSON report to this path")
    args = ap.parse_args(argv)

    if args.pdf:
        from rules_ingest import run as convert
        out = os.path.splitext(args.pdf)[0] + ".json"
        print(f"[tests] converting {args.pdf} ...", file=sys.stderr)
        result = convert(args.pdf)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        targets = [out]
    elif args.json_path:
        targets = [args.json_path]
    else:
        targets = _default_jsons()

    targets = [t for t in targets if os.path.exists(t)]
    if not targets:
        print("error: no JSON to test (pass a path, put one in ./output/, or use --pdf)",
              file=sys.stderr)
        return 2

    all_ok, all_results = True, {}
    for json_path in targets:
        if len(targets) > 1:
            print(f"\n########## {os.path.basename(json_path)} ##########")
        doc = loader.load(json_path)
        results = runner.run(doc)
        report, ok = runner.summarize(results)
        print(report)
        all_ok = all_ok and ok
        all_results[json_path] = results
    if args.report:
        payload = (all_results[targets[0]] if len(targets) == 1
                   else all_results)
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
