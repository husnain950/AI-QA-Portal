#!/usr/bin/env python3
"""CLI: convert an FBR legal-text PDF into the structured JSON format.

Usage:
    python scripts/fbr_pdf_to_json.py INPUT.pdf [-o OUTPUT.json] [--quiet]

Example:
    python scripts/fbr_pdf_to_json.py "Income Tax Ordinance, 2001 Amended upto 20.02.2026.pdf"

The output JSON matches the schema of
``_Income_Tax_Ordinance__2001_Amended_upto_20.02.2026.json``:

    { "metadata": {...},
      "chapters":  [ {code, heading, parts, divisions, sections}, ... ],
      "schedules": [ ... ] }

where each leaf *section* is
    { code, heading, page_number, html, plain_text,
      start_page, end_page, footnotes: [{ref, marker, text}, ...] }
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# scripts/ lives one level below the repo root -- make the root importable and
# anchor all default paths there, so this works from any working directory.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from rules_ingest import run  # noqa: E402 (sys.path bootstrap above)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Convert an FBR PDF to structured JSON.")
    ap.add_argument("pdf", help="path to the input PDF")
    ap.add_argument("-o", "--output", help="output JSON path "
                    "(default: alongside the PDF)")
    ap.add_argument("--quiet", action="store_true", help="suppress progress output")
    ap.add_argument("--admit-below-floor", action="store_true",
                    help="convert a scan whose inter-engine agreement is under "
                         "the fidelity floor instead of refusing it. The result "
                         "is written to _provisional/ beside the normal output, "
                         "never into it, and carries "
                         "metadata.ocr.provisional=true. Off by default.")
    args = ap.parse_args(argv)

    if not os.path.exists(args.pdf):
        print(f"error: file not found: {args.pdf}", file=sys.stderr)
        return 2

    def progress(msg):
        if not args.quiet:
            print(f"[fbr] {msg}", file=sys.stderr)

    result = run(args.pdf, progress=progress,
                 admit_below_floor=args.admit_below_floor)

    out = args.output or os.path.splitext(args.pdf)[0] + ".json"
    # A provisional document must not be able to reach the corpus, and this is
    # the ONLY writer, so the redirect belongs here rather than in every caller.
    # The corpus is defined as output/*.json -- P08 is the anomaly where a file
    # the gate had refused stayed in the corpus because nothing owned the point
    # of withdrawal, and admitting sub-floor text without a separate lane would
    # recreate exactly that.
    if (result["metadata"].get("ocr") or {}).get("provisional"):
        d, base = os.path.split(os.path.abspath(out))
        out = os.path.join(d, "_provisional", base)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        progress(f"PROVISIONAL -- not part of the corpus; writing to {out}")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    m = result["metadata"]
    progress(f"wrote {out}")
    progress(f"pages={m['total_pages']} chapters={m['chapters_count']} "
             f"schedules={m['schedules_count']} sections={m['sections_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
