"""Per-document invariant exemptions: the scoping must actually scope.

The risk this pins is not "does the happy path work" -- it is that a too-loose
`applies_to`, or a typo'd invariant name, quietly stops gating a document nobody
meant to exempt. Both of those fail silently without a check.
"""

from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from suite import runner  # noqa: E402


def _cases_file(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": []}), encoding="utf-8")
    return str(path)


def _exemptions_file(tmp_path, entries):
    path = tmp_path / "exemptions.json"
    path.write_text(json.dumps({"exemptions": entries}), encoding="utf-8")
    return str(path)


def _invariants(failing=True):
    """A one-invariant module standing in for a lane's invariants."""
    return SimpleNamespace(ALL_INVARIANTS=[
        ("always_fails", lambda doc: ["a failure"] if failing else []),
    ])


def _doc(filename):
    return {"metadata": {"filename": filename}}


def test_matching_exemption_stops_the_failure_gating(tmp_path):
    ex = _exemptions_file(tmp_path, [
        {"applies_to": "Customs Rules, 2001", "invariant": "always_fails",
         "reason": "traced to the source PDF"},
    ])
    results = runner.run(_doc("Customs Rules, 2001 (Updated Up to 30.06.2023)"),
                         _invariants(), _cases_file(tmp_path), ex)
    _, ok = runner.summarize(results)

    assert ok, "an exempted invariant must not fail the build"
    assert [i["name"] for i in results["invariants"]] == []
    assert [i["name"] for i in results["exempt_invariants"]] == ["always_fails"]
    # the hits are still counted -- an exemption documents a failure, it does not hide it
    assert results["exempt_invariants"][0]["n_failures"] == 1
    assert results["exempt_invariants"][0]["reason"] == "traced to the source PDF"


def test_exemption_does_not_leak_to_another_document(tmp_path):
    ex = _exemptions_file(tmp_path, [
        {"applies_to": "Customs Rules, 2001", "invariant": "always_fails",
         "reason": "scoped to one compilation"},
    ])
    results = runner.run(_doc("Sales Tax Rules, 2006 (Updated upto 01-01-2025)"),
                         _invariants(), _cases_file(tmp_path), ex)
    _, ok = runner.summarize(results)

    assert not ok, "a document outside applies_to must still be gated"
    assert [i["name"] for i in results["invariants"]] == ["always_fails"]
    assert results["exempt_invariants"] == []


def test_stale_exemption_announces_itself(tmp_path):
    """A passing exempt invariant is reported, so the entry can be deleted."""
    ex = _exemptions_file(tmp_path, [
        {"applies_to": "Customs Rules", "invariant": "always_fails", "reason": "fixed since"},
    ])
    results = runner.run(_doc("Customs Rules, 2001"), _invariants(failing=False),
                         _cases_file(tmp_path), ex)
    report, ok = runner.summarize(results)

    assert ok
    assert results["exempt_invariants"][0]["passed"] is True
    assert "stale" in report


def test_no_exemptions_file_means_no_exemptions(tmp_path):
    results = runner.run(_doc("anything"), _invariants(), _cases_file(tmp_path),
                         str(tmp_path / "does-not-exist.json"))
    _, ok = runner.summarize(results)
    assert not ok
    assert results["exempt_invariants"] == []


def test_shipped_exemptions_name_real_invariants():
    """A typo'd invariant name would exempt nothing while looking like it did."""
    for lane in ("acts", "rules", "ordinance"):
        path = runner.exemptions_path_for(lane)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            entries = json.load(fh).get("exemptions", [])
        known = {name for name, _ in runner.invariants_for(lane).ALL_INVARIANTS}
        for entry in entries:
            assert entry["invariant"] in known, (
                f"{lane}: exemption names unknown invariant {entry['invariant']!r}")
            assert entry.get("reason"), (
                f"{lane}: exemption for {entry['invariant']!r} carries no reason")


def test_shipped_exemptions_match_exactly_one_corpus_document():
    """`applies_to` is a substring match, so an over-broad value silently widens scope."""
    import glob

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools"))
    from corpus_paths import get  # noqa: E402  (needs the bootstrap above)

    for lane in ("acts", "rules", "ordinance"):
        path = runner.exemptions_path_for(lane)
        if not os.path.exists(path):
            continue
        names = [os.path.splitext(os.path.basename(p))[0]
                 for p in glob.glob(os.path.join(str(get(lane).output_path()), "*.json"))]
        if not names:  # corpus not staged (CI); nothing to check against
            continue
        with open(path, encoding="utf-8") as fh:
            entries = json.load(fh).get("exemptions", [])
        for entry in entries:
            hit = [n for n in names if entry["applies_to"] in n]
            assert len(hit) == 1, (
                f"{lane}: applies_to {entry['applies_to']!r} matches {len(hit)} "
                f"documents {hit}, expected exactly 1")
