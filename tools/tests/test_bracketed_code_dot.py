"""The amendment bracket may wrap the CODE, with the dot outside it.

Sales Tax Special Procedures Rules 2007 prints rules 58U and 58V as

    111[58U]. Application:--The provisions of this Chapter shall apply to
    112[58V]. Conditions and limitations for availing zero-rating facility:--(1)

because S.R.O. 188(I)/2015 *renamed* rules 59 and 60: the bracket encloses the
new number alone, not the section, so the terminating dot prints after the
closing ``]``.  Every other inserted section in the same document opens the
bracket before the code and never closes it (``106[58S. Application.--``), which
is the only shape ``_DOTFORM_RE`` was written for.

The failure was not a miss.  ``_BRACKETED_DOTLESS_RE`` -- the last pattern
``_candidate_code_raw`` tries -- backtracked ``CODE`` to its digits and read the
suffix letter as the title's first capital, so ``111[58U].`` yielded the code
**58**, a real rule of Chapter IX forty pages earlier.  58U and 58V bound to
nothing, came out as heading-only leaves, and their 5,534 characters were handed
to 58W by ``build_sections``' structural-boundary carry.  Both 2007 editions,
four ``section_carries_its_body`` hits.
"""

from __future__ import annotations

import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.builder import _candidate_code  # noqa: E402


class _Line:
    """The one thing ``_candidate_code`` reads off a body line."""

    def __init__(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text


def code(text: str) -> str | None:
    return _candidate_code(_Line(text))


#: The lines the two editions actually print, verbatim.
RENAMED = [
    ("111[58U]. Application:--The provisions of this Chapter shall apply to", "58U"),
    ("112[58V]. Conditions and limitations for availing zero-rating facility:--(1)",
     "58V"),
]


def test_the_renamed_rule_binds_to_its_own_code():
    for text, want in RENAMED:
        assert code(text) == want, text


def test_it_no_longer_mints_the_digits_as_a_separate_section():
    """The regression this actually was: 58U read as rule 58.

    Rule 58 is real and sits in Chapter IX, so the wrong code was not inert --
    it added a candidate position forty pages past section 58's own page.
    """
    for text, _want in RENAMED:
        assert code(text) != "58", text


def test_the_bracket_must_be_closed_around_the_code():
    """The guard: both brackets, or this is not the renamed shape.

    Without the opening bracket the pattern would read a wrapped amendment
    quotation's own closing ``]`` as a section start.
    """
    assert code("58U]. Application:--The provisions of this Chapter") is None


def test_the_shapes_the_same_document_already_parsed_are_unchanged():
    """Tried before ``_BRACKETED_DOTLESS_RE`` but after everything else."""
    assert code("106[58S. Application.--The provisions of this Chapter shall") == "58S"
    assert code("58W. Application.— The provisions of this Chapter shall apply") == "58W"
    assert code("6,71,76,81[194. Appeal to High Court.-") == "194"
    assert code("5[(14-A. Provision of accommodation at Customs-ports, etc.-") == "14A"
    assert code("602[“47A. Alternative dispute resolution.—") == "47A"
    assert code("4[83. A Omitted]") == "83A"
    assert code("1[230E Directorate General of Law.-") == "230E"


def test_a_year_in_a_bracket_is_still_not_a_section():
    """``is_code_like`` is what stops this reading a law-report citation."""
    assert code("1969]. The Customs Act applies to") is None
    assert code("14[2019]. Something that is not a rule") is None


def test_a_bracketed_table_row_serial_is_not_a_section():
    """The one line in the corpus the unsuffixed form would have gained.

    Sales Tax 01.07.2014 prints ``2[21].Where any person repeats an offence``
    inside section 33's offences TABLE, forty pages past section 21's own page.
    The letter-suffix requirement is what separates a renumbering from a serial.
    """
    assert code("2[21].Where any person repeats an") is None
    assert code("25, 38 1[38A or 40B].") is None
