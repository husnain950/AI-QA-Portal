"""A ``PART-N`` body line may cut a section only where its chapter holds that part.

Round 13 measured the bare ``PART\\s+`` -> ``PART[\\s\\-]+`` widening at 14 real
boundaries against 6 losses and shipped neither, because the 6 are the dangerous
kind.  Both are annexure FORMS -- Customs Rules 2001 rule 34's permission form,
whose item counter runs 8, 9, 10, 11 *across* its parts, and Sales Tax Rules 2006
form STR-11 -- and slicing a form into the next rule leaves text conserved at
100.000% and merely misplaced.  Nothing in the suite catches that, so the
regression would have reported itself as a success.

What separates the two populations is not the spelling of the line.  Sales Tax
Rules 2006 (01-01-2025) prints BOTH: five real ``PART-N`` captions under CHAPTER
XI, which holds ``PART I``..``PART V``, and form STR-11's two inside rule 165
under CHAPTER XVIII, which holds no parts at all.  One document -- so no
exemption, and no per-document rule, can tell them apart.  The container tree
can.

Both halves are pinned here on purpose.  The POSITIVE case fails without the
widening; the NEGATIVE case fails without the guard; and both go through
``build_sections``, so they also fail if ``_part_codes_in_scope`` is wired up
wrong and hands ``_build_one`` an empty set -- which every unit test of the
predicate alone would happily pass.
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


#: The shape both cases share: a rule, a ``PART-II`` line at the end of its body,
#: the part's caption, then the next rule.  This is Sales Tax Rules 2006 at rule
#: 87 and, line for line, form STR-11 inside rule 165.
_BODY = [
    (1, "87. Application.- A person supplying goods shall apply in the form"),
    (1, "set out in this Part and shall pay the amount due."),
    (2, "PART-II"),
    (2, "REGISTRATION OF PERSONS"),
    (2, "88. Procedure.- The Commissioner shall register the applicant on"),
    (2, "receipt of a complete application."),
]


def _run(chapter_holds_part_ii: bool):
    """Build the same six lines under a chapter that does, or does not, hold
    ``PART II``.  Everything else is identical."""
    refs = [LineRef(page=pg, line=_line(t)) for pg, t in _BODY]
    s87 = SectionEntry(code="87", heading="Application", printed_page=1)
    s88 = SectionEntry(code="88", heading="Procedure", printed_page=2)

    part_i = Node(kind="part", code="PART I", heading="SUPPLY OF GOODS",
                  sections=[s87])
    chapter = Node(kind="chapter", code="CHAPTER XI", heading="SPECIAL PROCEDURE")
    if chapter_holds_part_ii:
        part_ii = Node(kind="part", code="PART II",
                       heading="REGISTRATION OF PERSONS", sections=[s88])
        chapter.parts = [part_i, part_ii]
        s87.parent, s88.parent = part_i, part_ii
    else:
        # the STR-11 shape: the form's parts belong to no container, so both
        # rules hang off the chapter itself and it holds no parts at all
        chapter.sections = [s87, s88]
        s87.parent = s88.parent = chapter

    containers = [chapter] + list(chapter.parts)
    built = build_sections(refs, [s87, s88], {}, {}, page_offset=0,
                           containers=containers)
    assert id(s87) in built and id(s88) in built, "both rules must bind"
    return built[id(s87)].plain_text


def test_a_vouched_part_line_cuts_the_section():
    """CHAPTER XI holds PART II, so rule 87 ends at its caption.

    Fails without the separator widening: ``PART\\s+`` never matched ``PART-II``,
    so the caption and the part's heading sat in rule 87's body -- five such
    captions per Sales Tax Rules 2006 edition, and the invariant written to catch
    a swallowed container heading carries the same narrow spelling and reports
    zero.
    """
    text = _run(chapter_holds_part_ii=True)
    assert "PART-II" not in text, (
        "PART-II opens a part CHAPTER XI really holds -- it must cut rule 87, "
        f"not sit in its body:\n{text}")
    assert "REGISTRATION OF PERSONS" not in text, (
        "the part's caption goes with it; the tree already holds it as PART II's "
        f"heading, so leaving it here prints it twice:\n{text}")
    assert text.startswith("87. Application."), text
    assert "shall pay the amount due" in text, (
        "the cut must not eat rule 87's own text")


def test_an_unvouched_part_line_does_not_cut_the_section():
    """The same line, in a chapter holding no parts, is a FORM's part.

    Fails without the guard: the widening alone cuts here too, and rule 87 loses
    the tail of its own form to rule 88 while total conserved text does not move
    at all.  That is the failure mode that has to be impossible, not merely
    unlikely -- it is invisible to every conservation number in the suite.
    """
    text = _run(chapter_holds_part_ii=False)
    assert "PART-II" in text, (
        "no container vouches for PART-II here, so it is form furniture and "
        f"must stay in rule 87's body:\n{text}")
    assert "REGISTRATION OF PERSONS" in text, (
        f"and so must the line under it:\n{text}")


def test_the_two_cases_differ_only_in_the_container_tree():
    """The discrimination is the tree's, not the line's.

    Guards against a fix that reads the line harder -- a font-size test, a page
    position, a keyword list -- instead of asking the container.  Both runs feed
    ``build_sections`` byte-identical body lines.
    """
    vouched = _run(chapter_holds_part_ii=True)
    unvouched = _run(chapter_holds_part_ii=False)
    assert vouched != unvouched
    assert unvouched.startswith(vouched.split("\n")[0]), (
        "same rule 87 heading in both -- only the cut differs")
