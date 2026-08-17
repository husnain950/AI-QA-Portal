#!/usr/bin/env python3
"""Which SOURCE LINES the conservation audit's missing words came from.

``audit_completeness.py`` says *how many* words were dropped and which ones;
it cannot say *where they were printed*, and "which words" alone is easy to
misread -- ``{'ART': 258}`` sat at the top of a histogram for weeks before P16
showed it was a running header, not lost statute.  This walks the same page
model the pipeline saw, scores every source line by how many still-missing
tokens it carries, and prints the worst lines with their page and zone.

    python scripts/why_missing.py "output/Finance Act, 2014.json" --pdf "Acts/.../x.pdf"
    python scripts/why_missing.py OUT.json --pdf IN.pdf --zone footnotes --lines 40

A line is reported ``ABSENT`` when its own words are the missing ones, and
``partial`` when only some are -- the difference between text that never reached
a leaf and text that was split across one.  Read the PAGE RANGE first: a
contiguous run of absent lines is one region that lost its container, which is a
different defect from absences scattered across the document.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.audit_completeness import _words, join_dropcaps, output_text  # noqa: E402


def source_lines(pdf_path: str):
    """``[(page, zone, text)]`` for every zoned line, in document order.

    Deliberately the same construction as ``audit_completeness.source_from_pdf``
    -- same calibration, same skipped TOC pages -- so the tokens it reports as
    missing are exactly the ones the gate reports.  A probe that zones its input
    differently from the gate measures the difference between two page models.
    """
    import pdfplumber

    from acts_ingest.calibrate import calibrate
    from acts_ingest.pagemodel import build_page_model

    pdf = pdfplumber.open(pdf_path)
    cal = calibrate(pdf)
    out = []
    for i in range(cal.toc_pages, len(pdf.pages)):
        pm = build_page_model(pdf.pages[i], i + 1, cal, pdf_path)
        for b in pm.body_blocks:
            out.append((i + 1, "body", b.text()))
        for ln in pm.footnote_lines:
            out.append((i + 1, "foot", ln.text()))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--zone", choices=("body", "footnotes"), default="body")
    ap.add_argument("--lines", type=int, default=25, help="worst N lines to print")
    ap.add_argument("--top", type=int, default=20, help="missing words to list")
    ap.add_argument("--width", type=int, default=110)
    args = ap.parse_args(argv)

    doc = json.load(open(args.json_path, encoding="utf-8"))
    o_body, o_foot = output_text(doc)
    src = source_lines(args.pdf)

    if args.zone == "body":
        keep, out_text = "body", o_body
    else:
        # same union the gate uses: a marker's note can be attached in either zone
        keep, out_text = "foot", o_foot + "\n" + o_body

    ow = collections.Counter(_words(out_text))
    # same drop-cap join the gate applies, so this probe's missing set is exactly
    # the gate's -- a probe normalising differently reports different words
    src = [(p, z, join_dropcaps(t, set(ow))) for p, z, t in src]
    s_text = "\n".join(t for _p, z, t in src if z == keep)
    sw = collections.Counter(_words(s_text))
    missing = sw - ow
    print(f"{args.zone}: source={sum(sw.values())} missing={sum(missing.values())}")
    if not missing:
        return 0
    print("top missing words:", dict(missing.most_common(args.top)))

    # A token histogram cannot tell "this line never reached a leaf" from "this
    # word is one short somewhere in the document", because the comparison is a
    # multiset over the whole edition: a line is flagged merely for CONTAINING a
    # globally-short token.  That is how a 45-word residue reads as 30 damaged
    # pages when it is really one dropped region.  So test the line's own WORD
    # SEQUENCE: if no 4-gram of it survives anywhere in the output, the line
    # itself is absent -- and that is reflow-proof, which a substring test is not.
    ow_grams = set()
    otoks = _words(out_text)
    for i in range(len(otoks) - 3):
        ow_grams.add(tuple(otoks[i:i + 4]))

    absent, partial = [], []
    for page, zone, text in src:
        if zone != keep:
            continue
        toks = _words(text)
        if not toks:
            continue
        hit = sum(1 for t in toks if missing.get(t))
        if not hit:
            continue
        grams = [tuple(toks[i:i + 4]) for i in range(len(toks) - 3)]
        # too short to shingle: fall back to "are ALL its tokens missing?"
        gone = (not any(g in ow_grams for g in grams)) if grams \
            else all(missing.get(t) for t in toks)
        (absent if gone else partial).append((hit, page, text))

    print(f"\nlines carrying a missing token: {len(absent) + len(partial)}"
          f"  ({len(absent)} whose own text is ABSENT from the output)")
    if absent:
        print(f"ABSENT pages: {sorted({p for _h, p, _t in absent})}")
    print(f"\n{'page':>5} {'miss':>4}  line")
    for hit, page, text in sorted(absent, key=lambda r: r[1])[:args.lines]:
        print(f"{page:5d} {hit:4d}  [ABSENT ] {text.strip()[:args.width]}")
    shown = max(0, args.lines - len(absent))
    for hit, page, text in sorted(partial, key=lambda r: (-r[0], r[1]))[:shown]:
        print(f"{page:5d} {hit:4d}  [partial] {text.strip()[:args.width]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
