"""Footnote text joins its fragments the way body text does.

Federal Excise Act, 2005 (30-06-2025) p.45 sets the first glyph of footnote 8
in a different size from the rest of the note:

    F    x0=135.86  x1=141.84  top=645.77  size=9.96
    or   x0=141.86  x1=148.50  top=647.56  size=8.04
    the  x0=150.49  x1=160.41  top=647.56  size=8.04

so the note reads "For the full stop, a colon and the word 'and' substituted
by Tax Laws (Amendment) Act, 2024."  ``pagemodel._merge_split_words`` will not
merge "F" and "or" -- it requires ``|dsize| <= 0.3`` and ``dtop <= 0.3`` and
this pair steps 1.92pt and 1.79pt -- and ``builder._deglyph`` cannot repair it
either, because ``_GLYPH_RUN_RE`` needs at least three single letters.

The body renderer copes with exactly this: ``_render_words`` glues any pair
less than 2.0pt apart that carries no real space glyph.  ``_join`` did not --
it was a bare ``" ".join`` -- so the portal printed "F or the full stop".

Note the two gaps this test pins.  F->or is 0.02pt with no space character
between them; or->the is 1.99pt, under the same threshold, but a real space
glyph sits at x0 148.46, so it must NOT be glued.  The space glyph, not the
gap alone, is what carries the decision.

QA Cycle 1 row CH5-02.
"""
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.footnotes import _join  # noqa: E402


class _W:
    """The four attributes ``_join`` reads off an extracted word."""

    def __init__(self, text, x0, x1, space_before=False):
        self.text = text
        self.x0 = x0
        self.x1 = x1
        self.space_before = space_before


#: p.45 footnote 8, verbatim coordinates from pdfplumber.
FOOTNOTE_8 = [
    _W("F", 135.86, 141.84),
    _W("or", 141.86, 148.50),
    _W("the", 150.49, 160.41, space_before=True),
    _W("full", 162.35, 173.46, space_before=True),
    _W("stop,", 175.00, 188.00, space_before=True),
]


def test_the_split_capital_rejoins_its_word():
    assert _join(FOOTNOTE_8).startswith("For the full stop,")


def test_a_real_space_glyph_still_separates():
    # or -> the is a 1.99pt gap, under the 2.0pt threshold, but carries a space
    assert "orthe" not in _join(FOOTNOTE_8)
    assert "or the" in _join(FOOTNOTE_8)


def test_an_ordinary_note_is_unchanged():
    words = [
        _W("Word", 138.0, 158.0),
        _W("omitted", 160.0, 190.0, space_before=True),
        _W("by", 192.0, 200.0, space_before=True),
        _W("Finance", 202.0, 230.0, space_before=True),
        _W("Act,", 232.0, 246.0, space_before=True),
        _W("2023", 248.0, 266.0, space_before=True),
    ]
    assert _join(words) == "Word omitted by Finance Act, 2023"


def test_a_word_list_with_no_geometry_still_joins():
    # parse_amendment_list and the OCR path hand over words without x0/x1
    class _Bare:
        def __init__(self, text):
            self.text = text

    assert _join([_Bare("Inserted"), _Bare("by"), _Bare("Finance")]) \
        == "Inserted by Finance"
