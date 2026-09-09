"""An omitted section cannot borrow a later section's heading terminator.

The Sales Tax Act prints section 32AA as an omission immediately before the
next chapter:

    6[32AA. ***]
    Chapter-VII
    OFFENCES AND PENALTIES
    33. Offences and penalties.-

``_find_heading_split`` used to scan through the structural boundary and use
section 33's dash, making the chapter code, caption, and next section title part
of 32AA's heading.  Merely stopping the scan loses 32AA altogether because its
omission line has no terminator of its own.  This fixture pins both sides through
body-driven discovery and the section builder.
"""

from __future__ import annotations

import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.builder import LineRef, build_sections  # noqa: E402
from legal_ingest.discover import discover_structure  # noqa: E402
from legal_ingest.pagemodel import Line, Table, Word  # noqa: E402


def _line(words: list[tuple[str, float]]) -> Line:
    out, x = [], 60.0
    for text, size in words:
        out.append(Word(text=text, x0=x, x1=x + 6 * len(text), top=100.0,
                        size=size, fontname="Arial-BoldMT"))
        x += 6 * len(text) + 4
    return Line(top=100.0, words=out)


def _ordinary(text: str) -> Line:
    return _line([(word, 10.0) for word in text.split()])


def _flatten(nodes):
    for node in nodes:
        yield node
        yield from _flatten(node.parts)
        yield from _flatten(node.divisions)


def test_omitted_32aa_survives_without_borrowing_the_next_heading():
    refs = [
        LineRef(1, _ordinary("Chapter-VI")),
        LineRef(1, _ordinary("APPOINTMENT OF OFFICERS OF SALES TAX")),
        LineRef(1, _ordinary(
            "30. Appointment of authorities.- The Board may appoint officers.")),
        LineRef(2, _line([
            ("6", 6.5),
            ("[32AA.", 10.0),
            ("***]", 10.0),
        ])),
        LineRef(3, _ordinary("Chapter-VII")),
        LineRef(3, _ordinary("OFFENCES AND PENALTIES")),
        LineRef(3, _ordinary(
            "33. Offences and penalties.- Whoever commits an offence is liable.")),
    ]

    chapters, entries = discover_structure(refs, {}, {}, _gate=False)
    by_code = {entry.code: entry for entry in entries}

    assert "32AA" in by_code, (
        "stopping at CHAPTER VII must fall back to the omission line instead of "
        "dropping section 32AA")
    omitted = by_code["32AA"]
    assert omitted.heading == "***", omitted.heading

    built = build_sections(
        refs,
        entries,
        {},
        {},
        page_offset=0,
        containers=list(_flatten(chapters)),
    )
    assert id(omitted) in built, "the discovered omission must remain a leaf"

    leaf = built[id(omitted)]
    assert leaf.plain_text.endswith("[32AA. ***]"), leaf.plain_text
    for leaked in ("Chapter-VII", "OFFENCES AND PENALTIES",
                   "33. Offences and penalties"):
        assert leaked not in leaf.heading, leaf.heading
        assert leaked not in leaf.html, leaf.html
        assert leaked not in leaf.plain_text, leaf.plain_text


def test_untitled_one_sentence_rule_keeps_body_and_stops_at_next_rule():
    refs = [
        LineRef(1, _ordinary("CHAPTER I")),
        LineRef(1, _ordinary("PRELIMINARY")),
        LineRef(2, _ordinary(
            "47A. Delayed perishable goods may be released on written request.")),
        LineRef(2, _ordinary(
            "48. Failure to comply.- A person who fails to comply is liable.")),
    ]

    chapters, entries = discover_structure(refs, {}, {}, _gate=False)
    by_code = {entry.code: entry for entry in entries}
    assert set(by_code) == {"47A", "48"}
    assert by_code["47A"].heading == ""

    built = build_sections(
        refs,
        entries,
        {},
        {},
        page_offset=0,
        containers=list(_flatten(chapters)),
    )
    leaf = built[id(by_code["47A"])]
    assert "Delayed perishable goods" in leaf.plain_text
    assert "48. Failure to comply" not in leaf.plain_text


def test_untitled_rule_followed_by_table_is_not_dropped():
    refs = [
        LineRef(1, _ordinary("CHAPTER XII")),
        LineRef(2, _ordinary(
            "216. Repayment shall be made according to the table below:")),
        LineRef(2, Table(
            top=120.0,
            bottom=180.0,
            html="<table><tr><td>Period</td><td>Amount</td></tr></table>",
            plain="Period Amount",
        )),
        LineRef(3, _ordinary(
            "217. Temporary import is allowed subject to these conditions:- "
            "The importer shall furnish a guarantee.")),
    ]

    chapters, entries = discover_structure(refs, {}, {}, _gate=False)
    by_code = {entry.code: entry for entry in entries}
    assert set(by_code) == {"216", "217"}
    assert by_code["216"].heading == ""

    built = build_sections(
        refs,
        entries,
        {},
        {},
        page_offset=0,
        containers=list(_flatten(chapters)),
    )
    leaf = built[id(by_code["216"])]
    assert "Repayment shall be made" in leaf.plain_text
    assert "Period Amount" in leaf.plain_text
