"""A terminal ``As Amended:-`` list is the footnote apparatus, not body text.

Customs Rules 2001 (30.06.2023) prints its amendment apparatus ONCE at the end of
the document -- the caption on p561 and 158 numbered S.R.O. entries running to
p563 -- instead of as per-page footnotes.  Every gate in ``footnotes.py`` is
calibrated for the footnote-SIZED apparatus, and this list is set at body size
(10.0pt) with no edit verb in any entry, so the whole of it read as body: the 157
notification lines became the text of rule 1122 (*Audit*), and all 665 inline
markers cited notes that had no record.  Measured at round 37:
**665 unresolved markers -> 0, 670 citations bound, 158 notes, 0 leaves lost**.

The NEGATIVE cases are the point of the gate.  "as amended:-" is ordinary
statutory prose -- it opens a proviso in half this corpus -- and cutting the body
at a bare caption would silently delete every line below it.  What identifies the
apparatus is that essentially EVERYTHING under the caption is a numbered
notification entry, so both a floor on the count and a share of the lines below
are required, and a numbered list that is not notifications does not qualify.
"""

from __future__ import annotations

import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.builder import LineRef  # noqa: E402
from legal_ingest.footnotes import (  # noqa: E402
    amendment_list_start,
    parse_amendment_list,
)
from legal_ingest.pagemodel import Line, Word  # noqa: E402

#: p561 of Customs Rules 2001 (30.06.2023), verbatim -- including entry 53, whose
#: dot the source drops, and 23A, the lettered entry the numbering interpolates.
_APPARATUS = [
    "As Amended:-",
    "1. S.R.O.247(I)/2002, - dated 08.05.2002.",
    "2. S.R.O.375(I)/2002, - dated 15.06.2002.",
    "23. S.R.O.1174(I))/2005 - dated 23.11.2005",
    "23A. S.R.O.23(I)/2006 - dated 05.01.2006",
    "53 S.R.O.510(I)/2010 - dated 11.06.2010",
]
_BODY = [
    "1122. Audit.- The Board may cause an audit of the licencee.",
    "C.No.10(18)L&P/2002",
    "(Manzoor Ahmad)",
    "Member (Customs)",
]


def _line(text: str) -> Line:
    words, x = [], 93.6
    for w in text.split(" "):
        words.append(Word(text=w, x0=x, x1=x + 5 * len(w), top=100.0,
                          size=10.0, fontname="TimesNewRomanPSMT"))
        x += 5 * len(w) + 3
    return Line(top=100.0, words=words)


def _refs(texts, page=561):
    return [LineRef(page=page, line=_line(t)) for t in texts]


def test_the_apparatus_is_cut_out_of_the_body():
    texts = _BODY + _APPARATUS
    cut = amendment_list_start(texts)
    assert cut == len(_BODY), cut
    assert texts[cut] == "As Amended:-"


def test_every_entry_becomes_one_note_keyed_as_the_body_cites_it():
    cut = amendment_list_start(_BODY + _APPARATUS)
    notes = parse_amendment_list(_refs((_BODY + _APPARATUS)[cut:]))
    assert [n.marker for n in notes] == ["1", "2", "23", "23A", "53"]
    assert notes[0].text.startswith("1. S.R.O.247(I)/2002")
    assert notes[0].pdf_page == 561
    # the caption belongs to the apparatus and is dropped, as LEGAL REFERENCE is
    assert not any("As Amended" in n.text for n in notes)


def test_a_wrapped_entry_stays_with_its_own_note():
    wrapped = ["As Amended:-"] + [f"{i}. S.R.O.{i}(I)/2002 - dated 08.05.2002."
                                  for i in range(1, 6)] + [
        "reported as PTCL 2019 St. 4584."]
    notes = parse_amendment_list(_refs(wrapped))
    assert len(notes) == 5
    assert notes[-1].text.endswith("reported as PTCL 2019 St. 4584.")


def test_the_caption_alone_does_not_cut_the_document():
    prose = ["The Customs Act, 1969 (IV of 1969), as amended:-",
             "as amended:-",
             "(a) the goods shall be assessed under section 25;",
             "(b) the duty shall be paid within ten days."]
    assert amendment_list_start(prose) is None


def test_a_numbered_list_that_is_not_notifications_does_not_qualify():
    not_sros = ["As Amended:-"] + [f"{i}. Form STR-{i} appended to these rules."
                                   for i in range(1, 12)]
    assert amendment_list_start(not_sros) is None


def test_a_short_run_of_entries_below_live_body_does_not_qualify():
    """Both halves of the gate, each failed on its own."""
    too_few = ["As Amended:-",
               "1. S.R.O.247(I)/2002 - dated 08.05.2002.",
               "2. S.R.O.375(I)/2002 - dated 15.06.2002."]
    assert amendment_list_start(too_few) is None
    diluted = (["As Amended:-"]
               + [f"{i}. S.R.O.{i}(I)/2002 - dated 08.05.2002."
                  for i in range(1, 7)]
               + ["(a) the goods shall be assessed under section 25;"] * 3)
    assert amendment_list_start(diluted) is None


def test_the_notes_reach_the_body_pages_that_cite_them():
    """The reader is only half of it -- the notes must reach the CITATION view.

    Round 17's rule: a unit test of the predicate alone passes whether or not the
    answer reaches the cut.  These notes are printed on pages 561-563 and cited
    from page 7 onwards, which no footnote RUN spans; what binds them is
    ``_citation_scope``'s document-wide unique-marker path, and that path is the
    reason the apparatus does not need to be near the text it annotates.
    """
    from legal_ingest.pipeline import _citation_scope

    cut = amendment_list_start(_BODY + _APPARATUS)
    notes = parse_amendment_list(_refs((_BODY + _APPARATUS)[cut:], page=561))
    pages = list(range(1, 562))
    has_body = {p: p < 561 for p in pages}
    has_notes = {p: p == 561 for p in pages}
    fmap, _cited = _citation_scope({561: notes}, pages, has_body, has_notes)
    title, printed_on = fmap[7]["23A"]
    assert title.startswith("23A. S.R.O.23(I)/2006")
    assert printed_on == 561
