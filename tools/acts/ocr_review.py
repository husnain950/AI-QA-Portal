#!/usr/bin/env python3
"""Run the dual-engine OCR over every scanned page and write the audit trail.

Two kinds of report, both under ``reports/``:

``ocr-exclusions.md``
    one row per file that needs OCR, its measured agreement / low-confidence
    numbers, and whether it clears the fidelity floor.  A file below the floor
    is **not shipped** -- the row says so and asks for a clean source PDF.

``ocr-disagreements-<act>.md``
    every token the two engines read differently: page, both readings, both
    confidences, which one was accepted, and any enumerator repair applied.
    This is the file a lawyer checks a doubtful citation against.

Usage::

    ../.venv/bin/python scripts/ocr_review.py                  # whole corpus
    ../.venv/bin/python scripts/ocr_review.py "Acts/x/y.pdf"   # one file
    ../.venv/bin/python scripts/ocr_review.py --workers 6
    ../.venv/bin/python scripts/ocr_review.py --limit-pages 3  # smoke run

``--limit-pages`` is for smoke-testing only: it makes the numbers a *sample*,
the floor decision is not valid, and every report it writes says so at the top.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import functools
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from acts_ingest import ocr

REPORTS = os.path.join(_ROOT, "reports")
_PARTIAL_WARNING = (
    "> **PARTIAL RUN (`--limit-pages`).** The numbers below are a sample, so "
    "the fidelity decision in this file is NOT valid. Re-run without "
    "`--limit-pages` before shipping or excluding anything.\n")


def find_pdfs(root: str = "Acts") -> list[str]:
    """Every PDF under ``root`` -- including the extensionless ones."""
    out = []
    for p in sorted(glob.glob(os.path.join(_ROOT, root, "**", "*"),
                              recursive=True)):
        if not os.path.isfile(p) or os.path.basename(p).startswith("."):
            continue
        if p.lower().endswith((".doc", ".docx", ".json", ".md", ".txt")):
            continue
        with open(p, "rb") as fh:
            if fh.read(5) == b"%PDF-":
                out.append(p)
    return out


def run_file(path: str, dpi: int, pool, limit: int | None):
    """Score one file with ``ocr.page_fidelity`` -- the module owns the loop.

    The per-page trigger is the whole point: ``Finance Act 2025.pdf`` prints a
    real 58-character running header over a scanned body, so page 1 has text
    and pages 5-292 do not.
    """
    total, pages = ocr.scanned_pages(path)
    if not pages:
        return None, total, 0
    todo = pages[:limit] if limit else pages
    t0 = time.time()
    # One pool for the whole corpus: each worker loads the ONNX models once
    # (~5s), and re-creating the pool per file would spend half an hour of the
    # run doing nothing but that.
    mapper = (functools.partial(pool.map, chunksize=1) if pool else map)
    fid = ocr.page_fidelity(path, pages=todo, dpi=dpi, mapper=mapper)
    if fid.failed:
        print(f"    !! pages that failed to OCR: {fid.failed}",
              file=sys.stderr, flush=True)
    print(f"  {len(todo)}/{len(pages)} OCR pages of {total} in "
          f"{time.time() - t0:.0f}s -- agreement {fid.mean_agreement:.1f}%, "
          f"low-conf {fid.low_conf_share:.1f}%, "
          f"{'ADMIT' if fid.admitted else 'EXCLUDE'} ({fid.reason})",
          flush=True)
    return fid, total, len(pages)


def slug(path: str) -> str:
    name = os.path.splitext(os.path.basename(path))[0]
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()


def write_disagreements(fid, partial: bool) -> str:
    out = os.path.join(REPORTS, f"ocr-disagreements-{slug(fid.path)}.md")
    rel = os.path.relpath(fid.path, _ROOT)
    lines = [f"# OCR disagreements -- {os.path.basename(fid.path)}", ""]
    if partial:
        lines += [_PARTIAL_WARNING, ""]
    lines += [
        f"Source: `{rel}`  ",
        f"OCR pages scored: {fid.pages} ({fid.blank} blank)  ",
        f"Tokens: {fid.tokens}  ",
        f"Mean inter-engine agreement: **{fid.mean_agreement:.2f}%**  ",
        f"Low-confidence tokens: **{fid.low_conf_share:.2f}%**  ",
        f"Verdict: **{'ADMITTED' if fid.admitted else 'EXCLUDED'}** "
        f"({fid.reason})",
        "",
        "Every row is a token the two engines read differently. `accepted` is "
        "the higher-confidence reading; it is flagged `needs_review` "
        "regardless, and is never treated as certain downstream.",
        "",
        "| page | x0 | top | tesseract | conf | rapidocr | conf | accepted | repair |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
    for w in fid.disagreements:
        lines.append(
            f"| {w.get('page')} | {w['x0']:.0f} | {w['top']:.0f} "
            f"| `{esc(w.get('tesseract'))}` | {w.get('conf_tesseract')} "
            f"| `{esc(w.get('rapidocr'))}` | {w.get('conf_rapidocr')} "
            f"| `{esc(w['text'])}` "
            f"| {('`' + esc(w['repair']) + '` -> `' + esc(w['text']) + '`') if 'repair' in w else ''} |")
    if not fid.disagreements:
        lines.append("| - | - | - | - | - | - | - | (none) | |")

    lines += ["", f"## Enumerator repairs ({len(fid.repairs)})", "",
              "Structural clause markers rewritten from the known sequence. "
              "Body words and digits are never rewritten: `99A` misread as "
              "`994A` is not recoverable by sequence, and a plausible guess is "
              "worse than a flagged error.", ""]
    if fid.repairs:
        lines += ["`kind` = `shape`: both engines read the same value and "
                  "differed only in the bracket glyphs, so only the shape was "
                  "normalised. `kind` = `sequence`: neither reading parsed as "
                  "an enumerator, so the position relative to an agreed anchor "
                  "supplied the value -- the only case where a value is "
                  "inferred rather than read.", "",
                  "| page | x0 | top | before | after | kind | alphabet | conf |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for r in fid.repairs:
            lines.append(f"| {r['page']} | {r['x0']:.0f} | {r['top']:.0f} "
                         f"| `{esc(r['before'])}` | `{esc(r['after'])}` "
                         f"| {r.get('kind', '?')} "
                         f"| {r['alphabet']} | {r['conf']} |")
    else:
        lines.append("(none)")

    lines += ["", f"## Lines only RapidOCR saw ({len(fid.missed)})", "",
              "Text Tesseract dropped entirely. These yield no word (geometry "
              "comes from Tesseract) but count against the page's agreement, "
              "because a silently dropped line is worse than a wrong one.", ""]
    for pageno, text in fid.missed:
        lines.append(f"- p{pageno}: `{esc(text)}`")
    if not fid.missed:
        lines.append("(none)")
    lines.append("")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return out


def write_exclusions(rows: list, partial: bool) -> str:
    out = os.path.join(REPORTS, "ocr-exclusions.md")
    admitted = [r for r in rows if r["fid"].admitted]
    excluded = [r for r in rows if not r["fid"].admitted]
    lines = ["# OCR fidelity -- admitted and excluded files", ""]
    if partial:
        lines += [_PARTIAL_WARNING, ""]
    lines += [
        f"Generated by `scripts/ocr_review.py` at {ocr.DEFAULT_DPI} dpi over "
        f"**all** OCR pages of each file (never a sample).",
        "",
        f"Floor: mean inter-engine agreement >= {ocr.AGREEMENT_FLOOR:.0f}% "
        f"**and** low-confidence tokens <= "
        f"{ocr.LOW_CONF_SHARE_CEILING:.0f}% (a token is low-confidence when "
        f"the accepted engine scored it under {ocr.LOW_CONF:.0f}).",
        "",
        "Page confidence is the *inter-engine agreement rate*, not either "
        "engine's self-report: on a degraded scan Tesseract reports 95 on a "
        "token it got wrong, and only a second recogniser exposes that.",
        "",
        f"| file | pages | OCR pages | blank | tokens | agreement | low-conf | verdict |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in sorted(rows, key=lambda r: -r["fid"].mean_agreement):
        f = r["fid"]
        lines.append(
            f"| `{os.path.relpath(f.path, _ROOT)}` | {r['total']} | {f.pages} "
            f"| {f.blank} | {f.tokens} | {f.mean_agreement:.2f}% "
            f"| {f.low_conf_share:.2f}% "
            f"| {'admit' if f.admitted else '**EXCLUDE**'} |")

    lines += ["", f"## Excluded -- {len(excluded)} file(s), not shipped", ""]
    if excluded:
        lines.append("These are below the floor. The defect is in the *source "
                     "scan*, not the recognisers: no DPI or PSM setting "
                     "recovers them (300/400/500 dpi x psm auto/6/4 moved mean "
                     "Tesseract confidence 90.5 -> 91.5 only). **Request a "
                     "clean source PDF from FBR for each of these** -- a "
                     "text-layer or higher-quality scan -- rather than "
                     "shipping a text nobody can certify.")
        lines.append("")
        for r in excluded:
            f = r["fid"]
            worst = sorted(f.per_page, key=lambda t: t[1])[:5]
            lines += [
                f"### `{os.path.relpath(f.path, _ROOT)}`", "",
                f"- {f.pages} OCR pages of {r['total']}, {f.tokens} tokens",
                f"- mean agreement **{f.mean_agreement:.2f}%**, "
                f"low-confidence **{f.low_conf_share:.2f}%**",
                f"- fails: {f.reason}",
                f"- worst pages (page, agreement%, tokens): "
                + ", ".join(f"({p}, {a}, {n})" for p, a, n in worst),
                f"- {len(f.disagreements)} flagged tokens, {len(f.repairs)} "
                f"enumerator repairs, {len(f.missed)} lines Tesseract dropped "
                f"-- see `ocr-disagreements-{slug(f.path)}.md`",
                "- action: **request a clean source PDF**", "",
            ]
    else:
        lines.append("(none)")

    lines += ["", f"## Admitted -- {len(admitted)} file(s)", ""]
    for r in admitted:
        f = r["fid"]
        lines.append(f"- `{os.path.relpath(f.path, _ROOT)}` -- "
                     f"{f.mean_agreement:.2f}% agreement, "
                     f"{len(f.disagreements)} tokens still flagged "
                     f"`needs_review` (see `ocr-disagreements-{slug(f.path)}.md`)")
    if not admitted:
        lines.append("(none)")
    lines.append("")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*", help="PDFs (default: every PDF in Acts/)")
    ap.add_argument("--dpi", type=int, default=ocr.DEFAULT_DPI)
    ap.add_argument("--workers", type=int, default=4,
                    help="parallel pages (each worker loads its own models)")
    ap.add_argument("--limit-pages", type=int, default=None,
                    help="smoke run: OCR only the first N scanned pages")
    ap.add_argument("--min-ocr-pages", type=int, default=1,
                    help="skip files with fewer scanned pages than this")
    args = ap.parse_args(argv)

    paths = [p if os.path.isabs(p) else os.path.join(_ROOT, p)
             for p in args.paths] or find_pdfs()
    os.makedirs(REPORTS, exist_ok=True)
    rows = []
    pool = (ProcessPoolExecutor(max_workers=args.workers)
            if args.workers > 1 else None)
    for path in paths:
        try:
            total, pages = ocr.scanned_pages(path)
        except Exception as exc:
            print(f"!! {path}: {exc}", file=sys.stderr)
            continue
        if len(pages) < args.min_ocr_pages:
            continue
        print(f"[ocr] {os.path.relpath(path, _ROOT)}", flush=True)
        try:
            fid, total, n = run_file(path, args.dpi, pool, args.limit_pages)
        except BrokenProcessPool:
            # A worker was killed (memory pressure -- each ONNX session is
            # ~500MB and this box runs other conversions).  A broken pool
            # stays broken, so finish serially rather than lose the sweep.
            print("    !! worker died; continuing SERIALLY", file=sys.stderr,
                  flush=True)
            pool.shutdown(wait=False)
            pool = None
            fid, total, n = run_file(path, args.dpi, None, args.limit_pages)
        if fid is None:
            continue
        rows.append({"fid": fid, "total": total, "ocr_pages": n})
        if not fid.tokens:
            # every "scanned" page turned out to be genuinely blank (the
            # trailing leaf most Customs editions end on): nothing to audit
            print("       -> blank pages only, no disagreement report",
                  flush=True)
            continue
        print(f"       -> {os.path.relpath(write_disagreements(fid, bool(args.limit_pages)), _ROOT)}",
              flush=True)
        # Rewrite the summary after every file: the whole corpus is ~1,850
        # scanned pages at ~6s each, so a run that is interrupted must still
        # leave a valid report for the files it did finish.
        write_exclusions(rows, bool(args.limit_pages))
    if pool:
        pool.shutdown()
    if not rows:
        print("no scanned pages found", file=sys.stderr)
        return 1
    out = write_exclusions(rows, bool(args.limit_pages))
    bad = [r for r in rows if not r["fid"].admitted]
    print(f"\n{len(rows)} file(s) needed OCR; {len(bad)} below the floor -> "
          f"{os.path.relpath(out, _ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
