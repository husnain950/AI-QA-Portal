"""The anomaly register is committed, so a change to it has to be deliberate.

``data/corpora/*/output/`` is gitignored, so ``run_tests_smoke.py`` SKIPs all three
lane suites on CI and the register was enforced by nothing but prose in
``wip/tasks.md``.  Seven rounds moved it 210 -> 64 and a silent regression would
have been invisible to every check the project runs.

This is the same trick ``test_profile_auto_resolves_the_lane.py`` uses to get a
corpus-dependent fact onto CI: replay a committed measurement.  With no corpus the
test skips, exactly as the lane suites do; with one staged it compares.

A round that IMPROVES the register fails this test until ``register.json`` is
updated.  That is intended -- the number then moves in the same PR that moved it.
"""

from __future__ import annotations

import collections
import json
import pathlib
import re
import subprocess
import sys

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SNAPSHOT = _ROOT / "tools" / "suite" / "register.json"

sys.path.insert(0, str(_ROOT / "tools"))
from corpus_paths import LABELS, output_dir  # noqa: E402

_FAIL = re.compile(r"\[ *FAIL \((\d+)\)\] +([a-z_]+)")


def _measure(lane: str) -> dict[str, int]:
    """Hits per invariant for one lane, read from the suite's own output.

    The suite has no machine-readable per-invariant total -- ``--json`` truncates
    ``failures`` to 20 while keeping ``n_failures`` -- and parsing the printed
    line is what ``scan_heading_leaks.py`` already does.
    """
    out = subprocess.run(
        [sys.executable, str(_ROOT / "tools" / "run_suite.py"), lane],
        capture_output=True, text=True, cwd=_ROOT,
    ).stdout
    counts: collections.Counter = collections.Counter()
    for m in _FAIL.finditer(out):
        counts[m.group(2)] += int(m.group(1))
    return dict(counts)


def _staged() -> bool:
    return all(any(output_dir(lane).glob("*.json")) for lane in LABELS)


def test_register_matches_the_committed_snapshot():
    if not _staged():
        pytest.skip("corpus not staged -- the lane suites skip here too")
    snapshot = json.loads(_SNAPSHOT.read_text())["lanes"]
    live = {lane: _measure(lane) for lane in LABELS}
    assert live == snapshot, (
        "the anomaly register moved.\n"
        f"  committed: {json.dumps(snapshot, sort_keys=True)}\n"
        f"  measured:  {json.dumps(live, sort_keys=True)}\n"
        "If this is an improvement, regenerate tools/suite/register.json in the "
        "same PR. If it is not, it is a regression."
    )


def test_snapshot_total_agrees_with_its_own_lanes():
    """The headline number and the per-lane detail cannot drift apart.

    ``total`` is what the write-ups quote; the lanes are what the test compares.
    Nothing else would notice if a hand edit moved one and not the other.
    """
    payload = json.loads(_SNAPSHOT.read_text())
    counted = sum(sum(inv.values()) for inv in payload["lanes"].values())
    assert payload["total"] == counted, (
        f"register.json total is {payload['total']} but its lanes sum to {counted}"
    )


def test_snapshot_names_only_real_invariants():
    """A typo'd invariant name would make the snapshot silently under-gate."""
    from suite import runner

    for lane, invariants in json.loads(_SNAPSHOT.read_text())["lanes"].items():
        bound = {name for name, _ in runner.invariants_for(lane).ALL_INVARIANTS}
        unknown = set(invariants) - bound
        assert not unknown, f"{lane}: register.json names {unknown}, not in ALL_INVARIANTS"
