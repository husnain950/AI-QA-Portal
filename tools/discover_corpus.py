#!/usr/bin/env python3
"""Measure every document in the corpus, assign it a schema family, report.

    python tools/discover_corpus.py --write        # measure, assign, write artifacts
    python tools/discover_corpus.py --check        # rerun must be byte-identical
    python tools/discover_corpus.py --assert       # every family exercised, 0 unexplained
    python tools/discover_corpus.py --reconcile    # disk vs FBR_Document_Inventory.xlsx
    python tools/discover_corpus.py --verify-lanes # classifier vs today's lane routing

This is the DISCOVERY half of the split, and it is a tool rather than a package
module on purpose: production imports ``legal_ingest.signature`` and
``legal_ingest.families`` to classify ONE document, and never imports this file.
Discovery -- the census, the group-by, the drift table, the coverage grid -- runs
here, when someone asks.

There is no sampler. Measured, a full census over all 190 staged documents takes
about 26 seconds on eight threads, so choosing a representative subset would cost
more code than it saves and would hide exactly the drift the report exists to
show. The stratification axes survive as report groupings and as the coverage
assertion; they never decide what gets read.

  # ponytail: full census, ~26s over 190 documents. Add stratified sampling when
  # the corpus passes ~5k documents or per-document cost passes ~1s.

There is no clustering algorithm either. ``--write`` emits a ``Counter``
group-by on ``(container_order, has_toc, family)`` -- twelve keys over this
corpus -- because that is the evidence a human reads, and the five ordered
predicates in ``families.py`` are what code runs. Neither is a model, and both
are rerunnable to the byte.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_paths import LABELS, REPO_ROOT, get  # noqa: E402 (sys.path bootstrap)
from legal_ingest.families import (  # noqa: E402
    BY_LABEL,
    FAMILIES,
    Assignment,
    classify,
    inherit,
)
from legal_ingest.signature import Signature, measure  # noqa: E402
from stage_corpus import iter_documents  # noqa: E402

OUT_DIR = REPO_ROOT / "tools" / "discovery"
SIGNATURES = OUT_DIR / "signatures.json"
REPORT = OUT_DIR / "report.md"
UNEXPLAINED = OUT_DIR / "unexplained.json"

#: A document is treated as having a contents page above this many recognised
#: rows. Report-only: no family predicate turns on it, because a TOC-less
#: document already has a working path (``discover.discover_structure``).
TOC_ROWS_MIN = 20


# ---------------------------------------------------------------------------
# census


def _sources() -> list[tuple[str, Path, Path]]:
    """``(lane, root, path)`` for every staged source document, all lanes."""
    found = []
    for lane in LABELS:
        root = get(lane).source_within(get(lane).path())
        if not root.is_dir():
            continue
        found += [(lane, root, path) for path in iter_documents(root)]
    return found


def census(workers: int = 8) -> list[dict]:
    """Measure and classify every staged document, then run group inheritance."""
    sources = _sources()
    with ThreadPoolExecutor(workers) as pool:
        sigs = list(pool.map(lambda s: measure(s[2], s[1]), sources))

    rows = [{"lane": lane, "signature": sig, "assignment": classify(sig)}
            for (lane, _, _), sig in zip(sources, sigs)]

    # A document with no text layer can still be placed, when every text-bearing
    # edition of its own group agrees. Unanimity is not ceremony: the "Finance
    # Acts" folder holds five container shapes, and without the check its nine
    # scans would inherit from a filing convention.
    by_group = collections.defaultdict(list)
    for row in rows:
        by_group[(row["lane"], row["signature"].group)].append(row)
    for key, members in by_group.items():
        label = inherit([m["assignment"] for m in members])
        if not label:
            continue
        scored = [m["assignment"].confidence for m in members
                  if m["assignment"].source == "measured" and m["assignment"].family == label]
        measured = len(scored)
        confidence = sum(scored) / measured
        for member in members:
            a = member["assignment"]
            # Only a missing text layer is a gap in MEASUREMENT. That a document
            # is Urdu, or is a legacy .doc, is a fact about the document itself:
            # inheriting "consolidated" from its group would hand a .docx to a
            # PDF parser and an RTL scan to a pipeline with no RTL support.
            if a.family == "no_text_layer":
                # Confidence is the group's, not the scan's own: carrying the
                # no_text_layer score across made a Finance Act read "amending,
                # 0.25", which is the confidence of a fact about a missing text
                # layer, not of the assignment being reported.
                member["assignment"] = Assignment(
                    family=label, confidence=confidence, source="group",
                    evidence=a.evidence + (f"inherited: all {measured} measured "
                                           f"editions of {key[1]!r} are {label}",))
    return rows


def serialise(rows: list[dict]) -> dict:
    return {
        "_comment": [
            "Generated by `python tools/discover_corpus.py --write`. Do not hand-edit.",
            "A document that should stay unexplained belongs in unexplained.json.",
        ],
        "documents": len(rows),
        "families": dict(collections.Counter(
            r["assignment"].family or "unexplained" for r in rows)),
        "records": [{"lane": r["lane"],
                     "signature": r["signature"].as_dict(),
                     "assignment": r["assignment"].as_dict()} for r in rows],
    }


# ---------------------------------------------------------------------------
# report


def _has_toc(sig: Signature) -> bool:
    return sig.toc_rows >= TOC_ROWS_MIN or sig.toc_dot_leaders >= TOC_ROWS_MIN


def _shape(sig: Signature, assignment: Assignment) -> tuple[str, str, str]:
    return (sig.container_order or "flat",
            "toc" if _has_toc(sig) else "notoc",
            assignment.family or "unexplained")


def _table(header: list[str], body: list[list]) -> list[str]:
    return ["| " + " | ".join(header) + " |",
            "|" + "|".join(["---"] * len(header)) + "|",
            *["| " + " | ".join(str(c) for c in row) + " |" for row in body]]


def report(rows: list[dict]) -> str:
    out = ["# Corpus structure discovery", "",
           "Generated by `python tools/discover_corpus.py --write`. Every number below is",
           "measured from the staged corpus; nothing here is hand-entered.", ""]

    # 1 -- census
    fam = collections.Counter(r["assignment"].family or "unexplained" for r in rows)
    out += ["## 1. Census", "",
            f"**{len(rows)} documents**, "
            f"{len({(r['lane'], r['signature'].group) for r in rows})} document groups, "
            f"{len(LABELS)} lanes.", ""]
    out += _table(["family", "documents", "parseable", "mean confidence"],
                  [[label,
                    fam.get(label, 0),
                    "yes" if BY_LABEL[label].profile else "no",
                    round(sum(r["assignment"].confidence for r in rows
                              if r["assignment"].family == label)
                          / max(fam.get(label, 0), 1), 2)]
                   for label in [f.label for f in FAMILIES]]
                  + [["**unexplained**", fam.get("unexplained", 0), "--", "--"]])
    out += ["",
            "By lane: " + ", ".join(
                f"{lane} {sum(1 for r in rows if r['lane'] == lane)}" for lane in LABELS),
            f"Inherited from group (no text layer of their own): "
            f"{sum(1 for r in rows if r['assignment'].source == 'group')}", ""]

    # 2 -- families and the thresholds that decide them
    out += ["## 2. Families", "",
            "`required` decides membership, `optional` decides confidence. Order is",
            "significant: the first family whose required set holds wins.", ""]
    out += _table(["#", "family", "required signals", "optional signals", "n"],
                  [[i + 1, f.label,
                    ", ".join(n for n, _ in f.required) or "--",
                    ", ".join(n for n, _ in f.optional) or "--",
                    fam.get(f.label, 0)] for i, f in enumerate(FAMILIES)])
    out += [""]

    # 3 -- the group-by. This is the clustering, shown as evidence.
    out += ["## 3. Shape group-by", "",
            "`container_order | contents page | family`. Container order and TOC presence",
            "are FIELDS, not families -- the pipeline already handles both -- so this table",
            "is what shows whether the five families are cutting the corpus where it bends.", ""]
    shapes = collections.Counter(_shape(r["signature"], r["assignment"]) for r in rows)
    out += _table(["n", "containers", "contents", "family", "example group"],
                  [[n, k[0], k[1], k[2],
                    next(r["signature"].group for r in rows
                         if _shape(r["signature"], r["assignment"]) == k)]
                   for k, n in shapes.most_common()])
    out += [""]

    # 4 -- drift within a document group
    out += ["## 4. Drift inside a document group", "",
            "A group whose editions do not all share one family and one container order.",
            "This is where a publisher re-typesetting mid-group becomes visible, and where",
            "a folder that is a filing convention rather than a document group gives itself",
            "away.", ""]
    drifted = 0
    for (lane, group), members in sorted(collections.defaultdict(
            list, {k: v for k, v in _by_group(rows).items()}).items()):
        keys = {(m["assignment"].family, m["signature"].container_order) for m in members}
        if len(keys) < 2:
            continue
        drifted += 1
        out += [f"### {lane} / {group}  ({len(members)} editions, {len(keys)} shapes)", ""]
        out += _table(["pages", "family", "containers", "CH", "dot leaders", "producer", "file"],
                      [[m["signature"].pages,
                        m["assignment"].family or "unexplained",
                        m["signature"].container_order or "flat",
                        m["signature"].chapter_lines,
                        m["signature"].toc_dot_leaders,
                        (m["signature"].producer or "--")[:34],
                        m["signature"].path.split("/")[-1][:58]]
                       for m in sorted(members, key=lambda m: m["signature"].pages)])
        out += [""]
    if not drifted:
        out += ["*No group drifts.*", ""]

    # 5 -- what a human must look at
    out += ["## 5. Low confidence and unexplained", "",
            "Low confidence means the document parses but does not look like the rest of its",
            "family. Unexplained means no family's required set held, and the pipeline",
            "refuses it rather than forcing it into the nearest shape.", ""]
    flagged = [r for r in rows if not r["assignment"].confident]
    parseable = [r for r in flagged
                 if r["assignment"].family and BY_LABEL[r["assignment"].family].profile]
    out += _table(["family", "conf", "lane", "evidence", "file"],
                  [[r["assignment"].family or "**unexplained**",
                    round(r["assignment"].confidence, 2), r["lane"],
                    "; ".join(r["assignment"].evidence)[:70],
                    r["signature"].path.split("/")[-1][:52]]
                   for r in sorted(parseable + [r for r in flagged
                                                if not r["assignment"].family],
                                   key=lambda r: r["assignment"].confidence)]) \
        if parseable or any(not r["assignment"].family for r in flagged) \
        else ["*Every parseable document is confident.*"]
    out += [""]

    # 6 -- coverage
    out += ["## 6. Coverage", "",
            "Every (family, container order) cell the corpus exercises. A cell that empties",
            "on a rerun means a family stopped being tested by real documents.", ""]
    cells = collections.Counter((r["assignment"].family or "unexplained",
                                 r["signature"].container_order or "flat") for r in rows)
    orders = sorted({c[1] for c in cells})
    out += _table(["family"] + orders,
                  [[f.label] + [cells.get((f.label, o), "·") for o in orders]
                   for f in FAMILIES])
    out += ["", f"*{len(cells)} of {len(FAMILIES) * len(orders)} cells exercised.*", ""]
    return "\n".join(out) + "\n"


def _by_group(rows):
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[(row["lane"], row["signature"].group)].append(row)
    return grouped


# ---------------------------------------------------------------------------
# modes


def _exempt() -> dict:
    """``applies_to`` substring -> reason, in the shape suite exemptions use."""
    if not UNEXPLAINED.exists():
        return {}
    return {e["applies_to"]: e["reason"]
            for e in json.loads(UNEXPLAINED.read_text()).get("exemptions", [])}


def do_write(rows) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SIGNATURES.write_text(json.dumps(serialise(rows), indent=1) + "\n")
    REPORT.write_text(report(rows))
    print(f"{len(rows)} documents -> {SIGNATURES.relative_to(REPO_ROOT)}, "
          f"{REPORT.relative_to(REPO_ROOT)}")
    for label, n in sorted(serialise(rows)["families"].items(), key=lambda kv: -kv[1]):
        print(f"  {n:>4}  {label}")
    return 0


def do_check(rows) -> int:
    if not SIGNATURES.exists():
        print("no signatures.json -- run --write first", file=sys.stderr)
        return 1
    want = SIGNATURES.read_text()
    got = json.dumps(serialise(rows), indent=1) + "\n"
    if want == got:
        print("no drift")
        return 0
    old = {r["signature"]["path"]: r for r in json.loads(want)["records"]}
    new = {r["signature"]["path"]: r for r in json.loads(got)["records"]}
    for path in sorted(set(old) | set(new)):
        a, b = old.get(path), new.get(path)
        if a is None:
            print(f"  NEW      {b['assignment']['family']}  {path}")
        elif b is None:
            print(f"  GONE     {a['assignment']['family']}  {path}")
        elif a["assignment"]["family"] != b["assignment"]["family"]:
            print(f"  MOVED    {a['assignment']['family']} -> "
                  f"{b['assignment']['family']}  {path}")
        elif a != b:
            print(f"  CHANGED  {path}")
    print("\ndrift: signatures.json is stale, rerun --write and review the diff",
          file=sys.stderr)
    return 1


def do_assert(rows) -> int:
    errors = []
    exempt = _exempt()
    for family in FAMILIES:
        if not any(r["assignment"].family == family.label for r in rows):
            errors.append(f"family {family.label!r} matches no document -- "
                          f"it is no longer exercised by the corpus")
    for row in rows:
        if row["assignment"].family:
            continue
        name = row["signature"].path
        if not any(key in name for key in exempt):
            errors.append(f"unexplained, and not in unexplained.json: {name}")
    for err in errors:
        print(f"FAIL {err}")
    print(f"\n{len(rows)} documents, {len(errors)} problems")
    return 1 if errors else 0


_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _inventory_paths(xlsx: Path) -> set[str]:
    """``Relative Path`` from the inventory, read with stdlib zipfile.

    The workbook is an ORACLE for the disk walk, never an input to it: nothing
    downstream reads a column of it, so a stale inventory can report a mismatch
    but can never change a family.
    """
    book = zipfile.ZipFile(xlsx)
    shared = ["".join(t.text or "" for t in si.iter(_NS + "t"))
              for si in ET.fromstring(book.read("xl/sharedStrings.xml"))]
    paths, header = set(), None
    for row in ET.fromstring(book.read("xl/worksheets/sheet2.xml")).iter(_NS + "row"):
        cells = []
        for cell in row.iter(_NS + "c"):
            value = cell.find(_NS + "v")
            cells.append(shared[int(value.text)] if cell.get("t") == "s" and value is not None
                         else (value.text if value is not None else ""))
        if header is None:
            header = cells
            continue
        record = dict(zip(header, cells))
        if record.get("Relative Path"):
            paths.add(record["Relative Path"])
    return paths


def do_reconcile(rows, xlsx: Path) -> int:
    if not xlsx.exists():
        print(f"inventory not found: {xlsx} -- SKIP")
        return 0
    listed = _inventory_paths(xlsx)
    # The inventory is keyed <Category>/<Group>/<rest>; the staged tree drops the
    # Category for the Ordinance (registry rule). Compare on basename, which is
    # what sync_acts already joins JSON to PDF on.
    # Seventeen inventory filenames carry leading whitespace; the staged copies
    # keep it verbatim (renaming a source breaks the metadata.filename join that
    # pairs a JSON back to its PDF), so the comparison strips it on both sides.
    on_disk = {Path(r["signature"].path).name.strip() for r in rows}
    missing = sorted(p for p in listed if Path(p).name.strip() not in on_disk)
    extra = sorted(on_disk - {Path(p).name.strip() for p in listed})
    print(f"inventory {len(listed)} rows, staged {len(rows)} documents")
    for path in missing:
        print(f"  MISSING from the staged corpus: {path}")
    for name in extra:
        print(f"  not in the inventory (staged anyway): {name}")
    if missing:
        print(f"\n{len(missing)} inventory documents are not staged", file=sys.stderr)
        return 1
    print("every inventory document is staged")
    return 0


def do_verify_lanes(rows) -> int:
    """Where the classifier and today's directory routing disagree.

    Today the profile is chosen by lane: acts and rules both parse as
    consolidated statutes, and the ordinance lane goes to a separate pipeline
    built for one law. A disagreement here is not automatically a bug -- the
    amending instruments SHOULD disagree, and that is the change -- but anything
    outside the expected sets is a finding.
    """
    disagree = collections.Counter()
    for row in rows:
        family = row["assignment"].family
        if family == "consolidated" or family is None:
            continue
        if family in ("unconvertible", "urdu", "no_text_layer"):
            disagree[(row["lane"], f"refused: {family}")] += 1
        else:
            disagree[(row["lane"], family)] += 1
    for (lane, family), n in sorted(disagree.items()):
        print(f"  {n:>3}  {lane:<10} would parse as {family}")
    print(f"\n{sum(disagree.values())} of {len(rows)} documents route differently "
          f"under --profile auto")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    for flag, help_text in (("--write", "measure and write the artifacts"),
                            ("--check", "fail if a rerun differs from signatures.json"),
                            ("--assert", "fail on an unexercised family or an "
                                         "unexplained document"),
                            ("--reconcile", "compare the staged corpus to the inventory"),
                            ("--verify-lanes", "classifier vs today's lane routing")):
        mode.add_argument(flag, action="store_true", help=help_text)
    ap.add_argument("--inventory", default=None,
                    help="path to FBR_Document_Inventory.xlsx (for --reconcile)")
    args = ap.parse_args(argv)

    rows = census()
    if not rows:
        print("no corpus staged -- SKIP")
        return 0
    if args.write:
        return do_write(rows)
    if args.check:
        return do_check(rows)
    if getattr(args, "assert"):
        return do_assert(rows)
    if args.reconcile:
        return do_reconcile(rows, Path(args.inventory or "").expanduser())
    return do_verify_lanes(rows)


if __name__ == "__main__":
    raise SystemExit(main())
