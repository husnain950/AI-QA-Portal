"""A runner-up prose size too close to the body is a SECOND BODY, not a footnote.

Sales Tax Rules 2006 (01-01-2025) sets its rules at 12.0pt and prints two whole
pages -- p31 and p152, 991 words between them -- at 11.0pt.  Counted over the
36-page sample 11.0 is the second commonest size (1,168 words against 9.0's
846), so ``calibrate`` paired 12.0 with 11.0, a gap of 1.0 under
``SIZE_GAP_MIN``, and gave the document up: ``zone_mode "none"``,
``footnote_marker_max_size 0.0``, **869 inline markers and 0 footnote records**.

No footnote invariant could see it.  A document that records zero of something
passes every invariant about that thing.

The histograms below are the real measured ones, rounded to 0.1pt as
``calibrate`` rounds them.  The Finance Act 2022 case is the guard on the other
side: below its 10.0pt runner-up it offers 5.5pt (12 words) and 6.1pt (11), and
neither is a footnote size -- promoting one would cut its zone boundary from
10.5 to 8.25 for no reason.
"""

import collections
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "packages"))

from legal_ingest.calibrate import SIZE_GAP_MIN, _prose_sizes  # noqa: E402


def band(counter, share):
    """The same histogram, with ``share`` of each size's words low on the page."""
    return collections.Counter({s: int(round(n * share)) for s, n in counter.items()})

# Sales Tax Rules 2006 (01-01-2025), 36 sampled pages.  11.0 outranks 9.0.
SALES_TAX_RULES = collections.Counter({
    12.0: 7649, 11.0: 1168, 9.0: 846, 10.0: 680, 8.0: 502, 7.0: 237,
    13.0: 227, 6.0: 91, 7.6: 44, 14.0: 31, 6.5: 23, 5.0: 12, 11.5: 9,
    4.5: 9, 4.0: 8, 8.5: 5, 2.5: 5,
})

# Finance Act 2022, 35 sampled pages.  Nothing below 10.0 is prose.
FINANCE_ACT_2022 = collections.Counter({
    11.0: 6642, 12.0: 1011, 10.0: 931, 14.0: 31, 5.5: 12, 6.1: 11,
})

# Finance Act 2024, 36 sampled pages.  8.0pt is schedule tariff text, not notes.
FINANCE_ACT_2024 = collections.Counter({11.0: 6800, 10.0: 1400, 8.0: 573, 12.0: 200})

# An ordinary single-regime document: body and footnote, cleanly separated.
CUSTOMS = collections.Counter({12.0: 10074, 9.0: 4367, 8.0: 150, 11.0: 33, 10.0: 28})


def test_a_second_body_is_skipped_for_the_real_footnote_size():
    # 63% of its 9.0pt words sit in the bottom band; measured.
    body, footnote = _prose_sizes(SALES_TAX_RULES, band(SALES_TAX_RULES, 0.63))
    assert body == 12.0
    # NOT 11.0: that is the second regime's body, and it would zone the
    # document "none" and leave all 869 markers unresolved.
    assert footnote == 9.0
    assert body - footnote >= SIZE_GAP_MIN, "the pair must clear the gap test"


def test_a_candidate_below_the_mass_floor_is_not_promoted():
    body, footnote = _prose_sizes(FINANCE_ACT_2022, band(FINANCE_ACT_2022, 1.0))
    assert body == 11.0
    # 5.5 and 6.1 clear the gap but are decoration, not prose: 12 and 11 words
    # against a 1% floor of ~86.  The runner-up stands, and `calibrate` decides
    # the zone on the separator rule as it did before.
    assert footnote == 10.0
    assert body - footnote < SIZE_GAP_MIN


def test_a_candidate_that_is_not_at_the_foot_of_the_page_is_not_promoted():
    # Finance Act 2024: 573 words at 8.0pt, 5.5% of the sample, so it clears the
    # mass floor comfortably -- and only 31% of them are in the bottom band,
    # because they are SCHEDULE TARIFF ROWS.  Promoting it was measured: 10 false
    # footnote records reading "S. No. Taxable Income Rate of Tax", 51 table rows
    # shredded.  The document must keep its "no zone" answer.
    body, footnote = _prose_sizes(FINANCE_ACT_2024, band(FINANCE_ACT_2024, 0.31))
    assert (body, footnote) == (11.0, 10.0)
    assert body - footnote < SIZE_GAP_MIN, "still zoned 'none' by calibrate"


def test_a_single_regime_document_is_untouched():
    assert _prose_sizes(CUSTOMS, band(CUSTOMS, 0.39)) == (12.0, 9.0)


def test_the_floor_scales_with_the_sample():
    # The same shape, one tenth the size: 9.0 is now 1.4% of the words and
    # clears the floor, so it is promoted.  A fixed word count could not do
    # this -- the floor has to be a share.
    small = collections.Counter({12.0: 700, 11.0: 100, 9.0: 12})
    assert _prose_sizes(small, band(small, 1.0)) == (12.0, 9.0)
    # ...and one word fewer puts 9.0 under both the 1% floor and the >= 4 cut
    # it shares with `ranked`, so the runner-up stands and the document keeps
    # the "no zone" answer it has today.
    tiny = collections.Counter({12.0: 700, 11.0: 100, 9.0: 3})
    assert _prose_sizes(tiny, band(tiny, 1.0)) == (12.0, 11.0)
