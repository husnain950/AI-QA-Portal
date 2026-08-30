#!/usr/bin/env python3
"""Conservation gate over many editions at once -- one table, one exit code.

    python tools/acts/audit_all.py --family customs

Pairs each output JSON with its source PDF by ``metadata.filename`` (not by
guessing the name back), re-scans the PDF independently, and applies the gate:
body >= 99.99%, footnotes 100.000%.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import pathlib
import re
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ``scripts/`` became ``tools/`` and this import was never repointed, so the
# corpus-wide conservation gate the suite README names has been dying on
# ModuleNotFoundError.  ``ACTS`` went with it: convert_all binds its lanes at
# run time now, and the corpus root is what corpus_paths exists to answer.
from convert_all import CONSOLIDATED, is_pdf  # noqa: E402
from corpus_paths import output_dir, source_dir  # noqa: E402 (bootstrap above)

ACTS = pathlib.Path(source_dir("acts"))
OUT = pathlib.Path(output_dir("acts"))
BODY_GATE = 99.99
FOOT_GATE = 100.0


def source_for(js: pathlib.Path) -> pathlib.Path | None:
    """The PDF this JSON came from, by its recorded basename."""
    want = (json.load(js.open()).get("metadata") or {}).get("filename")
    if not want:
        return None
    for p in ACTS.rglob("*"):
        if p.is_file() and p.name == want and is_pdf(p):
            return p
    return None


def audit(pair):
    js, pdf = pair
    r = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit_completeness.py"),
         "--pdf", str(pdf), str(js)],
        capture_output=True, text=True)
    txt = r.stdout
    nums = re.findall(r"conserved=([\d.]+)%\s+missing=(\d+)", txt)
    top = re.findall(r"top missing words: (\{.*?\})", txt)
    if len(nums) < 2:
        return js, None, None, None, None, (r.stderr or txt)[-120:]
    (b, bm), (f, fm) = nums[0], nums[1]
    return js, float(b), int(bm), float(f), int(fm), (top[0][:90] if top else "")


def audit_corpus_purity() -> int:
    """No provisional document may sit in the corpus. Returns the failure count.

    The corpus is ``output/*.json``; sub-floor documents are admitted only into
    ``output/_provisional/`` (see ``pipeline.run(admit_below_floor=...)``).  The
    single writer enforces that on the way out, and this is the audit that
    enforces it on what is actually on disk -- the distinction P08 was: the gate
    refused to *create* a sub-floor file and nothing owned *ensuring its
    absence*, so an already-written one stayed in the corpus for 39 hours.
    `inv_provisional_is_flagged` cannot cover this, because an invariant is
    handed a document and never its path.

    Two ways it can go wrong, both checked: a corpus file that declares itself
    provisional, and a stale corpus copy shadowing a provisional document of the
    same name.
    """
    bad = 0
    prov_dir = OUT / "_provisional"
    for js in sorted(OUT.glob("*.json")):
        try:
            ocr = ((json.loads(js.read_text(encoding="utf-8")).get("metadata")
                    or {}).get("ocr") or {})
        except ValueError:
            continue
        if ocr.get("provisional"):
            print(f"  [!!] {js.name}: declares metadata.ocr.provisional inside "
                  f"the corpus -- belongs in _provisional/")
            bad += 1
        elif (prov_dir / js.name).exists():
            print(f"  [!!] {js.name}: a provisional document of this name exists, "
                  f"so this corpus copy is stale (ledger P08)")
            bad += 1
    print(f"corpus purity: {'OK' if not bad else f'{bad} PROBLEM(S)'} "
          f"({len(list(OUT.glob('*.json')))} corpus, "
          f"{len(list(prov_dir.glob('*.json'))) if prov_dir.exists() else 0} "
          f"provisional)")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", choices=sorted(CONSOLIDATED) + ["all"], default="all")
    ap.add_argument("--jobs", type=int, default=5)
    ap.add_argument("--purity-only", action="store_true",
                    help="run only the corpus-purity check (no PDF re-scan)")
    ap.add_argument("--json", dest="json_report", metavar="REPORT",
                    help="also write the table as JSON (consumed by the QA portal)")
    args = ap.parse_args()

    purity = audit_corpus_purity()
    if args.purity_only:
        return 1 if purity else 0

    fam = None if args.family == "all" else CONSOLIDATED[args.family]
    pairs = []
    for js in sorted(OUT.glob("*.json")):
        pdf = source_for(js)
        if pdf is None:
            print(f"  [??] {js.name}: source PDF not found")
            continue
        if fam and pdf.parent.name != fam:
            continue
        pairs.append((js, pdf))
    if not pairs:
        print("nothing to audit", file=sys.stderr)
        return 2

    print(f"{'edition':50s} {'body%':>8s} {'miss':>5s} {'fn%':>8s} {'miss':>5s}  gate")
    bad = 0
    editions = []
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for js, b, bm, f, fm, note in pool.map(audit, pairs):
            if b is None:
                print(f"{js.stem[:50]:50s}  ERROR {note}")
                bad += 1
                editions.append({"json": js.name, "error": note, "passed": False})
                continue
            ok = b >= BODY_GATE and f >= FOOT_GATE
            bad += 0 if ok else 1
            print(f"{js.stem[:50]:50s} {b:8.3f} {bm:5d} {f:8.3f} {fm:5d}  "
                  f"{'PASS' if ok else 'FAIL'}"
                  + ("" if ok else f"  {note}"))
            editions.append({
                "json": js.name,
                "body_conserved": b, "body_missing": bm,
                "footnote_conserved": f, "footnote_missing": fm,
                "passed": ok,
                "note": "" if ok else note,
            })

    print(f"\n{len(pairs) - bad}/{len(pairs)} within gate "
          f"(body >= {BODY_GATE}%, footnotes {FOOT_GATE}%)")

    # Machine-readable twin of exactly what was printed above, so a consumer (the QA
    # portal) never re-derives the gate -- it reads the same numbers this run decided on.
    if args.json_report:
        report = {
            "gates": {"body": BODY_GATE, "footnote": FOOT_GATE},
            "within_gate": len(pairs) - bad,
            "total": len(pairs),
            "purity_problems": purity,
            "editions": sorted(editions, key=lambda row: row["json"].casefold()),
        }
        with open(args.json_report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1, sort_keys=True)
        print(f"wrote {args.json_report}")

    return 1 if (bad or purity) else 0


if __name__ == "__main__":
    raise SystemExit(main())
