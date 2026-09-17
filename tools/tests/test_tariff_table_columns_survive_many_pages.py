"""A tariff table labelled ``Col.(1) Col.(2) ...`` and printed over many pages.

The Federal Excise First and Third Schedules print eleven pages of four-column
tariff data that reached the review portal as ``<p>`` prose (QA Cycle 1, rows
FS-02 and FS-07).  Four separate things had to hold before a reader got a table,
and each one is pinned below because each was a real defect:

1. **The numbering row is spelled ``Col.(1)``, not ``(1)``.**  ``_NUM_TOKEN``
   matched only the bare form, so ``find_table_spans`` accepted no span at all
   and every row fell through to a paragraph.

2. **The gutters cannot be measured by demanding white.**  Across the 221 data
   rows of Table-I about 2% put a word in each gutter, so ``_white_gap_between``
   returned None for all three and ``_boundaries`` fell back to the midpoints
   between the numbering labels' CENTRES.  That is only right when a label is
   centred over its own column, and ``Col.(1)`` is a label wider than the serial
   column it names: its centre sits ~30pt right of the real boundary, so the
   description column's left words were stolen into the serial column and every
   wrapped row was shredded into one ``<tr>`` per printed line.

3. **The header block is reprinted on every page.**  Only the first is the
   thead; the other nine rendered as data rows, one of them with the previous
   row's wrapped tail glued into its ``Col.(2)`` cell.

4. **A row may cross a page break.**  ``_assign`` sorted a column's words on
   ``top``, which restarts at the head of each page, so the continuation sorted
   BEFORE the text it continues (Table-I serial 6).

The geometry below is page 73's, measured from the source: serial at x0~139,
description at 174.1, heading code at 319, rate at 406, and the numbering labels
centred at 144.7 / 241.0 / 357.0 / 454.8.
"""

from __future__ import annotations

import pathlib
import re
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.builder import LineRef  # noqa: E402
from legal_ingest.pagemodel import Line, Word  # noqa: E402
from legal_ingest.tables import (  # noqa: E402
    _boundaries, find_table_spans, render_table)  # noqa: E402

#: measured left edge of each column on page 73
COL = (139.0, 174.1, 319.0, 406.0)


def _line(cells, top=200.0):
    """One printed line: (text, x0) per cell, words laid out from that x0."""
    words = []
    for text, x0 in cells:
        x = x0
        for w in text.split(" "):
            words.append(Word(text=w, x0=x, x1=x + 5.7 * len(w), top=top,
                              size=10.0, fontname="TimesNewRomanPSMT"))
            x += 5.7 * len(w) + 3.4
    return Line(top=top, words=words)


#: measured centres of the four numbering labels on page 73
LABEL_X = (130.1, 226.4, 342.4, 440.2)


def _header(top=200.0, label="({n})"):
    """The three-line header block plus its numbering row.

    ``label`` is the numbering row's spelling.  The source prints ``Col.(1)``;
    the bare ``(1)`` is the ordinary form, and the tests for defects 2-4 use it
    so that each one fails for its OWN reason on the pre-round parser rather
    than for the unrecognised spelling.
    """
    return [
        _line([("S.No.", 130.9), ("Description of Goods", COL[1]),
               ("Heading/", COL[2]), ("Rate of Duty", COL[3])], top),
        _line([("sub-heading", COL[2])], top + 12),
        _line([("Number", COL[2])], top + 24),
        _line([(label.format(n=i + 1), x) for i, x in enumerate(LABEL_X)],
              top + 36),
    ]


def _data(n, top0=260.0):
    """``n`` ordinary one-line data rows."""
    return [_line([(str(i + 3), COL[0]), (f"Goods number {i + 3}", COL[1]),
                   (f"24.{i:02d}", COL[2]), ("Ten per cent", COL[3])],
                  top0 + 13 * i)
            for i in range(n)]


def _bridging_row(top):
    """A row whose serial cell runs into the gutter and closes it.

    Page 72 prints ``omitted]`` from x0 126.0, and a handful of rows like it are
    what defeats an all-or-nothing white-gutter test across many pages.
    """
    return _line([("omitted-entry", 126.0)], top)


