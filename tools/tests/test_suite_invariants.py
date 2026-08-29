"""The per-lane invariant binding, checked without a corpus.

This matters because CI never runs the regression suites -- `data/corpora/*/output/` is
gitignored, so every lane SKIPs there. The suite's own gate (a byte-compare of all 103
editions' reports) only runs on a machine with the corpus staged. These assertions are the
part that can run anywhere, and they cover the failure mode the split introduced: an
invariant resolving to the wrong lane's implementation, which no import error would catch.
"""

from __future__ import annotations

import functools
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from suite import runner  # noqa: E402
from suite.invariants import _common  # noqa: E402

#: The Acts and the Rules run the same 58 checks; the Ordinance pipeline has no OCR
#: stage and no provisional/text-density concepts, so it runs 45.
EXPECTED_COUNTS = {"acts": 58, "rules": 58, "ordinance": 45}


def test_section_attribution_helpers():
    """The predicates behind ``section_carries_its_body`` /
    ``no_foreign_section_start_in_body``.  They decide whether a leaf is reported
    as having lost its statutory text to a neighbour, so the shapes they must
    tell apart are pinned rather than left to the corpus."""
    _common._demo_section_attribution()


def test_heading_leak_class_helpers():
    """The O02/O03 detectors (caption-in-heading, LEGAL REFERENCE, body chapters)."""
    _common._demo_heading_leak_class()


def test_toc_omitted_chapter_caption_not_glued():
    """PDF-independent pin: Customs 14A must not absorb the Chapter IV caption."""
    from suite.invariants.acts import inv_toc_omitted_chapter_caption_not_glued

    assert inv_toc_omitted_chapter_caption_not_glued({}) == []


def test_each_lane_binds_its_full_invariant_set():
    for lane, expected in EXPECTED_COUNTS.items():
        bound = runner.invariants_for(lane).ALL_INVARIANTS
        names = [name for name, _ in bound]
        assert len(bound) == expected, f"{lane}: {len(bound)} invariants, expected {expected}"
        assert len(set(names)) == len(names), f"{lane}: duplicate invariant name"
        assert all(callable(fn) for _, fn in bound), f"{lane}: non-callable invariant"


def _bound_kwarg(fn, kw):
    """The value an invariant will actually use, whether defaulted or bound per lane."""
    if isinstance(fn, functools.partial):
        return fn.keywords[kw]
    return (fn.__kwdefaults__ or {})[kw]


def test_split_ordinal_binds_per_lane():
    """The Rules regex carries a negative lookahead the other two lanes must not get.

    This is the one shared invariant whose behaviour genuinely differs by lane, so it is
    the one place a wrong binding would silently change what the suite reports.
    """
    got = {lane: _bound_kwarg(dict(runner.invariants_for(lane).ALL_INVARIANTS)
                              ["no_split_ordinals"], "split_ordinal").pattern
           for lane in EXPECTED_COUNTS}

    assert got["rules"].endswith(r"(?!\s*\.\s*\d)"), "Rules lost its lookahead"
    assert got["acts"] == got["ordinance"] == _common._SPLIT_ORDINAL.pattern
    assert got["acts"] != got["rules"], "Acts must not inherit the Rules regex"


def test_ref_key_binds_per_lane():
    """Ordinance sorts footnote refs its own way; Acts and Rules share one implementation."""
    from suite.invariants import ordinance

    got = {lane: _bound_kwarg(dict(runner.invariants_for(lane).ALL_INVARIANTS)
                              ["footnotes_in_numeric_order"], "ref_key")
           for lane in EXPECTED_COUNTS}

    assert got["acts"] is got["rules"] is _common._ref_key
    assert got["ordinance"] is ordinance._ref_key
    assert got["ordinance"] is not _common._ref_key


def test_lane_overrides_win_over_the_shared_copy():
    """A lane defining its own inv_<name> must shadow _common's, not sit beside it."""
    import importlib

    for lane in EXPECTED_COUNTS:
        mod = importlib.import_module(f"suite.invariants.{lane}")
        bound = dict(runner.invariants_for(lane).ALL_INVARIANTS)
        for attr in vars(mod):
            if not attr.startswith("inv_"):
                continue
            name = attr[len("inv_"):]
            # A lane-local invariant that no order list mentions is dead code -- the
            # override would silently never run.
            assert name in bound, f"{lane}: {attr} is defined but never bound"
            assert bound[name] is getattr(mod, attr), (
                f"{lane}: {attr} is shadowed by the shared copy instead of overriding it")


def test_unknown_invariant_name_is_an_error_not_a_silent_skip():
    try:
        _common.all_invariants({}, ["definitely_not_an_invariant"])
    except KeyError as err:
        assert "definitely_not_an_invariant" in str(err)
    else:
        raise AssertionError("an unknown invariant name must raise, not be skipped")


def test_o03_cases_are_shipped():
    import json
    import os

    path = os.path.join(os.path.dirname(__file__), "..", "suite", "cases", "acts.json")
    with open(path, encoding="utf-8") as fh:
        cases = json.load(fh)["cases"]
    ids = {c["id"] for c in cases}
    for cid in (
        "o03_2025_sec14a_heading_clean",
        "o03_2025_sec14a_body_present",
        "o03_2025_sec14_no_14a_text",
        "o03_2025_sec14_no_legal_reference",
        "o03_2025_chapter_iv_present",
        "o02_2025_sec72a_heading_from_body",
        "rca_2007_sec14a_body_present",
        "rca_2007_sec14_no_14a_text",
    ):
        assert cid in ids, cid
    o03 = [c for c in cases if c["id"].startswith("o03_2025_")]
    assert all(c["applies_to"] == "30th June, 2025" for c in o03)
    assert all(c["status"] == "active" for c in o03)
