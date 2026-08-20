#!/usr/bin/env python3
"""Pipeline gate: package self-checks always, corpus regression suites when present.

Two tiers, because the two kinds of check need different things:

* **Self-checks** (``<module>._demo()``) are pure and need no corpus, so they run
  everywhere including CI. They are where the grammars and calibration are pinned --
  the code a new pipeline fork diverges from first.
* **Regression suites** (``tools/<pipeline>/run_tests.py``) assert invariants and cases
  against converted output under ``data/corpora/<pipeline>/output/``, which is
  gitignored and absent from CI. Missing corpus is a SKIP, never a failure; a present
  corpus that fails is a hard failure.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

#: pipeline package -> (regression runner, corpus env var, corpus default dir)
PIPELINES = {
    "fbr_ingest": ("tools/ordinance/run_tests.py", "CORPUS_ORDINANCE", "ordinance"),
    "acts_ingest": ("tools/acts/run_tests.py", "CORPUS_ACTS", "acts"),
}


def _self_checks(package: str, errors: list[str]) -> None:
    """Run every ``_demo()`` the package exposes.

    Discovered rather than listed: the Ordinance pipeline has none, the Acts pipeline
    has seven, and a fork will grow its own. A hardcoded list silently stops covering
    whatever gets added -- this file used to run exactly one of the seven.
    """
    package_dir = ROOT / "packages" / package
    ran = 0
    for path in sorted(package_dir.glob("*.py")):
        if path.name.startswith("__"):
            continue
        module_name = f"{package}.{path.stem}"
        try:
            module = importlib.import_module(module_name)
        except Exception as err:
            errors.append(f"{module_name}: import failed: {err}")
            print(f"FAIL import {module_name}: {err}")
            continue
        demo = getattr(module, "_demo", None)
        if not callable(demo):
            continue
        try:
            demo()
            ran += 1
        except Exception as err:
            errors.append(f"{module_name}._demo: {err}")
            print(f"FAIL {module_name}._demo: {err}")
    print(f"OK {package}: {ran} self-check(s) passed")


def _corpus_dir(env: str, default: str) -> Path:
    raw = os.environ.get(env) or str(ROOT / "data" / "corpora" / default)
    return ROOT / raw  # a no-op when raw is already absolute


def _regression(runner: str, env: str, default: str, errors: list[str]) -> None:
    corpus = _corpus_dir(env, default)
    if not any(corpus.glob("output/*.json")):
        print(f"SKIP {runner}: no converted output under {corpus}/output")
        return
    environ = {**os.environ, "PYTHONPATH": os.pathsep.join(
        [str(ROOT / "packages"), os.environ.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)}
    result = subprocess.run(
        [sys.executable, str(ROOT / runner)],
        cwd=ROOT, env=environ, capture_output=True, text=True,
    )
    # the per-edition banner is "########## name ##########", so count LINES
    editions = sum(1 for ln in result.stdout.splitlines()
                   if ln.startswith("##########")) or 1
    if result.returncode == 0:
        print(f"OK {runner}: {editions} edition(s) pass")
        return
    errors.append(f"{runner}: exit {result.returncode}")
    print(f"FAIL {runner}: exit {result.returncode}")
    for line in result.stdout.splitlines():
        if "FAIL" in line or "RESULT:" in line:
            print(f"    {line}")
    print(result.stderr[-2000:], file=sys.stderr)


def main() -> int:
    errors: list[str] = []

    # The path resolver every pipeline tool now depends on. It is checked first
    # because a wrong repo root makes every result below meaningless.
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from corpus_paths import _demo as paths_demo

        paths_demo()
    except Exception as err:
        errors.append(f"tools/corpus_paths.py: {err}")
        print(f"FAIL tools/corpus_paths.py: {err}")

    for package, (runner, env, default) in PIPELINES.items():
        try:
            module = importlib.import_module(package)
            print(f"OK import {package} from {getattr(module, '__file__', '?')}")
        except Exception as err:
            errors.append(f"{package}: {err}")
            print(f"FAIL import {package}: {err}")
            continue
        _self_checks(package, errors)
        _regression(runner, env, default, errors)

    if errors:
        print(f"Pipeline gate failed ({len(errors)} error(s))")
        return 1
    print("Pipeline gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
