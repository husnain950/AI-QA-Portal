#!/usr/bin/env python3
"""Batch-convert the Acts corpus to JSON.

    python tools/acts/convert_all.py --family customs
    python tools/acts/convert_all.py --phase 1 --batch 6
    python tools/acts/convert_all.py --phase 2 --skip-existing
    python tools/acts/convert_all.py --list

Runs each PDF in a SEPARATE PROCESS, in batches.  Two reasons: a 950-page
edition holds a lot of pdfplumber state, and a single edition that raises must
not abort the other 90 -- each failure is reported and the run continues.

Scanned and text-layer editions are scheduled SEPARATELY (see ``main``): OCR is
memory-bound and does not parallelise on this corpus, while text-layer files do.

Every run leaves an audit trail under ``output/_run/``:

    status.json      live counters -- poll THIS to see if a run is alive
    report.md        per-file status, duration, and the FULL failure reason
    <name>.log       that file's own stderr, tailable while it runs

and a document the pipeline REFUSED is moved out of ``output/`` into
``output/_refused/`` rather than being left behind (see ``_quarantine``).
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as _dt
import json
import os
import pathlib
import re
import subprocess
import sys
import time

# Upstream this file sat at <pipeline-repo>/scripts/, beside the Acts/ sources and
# output/. In the monorepo the code and the corpus are separate: the pipeline lives
# under packages/, and the corpus is the gitignored $CORPUS_ACTS tree that
# sync_corpus.py and run_tests.py already read.
_HERE = pathlib.Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
if str(_ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(_ROOT / "packages"))

CORPUS = pathlib.Path(
    os.environ.get("CORPUS_ACTS") or (_ROOT / "data" / "corpora" / "acts")
)
if not CORPUS.is_absolute():
    CORPUS = _ROOT / CORPUS          # .env ships a repo-relative path
# Sources live under Acts/ where that exists, else at the corpus root -- the same
# rule sync_acts._source_pdf_index applies, so the two agree on what a source is.
ACTS = CORPUS / "Acts" if (CORPUS / "Acts").is_dir() else CORPUS
OUT = CORPUS / "output"
#: run artifacts and quarantine.  Both are SUBDIRECTORIES of output/ so that the
#: ``output/*.json`` glob defining the corpus (run_tests.py, density_table.py,
#: audit_all.py) does not see them.
RUN_DIR = OUT / "_run"
REFUSED = OUT / "_refused"

# Phase 1 = the consolidated acts, which share the Ordinance's shape (TOC +
# Chapter -> Section + Schedules + footnotes).  Everything else is Phase 2.
CONSOLIDATED = {
    "customs": "Customs Act, 1969",
    "salestax": "The Sales Tax Act, 1990",
    "excise": "The Federal Excise Act, 2005",
}


def is_pdf(p: pathlib.Path) -> bool:
    """Magic bytes, not the extension.

    Six files in this corpus have no ``.pdf`` extension ("Customs Act, 1969 as
    amended up to 30.06.2019"), and pathlib reports their suffix as ".2019" -- so
    both a ``*.pdf`` glob and a ``suffix == '.pdf'`` test skip them silently.
    """
    try:
        with p.open("rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def discover(family: str | None, phase: int | None) -> list[pathlib.Path]:
    out = []
    for p in sorted(ACTS.rglob("*")):
        if not p.is_file() or p.name == ".DS_Store" or not is_pdf(p):
            continue
        fam = p.parent.name
        consolidated = fam in CONSOLIDATED.values()
        if phase == 1 and not consolidated:
            continue
        if phase == 2 and consolidated:
            continue
        if family and CONSOLIDATED.get(family, family) != fam:
            continue
        out.append(p)
    return out


def out_path(pdf: pathlib.Path) -> pathlib.Path:
    """Output name derived from the source stem, which already carries the act
    and its amendment date.  ``metadata.filename`` keeps the original basename,
    which is what the test registry's ``applies_to`` matches on."""
    stem = pdf.name
    stem = re.sub(r"\.pdf$", "", stem, flags=re.I)
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    return OUT / f"{stem}.json"


def _reason(text: str, rc: int = 1) -> str:
    """Why a child failed: the signal if it was killed, else its last real line.

    Taking ``[-1]`` unconditionally is why 5 of 14 failures in the 2026-08-04
    Phase-2 run reported an empty reason: a traceback that ends with a newline
    leaves a blank final element, so the one line that said what went wrong was
    thrown away.  No truncation either -- the pipeline's refusals are
    deliberately long because they carry the measured evidence (agreement
    percentages, character counts).

    A negative return code is a SIGNAL, not an exception, and then there is no
    error text at all -- the last line is whatever progress the child had just
    printed, which reads as if that step were the problem.  Finance Act 2012-2013
    "failed" with the reason ``TOC parsed: 0 chapters ...``, a progress line, and
    the same shape explains the other blank failures.  On a box in heavy swap the
    likeliest signal is the OOM killer, so name it rather than implying the
    parser raised.
    """
    if rc < 0:
        import signal
        try:
            name = signal.Signals(-rc).name
        except ValueError:                                # pragma: no cover
            name = f"signal {-rc}"
        extra = (" -- the process was killed, it did not raise. On a memory-"
                 "pressured box suspect the OOM killer; check swap."
                 if -rc in (signal.SIGKILL, signal.SIGSEGV, signal.SIGBUS)
                 else " -- the process was killed, it did not raise.")
        last = next((ln.strip() for ln in
                     reversed((text or "").strip().splitlines()) if ln.strip()), "")
        return f"KILLED by {name}{extra}" + (f" Last progress: {last}" if last else "")
    for line in reversed((text or "").strip().splitlines()):
        if line.strip():
            return line.strip()
    return ""


def _quarantine(dest: pathlib.Path, reason: str) -> str:
    """Move a refused document's PREVIOUS output out of the corpus.

    ``pipeline.run`` refuses to write a file below the OCR fidelity floor, or one
    that lost its statute -- but refusing to write does nothing about the bad
    JSON already sitting there from an earlier run, and ``output/*.json`` is what
    defines the corpus.  Measured 2026-08-04: the Right of Access to Information
    Act 2017 file, recorded EXCLUDE at 80.49% agreement, was still being shipped
    from a 2026-08-03 write, along with five other refused documents.  A refusal
    that leaves the old file in place is cosmetic.

    Moved, not deleted: it is the only record of what was previously shipped, and
    it is what a future clean source PDF gets diffed against.
    """
    if not dest.exists():
        return ""
    REFUSED.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    away = REFUSED / f"{dest.name}.{stamp}"
    dest.replace(away)
    (REFUSED / f"{dest.name}.{stamp}.why.txt").write_text(
        f"{dest.name}\nquarantined {stamp}\n\n{reason}\n", encoding="utf-8")
    return away.name


def _read_log(log: pathlib.Path) -> str:
    """What the child wrote, for ``_reason``. Never raises -- a missing or
    unreadable log must not turn a conversion result into a crash."""
    try:
        return log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def convert(pdf: pathlib.Path, timeout: float | None = None,
            keep_log: bool = True, admit_below_floor: bool = False) -> dict:
    dest = out_path(pdf)
    t0 = time.time()
    # The child writes STRAIGHT INTO its log file, unbuffered, rather than into a
    # pipe we read after it exits.  ``capture_output=True`` was why no run could be
    # watched while it ran: the log was written only on exit, so mid-run it still
    # held the PREVIOUS attempt's content.  Tailing it during the 2026-08-07
    # Finance Act 2017-18 conversion showed `scanned page 150/683` -- the exact
    # page the previous attempt had died on -- while the process was past page 390,
    # which reads as "hung at the old failure point" (ledger P10 follow-up).
    # PYTHONUNBUFFERED is required: writing to a FILE, the child would otherwise
    # block-buffer 8 KB at a time and the log would advance in useless jumps.
    log = (RUN_DIR / f"{dest.stem}.log") if keep_log else None
    if log is not None:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, str(_HERE / "acts_pdf_to_json.py"),
            str(pdf), "-o", str(dest)]
    if admit_below_floor:
        argv.append("--admit-below-floor")
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    try:
        if log is None:
            r = subprocess.run(argv, capture_output=True, text=True,
                               timeout=timeout, env=env)
            rc, out, err = r.returncode, r.stdout, r.stderr
        else:
            with log.open("w", encoding="utf-8") as fh:
                r = subprocess.run(argv, stdout=fh, stderr=subprocess.STDOUT,
                                   timeout=timeout, env=env)
            rc, out, err = r.returncode, _read_log(log), ""
    except subprocess.TimeoutExpired as exc:
        # A HANG must report as a failure, not as work still in progress.  Four
        # Sales Tax conversions launched 2026-08-03 were found alive 25 hours
        # later, each having burned ~16 hours of CPU at ~10% with no output --
        # a spin, not slow progress (ledger P07).  With no timeout they were
        # indistinguishable from a large edition being slow, so the corpus count
        # disagreed across three sessions and those editions were reported as
        # "still running" every time.  Worse, had one ever finished it would have
        # overwritten output/ using whatever the code looked like a day earlier.
        # A killed child leaves its progress on disk when it streams (above), so
        # the log survives the timeout; only the pipe path has to salvage stdout.
        if log is not None:
            rc, out = 124, _read_log(log)
        else:
            rc, out = 124, (exc.stdout or b"").decode("utf-8", "replace") \
                if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = (f"TIMEOUT after {timeout:.0f}s -- killed. This is a hang, not a "
               f"slow file; see ledger P07.")
        if log is not None:
            try:
                with log.open("a", encoding="utf-8") as fh:
                    fh.write("\n" + err + "\n")
            except OSError:
                pass
    elapsed = time.time() - t0

    reason = _reason(err or out, rc) if rc else ""
    return {"pdf": pdf, "rc": rc, "reason": reason, "elapsed": elapsed,
            "quarantined": _quarantine(dest, reason) if rc else ""}


