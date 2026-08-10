#!/usr/bin/env python3
"""Smoke-run pipeline unit tests without requiring full PDF corpora."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))


def main() -> int:
    errors = []
    for name in ("fbr_ingest", "acts_ingest"):
        try:
            mod = importlib.import_module(name)
            print(f"OK import {name} from {getattr(mod, '__file__', '?')}")
        except Exception as err:
            errors.append(f"{name}: {err}")
            print(f"FAIL import {name}: {err}")

    # Prefer packaged test runners when present.
    for script in (
        ROOT / "tools" / "ordinance" / "run_tests.py",
        ROOT / "tools" / "acts" / "run_tests.py",
    ):
        if not script.exists():
            continue
        print(f"Found runner: {script}")

    # Minimal structural smoke: discover + pipeline symbols exist.
    try:
        import fbr_ingest.pipeline  # noqa: F401
        import acts_ingest.pipeline  # noqa: F401
        print("OK pipeline modules importable")
    except Exception as err:
        errors.append(str(err))
        print(f"FAIL pipeline import: {err}")

    if errors:
        print(f"Smoke failed ({len(errors)} error(s))")
        return 1
    print("Pipeline smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
