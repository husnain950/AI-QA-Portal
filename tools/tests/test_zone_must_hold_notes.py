"""A footnote zone must contain FOOTNOTES, not a table set below body size.

Finance Act 2019 sets its schedules' tariff tables at 8.0pt against an 11.0pt
body. The size split is textbook and everything under it is table, so the
document shipped **95 footnote records of which 5 bound to anything** and not
one read like a note -- `Breeding bulls 0102.2910 0% Nil`, and one record
swallowed the table's own numbering row `S. No. Description PCT Code Customs
Duty / (1) (2) (3) (4) (5)`.

The line floor is the half that makes this safe, and it is not hypothetical:
Customs Rules 2001 prints its apparatus once at the end at BODY size, so its
size zone holds 24 lines and not one note -- while the document carries 419
real records and 656 citations. Demoting on that evidence would have destroyed
round 37's work.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "packages"))

from legal_ingest.calibrate import (  # noqa: E402
    ZONE_NOTE_MIN_LINES,
    _zone_holds_notes,
)


class _Word:
    def __init__(self, size):
        self.size = size


class _Line:
    """The two attributes `_zone_holds_notes` reads off a calibrate line."""

    def __init__(self, text, size):
        self._text, self.max_size = text, size
        self.words = [_Word(size)]

    def text(self):
        return self._text


TARIFF = "Breeding bulls 0102.2910 0% Nil"
NOTE = "Substituted by the Finance Act, 2003 (IV of 2003), s.4."


def _zone(n_tariff, n_note, size=8.0):
    return ([_Line(TARIFF, size)] * n_tariff) + ([_Line(NOTE, size)] * n_note)


def test_a_zone_of_tariff_rows_is_not_a_footnote_zone():
    # Finance Act 2019's shape: a large zone, one edit verb in it.
    assert not _zone_holds_notes(_zone(594, 1), cut=9.5)


def test_a_zone_of_real_notes_is_kept():
    assert _zone_holds_notes(_zone(100, 100), cut=9.5)


def test_a_thin_zone_is_never_demoted():
    # Customs Rules 2001: 24 zone lines, no notes among them, because its
    # apparatus is printed once at the end at BODY size. Not evidence.
    assert _zone_holds_notes(_zone(24, 0), cut=9.5)
    assert _zone_holds_notes(_zone(ZONE_NOTE_MIN_LINES - 1, 0), cut=9.5)


def test_the_floor_is_exactly_where_it_says():
    assert not _zone_holds_notes(_zone(ZONE_NOTE_MIN_LINES, 0), cut=9.5)


def test_lines_above_the_cut_are_not_the_zone():
    # Body text never counts towards the zone, however much of it there is, so a
    # document cannot be demoted by its body being large.
    body = [_Line("Where any person fails to furnish a return", 11.0)] * 5000
    assert _zone_holds_notes(body + _zone(24, 0), cut=9.5)


def test_five_percent_notes_is_enough_to_keep_the_zone():
    # Income Tax Rules 2002 (Aug 2008) measures 5.4% and must survive; it is the
    # nearest real document above the cut.
    assert _zone_holds_notes(_zone(565, 32), cut=9.5)
