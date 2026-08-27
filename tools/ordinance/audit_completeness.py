#!/usr/bin/env python3
"""Completeness audit: prove no PDF body/footnote content was dropped.

Legal text is unforgiving -- a missing "[", ".", or amendment marker changes
meaning.  This tool reconstructs the *source* text the pipeline saw (the zoned
body and footnote words for every page) and compares it, as multisets, against
what actually landed in the output JSON (section/leaf plain_text + table text +
footnote text).  It reports every token and every key punctuation mark that is
in the source but missing from the output.

Usage:
    python scripts/audit_completeness.py [output.json]        # uses pmcache + output/
    python scripts/audit_completeness.py --pdf INPUT.pdf      # scan the PDF directly

Exit code is non-zero if the drop exceeds the tolerance (CI-friendly).
"""

from __future__ import annotations

import argparse
import collections
import glob
import os
import re
import sys

# scripts/ lives one level below the repo root -- make the root importable and
# anchor all default paths there, so this works from any working directory.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from corpus_paths import output_dir  # noqa: E402 (sys.path bootstrap above)

# key punctuation that carries legal meaning and must be conserved
_PUNCT = "[](){}.,;:%—–\"'"


def _norm(text: str) -> str:
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")
    # Join a hyphen at a word boundary so the same compound conserves regardless
    # of how it is rendered: the source wraps it ("sub-\nsection") while the
    # RC-7-fixed output keeps the compound hyphen ("sub-section") -- both must
    # normalise to the same token ("subsection").  Matches a hyphen followed by
    # optional whitespace/newline and a lowercase letter (never a spaced em-dash
    # separator, which uses the "–"/"—" glyphs tracked as punctuation).
    text = re.sub(r"-\s*\n?\s*(?=[a-z])", "", text)
    # Collapse intra-word glyph spacing ("i n c o me" -> "income", RC-6d) on both
    # sides so the de-glyphed output conserves against the glyph-spaced source.
    text = re.sub(r"(?:\b[A-Za-z] ){2,}[A-Za-z][a-z]{0,3}\b",
                  lambda m: m.group(0).replace(" ", ""), text)
    return text


def _words(text: str):
    # alphabetic word tokens length >= 2 (digits excluded: markers become refs
    # like 33.2 and would create false diffs)
    return re.findall(r"[A-Za-z][A-Za-z'’]+", _norm(text))


def _punct_counts(text: str):
    c = collections.Counter(ch for ch in text if ch in _PUNCT)
    return c


# ---------------------------------------------------------------------------
# source (what the pipeline saw) and output (what it produced)
# ---------------------------------------------------------------------------

def source_from_cache(cache: str):
    import pickle
    body, foot = [], []
    for f in sorted(glob.glob(os.path.join(cache, "*.pkl")), key=lambda p: int(os.path.basename(p)[:-4])):
        pm = pickle.load(open(f, "rb"))
        for b in getattr(pm, "body_blocks", pm.body_lines):
            body.append(b.text())
        for ln in pm.footnote_lines:
            foot.append(ln.text())
    return "\n".join(body), "\n".join(foot)


def source_from_pdf(pdf_path: str):
    import pdfplumber

    from fbr_ingest.pagemodel import build_page_model
    from fbr_ingest.pipeline import _detect_toc_page_count
    pdf = pdfplumber.open(pdf_path)
    body, foot = [], []
    # skip exactly the TOC pages the pipeline itself skips -- the count is
    # edition-specific (2026: 19, 30.06.2024: 26, 31.07.2025: 1), and counting
    # TOC pages as body source fabricates "missing" words in the report
    toc_pages = _detect_toc_page_count(pdf)
    for i in range(toc_pages, len(pdf.pages)):
        pm = build_page_model(pdf.pages[i], i + 1)
        for b in pm.body_blocks:
            body.append(b.text())
        for ln in pm.footnote_lines:
            foot.append(ln.text())
    return "\n".join(body), "\n".join(foot)


def output_text(doc: dict):

    body_parts, foot_parts = [], []

    def visit(o):
        if not isinstance(o, dict):
            return
        # structural code + heading count as body text (they carry the CHAPTER/
        # PART/DIVISION/SCHEDULE words that live in structure, not leaf text)
        body_parts.append(o.get("code", "") or "")
        body_parts.append(o.get("heading", "") or "")
        if "plain_text" in o:
            body_parts.append(o["plain_text"])
            body_parts.append(re.sub(r"<[^>]+>", " ", o.get("html", "")))
        for fn in o.get("footnotes", []):
            foot_parts.append(fn.get("text", ""))
        for k in ("parts", "divisions", "sections"):
            for c in o.get(k, []):
                visit(c)

    for root in ("chapters", "schedules"):
        for node in doc.get(root, []):
            visit(node)
    pre = doc.get("preamble") or {}
    body_parts.append(pre.get("plain_text", ""))
    return "\n".join(body_parts), "\n".join(foot_parts)


