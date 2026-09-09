"""A quoted tariff code must not advance a Finance Act's clause cursor.

Finance Act 2024 clause 7 quotes a tariff-table amendment containing
``8517.1390``.  The grid is text-only in the page model, so its rows are
ordinary ``Line`` objects rather than provenance-marked ``Table`` objects.
Discovery read ``8517`` as a clause code, borrowed clause 8's heading
terminator from the multiline lookahead, and advanced the monotonic cursor
past every real clause that followed.

The fixture keeps the source shape: an amending clause, a text-only TABLE with
its column-numbering row, ``1430 and 8517.1390) shall be added.``, then real
clauses 8 and 9.  It exercises discovery and section binding together so merely
hiding the bad code cannot pass while clause 8 is still swallowed.
"""

from __future__ import annotations

import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages"), str(_ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.builder import LineRef, build_sections  # noqa: E402
from legal_ingest.discover import discover_structure  # noqa: E402
from legal_ingest.pagemodel import Line, Word  # noqa: E402
from legal_ingest.profiles import AMENDING  # noqa: E402
from legal_ingest.tables import find_table_spans  # noqa: E402
from suite.invariants._common import inv_clause_codes_plausible  # noqa: E402


def _line(text: str, left: float = 60.0) -> Line:
    words, x = [], left
    for token in text.split(" "):
        words.append(Word(
            text=token,
            x0=x,
            x1=x + 6 * len(token),
            top=100.0,
            size=10.0,
            fontname="ArialMT",
        ))
        x += 6 * len(token) + 4
    return Line(top=100.0, words=words)


def _finance_act_2024_refs(clause_left: float = 60.0) -> list[LineRef]:
    """Clause 7's text-only tariff grid followed by clauses 8 and 9."""
    body = [
        (1, 60.0, "1. Short title and commencement.— This Act may be called "
                  "the Finance Act, 2024."),
        (1, 60.0, "It shall come into force at once."),
        (7, 60.0, "7. Amendment of the Customs Act, 1969.— In the Customs Act, "
                  "1969, the following amendments shall be made."),
        (7, 60.0, "In the First Schedule, in the TABLE, the following entries "
                  "shall be added, namely:—"),
        (7, 120.0, "TABLE"),
        (7, 120.0, "PCT heading Existing entry New entry"),
        (7, 120.0, "(1) (2) (3)"),
        (7, 120.0, "1430 and"),
        (7, 120.0, "8517.1390) shall be added."),
        (8, clause_left, "8. Amendments of the Sales Tax Act, 1990.— In the "
                         "Sales Tax Act, 1990, the following amendments shall "
                         "be made."),
        (8, clause_left, "The quoted tariff amendment above belongs to clause 7."),
        (9, clause_left, "9. Amendment of the Federal Excise Act, 2005.— In the "
                         "Federal Excise Act, 2005, the following amendment "
                         "shall be made."),
    ]
    refs = [LineRef(page=page, line=_line(text, left))
            for page, left, text in body]
    # This is intentionally the gridless path: pagemodel has not replaced any
    # line with its ruled-grid Table type, but the existing fallback detector
    # has enough structure to establish table provenance.
    assert not any(getattr(ref.line, "is_table", False) for ref in refs)
    return refs


def _discover(refs: list[LineRef]):
    _chapters, entries = discover_structure(
        refs, printed_by_page={}, page_footnotes={}, profile=AMENDING)
    return entries


def test_tariff_code_stays_in_clause_7_and_real_clause_8_is_discovered():
    refs = _finance_act_2024_refs()
    assert find_table_spans(refs) == [(4, 9)], (
        "the synthetic tariff grid must exercise fallback table provenance")

    entries = _discover(refs)
    assert [entry.code for entry in entries] == ["1", "7", "8", "9"]

    built = build_sections(
        refs, entries, {}, {}, page_offset=0, containers=[])
    by_code = {entry.code: built[id(entry)] for entry in entries}
    assert "8517.1390) shall be added" in by_code["7"].plain_text
    assert by_code["8"].plain_text.startswith(
        "8. Amendments of the Sales Tax Act, 1990.")
    assert "Federal Excise Act" in by_code["9"].plain_text


def test_real_clause_heading_bounds_a_table_even_without_left_margin_signal():
    """A real clause remains eligible when its geometry cannot end the span.

    ``find_table_spans`` normally stops when body text returns to the left
    margin.  This adversarial variant keeps clauses 8 and 9 at the table's
    indentation, forcing discovery's independent heading bound to preserve the
    genuine sequence.
    """
    refs = _finance_act_2024_refs(clause_left=120.0)
    assert find_table_spans(refs) == [(4, len(refs))]
    assert [entry.code for entry in _discover(refs)] == ["1", "7", "8", "9"]


def test_implausible_jump_outside_a_table_still_reaches_the_invariant():
    """The parser fix must not turn off ``clause_codes_plausible``.

    An independently terminated 8517 heading outside a detected table remains
    discoverable.  The invariant must therefore stay red on that adversarial
    shape instead of having its signal weakened by a blanket numeric cap.
    """
    refs = [
        LineRef(1, _line("1. Short title and commencement.— This Act may be "
                         "called the Test Act, 2024.")),
        LineRef(7, _line("7. Amendment of the Customs Act, 1969.— The Act shall "
                         "be amended in the prescribed manner.")),
        LineRef(8, _line("8517. Amendment of the Sales Tax Act, 1990.— This is "
                         "an independently terminated synthetic heading.")),
    ]
    entries = _discover(refs)
    assert [entry.code for entry in entries] == ["1", "7", "8517"]

    doc = {
        "metadata": {"chapters_count": 1},
        "chapters": [{"sections": [{"code": entry.code}
                                   for entry in entries]}],
    }
    failures = inv_clause_codes_plausible(doc)
    assert len(failures) == 1
    assert "7->8517" in failures[0]
