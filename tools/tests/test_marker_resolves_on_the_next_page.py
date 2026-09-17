"""A marker printed on one page may have its note printed on the next.

Federal Excise Act, 2005 (30-06-2025) pp.79-80 carry serial 55 of TABLE 1, a
vehicle tariff row whose rate cells continue across the page break.  Page 79's
body prints markers 1, 4, 6, 7, 8 and 2, but its footnote block holds only
notes 1 and 2:

    p.79 body   ...87.02), 4[and till the 30th day of June, 2026 electric
    p.79 body   6[10]% ad val.   7[30]% ad val.   8[40]% ad val.]
    p.79 notes  1 Serial number 55 and 55A ... substituted by Finance Act, 2019.
    p.80 notes  4 Expression inserted by Finance Act, 2021.
    p.80 notes  6/7/8 Expression substituted by Finance (Supplementary) Act, 2022.

``footnote_runs`` ends a run at any page that has both body and notes, so in a
bottom-of-page layout every page is its own run and page 79 cannot see page
80's notes.  The document-wide ``unique`` escape hatch beside it only fires
for a marker occurring exactly once in the whole document, which per-page
renumbering never satisfies.  So 4, 6, 7 and 8 shipped as unresolved
``<sup class="marker">`` while their notes sat one page away.

The neighbour rule added here is deliberately narrow: a body page may read
page + 1's note for a marker it has NO note of its own for, and only when
page + 1's own body does not cite that marker.  Page 80's body cites 1, 2, 3,
5 and 9-15 -- never 4, 6, 7 or 8 -- so nothing is being stolen.  Where
numbering genuinely restarts, the next page's body claims its own markers and
the rule stays silent.

QA Cycle 1 row FS-06.  Also closes 42.3, 61.5 and 100.1 in the same document,
which the reviewer did not log.
"""
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.footnotes import Footnote  # noqa: E402
from legal_ingest.pipeline import _citation_scope  # noqa: E402


def _fn(marker, text, page):
    return Footnote(marker=marker, text=text, html=f"<p>{text}</p>",
                    records=[], pdf_page=page, end_pdf_page=page)


#: pp.79-80 as the source prints them.
PAGE_FOOTNOTES = {
    79: [_fn("1", "Serial number 55 and 55A substituted by Finance Act, 2019.", 79),
         _fn("2", "Serial number 55B substituted by Finance (Supplementary) Act, 2022.", 79)],
    80: [_fn("1", "New serial number 55C inserted by Finance Act, 2020.", 80),
         _fn("2", "New serial number 55D inserted by Finance Act, 2020.", 80),
         _fn("4", "Expression inserted by Finance Act, 2021.", 80),
         _fn("6", "Expression substituted by Finance (Supplementary) Act, 2022.", 80),
         _fn("7", "Expression substituted by Finance (Supplementary) Act, 2022.", 80),
         _fn("8", "Expression substituted by Finance (Supplementary) Act, 2022.", 80)],
}
#: The same marker numbers occur on many other pages of the document, which is
#: why _citation_scope's document-wide "unique" path cannot reach them: it only
#: binds a marker that appears exactly ONCE in the whole document.  p.73 here
#: stands for the rest of the corpus of notes.
PAGE_FOOTNOTES[73] = [
    _fn("1", "The figure 'ten' substituted through Tax Laws Ordinance, 2022.", 73),
    _fn("2", "New serial number 7a inserted by Finance Act, 2024.", 73),
    _fn("4", "New serial numbers 8a and 8b inserted by Finance Act, 2020.", 73),
    _fn("6", "Words added by Finance Act, 2024.", 73),
    _fn("7", "New serial number 8c inserted by Finance Act, 2021.", 73),
    _fn("8", "Words substituted by Finance Act, 2022.", 73),
]

PAGES = [73, 79, 80]
HAS_BODY = {73: True, 79: True, 80: True}
HAS_NOTES = {73: True, 79: True, 80: True}
#: what each page's BODY actually cites
BODY_MARKERS = {73: {"1", "2", "4", "6", "7", "8"},
                79: {"1", "2", "4", "6", "7", "8"}, 80: {"1", "2"}}


def scope(body_markers=None):
    fmap, cited = _citation_scope(PAGE_FOOTNOTES, PAGES, HAS_BODY, HAS_NOTES,
                                  body_markers=body_markers)
    return fmap, cited


def test_an_uncontested_marker_binds_to_the_next_page():
    fmap, _ = scope(BODY_MARKERS)
    for marker in ("4", "6", "7", "8"):
        title, note_pg = fmap[79][marker]
        assert note_pg == 80, marker
        assert "Expression" in title, marker


def test_the_page_keeps_its_own_notes_first():
    fmap, _ = scope(BODY_MARKERS)
    assert fmap[79]["1"][1] == 79
    assert "Serial number 55 and 55A" in fmap[79]["1"][0]
    assert fmap[79]["2"][1] == 79


def test_a_contested_marker_is_left_alone():
    # page 80's body cites 1 and 2 itself, so page 79 must not take them
    fmap, _ = scope(BODY_MARKERS)
    assert fmap[79]["1"][1] == 79
    assert fmap[79]["2"][1] == 79
    # and if page 80's body also cited 6, page 79 could not have it
    contested = {**BODY_MARKERS, 80: {"1", "2", "6"}}
    fmap2, _ = scope(contested)
    assert "6" not in fmap2[79]


def test_the_borrowed_note_attaches_to_the_citing_page():
    _, cited = scope(BODY_MARKERS)
    markers = {fn.marker for fn in cited[79]}
    assert {"4", "6", "7", "8"} <= markers


def test_without_a_body_census_nothing_is_borrowed():
    # the old behaviour, for any caller that cannot supply one
    fmap, _ = scope(None)
    for marker in ("4", "6", "7", "8"):
        assert marker not in fmap[79], marker