def _refs(lines, page=73):
    return [LineRef(page=page, line=ln) for ln in lines]


def _cells(html):
    return [re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
            for row in re.findall(r"<tr>(.*?)</tr>", html, re.S)]


def test_a_col_prefixed_numbering_row_is_a_numbering_row():
    """FS-02: the span is found at all.  Before, ``find_table_spans`` returned []."""
    refs = _refs(_header(label="Col.({n})") + _data(6))
    assert find_table_spans(refs) == [(0, len(refs))]


def test_the_boundary_comes_from_the_gutter_not_the_label_centres():
    """Defect 2, pinned on ``_boundaries`` itself.

    The labels carry page 73's measured extents, so the centres are the real
    ones (144.7, 241.0, ...) and the centre-midpoint rule puts the first
    boundary at ~192.8 -- 19pt INSIDE a description column that starts at 174.1.
    Two rows out of 42 bridge the gutter, which is all it takes to deny the
    white test, so the pre-round parser had nothing else to fall back on.

    Spelled ``(1)`` on purpose: this defect is not the ``Col.`` spelling, and a
    test that needed the spelling fix to fail would be pinning that instead.
    """
    num_words = [Word(text=f"({i + 1})", x0=x0, x1=x1, top=236.0, size=10.0,
                      fontname="TimesNewRomanPSMT")
                 for i, (x0, x1) in enumerate(
                     [(130.1, 159.3), (226.4, 255.6),
                      (342.4, 371.6), (440.2, 469.4)])]
    lines = _data(40)
    lines.insert(12, _bridging_row(700.0))
    lines.insert(30, _bridging_row(701.0))
    bounds = _boundaries(num_words, _refs(lines))
    assert 150.0 <= bounds[1] < 174.1, (
        f"first boundary {bounds[1]:.1f} is not in the gutter between the "
        f"serial column and the description column at 174.1")


def test_a_wrapped_description_stays_in_one_cell():
    """What the boundary buys: serial 6 of Table-I wraps over five lines.

    Carries the multi-page condition (40 rows, two of them bridging) so the
    white test is denied and the cell depends on the valley boundary.  Without
    it the boundary lands at ~186.8 and the short leading word of a wrapped
    line -- "or" of "or fruits", which ends at 185.5 -- falls into the serial
    cell, which is the shredding this round is about.
    """
    lines = _header() + _data(40)
    lines.insert(12, _bridging_row(690.0))
    lines.insert(30, _bridging_row(691.0))
    lines += [
        _line([("96", COL[0]), ("Aerated waters if", COL[1]),
               ("Respective", COL[2]), ("Twenty per cent", COL[3])], 700.0),
        _line([("manufactured wholly", COL[1])], 713.0),
        _line([("from juices or pulp", COL[1])], 726.0),
        _line([("or fruits", COL[1])], 739.0),
    ]
    row = [r for r in _cells(render_table(_refs(lines)))
           if r and r[0].strip() == "96"]
    assert row and row[0][1] == (
        "Aerated waters if manufactured wholly from juices or pulp or fruits"), row


def test_a_reprinted_header_block_is_not_a_data_row():
    """Only the first header block is the thead; page 2's copy is not data."""
    lines = _header() + _data(4) + _header(600.0) + _data(4, 700.0)
    html = render_table(_refs(lines))
    assert "<td>S.No.</td>" not in html, html
    assert "<td>(1)</td>" not in html, html
    assert html.count("<th>(1)</th>") == 1, html


def test_a_row_that_crosses_a_page_break_keeps_its_reading_order():
    """``top`` restarts on the next page, so it cannot order a column's words."""
    lines = _header() + [
        _line([("9", COL[0]), ("first half of the description", COL[1])], 700.0),
    ]
    refs = _refs(lines)
    # the wrapped tail, printed at the TOP of the next page
    refs.append(LineRef(page=74,
                        line=_line([("and its continuation", COL[1])], 190.0)))
    html = render_table(refs)
    row = [r for r in _cells(html) if r and r[0].strip() == "9"][0]
    assert row[1] == "first half of the description and its continuation", row
