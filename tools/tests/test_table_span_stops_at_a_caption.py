"""A gridless table span stops at a CHAPTER / PART / Division caption.

``pagemodel`` already guards the GRID path -- "never swallow a structural
heading into a table just because it grazes the bbox" -- but
``tables.find_table_spans`` had no equivalent, and it extends a span on a margin
test: a line is still in the table while it starts at or right of the table's
first column.  A CENTRED caption sits well to the RIGHT of that column, so the
test never fires.

Page 102 of Customs Rules 2001 (30.06.2023) ends rule 325's repeal table with
``2&30 [CHAPTER XIV`` and ``TRANSSHIPMENT``, and both were folded into the LAST
DATA ROW::

    <td>S.R.O. 1319(I)/1996 2&amp;30</td><td>24.11.1996 [CHAPTER XIV TRANSSHIPMENT</td>

The caption's own citation markers then rendered as literal cell text while still
being registered as citations of that leaf, so once round 37 gave the document
footnote records the notes were attached to a leaf whose html shows no ``<sup>``
-- one ``footnote_on_citing_leaf`` hit.

The decoration class is the part to read twice: the source prints the marker RUN
``2&30`` glued to the bracket, which ``builder._STRUCT_DECOR_RE`` (single marker
only) does not strip.  Both ends of ``_CAPTION_RE`` are anchored so a DATA ROW --
which carries its other columns on the same line -- can never match it.
"""

from __future__ import annotations

import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.builder import LineRef  # noqa: E402
from legal_ingest.pagemodel import Line, Word  # noqa: E402
from legal_ingest.tables import _is_caption_line, find_table_spans  # noqa: E402


def _line(text: str, x0: float = 137.2) -> Line:
    words, x = [], x0
    for w in text.split(" "):
        words.append(Word(text=w, x0=x, x1=x + 5 * len(w), top=100.0,
                          size=10.0, fontname="TimesNewRomanPSMT"))
        x += 5 * len(w) + 3
    return Line(top=100.0, words=words)


#: rule 325's repeal table, as page 102 prints it
_TABLE = [
    ("S. No. Notification No. Date", 129.6),
    ("(1) (2) (3)", 134.7),
    ("1. C.No.10(34)-cus.III/58 18.04.1963", 137.2),
    ("2. S.R.O. 3(I)70 02.01.1970", 137.2),
    ("21. S.R.O. 1319(I)/1996 24.11.1996", 132.1),
]
#: the chapter caption that follows it, centred at x0 291 -- right of the table
_CAPTION = [("2&30 [CHAPTER XIV", 291.1), ("TRANSSHIPMENT", 291.2)]


def test_the_caption_is_not_absorbed_as_a_table_row():
    refs = [LineRef(page=102, line=_line(t, x))
            for t, x in _TABLE + _CAPTION]
    assert find_table_spans(refs) == [(0, len(_TABLE))]


def test_the_table_itself_is_still_found_whole():
    """The guard must not shorten a table that carries no caption."""
    refs = [LineRef(page=102, line=_line(t, x)) for t, x in _TABLE]
    assert find_table_spans(refs) == [(0, len(_TABLE))]


def test_every_decoration_the_source_prints_on_a_caption():
    for text in ("CHAPTER XIV", "[CHAPTER XIV", "2[CHAPTER XIV",
                 "2&30 [CHAPTER XIV", "34[PART-3", "PART-II", "Division IIA",
                 "Sub-Chapter-VII"):
        assert _is_caption_line(_line(text)), text


def test_a_data_row_is_never_a_caption():
    """Anchored at both ends, so a cell naming a Part cannot end the table."""
    for text in ("21. S.R.O. 1319(I)/1996 24.11.1996",
                 "S. No. Notification No. Date",
                 "(1) (2) (3)",
                 "2. Part II of the Schedule shall apply",
                 "TRANSSHIPMENT"):
        assert not _is_caption_line(_line(text)), text
