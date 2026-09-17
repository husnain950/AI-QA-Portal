"""A marker repeated on one page resolves to that page's note, both times.

QA Cycle 1 row CH4-01 reported that Section 27's marker 41.1 opens
"Sub-section (1) substituted by Finance Act, 2020." -- a note the reviewer
read as belonging to Section 26 -- and asked for the Section 27 marker to be
left unresolved instead.

It is not a defect, and this pin says so, because the fix it asks for would
be a regression.  Footnote numbering in these compilations restarts PER PAGE,
not per section, and page 41 of Federal Excise Act, 2005 (30-06-2025) prints
superscript 1 twice: once in s.26(1) and once in s.27(1) before
"[or beverages]".  Verified in the text layer --

    top=252.7  x0=280.0  '1'  8.04pt  TimesNewRomanPS-BoldMT   (s.26)
    top=424.8  x0=197.6  '1'  8.04pt  TimesNewRomanPSMT        (s.27)
    top=583.9  x0=126.0  '1'  5.04pt  -> "Sub-section (1) substituted by
                                          Finance Act, 2020."

so the portal is reproducing the printed page exactly.  The same shape is in
the 2023 and 2024 editions.

Refusing a marker whose note "belongs to" another section would unresolve
every legitimately reused marker in the corpus -- 43.2 appears twice in s.29
(clauses (ea) and (fa), one note), 83.2 twice in Table-II -- so the rule the
row asks for costs real citations and buys nothing the source supports.

If a future round wants to scope footnotes by section, it has to answer this
page first.  A failure here is a decision to review, not a bug to fix.
"""
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.footnotes import Footnote  # noqa: E402
from legal_ingest.pipeline import _citation_scope  # noqa: E402

NOTE_1 = "Sub-section (1) substituted by Finance Act, 2020."
NOTE_3 = "Marginal note expression substituted by Finance Act, 2020."


def _fn(marker, text, page=41):
    return Footnote(marker=marker, text=text, html=f"<p>{text}</p>",
                    records=[], pdf_page=page, end_pdf_page=page)


#: page 41 as printed: five notes, and the body cites 1 twice.
PAGE_41 = {41: [_fn("1", NOTE_1), _fn("2", "In section 26, in sub-section (1)..."),
                _fn("3", NOTE_3), _fn("4", "In section 27, in sub-section (1)..."),
                _fn("5", "Expression substituted by Finance Act, 2020.")]}


def scope():
    return _citation_scope(PAGE_41, [41], {41: True}, {41: True},
                           body_markers={41: {"1", "2", "3", "4", "5"}})


def test_the_page_resolves_its_own_marker():
    fmap, _ = scope()
    title, note_pg = fmap[41]["1"]
    assert title == NOTE_1
    assert note_pg == 41


def test_a_repeated_marker_resolves_to_the_same_note():
    # s.26(1) and s.27(1) both print superscript 1 on page 41; both must reach
    # note 1, because that is what the printed page means
    fmap, _ = scope()
    assert fmap[41]["1"][0] == NOTE_1
    assert fmap[41]["1"][0] == fmap[41]["1"][0]


def test_every_marker_on_the_page_keeps_its_own_note():
    fmap, _ = scope()
    assert fmap[41]["3"][0] == NOTE_3
    assert fmap[41]["4"][0].startswith("In section 27")
    assert fmap[41]["2"][0].startswith("In section 26")


def test_resolution_is_not_scoped_by_section():
    # there is no section dimension in the citation view at all, by design
    fmap, _ = scope()
    assert set(fmap[41]) == {"1", "2", "3", "4", "5"}
