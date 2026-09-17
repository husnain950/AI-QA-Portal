"""An omitted section whose bracket holds asterisks is still a placeholder line.

Federal Excise Act, 2005 (30-06-2025) p.49 prints omitted section 31 as its own
line, immediately under the last line of section 30(2):

    x0=126.0   such duties by any [officer of Inland Revenue]as it deems fit.
    x0=129.5   2[ 31***]
    x0=160.2   32. Option to pay fine in lieu of confiscation of conveyance.-

``BRACKETS_ONLY_RE`` -- ``^[\\d\\s\\[\\]]+$`` -- is what tells four different
callers that a line is nothing but an amendment bracket around a section
number.  It has no ``*`` in its character class, so "2[ 31***]" failed it: the
line was never claimed by ``pipeline.claim_placeholder_lines``, stayed inside
section 30's slice, and section 31 shipped as a heading-only leaf.  The portal
showed the omitted-31 citation inside section 30(2) and an empty section 31.

The omission spelling is the only difference between "[31]" and "[31***]" --
both are the same kind of line -- so the character class is widened once, at
the constant every caller shares, rather than at the one caller this row named.

QA Cycle 1 row CH5-03.
"""
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.footnotes import BRACKETS_ONLY_RE  # noqa: E402


def claimable(text: str) -> bool:
    """The gate the four callers apply, verbatim."""
    t = text.strip()
    return bool(t and "[" in t and BRACKETS_ONLY_RE.match(t))


#: The omission spellings this corpus prints, all of them placeholder lines.
OMITTED = [
    "2[ 31***]",          # Federal Excise 30-06-2025 p.49
    "1[31]",
    "3[***]",
    "4[ 5[ ] ]",          # a section inserted and later omitted -- nested
]

#: Deliberately still OUT.  Widening the class to digits and asterisks is the
#: whole change; letters are a separate population and a separate measurement.
#: "5[3A***]" (p.14) is an omitted LETTER-SUFFIXED section and stays unclaimed
#: -- admitting [A-Z] here would also admit any bracketed all-caps line, which
#: needs its own round.  "7[26to30***]" is a tariff-table cell, not a section.
STILL_OUT = [
    "5[3A***]",
    "7[26to30***]",
]

#: Lines that are NOT placeholders and must stay out.
PROSE = [
    "31. Omitted",
    "2[ 31***] and the rest of a sentence",
    "such duties by any [officer of Inland Revenue]as it deems fit.",
    "(2) Notwithstanding anything contained in this Act",
]


def test_an_asterisk_omission_is_claimable():
    for text in OMITTED:
        assert claimable(text), text


def test_prose_is_never_claimable():
    for text in PROSE:
        assert not claimable(text), text


def test_lettered_codes_are_a_separate_change():
    for text in STILL_OUT:
        assert not claimable(text), text


def test_the_bracket_is_still_required():
    # a bare number with no bracket is a folio or a serial, not a placeholder
    assert not claimable("31")
    assert not claimable("31***")
    assert not claimable("")
