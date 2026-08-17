#!/usr/bin/env python3
"""Strip host-local path variables from a .env before shipping it to CodeRun.

Local ``.env`` values like ``CORPUS_ORDINANCE=./data/corpora/ordinance`` override
the API image defaults (``/data/corpus/ordinance``, ``/seed/corpus/...``,
``/app/data/...``). The Library header then reports those directories as missing
even when the container has the intended mounts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HOST_PATH_KEYS = frozenset(
    {
        "CORPUS_ORDINANCE",
        "CORPUS_ACTS",
        "SEED_CORPUS_ORDINANCE",
        "SEED_CORPUS_ACTS",
        "DATABASE_PATH",
        "UPLOAD_DIR",
        "OCR_CACHE_DIR",
    }
)


def _assignment_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].lstrip()
    key, sep, _value = stripped.partition("=")
    if not sep:
        return None
    return key.strip() or None


def filter_deploy_env(text: str) -> str:
    """Drop host-path assignments; keep comments, blanks, and other keys."""
    kept: list[str] = []
    for line in text.splitlines(keepends=True):
        key = _assignment_key(line)
        if key in HOST_PATH_KEYS:
            continue
        kept.append(line)
    return "".join(kept)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src", type=Path, help="Source .env file")
    parser.add_argument("dest", type=Path, help="Filtered .env to write")
    args = parser.parse_args(argv)
    args.dest.write_text(filter_deploy_env(args.src.read_text(encoding="utf-8")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
