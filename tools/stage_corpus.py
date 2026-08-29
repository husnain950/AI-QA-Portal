#!/usr/bin/env python3
"""Stage the FBR document repository into the lane trees the pipeline reads.

    python tools/stage_corpus.py --from "/path/to/FBR Ordinance" [--dry-run]

The lane corpora under ``data/corpora/`` are gitignored and were staged by hand,
which is how they drifted from the repository they came from: measured against
``FBR_Document_Inventory.xlsx``, **28 of the 183 documents were missing**, and 26
of those were Ordinance -- the whole Islamabad Capital Territory (Tax on
Services) group and every amending ordinance. The Ordinance lane held exactly one
law, so its pipeline had only ever been measured against one law.

The mapping is a path rewrite, not a rule table. Every inventory row's
``Relative Path`` is ``<Category>/<Group>/<rest>``, verified for 183/183 rows
including the three-deep Recruitment Rules ones (the cadre folder is a SUB-group,
so ``<rest>`` simply carries it). ``Category`` names the lane; where the lane
keeps its sources under a titled subdirectory the registry already says so, so
the destination is ``corpus.source_within(corpus.path()) / <Group>/<rest>`` --
which puts Acts under ``acts/Acts/``, Rules under ``rules/Rules/`` and the
Ordinance beside ``output/``, exactly as each lane already files them.

Nineteen source files have no extension and are real PDFs; seventeen filenames
carry leading whitespace. Both are copied verbatim -- ``sync_acts.is_pdf``
sniffs magic bytes downstream, and renaming a source would break the
``metadata.filename`` join that pairs a JSON back to its PDF.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_paths import LABELS, get  # noqa: E402 (sys.path bootstrap above)

#: Inventory Category -> lane label. The only place the two vocabularies meet.
LANE_OF = {"Acts": "acts", "Rules": "rules", "Ordinance": "ordinance"}


def destination(rel: Path) -> Path | None:
    """Where an inventory-relative source path belongs, or None if unrecognised."""
    parts = rel.parts
    if len(parts) < 2 or parts[0] not in LANE_OF:
        return None
    corpus = get(LANE_OF[parts[0]])
    return corpus.source_within(corpus.path()).joinpath(*parts[1:])


#: Not sources. The Ordinance files its PDFs beside these, so a plain walk of
#: that lane's source directory would sweep up its converted JSON as well.
NON_SOURCE_DIRS = {"output", "reports"}


def iter_documents(root: Path):
    """Every source document under ``root``: real PDFs plus legacy Word files.

    By magic bytes, not extension -- nineteen corpus sources have no ``.pdf``
    suffix and five of them are Customs Act editions.
    """
    from legal_ingest.signature import is_pdf

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if NON_SOURCE_DIRS & set(path.relative_to(root).parts):
            continue
        if path.suffix.lower() in (".doc", ".docx") or is_pdf(path):
            yield path


def plan(source_root: Path) -> list[tuple[Path, Path]]:
    """Every (source, destination) pair that is not already staged."""
    pending = []
    for src in sorted(p for p in source_root.rglob("*") if p.is_file()):
        if src.name.startswith("."):
            continue
        dst = destination(src.relative_to(source_root))
        if dst is None or dst.exists():
            continue
        pending.append((src, dst))
    return pending


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="source", required=True,
                    help="the FBR repository root (holds Acts/, Rules/, Ordinance/)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be copied and change nothing")
    args = ap.parse_args(argv)

    source_root = Path(args.source).expanduser()
    if not source_root.is_dir():
        print(f"error: not a directory: {source_root}", file=sys.stderr)
        return 2

    pending = plan(source_root)
    for src, dst in pending:
        print(f"{'would copy' if args.dry_run else 'copy'} {dst}")
        if not args.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    verb = "would stage" if args.dry_run else "staged"
    print(f"\n{verb} {len(pending)} documents")
    for lane in LABELS:
        root = get(lane).source_within(get(lane).path())
        n = sum(1 for p in iter_documents(root))
        print(f"  {lane:<10} {n:>3} source documents under {root}")
    return 0


def _demo() -> None:
    # The whole mapping, asserted on the three shapes the inventory actually has.
    assert destination(Path("Acts/Customs Act, 1969/x.pdf")).as_posix().endswith(
        "acts/Acts/Customs Act, 1969/x.pdf")
    assert destination(Path("Rules/Recruitment Rules/Cadre/SRO 82(I)_2018")).as_posix(
    ).endswith("rules/Rules/Recruitment Rules/Cadre/SRO 82(I)_2018")
    # The Ordinance files its sources beside output/, with no titled subdirectory
    # -- the registry says so, and asking it is what keeps this from being a
    # second copy of that fact.
    ordinance = destination(Path("Ordinance/Income Tax Ordinance, 2001/x.pdf")).as_posix()
    assert ordinance.endswith("ordinance/Income Tax Ordinance, 2001/x.pdf"), ordinance
    assert destination(Path("FBR_Document_Inventory.xlsx")) is None
    assert destination(Path("Something/Else/x.pdf")) is None
    print("stage_corpus self-check passed")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        _demo()
    else:
        raise SystemExit(main())
