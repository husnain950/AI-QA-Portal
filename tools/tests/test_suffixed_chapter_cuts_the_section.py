"""A letter-suffixed ``CHAPTER`` line is a boundary, and must cut the section.

``builder._STRUCTURAL_RE``'s CHAPTER branch carried no letter-suffix class where
the PART and Division branches beside it both carry ``[A-Z]{0,2}``, so a chapter
inserted by amendment was not a boundary: ``1[CHAPTER XVI-A`` and its caption sat
in section 155's body across twenty Customs Act editions, and the whole
``XIV-A``..``XIV-D`` / ``V-A``..``V-C`` family in Sales Tax Rules 2006.  Measured
at round 18: **80 such lines across 24 documents**.

``grammar.CHAPTER_RE`` accepted every one of them the whole time -- its ``NUMERAL``
has always carried the suffix -- so this is the same parser/grammar disagreement
round 13 closed for the separator, on the other half of the same line.

This goes through ``build_sections`` rather than calling the predicate, for the
reason round 17 recorded: a unit test of the predicate alone passes whether or not
the widened answer actually reaches the cut.

The NEGATIVE case is not decoration.  The suffix class must not be widened the way
``grammar.ROMAN`` spells it (``\\s?-?[A-Z]{1,3}``): under ``IGNORECASE`` a SPACED
suffix eats the lowercase words *of / or / for*, which is the 28 ordinance false
positives recorded in ``test_structural_boundary_agrees_with_grammar.py``.  So a
cross-reference must still sit in the body it belongs to.
"""

from __future__ import annotations

import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.builder import LineRef, build_sections  # noqa: E402
from legal_ingest.pagemodel import Line, Word  # noqa: E402
from legal_ingest.toc import Node, SectionEntry  # noqa: E402


def _line(text: str) -> Line:
    words, x = [], 60.0
    for w in text.split(" "):
        words.append(Word(text=w, x0=x, x1=x + 6 * len(w), top=100.0,
                          size=10.0, fontname="ArialMT"))
        x += 6 * len(w) + 4
    return Line(top=100.0, words=words)


def _run(boundary_line: str):
    """Two sections with ``boundary_line`` plus a caption between them.

    Customs Act section 155 at the end of CHAPTER XVI, then the inserted
    CHAPTER XVI-A opening with section 156.  The tree already holds the inserted
    chapter -- it comes off the contents page -- which is why leaving its caption
    in the body prints it twice.
    """
    body = [
        (1, "155. Power to search.- The appropriate officer may search any"),
        (1, "person or conveyance leaving or entering Pakistan."),
        (2, boundary_line),
        (2, "PROVISIONS RELATING TO THE CUSTOMS COMPUTERIZED SYSTEM"),
        (2, "156. Definitions.- In this Chapter, unless there is anything"),
        (2, "repugnant, the following expressions shall have the meanings given."),
    ]
    refs = [LineRef(page=pg, line=_line(t)) for pg, t in body]
    s155 = SectionEntry(code="155", heading="Power to search", printed_page=1)
    s156 = SectionEntry(code="156", heading="Definitions", printed_page=2)

    ch16 = Node(kind="chapter", code="CHAPTER XVI", heading="SEARCHES",
                sections=[s155])
    ch16a = Node(kind="chapter", code="CHAPTER XVI-A",
                 heading="PROVISIONS RELATING TO THE CUSTOMS COMPUTERIZED SYSTEM",
                 sections=[s156])
    s155.parent, s156.parent = ch16, ch16a

    built = build_sections(refs, [s155, s156], {}, {}, page_offset=0,
                           containers=[ch16, ch16a])
    assert id(s155) in built and id(s156) in built, "both sections must bind"
    return built[id(s155)].plain_text


def test_a_suffixed_chapter_line_cuts_the_section():
    """``1[CHAPTER XVI-A`` ends section 155.  Fails without the widening."""
    text = _run("1[CHAPTER XVI-A")
    assert "CHAPTER XVI-A" not in text, (
        "CHAPTER XVI-A is a chapter boundary -- it must cut section 155, not "
        f"sit in its body:\n{text}")
    assert "CUSTOMS COMPUTERIZED SYSTEM" not in text, (
        "the chapter's caption goes with it; the tree already holds it as "
        f"CHAPTER XVI-A's heading, so leaving it here prints it twice:\n{text}")
    assert text.startswith("155. Power to search."), text
    assert "leaving or entering Pakistan" in text, (
        "the cut must not eat section 155's own text")


def test_the_fused_and_spaced_separator_forms_cut_too():
    """The three spellings the corpus actually prints, all boundaries.

    ``XIVA`` fused (Sales Tax Rules 2006), ``XVI-A`` hyphenated (Customs), and
    ``- VIAB`` with the separator spaced out.
    """
    for line in ("248[CHAPTER XIVA", "CHAPTER XVI-A", "[CHAPTER - VIAB"):
        text = _run(line)
        assert "CUSTOMS COMPUTERIZED SYSTEM" not in text, (
            f"{line!r} must cut section 155:\n{text}")


def test_a_chapter_cross_reference_still_sits_in_the_body():
    """``Chapter XII]`` is a wrapped table cell, not a boundary.

    Guards the widening against the spaced-suffix form: were the suffix class
    spelled ``\\s?-?[A-Z]{1,3}`` like ``grammar.ROMAN``, ``IGNORECASE`` would let
    it swallow a trailing lowercase word and every ``Chapter VII of`` in the
    corpus would cut a section.
    """
    for line in ("Chapter XII]", "Chapter VII of", "Chapter X or"):
        text = _run(line)
        assert line in text, (
            f"{line!r} is a cross-reference, not a boundary -- it must stay in "
            f"section 155's body:\n{text}")
