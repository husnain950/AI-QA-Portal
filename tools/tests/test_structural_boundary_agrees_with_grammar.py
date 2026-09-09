"""The three readers of "is this line a container heading?" must not disagree.

Round 13's defect was that they did.  ``grammar.CHAPTER_RE`` spells the separator
between the keyword and the numeral ``[\\s\\-]+`` and has asserted so since it was
written; ``builder._STRUCTURAL_RE`` and the suite's own ``_STRUCT_LINE`` both
spelled it ``\\s+``.  So the Sales Tax Act's ``Chapter-II`` was not a boundary:
nine chapter headings per edition were swallowed into the preceding section's
body -- 175 leaves across 21 documents in two lanes -- and the invariant written
to catch exactly that reported zero, because it carried the same narrow spelling.

They stay INDEPENDENT implementations on purpose: an invariant that imports the
parser's own regex checks nothing.  What they may not do is disagree, and nothing
compared them, which is why this survived twelve rounds.  This file is that
comparison.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

from corpus_paths import PACKAGES  # noqa: E402  (sys.path bootstrap)

if str(PACKAGES) not in sys.path:
    sys.path.insert(0, str(PACKAGES))

from legal_ingest.builder import is_structural_boundary  # noqa: E402
from legal_ingest.discover import _split_container_heading  # noqa: E402
from legal_ingest.grammar import CHAPTER_RE  # noqa: E402
from suite.invariants._common import _STRUCT_DECOR, _STRUCT_LINE  # noqa: E402

#: Lines that ARE container boundaries.  The hyphen forms are round 13; the
#: bracketed forms are round 1's amendment decoration.
BOUNDARIES = [
    "CHAPTER II", "Chapter II", "Chapter-II", "CHAPTER-II", "Chapter- I",
    "CHAPTER - V", "4[Chapter-I", "128[CHAPTER-XLI", "150[CHAPTER- XLIII",
    "PART III", "1[PART VA",
    # round 18: the letter suffix, fused and hyphenated.  ``grammar.CHAPTER_RE``
    # accepted all four before the parser did -- its NUMERAL has carried the
    # suffix all along -- which is the disagreement this closes.
    "CHAPTER XVI-A", "1[CHAPTER XIX-A", "248[CHAPTER XIVA", "[CHAPTER - VIAB",
]

#: The gap round 18 LOCATED and did not close: the separator, not the suffix.
#: Twenty Customs editions print ``CHAPTER – VI`` / ``CHAPTER – VII`` (EN DASH) as
#: real boundaries -- the next line is the caption, ``DRAWBACK`` and ``ARRIVAL AND
#: DEPARTURE OF CONVEYANCE`` -- and one Sales Tax Rules edition prints
#: ``CHAPTER – V`` above ``REFUND``.  ``[\s\-]+`` is ASCII, so none of them is a
#: boundary.
#:
#: This is NOT round 18's row and was deliberately left open: ``grammar.CHAPTER_RE``
#: rejects them too (its own separator is ``[\s\-]+``, and its ``[–—]`` branch reads
#: an en dash as introducing a same-line TITLE, not as a separator).  Round 18
#: widened the parser to agree with the grammar; closing this one has to move the
#: grammar first, which is a different decision on a shared regex.  Round 17
#: measured the en/em dash widening as gaining zero for PART -- that evidence does
#: NOT transfer, because it was the container guard that refused those, and the
#: CHAPTER branch has no such guard.
#:
#: These assertions pin the CURRENT, WRONG answer, the way the letter-suffix gap
#: was pinned before round 18 closed it.
KNOWN_GAP_ENDASH_CHAPTERS = [
    "CHAPTER – VI", "CHAPTER – VII", "CHAPTER – V", "CHAPTER – VIAB",
]

#: Lines that are NOT -- read with no ``container_codes``, which is what every
#: caller that cannot say which container a line sits in passes.  The first five
#: are what disqualified delegating to ``grammar`` outright: its roman suffix
#: class under IGNORECASE eats the lowercase words of/or/for, measured at 28
#: false positives in the ordinance lane.  ``chapter 87 35`` is a tariff row (4
#: more).  ``Chapter XII]`` is a wrapped table cell -- only LEADING decoration is
#: stripped.
#:
#: The four PART forms are round 17's guard, and they belong here rather than in
#: ``BOUNDARIES`` for a reason worth stating: since round 17 a hyphenated
#: ``PART-N`` IS a boundary -- but only where the enclosing chapter holds a part
#: with that code, and this list has no container to consult.  Unvouched they
#: still answer False, and so does the invariant, so the two still agree.  What
#: they now agree on is a blind spot rather than a gap: ``_STRUCT_LINE`` keeps
#: the narrow PART spelling deliberately, because widening it would report the
#: nine annexure-FORM part lines in the rules lane as defects.  The vouched half
#: is pinned document-level instead, in
#: ``test_hyphenated_part_needs_a_container.py``.
NOT_BOUNDARIES = [
    "Chapter-V of this Act;", "Chapter VII of", "Chapter X or", "Part V of",
    "Division III of", "chapter 87 35", "Chapter XII]",
    "PART-II", "PART-2", "34[PART-3", "PART-I",
]


def _invariant_says(line):
    return bool(_STRUCT_LINE.match(_STRUCT_DECOR.sub("", line.strip())))


def test_parser_and_invariant_agree():
    """The parser's cut and the invariant that reports a missed cut, on one list."""
    for line in BOUNDARIES:
        assert is_structural_boundary(line), f"parser missed boundary: {line!r}"
        assert _invariant_says(line), f"invariant missed boundary: {line!r}"
    for line in NOT_BOUNDARIES:
        assert not is_structural_boundary(line), f"parser over-cut: {line!r}"
        assert not _invariant_says(line), f"invariant over-reported: {line!r}"


def test_the_en_dash_chapter_gap_is_still_open():
    """Pins the gap round 18 located, so closing it has to move this file too."""
    for line in KNOWN_GAP_ENDASH_CHAPTERS:
        assert not is_structural_boundary(line), (
            f"{line!r} is a boundary now -- the en-dash separator widening "
            "landed; move it into BOUNDARIES, widen grammar.CHAPTER_RE to match, "
            "and re-measure the 42 lines across 21 documents")
        assert not _invariant_says(line), line


def test_grammar_is_the_authority_on_the_bare_chapter_form():
    """A bare CHAPTER row the grammar accepts must also be a boundary.

    The two may differ on contents-page furniture -- ``CHAPTER_RE`` also admits a
    same-line title after an en/em dash and a trailing folio, which a body line
    never has.  They may not differ on the bare form, which is the whole of the
    disagreement round 13 closed.
    """
    for line in ("CHAPTER II", "Chapter-II", "CHAPTER - V", "Chapter I"):
        assert CHAPTER_RE.match(line), f"grammar rejects {line!r}"
        assert is_structural_boundary(line), f"parser rejects {line!r}"


def test_a_boundary_the_split_cannot_read_would_become_a_nameless_division():
    """Being a boundary is half the decision; the other half is the split.

    ``discover`` re-parses the line ``is_structural_boundary`` just accepted.  A
    keyword it cannot read falls through to the Division branch and emits a
    nameless node that parents every following section -- round 1's failure.  So
    every boundary must split into a keyword the branch table knows.
    """
    for line in BOUNDARIES:
        kw, numeral = _split_container_heading(line)
        assert kw in ("CHAPTER", "PART", "DIVISION"), (line, kw)
        assert numeral, f"{line!r} split to an empty numeral"
