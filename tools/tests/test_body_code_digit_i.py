from __future__ import annotations

from legal_ingest.builder import LineRef
from legal_ingest.discover import discover_structure
from legal_ingest.pagemodel import Line, Word


def _line(text: str) -> Line:
    words = []
    x = 60.0
    for token in text.split():
        words.append(
            Word(
                text=token,
                x0=x,
                x1=x + 6 * len(token),
                top=100.0,
                size=10.0,
                fontname="Arial-BoldMT",
            )
        )
        x += 6 * len(token) + 4
    return Line(top=100.0, words=words)


def test_digit_one_between_h_and_j_is_the_letter_i_suffix():
    refs = [
        LineRef(1, _line("CHAPTER XXI")),
        LineRef(1, _line("CUSTOMS COMPUTERIZED SYSTEM")),
        LineRef(2, _line("556H. Data entry.- The officer shall enter the data.")),
        LineRef(2, _line("5561. Processing of gate-in.- The officer shall process it.")),
        LineRef(2, _line("556J. Filing of declaration.- The importer shall file it.")),
    ]

    _chapters, entries = discover_structure(refs, {}, {}, _gate=False)

    assert [entry.code for entry in entries] == ["556H", "556I", "556J"]


def test_unsequenced_numeric_5561_is_not_rewritten():
    refs = [
        LineRef(1, _line("CHAPTER I")),
        LineRef(2, _line("5561. A genuine numeric provision.- It remains numeric.")),
    ]

    _chapters, entries = discover_structure(refs, {}, {}, _gate=False)

    assert [entry.code for entry in entries] == ["5561"]
