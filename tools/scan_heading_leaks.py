#!/usr/bin/env python3
"""Scan staged Acts (and Rules) JSON for the heading-glue / stub / apparatus class.

Enumerates every Customs, Sales Tax and Federal Excise edition and reports:

  * ALL-CAPS chapter-caption runs in a section heading
  * ``LEGAL REFERENCE`` / ``LEGAL REFERENCS`` in body text
  * heading-only non-omitted leaves
  * body-printed ``CHAPTER N`` missing from the tree

Hits are either a parser miss or a traced exemption -- no third state.

    python tools/scan_heading_leaks.py              # acts + rules, if staged
    python tools/scan_heading_leaks.py acts         # one lane

Exits 0 with SKIP when the corpus is not staged (CI).
"""

from __future__ import annotations

import glob
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "tools"))

from corpus_paths import get  # noqa: E402
from suite import loader  # noqa: E402
from suite.invariants import _common  # noqa: E402

_FAMILIES = ("Customs", "Sales Tax", "Federal Excise")
_INVARIANTS = (
    "no_chapter_caption_in_section_heading",
    "no_footnote_text_in_body",
    "section_carries_its_body",
    "no_foreign_section_start_in_body",
    "body_chapters_in_tree",
)


def _family(filename: str) -> str | None:
    for name in _FAMILIES:
        if name.lower() in filename.lower():
            return name
    return None


def scan_lane(lane: str) -> list[dict]:
    paths = sorted(glob.glob(os.path.join(str(get(lane).output_path()), "*.json")))
    hits: list[dict] = []
    for path in paths:
        base = os.path.basename(path)
        if base.startswith("_"):
            continue
        family = _family(base)
        if family is None:
            continue
        doc = loader.load(path)
        for name in _INVARIANTS:
            fn = getattr(_common, f"inv_{name}")
            failures = fn(doc)
            for msg in failures:
                hits.append({
                    "lane": lane,
                    "family": family,
                    "file": base,
                    "invariant": name,
                    "message": msg,
                })
    return hits


def main(argv: list[str] | None = None) -> int:
    lanes = argv or sys.argv[1:] or ["acts", "rules"]
    all_hits: list[dict] = []
    scanned = 0
    for lane in lanes:
        out = get(lane).output_path()
        n = len(glob.glob(os.path.join(str(out), "*.json")))
        if n == 0:
            print(f"SKIP {lane}: no JSON under {out}")
            continue
        scanned += n
        hits = scan_lane(lane)
        all_hits.extend(hits)
        print(f"{lane}: scanned family editions, {len(hits)} hit(s)")

    if scanned == 0:
        print("SKIP: no staged corpus")
        return 0

    for h in all_hits:
        print(f"  [{h['family']}] {h['file']}: {h['invariant']}: {h['message']}")
    print(f"{len(all_hits)} hit(s) across {scanned} JSON file(s)")
    return 1 if all_hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
