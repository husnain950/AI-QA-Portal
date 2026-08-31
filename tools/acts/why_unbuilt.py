#!/usr/bin/env python3
"""Explain, per TOC entry, why ``build_sections`` did or did not place it.

    python tools/acts/why_unbuilt.py "Acts/Customs Act, 1969/....pdf" [--first 40]

Prints the code, its expected PDF page (printed + offset), the pages where the
body actually opens with that code, which resolution branch fired, and the
monotonic cursor.  Written because a stub section is a *cascade*: one bad
resolution advances the ``last`` cursor past everything after it, so reading the
FIRST failure is the only way to find the real cause -- the other 38 are shadow.
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings

warnings.filterwarnings("ignore")

# tools/acts/ -> tools/ -> the repo root.  Two levels of dirname reached `tools/`
# only, and `packages/` was never added at all, so every invocation of this script
# died on `ModuleNotFoundError: No module named 'legal_ingest'` -- the one
# diagnostic written for the stub-section cascade could not be run.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_ROOT, os.path.join(_ROOT, "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pdfplumber  # noqa: E402

from legal_ingest.builder import (  # noqa: E402
    LineRef,
    _candidate_code,
    _dotless_candidate_code,
)
from legal_ingest.calibrate import calibrate  # noqa: E402
from legal_ingest.pagemodel import build_page_model  # noqa: E402
from legal_ingest.pipeline import _page_starts_schedules, _toc_lines  # noqa: E402
from legal_ingest.profiles import BY_LABEL  # noqa: E402
from legal_ingest.toc import parse_toc  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--first", type=int, default=40,
                    help="report only the first N entries (default 40)")
    ap.add_argument("--code", help="report just this code, verbosely")
    ap.add_argument("--lane", default="acts", choices=sorted(BY_LABEL),
                    help="which printer profile to read the document with "
                         "(default acts). Both calibrate() and parse_toc() take "
                         "one and the pipeline always passes it; this script did "
                         "not, so every RULES document was measured with the Acts "
                         "folio, leader and ordinal settings -- wrong page offset, "
                         "wrong TOC row count, and a stub cascade reported at the "
                         "wrong entry. The rules lane holds a third of the register.")
    args = ap.parse_args()

    profile = BY_LABEL[args.lane]
    pdf = pdfplumber.open(args.pdf)
    cal = calibrate(pdf, profile=profile)
    chapters, schedules, ordered = parse_toc(_toc_lines(pdf, cal.toc_pages), profile)
    offset = cal.page_offset
    print(f"toc_pages={cal.toc_pages} offset={offset} zone={cal.zone_mode} "
          f"sections={len(ordered)}")

    first_body = (min(s.printed_page for s in ordered) + offset
                  if ordered else cal.toc_pages + 1)
    body_refs: list[LineRef] = []
    sched_started = False
    for pidx in range(first_body, len(pdf.pages) + 1):
        pm = build_page_model(pdf.pages[pidx - 1], pidx, cal)
        if not sched_started and _page_starts_schedules(pm):
            sched_started = True
        if sched_started:
            continue
        for ln in pm.body_blocks:
            body_refs.append(LineRef(page=pidx, line=ln))
    pdf.close()

    positions: dict[str, list[int]] = {}
    for i, ref in enumerate(body_refs):
        cc = _candidate_code(ref.line) or _dotless_candidate_code(ref.line)
        if cc:
            positions.setdefault(cc, []).append(i)

    print(f"body_refs={len(body_refs)} distinct codes found in body={len(positions)}\n")
    print(f"{'code':8s} {'exp':>5s} {'found pages':28s} {'branch':16s} cursor")

    last = -1
    shown = 0
    for k, entry in enumerate(ordered):
        expected = entry.printed_page + offset
        allpos = positions.get(entry.code, [])
        avail = [p for p in allpos if p > last]
        branch, chosen = "NONE", None
        for tol in (2, 4, 8):
            near = [p for p in avail if abs(body_refs[p].page - expected) <= tol]
            if near:
                chosen = min(near, key=lambda p: (abs(body_refs[p].page - expected), p))
                branch = f"page-anchor tol{tol}"
                break
        if chosen is not None:
            last = chosen

        if args.code and entry.code != args.code:
            continue
        if not args.code and shown >= args.first and branch != "NONE":
            continue
        shown += 1
        pages = sorted({body_refs[p].page for p in allpos})
        note = ""
        if branch == "NONE":
            if not allpos:
                note = "code never opens a body line"
            elif not avail:
                note = f"all {len(allpos)} occurrence(s) BEFORE cursor (blocked)"
            else:
                d = min(abs(body_refs[p].page - expected) for p in avail)
                note = f"nearest available occurrence is {d} page(s) away"
        print(f"{entry.code:8s} {expected:5d} {str(pages[:6])[:28]:28s} "
              f"{branch:16s} {last:6d} {note}")
        if args.code:
            for p in allpos:
                mark = ">>" if p == chosen else ("--" if p <= last else "  ")
                print(f"      {mark} idx={p} page={body_refs[p].page} "
                      f"{body_refs[p].line.text()[:78]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
