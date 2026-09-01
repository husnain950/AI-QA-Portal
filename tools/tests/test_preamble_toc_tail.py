"""The preamble must not carry the tail of the Contents page.

`inv_preamble_carries_no_toc_tail` counts, in the pipeline's own register, a
defect the portal currently answers by deleting the evidence:
`json_parser.is_junk_leaf` matches the same Contents column header and drops the
whole leaf, so the preamble *and* the enacting formula of four Customs Act
editions never reach a reviewer.

A gate that cannot fail is a no-op, so this file makes it fail on purpose.  The
third case is the one that matters most: the invariant is about the PREAMBLE, not
about the marker, and a Contents listing that is correctly parked in its own
addressable leaf must not be reported.
"""

from __future__ import annotations

import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from suite.invariants import _common  # noqa: E402

inv = _common.inv_preamble_carries_no_toc_tail

#: What the Customs Act 1969 editions actually print: the last rows of the
#: contents listing, then the enacting formula, in one node.
CUSTOMS_SHAPE = (
    "THE CUSTOMS ACT, 1969\n"
    "Section Page\n"
    "No.\n"
    "224 Extension of time limit. 212\n"
    "THE FIRST SCHEDULE 216\n"
    "xxi\n"
    "1[Act No. IV of 1969]\n"
    "[3rd March,1969]\n"
    "An Act to consolidate and amend the law relating to Customs\n"
    "It is hereby enacted as follows:-"
)


def test_fires_on_a_preamble_carrying_a_contents_tail():
    bad = inv({"preamble": {"plain_text": CUSTOMS_SHAPE}})
    assert len(bad) == 1, bad
    assert "Contents tail" in bad[0]


def test_fires_when_the_header_is_only_in_the_html():
    bad = inv({"preamble": {"plain_text": "", "html": "<p>Section Page No.</p>"}})
    assert len(bad) == 1, bad


def test_passes_on_a_clean_preamble():
    clean = (
        "1[Act No. IV of 1969]\n"
        "An Act to consolidate and amend the law relating to Customs\n"
        "It is hereby enacted as follows:-"
    )
    assert inv({"preamble": {"plain_text": clean}}) == []


def test_does_not_fire_on_a_contents_leaf_outside_the_preamble():
    """The addressable Contents sink is intentional, not a defect.

    `is_junk_leaf` already exempts `code=Contents` for this reason.  An invariant
    that fired here would report the pipeline doing the right thing.
    """
    doc = {
        "preamble": {"plain_text": "An Act to consolidate the law relating to Customs"},
        "chapters": [{"code": "Contents", "sections": [
            {"code": "Contents", "plain_text": "Section Page No.\n224 Extension. 212",
             "html": "<p>Section Page No.</p>"},
        ]}],
    }
    assert inv(doc) == []


def test_tolerates_a_document_with_no_preamble():
    assert inv({}) == []
    assert inv({"preamble": None}) == []
