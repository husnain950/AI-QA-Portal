#!/usr/bin/env python3
"""Run one lane's post-conversion regression suite.

Replaces three copies of ``tools/<lane>/run_tests.py`` that differed only in the lane
name, the ingest package they imported, and the corpus variable they read. The lane is
an argument now, and everything behind it -- corpus root, ingest package, invariants
module, cases file -- comes from the one registry in
:mod:`backend.services.corpus_registry`.

    python tools/run_suite.py acts                     # every edition in the corpus
    python tools/run_suite.py acts path/to/one.json    # one converted JSON
    python tools/run_suite.py rules --pdf some.pdf     # convert first, then test
"""

from __future__ import annotations

import argparse
import glob
import importlib
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "tools"))

# Relies on the sys.path bootstrap above; also puts packages/ on the path.
from corpus_paths import LABELS, get  # noqa: E402
from suite import loader, runner  # noqa: E402


def _default_jsons(lane: str) -> list[str]:
    """Every JSON in the lane's corpus -- the bare command gates ALL editions.

    (It used to test only whichever file sorted first, which silently gated
    the 30.06.2024 edition and nothing else.)
    """
    return sorted(glob.glob(os.path.join(str(get(lane).output_path()), "*.json")))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run post-conversion regression tests.")
    ap.add_argument("lane", choices=LABELS, help="which corpus to test")
    ap.add_argument("json_path", nargs="?", help="converted JSON to test")
    ap.add_argument("--pdf", help="convert this PDF first, then test its output")
    ap.add_argument("--json", dest="report", help="write full JSON report to this path")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    lane = args.lane

    if args.pdf:
        convert = importlib.import_module(get(lane).package).run
        out = os.path.splitext(args.pdf)[0] + ".json"
        print(f"[tests] converting {args.pdf} ...", file=sys.stderr)
        result = convert(args.pdf)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        targets = [out]
    elif args.json_path:
        targets = [args.json_path]
    else:
        targets = _default_jsons(lane)

    targets = [t for t in targets if os.path.exists(t)]
    if not targets:
        print(f"error: no JSON to test for {lane} (pass a path, convert into "
              f"{get(lane).output_path()}, or use --pdf)", file=sys.stderr)
        return 2

    invariants = runner.invariants_for(lane)
    cases_path = runner.cases_path_for(lane)
    exemptions_path = runner.exemptions_path_for(lane)

    all_ok, all_results = True, {}
    for json_path in targets:
        if len(targets) > 1:
            print(f"\n########## {os.path.basename(json_path)} ##########")
        doc = loader.load(json_path)
        results = runner.run(doc, invariants, cases_path, exemptions_path)
        report, ok = runner.summarize(results)
        print(report)
        all_ok = all_ok and ok
        all_results[json_path] = results
    if args.report:
        payload = all_results[targets[0]] if len(targets) == 1 else all_results
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