def is_scanned(pdf: pathlib.Path, sample: int = 8) -> bool:
    """Whether this PDF is scan-heavy, from a SAMPLE of its pages.

    Only used to choose a scheduling lane, so it does not need to be exact -- and
    it must be fast.  ``ocr.scanned_pages`` tests every page, which sounds cheap
    (geometry, no recognition) but measured at over two minutes across the 35
    Phase-2 files, ~3,500 pages including a 952-page edition: a two-minute stall
    before the first conversion starts, to decide something a handful of pages
    already answers.

    Sampling is sound here because editions in this corpus are wholly one thing
    or the other -- measured: Finance Act 2016-17 215/215 scanned, FA2020
    140/140, FA2025 289/292, the Supplementary Acts 15/15 and 9/9, every Customs
    edition 0/241.  The lone mixed case is Finance Act 2022 at 1/952 (its cover
    image), and a threshold well above one page keeps it in the fast lane where
    it belongs.
    """
    try:
        import warnings

        import pdfplumber

        from acts_ingest.pagemodel import _page_is_scan
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with pdfplumber.open(pdf) as doc:
                n = len(doc.pages)
                if not n:
                    return False
                step = max(1, n // sample)
                idx = list(range(0, n, step))[:sample]
                hits = sum(_page_is_scan(doc.pages[i]) for i in idx)
        # A quarter of the sample, but never zero: with max(2, ...) a ONE-page
        # document could never qualify, which misfiled the wholly-scanned 1-page
        # Income Tax Amendment Act 2016 as text-layer.  A quarter still keeps
        # Finance Act 2022 (1 scanned cover page in 952) in the fast lane.
        return hits >= max(1, len(idx) // 4)
    except Exception:
        return False


def _write_status(state: dict) -> None:
    """Publish live counters for anything that wants to know if a run is alive.

    Poll this file -- never ``pgrep -f convert_all.py``.  That pattern matches
    the command line of the WATCHER as well as the job, so an ``until ! pgrep``
    loop can never terminate: two of them span for an hour past the end of the
    2026-08-04 run, reporting "running" for a job that had finished.
    """
    try:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        (RUN_DIR / "status.json").write_text(
            json.dumps(state, indent=1, default=str), encoding="utf-8")
    except OSError:
        pass


def _write_report(results: list[dict], total: int, seconds: float) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    ok = [r for r in results if r["rc"] == 0]
    bad = [r for r in results if r["rc"] != 0]
    lines = [f"# Conversion run — {_dt.datetime.now():%Y-%m-%d %H:%M}", "",
             f"{len(ok)}/{total} converted in {seconds:.0f}s "
             f"({seconds / 60:.0f} min).", ""]
    if bad:
        lines += ["## Failed", "",
                  "| file | secs | reason | quarantined |", "|---|---|---|---|"]
        for r in sorted(bad, key=lambda r: r["pdf"].name):
            lines.append(f"| {r['pdf'].name} | {r['elapsed']:.0f} | "
                         f"{r['reason'].replace('|', '\\|')} | "
                         f"{r['quarantined'] or '—'} |")
        lines.append("")
    lines += ["## Converted", "", "| file | secs |", "|---|---|"]
    for r in sorted(ok, key=lambda r: -r["elapsed"]):
        lines.append(f"| {r['pdf'].name} | {r['elapsed']:.0f} |")
    (RUN_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", choices=sorted(CONSOLIDATED) + ["all"])
    ap.add_argument("--phase", type=int, choices=(1, 2))
    ap.add_argument("--batch", type=int, default=6,
                    help="text-layer PDFs converted concurrently (default 6)")
    ap.add_argument("--ocr-batch", type=int, default=1,
                    help="SCANNED PDFs converted concurrently (default 1). "
                         "Measured on a 16GB/8-core box, 3 pages per worker: "
                         "1 proc 0.200 pg/s, 2 procs 0.200 (no gain), 4 procs "
                         "0.082 (59%% WORSE), 6 procs 0.093. OCR is memory-bound "
                         "(~0.5-1GB per ONNX session) and every extra worker buys "
                         "swap thrash, not compute -- OMP_NUM_THREADS=1 does not "
                         "help. Raise this only after re-measuring on a box with "
                         "free RAM; do not tune it on intuition.")
    ap.add_argument("--list", action="store_true", help="list targets and exit")
    ap.add_argument("--skip-existing", action="store_true",
                    help="skip a PDF whose output JSON already exists. Lets an "
                         "interrupted multi-hour run resume instead of starting "
                         "over, and avoids the mixed-code-state hazard of half "
                         "the corpus being written by an older revision.")
    ap.add_argument("--admit-below-floor", action="store_true",
                    help="convert a scan below the OCR fidelity floor instead of "
                         "refusing it; the writer redirects it to "
                         "output/_provisional/ with metadata.ocr.provisional=true "
                         "(the user's 2026-08-07 decision). Use this to rebuild "
                         "the provisional lane after a parser change -- those "
                         "files are NOT produced by an ordinary run, so without "
                         "it they silently keep whatever revision last wrote "
                         "them.")
    ap.add_argument("--timeout", type=float, default=5400.0,
                    help="per-file wall-clock limit in seconds (default 5400). "
                         "A file that exceeds it is KILLED and reported failed: "
                         "a hang must not masquerade as work (ledger P07). The "
                         "slowest legitimate file is Finance Act 2025 at 289 "
                         "OCR'd pages, so keep well above that. 0 disables.")
    args = ap.parse_args()

    fam = None if args.family in (None, "all") else args.family
    files = discover(fam, args.phase)
    if not files:
        print("no matching PDFs", file=sys.stderr)
        return 2
    if args.list:
        for p in files:
            print(f"  {p.relative_to(ACTS)}  ->  {out_path(p).name}")
        print(f"{len(files)} file(s)")
        return 0
    if args.skip_existing:
        keep = [p for p in files if not out_path(p).exists()]
        if len(keep) != len(files):
            print(f"skipping {len(files) - len(keep)} already-converted file(s)")
        files = keep
        if not files:
            print("nothing to do -- every target already has output")
            return 0

    OUT.mkdir(exist_ok=True)
    t0 = time.time()
    results: list[dict] = []
    per_file = args.timeout or None
    total = len(files)
    # Publish "alive, not finished" BEFORE doing anything slow.  Classification
    # below takes ~8s, and during that window the previous run's status.json is
    # still the only one on disk -- a watcher polling ``finished`` reads the OLD
    # run's ``true`` and concludes instantly that this one is done.  That is
    # exactly the class of bug the status file exists to remove, so the very
    # first side effect of a run must be to stamp its own state.
    state = {"pid": os.getpid(), "started": _dt.datetime.now().isoformat(),
             "total": total, "done": 0, "ok": 0, "failed": 0,
             "running": [], "phase": "classifying", "finished": False}
    _write_status(state)

    # Partition by cost.  One --batch width cannot suit both populations: text
    # layer files are cheap and parallelise, scanned files are memory-bound and
    # measurably do NOT (see --ocr-batch). Running them at one width is why the
    # 2026-08-04 Phase-2 run took 3h08m.
    print(f"classifying {len(files)} file(s) by OCR cost ...")
    scanned = [p for p in files if is_scanned(p)]
    plain = [p for p in files if p not in scanned]
    print(f"  {len(plain)} text-layer (batch {args.batch})   "
          f"{len(scanned)} scanned (batch {args.ocr_batch})")
    state["phase"] = "converting"
    _write_status(state)

    for group, width in ((plain, args.batch), (scanned, args.ocr_batch)):
        if not group:
            continue
        with cf.ThreadPoolExecutor(max_workers=max(1, width)) as pool:
            futures = {pool.submit(convert, p, per_file, True,
                                   args.admit_below_floor): p for p in group}
            state["running"] = [p.name for p in group[:width]]
            _write_status(state)
            # as_completed, NOT pool.map: map yields in SUBMISSION order, so the
            # log sat at two lines for over two hours of the 2026-08-04 run while
            # later files had already finished. Progress must reflect completion.
            for fut in cf.as_completed(futures):
                r = fut.result()
                results.append(r)
                state["done"] = len(results)
                state["ok"] = sum(1 for x in results if x["rc"] == 0)
                state["failed"] = state["done"] - state["ok"]
                state["running"] = [p.name for p in futures.values()
                                    if p not in {x["pdf"] for x in results}][:width]
                _write_status(state)
                mark = " ok " if r["rc"] == 0 else "FAIL"
                print(f"  [{mark}] {r['pdf'].name[:58]:58} "
                      f"{r['elapsed']:5.0f}s  {state['done']}/{total}")
                if r["rc"]:
                    print(f"         {r['reason']}")
                    if r["quarantined"]:
                        print(f"         quarantined previous output -> "
                              f"_refused/{r['quarantined']}")

    seconds = time.time() - t0
    state.update(finished=True, running=[], seconds=round(seconds))
    _write_status(state)
    _write_report(results, total, seconds)

    failed = [r for r in results if r["rc"] != 0]
    print(f"\nconverted {total - len(failed)}/{total} in {seconds:.0f}s "
          f"({seconds / 60:.0f} min)")
    print(f"report: {RUN_DIR / 'report.md'}")
    if failed:
        print(f"\n{len(failed)} FAILED:")
        for r in sorted(failed, key=lambda r: r["pdf"].name):
            print(f"  {r['pdf'].relative_to(ACTS)}\n      {r['reason']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
