#!/usr/bin/env python3
"""Structure + text-density table over every converted JSON.

The number that gates conversions lived only inside
``tests.invariants.inv_text_density_plausible`` and was only ever printed when a
file FAILED, so "how is Phase 2 doing" could not be answered without hand-rolling
the same loop -- which is how a table got taken mid-reconversion and believed.

The summation deliberately mirrors that invariant line for line (``plain_text``
plus tag-stripped ``html`` over every leaf, plus the preamble, divided by
``total_pages - toc_pages_scanned``).  It therefore counts the same words twice,
because plain and html hold the same text -- so the printed density is roughly
2x true characters per page, and the floor of 200 is really about 100.  Matching
the gate matters more than being pretty; do not "fix" one without the other.

Usage:
    python3 scripts/density_table.py                # every output/*.json
    python3 scripts/density_table.py --phase 2      # Phase-2 only
    python3 scripts/density_table.py --stale        # flag outputs older than the code
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tests.loader import iter_all_leaves            # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
FLOOR = 200
TAGS = re.compile(r"<[^>]+>")
#: the three consolidated Phase-1 families; everything else is Phase 2
FAMILIES = {"customs": "customs", "sales tax": "salestax", "excise": "excise"}


def family(name: str) -> str:
    low = name.lower()
    for key, fam in FAMILIES.items():
        if key in low:
            return fam
    return "phase2"


def measure(path: str) -> dict:
    doc = json.load(open(path, encoding="utf-8"))
    meta = doc.get("metadata") or {}
    chars = 0
    for leaf in iter_all_leaves(doc):
        chars += len(leaf.get("plain_text") or "")
        chars += len(TAGS.sub(" ", leaf.get("html") or ""))
    chars += len((doc.get("preamble") or {}).get("plain_text") or "")
    pages = (meta.get("total_pages") or 0) - (meta.get("toc_pages_scanned") or 0)
    ocr = meta.get("ocr") or {}
    return {
        "name": os.path.basename(path),
        "family": family(os.path.basename(path)),
        "pages": pages,
        "chapters": meta.get("chapters_count") or 0,
        "sections": meta.get("sections_count") or 0,
        "schedules": meta.get("schedules_count") or 0,
        "density": round(chars / pages) if pages > 0 else 0,
        "agree": ocr.get("mean_agreement"),
        "flagged": ocr.get("needs_review_tokens"),
        "mtime": os.path.getmtime(path),
    }


def newest_code_mtime() -> float:
    """Latest mtime across acts_ingest -- an output older than this is stale."""
    return max(os.path.getmtime(p) for p in glob.glob(str(ROOT / "acts_ingest" / "*.py")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", type=int, choices=(1, 2))
    ap.add_argument("--stale", action="store_true",
                    help="mark outputs older than the newest acts_ingest module")
    args = ap.parse_args()

    rows = [measure(p) for p in sorted(glob.glob(str(ROOT / "output" / "*.json")))]
    if args.phase == 2:
        rows = [r for r in rows if r["family"] == "phase2"]
    elif args.phase == 1:
        rows = [r for r in rows if r["family"] != "phase2"]
    if not rows:
        print("no outputs matched", file=sys.stderr)
        return 2
    code_mtime = newest_code_mtime() if args.stale else 0.0

    rows.sort(key=lambda r: (r["family"], r["density"]))
    print(f"{'file':56} {'pg':>4} {'ch':>3} {'sec':>4} {'sch':>3} "
          f"{'c/pg':>6} {'ocr%':>6} {'flag':>5}  notes")
    for r in rows:
        notes = []
        if r["density"] < FLOOR:
            notes.append("BELOW FLOOR")
        if not r["sections"] and not r["schedules"]:
            notes.append("NO STRUCTURE")
        if args.stale and r["mtime"] < code_mtime:
            notes.append("STALE")
        print(f"{r['name'][:56]:56} {r['pages']:>4} {r['chapters']:>3} "
              f"{r['sections']:>4} {r['schedules']:>3} {r['density']:>6} "
              f"{(f'{r['agree']:.1f}' if r['agree'] is not None else '-'):>6} "
              f"{(r['flagged'] if r['flagged'] is not None else '-'):>5}  "
              f"{', '.join(notes)}")

    below = sum(1 for r in rows if r["density"] < FLOOR)
    nostruct = sum(1 for r in rows if not r["sections"] and not r["schedules"])
    stale = sum(1 for r in rows if args.stale and r["mtime"] < code_mtime)
    print(f"\n{len(rows)} file(s)   sections {sum(r['sections'] for r in rows)}   "
          f"below floor {below}   no structure {nostruct}"
          + (f"   stale {stale}" if args.stale else ""))
    return 1 if (below or nostruct) else 0


if __name__ == "__main__":
    raise SystemExit(main())
