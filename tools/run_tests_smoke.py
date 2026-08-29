#!/usr/bin/env python3
"""Pipeline gate: package self-checks always, corpus regression suites when present.

Two tiers, because the two kinds of check need different things:

* **Self-checks** (``<module>._demo()``) are pure and need no corpus, so they run
  everywhere including CI. They are where the grammars, the calibration and each
  corpus profile are pinned -- and since the Acts and Rules lanes are now one
  implementation behind two profiles, they are also where a profile-gated behaviour is
  asserted for both corpora without needing either.
* **Regression suites** (``tools/run_suite.py <lane>``) assert invariants and cases
  against converted output under ``data/corpora/<lane>/output/``, which is gitignored
  and absent from CI. Missing corpus is a SKIP, never a failure; a present corpus that
  fails is a hard failure.

The lanes come from :mod:`backend.services.corpus_registry`, so a fourth pipeline is
one registry entry rather than another table here.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

# Adds apps/api and packages/ to sys.path as a side effect, then hands us the one
# lane registry. This file used to carry its own three-entry table plus a copy of the
# corpus-path arithmetic; both are now read from the registry the API reads.
from corpus_paths import CORPORA  # noqa: E402 (sys.path bootstrap above)


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


def _regression(runner: list[str], output: Path | None, errors: list[str]) -> None:
    """Run a corpus-dependent check. ``output=None`` means the runner decides
    for itself whether its corpus is present (``discover_corpus`` reads source
    PDFs, not converted JSON, so it has no output directory to test)."""
    label = " ".join(runner)
    if output is not None and not any(output.glob("*.json")):
        print(f"SKIP {label}: no converted output under {output}")
        return
    environ = {**os.environ, "PYTHONPATH": os.pathsep.join(
        [str(ROOT / "packages"), os.environ.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)}
    result = subprocess.run(
        [sys.executable, str(ROOT / runner[0]), *runner[1:]],
        cwd=ROOT, env=environ, capture_output=True, text=True,
    )
    # the per-edition banner is "########## name ##########", so count LINES
    editions = sum(1 for ln in result.stdout.splitlines()
                   if ln.startswith("##########")) or 1
    if result.returncode == 0:
        print(f"OK {label}: {editions} edition(s) pass")
        return
    errors.append(f"{label}: exit {result.returncode}")
    print(f"FAIL {label}: exit {result.returncode}")
    for line in result.stdout.splitlines():
        if "FAIL" in line or "RESULT:" in line:
            print(f"    {line}")
    print(result.stderr[-2000:], file=sys.stderr)


def main() -> int:
    errors: list[str] = []

    # The path resolver every pipeline tool now depends on, and the registry behind
    # it. Checked first because a wrong repo root makes every result below meaningless.
    for module_name in ("corpus_paths", "backend.services.corpus_registry"):
        try:
            importlib.import_module(module_name)._demo()
        except Exception as err:
            errors.append(f"{module_name}: {err}")
            print(f"FAIL {module_name}: {err}")

    # The Acts and Rules lanes are two profiles of one implementation, so their
    # self-checks live in the shared package and must run once rather than per lane.
    # The lane packages themselves are thin profile bindings with no _demo() of their
    # own -- without this the gate silently ran zero self-checks after the merge.
    _self_checks("legal_ingest", errors)

    # Structure discovery is data, and stale data is worse than none: a family
    # threshold that has drifted away from the corpus still classifies, it just
    # classifies wrongly. `--check` re-measures and fails if the committed
    # signatures no longer match. Like the lane suites it needs the gitignored
    # corpus, so an unstaged tree is a SKIP -- `discover_corpus` prints
    # "no corpus staged" and exits 0.
    _regression(["tools/discover_corpus.py", "--check"], None, errors)

    for corpus in CORPORA:
        package = corpus.package
        runner = ["tools/run_suite.py", corpus.label]
        try:
            module = importlib.import_module(package)
            print(f"OK import {package} from {getattr(module, '__file__', '?')}")
        except Exception as err:
            errors.append(f"{package}: {err}")
            print(f"FAIL import {package}: {err}")
            continue
        _self_checks(package, errors)
        _regression(runner, corpus.output_path(), errors)

    if errors:
        print(f"Pipeline gate failed ({len(errors)} error(s))")
        return 1
    print("Pipeline gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
