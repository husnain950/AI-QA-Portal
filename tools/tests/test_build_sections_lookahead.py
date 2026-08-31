"""One bad page-anchor choice must not starve the entries printed behind it.

``build_sections`` walks a widening tolerance ladder outward from each entry's
expected page, so where a code opens a body line twice -- once at the page the
document really uses and once at a cross-reference -- the NEARER wrong candidate
is reached before the further right one.  The ordering guard below the ladder
rejects a match past where the next entry is EXPECTED; it cannot see a match
past where the next entry actually PRINTS.

Sales Tax 1990 (15.9.2021) is the measured case: s.3 is expected on page 34 and
its code opens a body line on 28 and on 37.  That block runs about six pages
ahead of its own contents page, so 28 is the real heading -- but tol=4 reaches
37 first, the monotonic cursor jumps past it, and ss.3A/3AA/3B/4/5/6/7 all print
BEFORE it.  Seven entries starved by one choice, five of them register hits.

The fixture reproduces that shape at minimum size and fails without the fix.
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
from legal_ingest.toc import SectionEntry  # noqa: E402


def _line(text: str) -> Line:
    words, x = [], 60.0
    for w in text.split(" "):
        words.append(Word(text=w, x0=x, x1=x + 6 * len(w), top=100.0,
                          size=10.0, fontname="ArialMT"))
        x += 6 * len(w) + 4
    return Line(top=100.0, words=words)


def _build():
    """s.3 openable on page 28 and 37; s.3A only on 31 and 33; s.7A on 39."""
    body = [
        (28, "3. Scope of tax.- Subject to the provisions of this Act, there shall"),
        (29, "be charged, levied and paid a tax known as sales tax."),
        (31, "3A. Collection of excess sales tax.- Any person who has collected"),
        (32, "any amount of tax in excess shall pay that amount to the Federal"),
        (33, "3A. Collection of excess sales tax.- continued on a later page"),
        (37, "3. Scope of tax as amended by the Finance Act shall be read to mean"),
        (39, "7A. Levy and collection of tax on specified goods and services.- The"),
        (40, "Federal Government may specify the goods and services liable to tax."),
    ]
    refs = [LineRef(page=pg, line=_line(t)) for pg, t in body]
    entries = [
        SectionEntry(code="3", heading="Scope of tax", printed_page=34),
        SectionEntry(code="3A", heading="Collection of excess sales tax",
                     printed_page=39),
        SectionEntry(code="7A", heading="Levy and collection of tax",
                     printed_page=45),
    ]
    built = build_sections(refs, entries, {}, {}, page_offset=0)
    return entries, built


def test_the_nearer_candidate_does_not_win_when_it_starves_the_next_entry():
    entries, built = _build()
    s3, s3a, s7a = entries
    assert id(s3) in built, "s.3 must bind at all"
    assert built[id(s3)].plain_text.startswith("3. Scope of tax.- Subject"), (
        "s.3 must bind to page 28, the heading its own block prints, not to the "
        "page-37 cross-reference the tolerance ladder reaches first"
    )
    assert id(s3a) in built, (
        "s.3A prints on 31 and 33, both BEFORE the page-37 candidate: if s.3 "
        "takes 37 the monotonic cursor starves s.3A and everything behind it"
    )
    assert id(s7a) in built, "s.7A prints after either choice and must be unaffected"


def test_the_filter_is_a_tie_break_and_never_removes_the_only_candidate():
    """A code that opens exactly one body line is resolved as it always was."""
    refs = [
        LineRef(page=40, line=_line("9. Debit and credit note.- Where a "
                                    "registered person has issued a tax invoice")),
        LineRef(page=41, line=_line("and as a result the amount shown is "
                                    "modified, the person shall issue a note.")),
    ]
    # the next entry's code never opens a body line, so EVERY candidate would
    # "starve" it -- the filter must stand down rather than reject the match
    entries = [
        SectionEntry(code="9", heading="Debit and credit note", printed_page=40),
        SectionEntry(code="10", heading="Refund of input tax", printed_page=42),
    ]
    built = build_sections(refs, entries, {}, {}, page_offset=0)
    assert id(entries[0]) in built
