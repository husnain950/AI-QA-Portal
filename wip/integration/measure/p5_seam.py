"""P5's API half, measured through the REAL sync rather than through the pieces.

Two documents, both real corpus files, chosen because each carries one of the two
defects:

  Customs Act 1969 (2014)  -- its PREAMBLE has a Contents tail glued in front of the
                              enacting formula, so `is_junk_leaf` deleted the leaf.
  Sales Tax Act 1990       -- two headings carry the `[...]` omission marker, which
                              the dot-leader substitution and the trailing mop-up
                              between them turned into `[ ]` and a bare `[`.

Run one pass with the old code and one with the new against the SAME scratch
database, so the second pass exercises carryover the way a deployment would:

    python3 wip/integration/measure/p5_seam.py --init --out /tmp/before.json   # old code
    python3 wip/integration/measure/p5_seam.py         --out /tmp/after.json   # new code
    python3 wip/integration/measure/p5_seam.py --diff /tmp/before.json /tmp/after.json

`--init` drops and recreates the scratch database; without it the existing rows stay,
which is the point.  Never points at a real database: the name is hard-coded.
"""

import argparse
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "data" / "corpora" / "acts"
STAGE = Path("/tmp/p5-seam-corpus")
SCRATCH_DB_NAME = "pdf_qa_p5scratch"

DOCS = [
    "Customs Act ,1969 (As amended up to 30th June, 2014)",
    "Sales Tax Act 1990 amended upto 30-06-2025",
]


def stage_corpus() -> Path:
    """A two-document corpus root, laid out the way `discover_acts_repo` expects."""
    if STAGE.exists():
        shutil.rmtree(STAGE)
    (STAGE / "output").mkdir(parents=True)
    (STAGE / "Acts").mkdir()
    pdfs = {p.name: p for p in (CORPUS / "Acts").rglob("*.pdf")}
    for stem in DOCS:
        src = CORPUS / "output" / f"{stem}.json"
        shutil.copy(src, STAGE / "output" / src.name)
        # NOT stripped: several corpus PDFs are named with a leading space, and
        # `metadata.filename` records the name verbatim -- which is how the real
        # `discover_acts_repo` pairs them.
        wanted = (json.loads(src.read_text(encoding="utf-8")).get("metadata") or {}).get(
            "filename", ""
        )
        pdf = pdfs.get(wanted) or pdfs.get(wanted.strip())
        if pdf is None:
            raise SystemExit(f"no PDF named {wanted!r} for {stem!r}")
        shutil.copy(pdf, STAGE / "Acts" / pdf.name)
    return STAGE


def scratch_url() -> str:
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    import backend.database as database

    base = database.normalize_database_url(
        os.environ.get("DATABASE_URL") or database.DEFAULT_DATABASE_URL
    )
    prefix, _, _ = base.rpartition("/")
    return f"{prefix}/{SCRATCH_DB_NAME}"


def init_db(url: str) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    prefix, _, name = url.rpartition("/")
    admin = create_engine(f"{prefix}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()

    api = ROOT / "apps" / "api"
    cfg = Config(str(api / "alembic.ini"))
    cfg.set_main_option("script_location", str(api / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


async def snapshot() -> dict:
    from backend.database import database_connection

    async with database_connection() as db:
        async with db.execute(
            "SELECT d.name, s.id, s.source_key, s.node_key, s.section_code,"
            " s.section_heading, s.review_status, s.quality_flags"
            " FROM sections s JOIN documents d ON d.id = s.document_id"
            " ORDER BY d.name, s.sort_order"
        ) as cur:
            rows = await cur.fetchall()
    # Rows are `DatabaseRow`, which iterates COLUMN NAMES -- tuple-unpacking one
    # silently yields the header for every row and collapses the whole snapshot to a
    # single key. Address the columns by name.
    out = {}
    for row in rows:
        raw = row["quality_flags"]
        try:
            codes = sorted(f.get("code", "") for f in json.loads(raw or "[]"))
        except (TypeError, json.JSONDecodeError):
            codes = []
        out[f"{row['name']}|{row['source_key']}"] = {
            "id": str(row["id"]), "node_key": row["node_key"],
            "code": row["section_code"], "heading": row["section_heading"],
            "status": row["review_status"], "flags": codes,
        }
    return out


async def run(out_path: Path, do_init: bool, force: bool = False) -> None:
    url = scratch_url()
    if do_init:
        init_db(url)
    os.environ["DATABASE_URL"] = url

    corpus = stage_corpus()
    from backend.sync_acts import run_sync

    summary = await run_sync(
        corpus, acts_repo=True, pdf_dir=corpus / "Acts", corpus_origin="acts",
        force=force,
    )
    state = await snapshot()
    print("sync: " + "  ".join(
        f"{k}={summary.get(k)}" for k in
        ("discovered", "validated", "added", "updated", "skipped", "failed")
    ))
    print(f"sections stored: {len(state)}")
    out_path.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")


def diff(before: Path, after: Path) -> None:
    a = json.loads(before.read_text(encoding="utf-8"))
    b = json.loads(after.read_text(encoding="utf-8"))

    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    kept = sorted(set(a) & set(b))
    reminted = [k for k in kept if a[k]["id"] != b[k]["id"]]
    reheaded = [k for k in kept if a[k]["heading"] != b[k]["heading"]]
    restatused = [k for k in kept if a[k]["status"] != b[k]["status"]]

    print(f"leaves before {len(a)}  after {len(b)}")
    print(f"  added        {len(added)}")
    print(f"  removed      {len(removed)}")
    print(f"  ids re-minted {len(reminted)}   <- must be 0")
    print(f"  status moved  {len(restatused)}   <- must be 0")
    print(f"  headings changed {len(reheaded)}")
    for k in added:
        print(f"\nADDED   {k}\n   flags={b[k]['flags']} status={b[k]['status']}"
              f"\n   heading={b[k]['heading']!r}")
    for k in removed:
        print(f"\nREMOVED {k}")
    for k in reheaded:
        print(f"\nHEADING {k}\n   before {a[k]['heading']!r}\n   after  {b[k]['heading']!r}")
    for k in reminted:
        print(f"\nRE-MINTED {k}: {a[k]['id']} -> {b[k]['id']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--diff", nargs=2, type=Path)
    args = ap.parse_args()
    if args.diff:
        diff(*args.diff)
        return
    if not args.out:
        ap.error("--out is required unless --diff")
    scratch_url()  # puts apps/api on sys.path
    asyncio.run(run(args.out, args.init, args.force))


if __name__ == "__main__":
    main()
