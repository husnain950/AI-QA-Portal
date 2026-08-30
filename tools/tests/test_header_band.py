"""The header band must drop the header, not whatever sits near the top of a page.

``calibrate`` derives the band from where a running header prints.  When no
string clears its 40% threshold the band falls back to a flat 5.5% of the page
-- a figure with no evidence behind it -- and everything above it used to be
discarded unconditionally.  That is ledger P37 in the one case the P37 fix did
not cover: Sales Tax Rules 2006 (01-01-2025) prints no header at all, so the top
of a page is simply where the next rule begins, and rules 35, 76, 101 and 150X
open their headings at top 41.0-41.5 against a 43.6pt band.  All four were
dropped as furniture and reported as heading-only stubs.

``header_keys`` is now filled from RECURRENCE when nothing clears 40%, so
"empty" means "no top line in this document repeats" -- and a document with no
repeating top line has no header to protect against.  Five of this corpus's 50
header-less documents do repeat one (Public Finance Management Act 2019
alternates two halves of a gazette masthead, Finance Act 2023 prints NATIONAL
ASSEMBLY SECRETARIAT), which is why the fallback is not simply "keep everything".
"""

from __future__ import annotations

import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.pagemodel import Line, Word, _is_header_line  # noqa: E402


class _Cal:
    def __init__(self, keys=()):
        self.header_max_top = 43.6
        self.header_keys = tuple(keys)


def _line(text: str, top: float) -> Line:
    words, x = [], 60.0
    for w in text.split(" "):
        words.append(Word(text=w, x0=x, x1=x + 6 * len(w), top=top,
                          size=10.0, fontname="TimesNewRomanPSMT"))
        x += 6 * len(w) + 4
    return Line(top=top, words=words)


_RULE_35 = "35. Responsibility of the claimant.—The automated processing of refund"
_MASTHEAD = "PART I] THE GAZETTE OF PAKISTAN, EXTRA., JUNE 30, 2019"


def test_a_statute_heading_in_the_band_survives_when_no_header_repeats():
    assert not _is_header_line(_line(_RULE_35, 41.1), _Cal(keys=()))


def test_a_measured_header_is_still_dropped():
    cal = _Cal(keys=(_MASTHEAD.replace("2019", "#").replace("30", "#"),))
    assert _is_header_line(_line(_MASTHEAD, 30.0), cal)


def test_a_bare_folio_in_the_band_is_dropped_with_or_without_keys():
    """Folio-normalising made every top-of-page number collapse to one key.

    A running header carries words; a folio does not -- so the folio is dropped
    on the text test, not by matching a key it should never have become.
    """
    for cal in (_Cal(keys=()), _Cal(keys=("SOME RUNNING HEADER",))):
        assert _is_header_line(_line("41", 30.0), cal)
        assert _is_header_line(_line("[ 41 ]", 30.0), cal)


def test_anything_below_the_band_is_never_a_header():
    assert not _is_header_line(_line(_MASTHEAD, 44.0), _Cal(keys=(_MASTHEAD,)))
