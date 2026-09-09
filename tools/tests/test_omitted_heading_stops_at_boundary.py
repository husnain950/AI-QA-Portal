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
from legal_ingest.pagemodel import Line, Word  # noqa: E402


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
