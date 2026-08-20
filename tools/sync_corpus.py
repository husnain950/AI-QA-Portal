#!/usr/bin/env python3
"""Sync Ordinance + Acts corpora into the QA portal database."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "packages"))

_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://crx:crx@127.0.0.1:5432/crx")
os.environ.setdefault("UPLOAD_DIR", str(ROOT / "data" / "uploads"))

from backend.services.corpus_sync import (  # noqa: E402
    default_acts_path,
    default_ordinance_path,
    run_corpus_sync,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Sync Ordinance + Acts into the QA portal")
    p.add_argument("--ordinance", type=Path, default=default_ordinance_path())
    p.add_argument("--acts", type=Path, default=default_acts_path())
    p.add_argument("--ordinance-only", action="store_true")
    p.add_argument("--acts-only", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument(
        "--metrics",
        action="store_true",
        help="Ingest pipeline QA reports from each repo's reports/ directory",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    summary = asyncio.run(
        run_corpus_sync(
            ordinance=args.ordinance,
            acts=args.acts,
            dry_run=args.dry_run,
            force=args.force,
            strict=args.strict,
            metrics=args.metrics,
            ordinance_only=args.ordinance_only,
            acts_only=args.acts_only,
        )
    )
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 1 if summary.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
