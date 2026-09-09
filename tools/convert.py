#!/usr/bin/env python3
"""Convert one FBR legal-text PDF into the structured JSON format.

    python tools/convert.py acts       "Acts/Customs Act 1969/....pdf"
    python tools/convert.py ordinance  "....pdf" -o out.json
    python tools/convert.py rules      "....pdf" --admit-below-floor

Replaces six files that said this between them: three 18-line `convert_<lane>.py`
shims which differed in three lines and loaded a sibling script by path through
`importlib.util.spec_from_file_location`, and three `<lane>_pdf_to_json.py` of which
two differed by a single import. The lane is an argument, and the pipeline behind it
comes from the one registry in `backend.services.corpus_registry`.

The output JSON is

    { "metadata": {...},
      "chapters":  [ {code, heading, parts, divisions, sections}, ... ],
      "schedules": [ ... ] }

where each leaf is
    { code, heading, page_number, html, plain_text,
      start_page, end_page, footnotes: [{ref, marker, text}, ...] }
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "tools"))

# Relies on the sys.path bootstrap above; also puts packages/ on the path.
from corpus_paths import LABELS, get  # noqa: E402
from legal_contract import stamp_run_provenance  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lane", choices=LABELS, help="which corpus this PDF belongs to")
    ap.add_argument("pdf", help="path to the input PDF")
    ap.add_argument("-o", "--output", help="output JSON path "
                    "(default: alongside the PDF)")
    ap.add_argument("--quiet", action="store_true", help="suppress progress output")
    ap.add_argument("--profile", choices=("lane", "auto"), default="auto",
                    help="how to choose the parser/profile. 'auto' (the default) "
                         "measures the document, refines the lane profile by "
                         "family, and routes flat Ordinance documents to "
                         "legal_ingest. 'lane' preserves the historical "
                         "lane-only parser and profile.")
    ap.add_argument("--admit-below-floor", action="store_true",
                    help="convert a scan whose inter-engine agreement is under "
                         "the fidelity floor instead of refusing it. The result "
                         "is written to _provisional/ beside the normal output, "
                         "never into it, and carries "
                         "metadata.ocr.provisional=true. Off by default. Only the "
                         "lanes with an OCR stage accept it.")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if not os.path.exists(args.pdf):
        print(f"error: file not found: {args.pdf}", file=sys.stderr)
        return 2

    def progress(msg):
        if not args.quiet:
            print(f"[{args.lane}] {msg}", file=sys.stderr)

    # The route is selected before loading a parser, so an Ordinance PDF can use
    # either fork without importing or merging them.  ParserRoute.load validates
    # its bound profile/auto kwargs before any conversion starts.
    try:
        route = get(args.lane).parser_for(args.pdf, profile=args.profile)
        run, kwargs = route.load()
    except (ImportError, KeyError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    progress(f"parser={route.package}"
             + (f" profile={route.profile}" if route.profile else ""))

    # Asked of the selected pipeline rather than recorded as another per-lane
    # fact: a route that grows an OCR stage starts accepting the flag without an
    # edit here.
    if "admit_below_floor" in inspect.signature(run).parameters:
        kwargs["admit_below_floor"] = args.admit_below_floor
    elif args.admit_below_floor:
        print(f"error: the {args.lane} pipeline has no OCR stage, so "
              f"--admit-below-floor does not apply", file=sys.stderr)
        return 2

    result = run(args.pdf, progress=progress, **kwargs)

    # Which conversion produced this file. The pipeline cannot know: `run()` is not
    # told its lane and has no opinion about revisions. This is the only writer, so
    # it is the only place that does know, and a file without these keys is one no
    # conversion wrote -- a suite fixture, or a direct `run()` call.
    stamp_run_provenance(result, args.lane)

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
    # Written through a temporary file in the same directory and renamed, because
    # `output/*.json` IS the corpus: a plain `open(out, "w")` truncates the previous
    # conversion the instant it opens, so a killed converter leaves a half-file in
    # the corpus and a sync running alongside reads it. `os.replace` is atomic
    # within a filesystem, so a reader sees the old file or the new one.
    tmp = f"{out}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, out)
    except BaseException:
        # Includes KeyboardInterrupt: an interrupted conversion must not leave its
        # scratch file behind for the next `output/*` glob to trip over.
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

    m = result["metadata"]
    progress(f"wrote {out}")
    progress(f"pages={m['total_pages']} chapters={m['chapters_count']} "
             f"schedules={m['schedules_count']} sections={m['sections_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
