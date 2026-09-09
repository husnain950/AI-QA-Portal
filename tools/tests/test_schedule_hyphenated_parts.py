"""Corpus-free lock for the twenty schedule PART lines located in round 17.

The handover records only two demonstrated parser defects: Arabic ``Part-1``
and ``Part-11`` are rejected by the schedule PART grammar.  The other eighteen
already classify as parts.  Three of those eighteen contain a source lowercase
``l`` where the page visually intends capital ``I``; preserving that distinction
is important because silently changing L to I would invent source text.

These fixtures exercise the complete schedule segmenter under the documented
Second/Fifth Schedule zoning, including the 8.5pt active-heading gate.  They do
not claim that every source line was set at active-heading size; establishing
the real geometry still requires the private PDFs.
"""

from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.builder import LineRef  # noqa: E402
from legal_ingest.pagemodel import Line, Word  # noqa: E402
from legal_ingest.schedules import _kind, _norm_code, build_schedules  # noqa: E402


@dataclass(frozen=True)
class PartCase:
    document: str
    schedule: str
    printed: str
    preserved_code: str
    intended_code: str | None = None

    @property
    def source_roman_defect(self) -> bool:
        return self.intended_code is not None


# The compact ranges in the handover expand to these twenty lines:
# 2021 I..VIII; 2025's seven listed forms; 2019's II..V between its existing
# PART I/PART VI nodes; and 2014's one numeric form.
PART_CASES = (
    *(
        PartCase("Finance Act, 2021", "FIFTH SCHEDULE", f"PART-{roman}",
                 f"PART {roman}")
        for roman in ("I", "II", "III", "IV", "V", "VI", "VII", "VIII")
    ),
    PartCase("Finance Act 2025", "FIFTH SCHEDULE", "Part-1", "PART 1"),
    PartCase("Finance Act 2025", "FIFTH SCHEDULE", "Part-Il", "PART IL",
             intended_code="PART II"),
    PartCase("Finance Act 2025", "FIFTH SCHEDULE", "Part-lll", "PART LLL",
             intended_code="PART III"),
    PartCase("Finance Act 2025", "FIFTH SCHEDULE", "Part-IV", "PART IV"),
    PartCase("Finance Act 2025", "FIFTH SCHEDULE", "Part-V", "PART V"),
    PartCase("Finance Act 2025", "FIFTH SCHEDULE", "Part-VI", "PART VI"),
    PartCase("Finance Act 2025", "FIFTH SCHEDULE", "Part-VIlI", "PART VILI",
             intended_code="PART VIII"),
    *(
        PartCase("Finance Act, 2019", "FIFTH SCHEDULE", f"PART-{roman}",
                 f"PART {roman}")
        for roman in ("II", "III", "IV", "V")
    ),
    PartCase("Finance Act, 2014", "SECOND SCHEDULE", "Part-11", "PART 11"),
)


def _line(text: str, size: float = 10.0) -> Line:
    words, x = [], 60.0
    for token in text.split(" "):
        words.append(Word(
            text=token,
            x0=x,
            x1=x + 6 * len(token),
            top=100.0,
            size=size,
            fontname="ArialMT",
        ))
        x += 6 * len(token) + 4
    return Line(top=100.0, words=words)


def _build(case: PartCase, heading_size: float) -> dict:
    refs: list[LineRef] = []
    if case.schedule == "FIFTH SCHEDULE":
        # A standalone Fifth title is intentionally outside the builder's
        # expected-ordinal window.  Opening Third first recreates the real
        # schedule zone and admits Fifth through the documented +2 tolerance.
        refs.extend([
            LineRef(page=1, line=_line("THIRD SCHEDULE")),
            LineRef(page=1, line=_line("Earlier schedule content.")),
        ])
    refs.extend([
        LineRef(page=2, line=_line(case.schedule)),
        LineRef(page=2, line=_line(case.printed, size=heading_size)),
        LineRef(page=2, line=_line(f"Fixture body for {case.document}.")),
    ])
    schedules = build_schedules(refs, {}, {}, {}, toc_schedules=None)
    return next(schedule for schedule in schedules if schedule["code"] == case.schedule)


def _case_id(case: PartCase) -> str:
    return f"{case.document}-{case.printed}"


def test_the_fixture_inventory_matches_the_documented_twenty_lines():
    assert len(PART_CASES) == 20
    counts: dict[str, int] = {}
    for case in PART_CASES:
        counts[case.document] = counts.get(case.document, 0) + 1
    assert counts == {
        "Finance Act, 2021": 8,
        "Finance Act 2025": 7,
        "Finance Act, 2019": 4,
        "Finance Act, 2014": 1,
    }


@pytest.mark.parametrize("case", PART_CASES, ids=_case_id)
def test_each_documented_form_is_lexically_a_part_without_repairing_its_numeral(
        case: PartCase):
    assert _kind(case.printed) == "part", case
    assert _norm_code(case.printed, "part") == case.preserved_code


@pytest.mark.parametrize("case", PART_CASES, ids=_case_id)
def test_each_documented_form_segments_when_it_is_in_the_active_heading_size_zone(
        case: PartCase):
    schedule = _build(case, heading_size=9.0)
    assert [part["code"] for part in schedule.get("parts", [])] == [
        case.preserved_code
    ]
    assert schedule["parts"][0]["plain_text"] == f"Fixture body for {case.document}."


@pytest.mark.parametrize("case", PART_CASES, ids=_case_id)
def test_each_documented_form_stays_content_below_the_active_heading_size_zone(
        case: PartCase):
    schedule = _build(case, heading_size=8.0)
    assert not schedule.get("parts")
    leaf = schedule["sections"][0]
    rendered = leaf["html"] + "\n" + leaf["plain_text"]
    assert case.printed in rendered
    assert f"Fixture body for {case.document}." in leaf["plain_text"]


def test_lowercase_l_source_defects_are_preserved_and_never_folded_to_i():
    defects = [case for case in PART_CASES if case.source_roman_defect]
    assert [(case.preserved_code, case.intended_code) for case in defects] == [
        ("PART IL", "PART II"),
        ("PART LLL", "PART III"),
        ("PART VILI", "PART VIII"),
    ]
    assert all(case.preserved_code != case.intended_code for case in defects)
