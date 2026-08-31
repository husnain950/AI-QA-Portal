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
import importlib
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lane", choices=LABELS, help="which corpus this PDF belongs to")
    ap.add_argument("pdf", help="path to the input PDF")
    ap.add_argument("-o", "--output", help="output JSON path "
                    "(default: alongside the PDF)")
    ap.add_argument("--quiet", action="store_true", help="suppress progress output")
    ap.add_argument("--profile", choices=("lane", "auto"), default="lane",
                    help="how to choose the parse profile. 'lane' (the default) "
                         "uses the corpus the PDF was filed under, which is how "
                         "this has always worked. 'auto' measures the document "
                         "and asks legal_ingest.families -- the only way an "
                         "amending instrument gets the amending profile, since "
                         "the Acts corpus holds both kinds and a filename cannot "
                         "tell them apart. A lane whose pipeline takes no profile "
                         "ignores it.")
    ap.add_argument("--admit-below-floor", action="store_true",
                    help="convert a scan whose inter-engine agreement is under "
                         "the fidelity floor instead of refusing it. The result "
                         "is written to _provisional/ beside the normal output, "
                         "never into it, and carries "
                         "metadata.ocr.provisional=true. Off by default. Only the "
                         "lanes with an OCR stage accept it.")
    args = ap.parse_args(argv)

    if not os.path.exists(args.pdf):
        print(f"error: file not found: {args.pdf}", file=sys.stderr)
        return 2

    run = importlib.import_module(get(args.lane).package).run

    def progress(msg):
        if not args.quiet:
            print(f"[{args.lane}] {msg}", file=sys.stderr)

    # Asked of the pipeline rather than recorded as another per-lane fact: the
    # Ordinance has no OCR stage, so its `run` has no such parameter, and a lane
    # that grows one starts accepting the flag without an edit here.
    kwargs = {}
    if args.profile == "auto":
        # ``auto``, not ``profile=None``: the lane's own profile stays bound by
        # the partial in acts_ingest/rules_ingest and is the FALLBACK the family
        # overrides. Passing None instead threw it away, which is how
        # --profile auto came to parse all 34 consolidated Rules documents as
        # Acts (wip/phase2-findings.md finding 1).
        if "auto" not in inspect.signature(run).parameters:
            print(f"error: the {args.lane} pipeline takes no profile, so "
                  f"--profile auto does not apply", file=sys.stderr)
            return 2
        kwargs["auto"] = True
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
