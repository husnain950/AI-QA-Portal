"""An ordinary numeral in a small-set table is not a citation.

``Word.marker_run`` gates on ``self.marker_max``, which ``calibrate`` derives
from the DOCUMENT's modal body size: ``body_size - 1.5``.  Federal Excise Act,
2005 (30-06-2025) is a 12.0pt document, so the cutoff is 10.5 -- correct for
the main body, whose markers are set at 8.0pt.  Its schedules are set at 9.0
to 10.0pt, so every ordinary numeral in them cleared the gate and became a
citation:

    p.72   TABLE 1                                    -> cite 72.1 on the title
    p.73   ...as prescribed against S. No. 9          -> cite 73.9
    p.76   2[ 14, 15 and 16***]                       -> 15 -> cite 80.15
    p.76   3[ 17 & 18 ]                               -> unresolved markers
    p.76   6[ 22 to 25***]                            -> unresolved marker
    p.84   IATA Traffic Conference Area 1 (North,     -> cite 84.1, numeral gone

The gate is therefore made local to the LINE, and the three conditions below
are each here because measuring demanded them.  Prototyped over the real page
model, body zone only, all 105 pages: 411 markers kept and 10 dropped, nine of
them the rows above.

  1. The line must have >= 2 words.  Without this, p.82's marker 1 -- which
     sits alone on its own line group, because its superscript baseline is
     3.5pt above the text it annotates and LINE_TOL is 3.0 -- is lost.
  2. The line's modal size must be below the document body.  Every main-body
     line has modal == body_size, so the body is untouched entirely.
  3. The candidate must not be bracket-adjacent.  Without this the rule lost
     22 real markers -- "5[3A***]", "2[***]", "13[57.", "1[Annex-A" -- whose
     own size IS the line's modal because the whole line is set small.

Sampled across nine further staged documents: 2,911 markers kept, 80 dropped,
every one of the 80 a false citation (the Sales Tax 1990 penalty table's
cross-references, "sections 193 and 228 of the Pakistan Penal Code", and a
"1 2 3 4 5 6" column-numbering row).

QA Cycle 1 rows FS-03, FS-04, FS-05, FS-08.
"""
import pathlib
import sys
import types

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.pagemodel import (  # noqa: E402
    Line,
    Word,
    _tighten_markers_on_small_lines,
)

#: Federal Excise 30-06-2025: 12.0pt body, so the document-wide cutoff is 10.5.
CAL = types.SimpleNamespace(body_size=12.0, marker_max_size=10.5)


def _line(tokens):
    """tokens = [(text, size)] laid out left to right, 3pt apart."""
    words, x = [], 126.0
    for text, size in tokens:
        words.append(Word(text=text, x0=x, x1=x + 5.5 * len(text), top=140.0,
                          size=size, fontname="TimesNewRomanPSMT",
                          marker_max=CAL.marker_max_size, footnote_size=8.0,
                          footnote_marker_max=10.0))
        x += 5.5 * len(text) + 3.0
    return Line(top=140.0, words=words)


def markers(tokens):
    """The tokens still read as markers after the line-local gate."""
    ln = _line(tokens)
    _tighten_markers_on_small_lines([ln], CAL)
    return [w.text for w in ln.words if w.is_marker]


# --- the numerals that must STOP being citations ----------------------------

def test_a_table_caption_numeral_is_not_a_citation():
    assert markers([("TABLE", 10.0), ("1", 10.0)]) == []


def test_a_serial_cross_reference_is_not_a_citation():
    got = markers([("against", 9.96), ("S.", 9.96), ("No.", 9.96),
                   ("9", 9.96), ("whichever", 9.96), ("is", 9.96)])
    assert got == []


def test_serial_numbers_inside_an_omission_range_are_not_citations():
    # p.76 -- the leading 2 IS the marker; 14, 15, 16 are the range
    got = markers([("2", 7.0), ("[", 11.0), ("14,", 9.0), ("15", 9.0),
                   ("and", 9.0)])
    assert got == ["2"]
    got = markers([("3", 7.0), ("[", 11.0), ("17", 9.0), ("&", 9.0),
                   ("18", 9.0), ("]", 11.0)])
    assert got == ["3"]
    got = markers([("6", 7.0), ("[", 11.0), ("22", 9.0), ("to", 9.0)])
    assert got == ["6"]


def test_an_iata_area_number_is_not_a_citation():
    got = markers([("Area", 9.96), ("1", 9.96), ("(North,", 9.96),
                   ("Central,", 9.96), ("fifty", 9.96)])
    assert got == []
    assert markers([("Conference", 9.96), ("Area", 9.96), ("2", 9.96)]) == []


# --- the markers that must SURVIVE ------------------------------------------

def test_a_bracket_adjacent_marker_survives_at_the_line_modal_size():
    # condition 3 -- without it these 22 sites were lost corpus-wide
    assert markers([("5", 8.0), ("[3A***]", 8.0)]) == ["5"]
    assert markers([("13", 7.0), ("[57.", 7.0)]) == ["13"]
    assert markers([("1", 8.0), ("[Annex-A", 8.0)]) == ["1"]
    assert markers([("2", 8.0), ("[***]", 8.0)]) == ["2"]


def test_a_lone_marker_on_its_own_line_survives():
    # condition 1 -- p.82's marker 1, raised 3.5pt clear of its own text
    assert markers([("1", 9.5)]) == ["1"]


def test_a_courier_marker_at_table_size_survives():
    # p.84 marker 4 is 9.96pt against an 11.04pt line -- still below the modal
    got = markers([("4", 9.96), ("[(b)", 11.04), ("Services", 11.04),
                   ("provided", 11.04)])
    assert got == ["4"]


def test_a_genuinely_small_marker_survives():
    assert markers([("3", 6.96), ("[8", 11.04), ("Cigarettes", 9.96),
                    ("of", 9.96), ("tobacco", 9.96)]) == ["3"]
    assert markers([("5", 6.48), ("[thousand", 9.96), ("per", 9.96),
                    ("kg", 9.96)]) == ["5"]


def test_the_main_body_is_untouched():
    # condition 2 -- a 12.0pt line keeps the document-wide cutoff exactly
    got = markers([("The", 12.0), ("cigarettes", 12.0), ("1", 8.04),
                   ("[or", 12.0), ("beverages]", 12.0)])
    assert got == ["1"]
    # and an ordinary number in 12pt body prose was never a marker anyway
    assert markers([("under", 12.0), ("section", 12.0), ("45A", 12.0),
                    ("of", 12.0), ("this", 12.0), ("Act", 12.0)]) == []
