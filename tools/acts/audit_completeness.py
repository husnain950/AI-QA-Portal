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
    # Only when the run is uniformly cased: a glyph-spaced word is spaced letter by
    # letter in ONE case, whereas a mixed run is two different things next to each
    # other.  Finance Act 2022 prints the degree symbol as a superscript, so its
    # source line reads "at a temperature of 20 o C in closed containers" and this
    # collapse turned "o C in" into the token "oCin" -- while the output renders
    # "20 oC in" from the x-gaps, giving 2 phantom missing words on a 162,417-word
    # edition, i.e. exactly enough to miss the 99.99% gate.
    def _collapse(m):
        run = m.group(0)
        letters = [c for c in run if c.isalpha()]
        if all(c.islower() for c in letters) or all(c.isupper() for c in letters):
            return run.replace(" ", "")
        return run
    text = re.sub(r"(?:\b[A-Za-z] ){2,}[A-Za-z][a-z]{0,3}\b", _collapse, text)
    return text


def _words(text: str):
    # alphabetic word tokens length >= 2 (digits excluded: markers become refs
    # like 33.2 and would create false diffs)
    return re.findall(r"[A-Za-z][A-Za-z'’]+", _norm(text))


def _punct_counts(text: str):
    c = collections.Counter(ch for ch in text if ch in _PUNCT)
    return c


#: the drop cap -- ONE capital, then an all-caps continuation ("A CT", "W HEREAS")
_DROPCAP_RE = re.compile(r"\b([A-Z]) ([A-Z]{2,})\b")
#: a mid-word split -- both fragments at least two letters ("Cust oms", "fol lowing").
#: The two-letter floor is what keeps ordinary prose out: with a one-letter
#: fragment allowed, "to a"/"of a"/"or a" joined to "toa"/"ofa"/"ora" wherever the
#: OUTPUT carried a jammed word of that spelling, and Finance Act 2011-12's
#: measured loss went from 25 words to 38 -- the audit inventing the very defect
#: `no_jammed_words` exists to report.  A single letter also cannot be in the
#: vocabulary (`_words` needs two characters), so guard 2 below cannot see it.
_SPLIT_WORD_RE = re.compile(r"\b([A-Za-z]{2,6}) ([a-z]{2,6})\b")


_AFFIX_RE = re.compile(r"^([^A-Za-z]*)([A-Za-z]*)(.*)$", re.S)


def _split_affix(tok: str):
    """``(leading punctuation, letters, trailing rest)`` for one token."""
    m = _AFFIX_RE.match(tok)
    return m.group(1), m.group(2), m.group(3)


def _joinable(a: str, b: str, out_vocab) -> bool:
    """Whether ``a`` + ``b`` is one word the source split and the output did not.

    Two accepted shapes, and nothing else:

    * the gazette DROP CAP -- one capital then an all-caps continuation
      (``A`` + ``CT``, ``W`` + ``HEREAS``)
    * a mid-word split whose halves are BOTH at least two letters
      (``Cust`` + ``oms``, ``fol`` + ``lowing``)

    The two-letter floor on the second shape is load-bearing.  With a one-letter
    fragment allowed, ``to a`` / ``of a`` / ``or a`` joined to ``toa``/``ofa``/``ora``
    wherever the OUTPUT carried a jammed word of that spelling, and Finance Act
    2011-12's measured loss went from 25 words to 38 -- the audit copying onto the
    source side the very defect ``no_jammed_words`` exists to report.  A single
    letter is also invisible to guard 2, because ``_words`` needs two characters
    for a token to be in the vocabulary at all.
    """
    if len(a) < 1 or len(b) < 2:
        return False
    joined = a + b
    if joined not in out_vocab:
        return False
    if len(a) == 1 and a.isupper() and b.isupper():
        return True                              # the drop cap
    if not (2 <= len(a) <= 6 and 2 <= len(b) <= 6 and b.islower()):
        return False
    # A mid-word split leaves fragments that are not words.  Requiring BOTH to be
    # absent from the output vocabulary is what separates it from prose, and it has
    # to be BOTH: with only "b is not a word", ``in sub-section`` joined to
    # ``insub-section`` on Finance Act 2013 -- because ``in`` is a word, ``sub`` is
    # not, and the output happens to carry ``insub`` from a line-break artifact --
    # inventing 35 missing words out of 49.  Refusing a real split whose first half
    # is also a word ("to tal") costs one reported word; accepting prose costs the
    # measurement.
    return a not in out_vocab and b not in out_vocab


