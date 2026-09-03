"""The preamble must not carry the tail of the Contents page.

`inv_preamble_carries_no_toc_tail` counts, in the pipeline's own register, a
defect the portal used to answer by deleting the evidence: `is_junk_leaf` matched
the same Contents column header and dropped the whole leaf, so the preamble *and*
the enacting formula of four Customs Act editions never reached a reviewer.  The
API now flags that leaf instead (`json_parser.assess_toc_tail`); these hits stay
here because the cause is the pipeline's.

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


#: Round 14: the column header is one SPELLING of the defect, not the defect.
#: Measured over the twenty converted Customs Act editions, fourteen open the
#: preamble correctly at ``1[Act No. IV of 1969]`` and SIX did not -- and two of
#: the six carry no column header at all.  Three more documents outside that
#: group were invisible for the same reason.  Widening the invariant took it
#: from 4 hits to 10 on IDENTICAL JSON, before the parser was touched.
FOLIO_ONLY_SHAPE = (
    "(xxii)\n"
    "1[Act No. IV of 1969]\n"
    "An Act to consolidate and amend the law relating to Customs\n"
    "It is hereby enacted as follows:-"
)

#: Two Federal Excise editions shipped a preamble that was the folio and nothing
#: else -- the enacting formula never reached it at all.
FOLIO_ALONE = "vi"

#: The Customs 30.06.2008 shape: schedule contents rows, no column header, and
#: (after the folio is stripped) no roman folio either.  Without the third branch
#: the invariant reported ZERO on a document that still carries the defect.
SCHEDULE_ROWS_SHAPE = (
    "THE FIRST SCHEDULE 213\n"
    "THE SECOND SHCEUDLE Omitted. 213\n"
    "THE THIRD SCHEDULE 213\n"
    "1[Act No. IV of 1969]\n"
    "It is hereby enacted as follows:-"
)


def test_fires_on_a_preamble_that_begins_on_a_front_matter_folio():
    bad = inv({"preamble": {"plain_text": FOLIO_ONLY_SHAPE}})
    assert len(bad) == 1, bad
    assert "front-matter folio" in bad[0]


def test_fires_when_the_preamble_is_the_folio_and_nothing_else():
    bad = inv({"preamble": {"plain_text": FOLIO_ALONE}})
    assert len(bad) == 1, bad


def test_fires_on_schedule_contents_rows_with_no_other_signal():
    """The branch that stops this gate being a no-op on Customs 30.06.2008.

    Its source prints ``THE SECOND SHCEUDLE`` -- a typo ``SCHEDULE_TOC_RE``
    rightly refuses -- so the parser cannot count that page as front matter, and
    once round 14 removed the folio the invariant had no signal left.
    """
    bad = inv({"preamble": {"plain_text": SCHEDULE_ROWS_SHAPE}})
    assert len(bad) == 1, bad
    assert "schedule contents row" in bad[0]


def test_a_roman_word_in_the_preamble_is_not_a_folio():
    """``mix`` is a valid roman numeral (MIX = 1009) and an ordinary word, and an
    uppercase ``I`` is a drop cap.  Both are why the pattern is bounded at
    ccxcix and lowercase rather than a plain ``[ivxlcdm]+``."""
    for word in ("mix", "civil", "I", "Vi", "dill"):
        assert inv({"preamble": {"plain_text": f"An Act\n{word}\nenacted"}}) == [], word


def test_a_subsection_marker_alone_on_a_line_is_still_reported_as_a_folio():
    """Honest limitation, pinned rather than hidden.

    ``(iv)`` on a line of its own is indistinguishable from a folio in the JSON;
    the PARSER separates them by geometry (centred, last line of the page, below
    the midpoint) and this invariant cannot see geometry.  No preamble in the
    corpus contains one -- measured, 9 roman-shaped lines over 1,292 preamble
    lines and every one a folio -- so the check is worth more than the risk.  If
    that ever changes this test is where the trade-off is written down.
    """
    assert inv({"preamble": {"plain_text": "An Act\n(iv)\nenacted"}}) != []


def test_passes_on_a_clean_preamble():
    clean = (
        "1[Act No. IV of 1969]\n"
        "An Act to consolidate and amend the law relating to Customs\n"
        "It is hereby enacted as follows:-"
    )
    assert inv({"preamble": {"plain_text": clean}}) == []


def test_does_not_fire_on_a_contents_leaf_outside_the_preamble():
    """The addressable Contents sink is intentional, not a defect.

    `json_parser.assess_toc_tail` exempts `code=Contents` for this reason.  An
    invariant that fired here would report the pipeline doing the right thing.
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