def _report(label, src, out):
    sw, ow = collections.Counter(_words(src)), collections.Counter(_words(out))
    missing = sw - ow                       # words in source, short in output
    n_src = sum(sw.values())
    n_missing = sum(missing.values())
    sp, op = _punct_counts(src), _punct_counts(out)
    punct_missing = {p: sp[p] - op.get(p, 0) for p in _PUNCT if sp[p] - op.get(p, 0) > 0}
    pct = 100.0 * (n_src - n_missing) / n_src if n_src else 100.0
    print(f"--- {label} ---")
    print(f"  word tokens: source={n_src}  conserved={pct:.3f}%  missing={n_missing}")
    if missing:
        print("  top missing words:", dict(missing.most_common(15)))
    if punct_missing:
        print("  missing punctuation (source - output):", punct_missing)
    return n_missing, punct_missing


def _resolve_json(json_path, pdf_path, lane):
    """The output JSON this audit is about.

    An explicit positional argument always wins.  Otherwise it is derived from
    the PDF's own basename, because the documented invocation
    ``audit_completeness.py --pdf INPUT.pdf`` used to fall through to
    ``sorted(glob(output/*.json))[0]`` -- the ALPHABETICALLY FIRST document in
    the lane.  It therefore compared one document's source text against another
    document's output and printed the result as if it meant something: measured
    on Customs 2007 it reported "body 13.430% conserved, 49164 missing" for a
    document that is actually at 100.000%.  A wrong conservation number is worse
    than none, so an unresolvable pair is now an error rather than a guess.
    """
    if json_path:
        return json_path
    outdir = output_dir(lane)
    if pdf_path:
        stem = os.path.splitext(os.path.basename(pdf_path))[0].strip()
        cand = os.path.join(outdir, stem + ".json")
        if os.path.exists(cand):
            return cand
        # the corpus PDFs carry stray leading spaces and comma placement that the
        # output filename does not always reproduce verbatim; match on a squashed key
        def key(s):
            return re.sub(r"[^a-z0-9]", "", s.lower())
        want = key(stem)
        hits = [p for p in sorted(glob.glob(os.path.join(outdir, "*.json")))
                if key(os.path.splitext(os.path.basename(p))[0]) == want]
        if len(hits) == 1:
            return hits[0]
        raise SystemExit(
            f"error: cannot resolve the output JSON for {os.path.basename(pdf_path)!r} "
            f"in {outdir} ({len(hits)} candidates). Pass it explicitly as the first "
            f"positional argument.")
    raise SystemExit("error: pass the output JSON path, or --pdf so it can be derived.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Completeness audit of a converted JSON.")
    ap.add_argument("json_path", nargs="?")
    ap.add_argument("--pdf")
    ap.add_argument("--cache", help="page-model pickle cache dir (else use --pdf)")
    ap.add_argument("--max-missing", type=int, default=200,
                    help="fail if more than this many word tokens are dropped")
    args = ap.parse_args(argv)

    import json
    jpath = _resolve_json(args.json_path, args.pdf, "ordinance")
    doc = json.load(open(jpath, encoding="utf-8"))

    if args.pdf:
        s_body, s_foot = source_from_pdf(args.pdf)
    elif args.cache:
        s_body, s_foot = source_from_cache(args.cache)
    else:
        print("error: pass --pdf INPUT.pdf (or --cache DIR with page-model pickles)",
              file=sys.stderr)
        return 2
    o_body, o_foot = output_text(doc)

    print("=" * 66)
    print("COMPLETENESS AUDIT")
    nb, pb = _report("BODY (section/leaf text + table cells)", s_body, o_body)
    # footnotes: source footnote text vs output footnotes (union body+foot on
    # both sides, since a marker's note can be attached in either zone)
    nf, pf = _report("FOOTNOTES", s_foot, o_foot + "\n" + o_body)
    print("=" * 66)
    ok = nb <= args.max_missing
    print(f"RESULT: {'PASS' if ok else 'DROP DETECTED'} | body words missing={nb}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