def join_split_words(text: str, out_vocab):
    """Rejoin a word the SOURCE LINE spaces and the output does not.

    Both sides read the same word boxes, but they join them by different rules:
    a page-model *line* puts a space between every box, while the pipeline's
    renderer decides from the x-gaps.  Wherever the source spaces a word mid-glyph
    the audit therefore scored a phantom loss:

    * the gazette DROP CAP -- ``A CT NO. X OF 2024``, ``W HEREAS , it is
      expedient`` -- reported as ``{'CT': 2, 'HEREAS': 1}`` on Finance Act 2024,
      2025 and Tax Laws (Amdt) 2024 (``_words`` drops single letters, so ``A``/``W``
      vanished and ``CT``/``HEREAS`` had nothing to match)
    * a mid-word split on a scan -- Pakistan Single Window 2021 prints
      ``the provisions of the Cust oms Act, 1969`` where the output correctly
      emits ``Customs``

    ``_norm`` already collapses the longer form of this (``i n c o me``) and joins
    line-break hyphenation, so this is the same normalisation continued, not a new
    allowance.  Two guards keep it from hiding a real absence:

    1. the joined form must be a word the OUTPUT actually contains -- otherwise
       ``REGISTRATION OF A COMPANY`` would collapse to ``ACOMPANY`` on the source
       side only and INVENT two missing words;
    2. it must not be two words that both stand alone in the output, so ordinary
       prose (``in come``, ``sub section``) is left exactly as printed even when
       the document also contains ``income``.

    Counts are preserved either way: a source printing the drop cap twice against
    one output occurrence still reports one word missing.
    """
    # Walked as a TOKEN STREAM, not with re.sub: a substitution advances past its
    # whole match, so in "the fol lowing" the failed pair "the fol" consumed "fol"
    # and the real split "fol lowing" was never tested.
    # Split on ALL whitespace runs and keep them: with only " " as the separator a
    # newline stays glued inside a token ("information:—\nA"), whose trailing text
    # then blocks the join -- which is why the drop cap joined per line but not in
    # the gate's newline-joined source text.
    out, parts = [], re.split(r"(\s+)", text)
    i = 0
    while i < len(parts):
        if i + 2 < len(parts) and parts[i + 1] == " ":
            a, b = parts[i], parts[i + 2]
            pa, ca, sa = _split_affix(a)
            pb, cb, sb = _split_affix(b)
            # ``b`` must be a WHOLE word: a trailing run that still carries letters
            # means its letters are only a fragment ("sub" out of "sub-section"),
            # and joining on that turned every "in sub-section" in Finance Act 2013
            # into "insub-section".
            if (not sa and not pb and not re.search(r"[A-Za-z]", sb)
                    and _joinable(ca, cb, out_vocab)):
                out.append(pa + ca + cb)
                parts[i + 2] = sb          # the joined pair keeps b's punctuation
                i += 2
                continue
        out.append(parts[i])
        i += 1
    return "".join(out)


# the name this was introduced under (ledger P20), kept so older callers work
join_dropcaps = join_split_words


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

    from acts_ingest.calibrate import calibrate
    from acts_ingest.pagemodel import build_page_model
    pdf = pdfplumber.open(pdf_path)
    body, foot = [], []
    # Skip exactly the TOC pages the pipeline itself skips, and zone each page
    # with the same calibration -- counting TOC pages as body source fabricates
    # "missing" words, and zoning them differently from the pipeline would make
    # the audit measure the difference between two page models rather than
    # between the source and the output.
    cal = calibrate(pdf)
    toc_pages = cal.toc_pages
    for i in range(toc_pages, len(pdf.pages)):
        # pdf_path so a SCANNED page's OCR text counts as source too --
        # otherwise the audit compares a blank source against real output
        pm = build_page_model(pdf.pages[i], i + 1, cal, pdf_path)
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
    ow = collections.Counter(_words(out))
    src = join_dropcaps(src, set(ow))
    sw = collections.Counter(_words(src))
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Completeness audit of a converted JSON.")
    ap.add_argument("json_path", nargs="?")
    ap.add_argument("--pdf")
    ap.add_argument("--cache", help="page-model pickle cache dir (else use --pdf)")
    ap.add_argument("--max-missing", type=int, default=200,
                    help="fail if more than this many word tokens are dropped")
    args = ap.parse_args(argv)

    import json
    jpath = args.json_path or (sorted(glob.glob(os.path.join(_ROOT, "output", "*.json"))) or [None])[0]
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
