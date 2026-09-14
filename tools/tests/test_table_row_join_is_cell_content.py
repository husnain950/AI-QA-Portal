"""A flattened table ROW is table content, not the start of another section.

``plain_text`` is flat, and the renderer flattens a table two different ways.
A cell whose content wraps contributes its own physical lines.  But a SHORT row
is emitted as ONE line with its cells joined by a single space -- and that
joined line is equal to no individual cell, so a ``_table_cell_lines`` that
collected cells alone could not see it.

Sales Tax Rules 2006 (01-01-2025) rule 13 carries the Schedule row

    <tr><td>44A</td><td>Steel ingots / bala</td><td>M. Tons</td></tr>

which flattens to ``44A Steel ingots / bala M. Tons``.  ``no_foreign_section
_start_in_body`` read that serial-number cell as the start of rule 44A and
reported it -- the rules lane's one hit of that class.

The hit was convincing because every other guard on that invariant agreed.  The
code folds to a real leaf; ``44A`` sorts after ``13``; and the victim IS
starved, because rule 44A is heading-only for a printing error the source makes
and ``exemptions/rules.json`` already covers (PDF page 66, a left double
quotation mark before the code).  Only the table exclusion could refuse it, and
it was looking at cells.

Both halves are pinned here.  The ROW-JOIN case fails without the fix.  The
WRAPPED-CELL case is the shape that already worked and must keep working -- a
fix that replaced the per-cell collection instead of adding to it would pass the
first test and silently drop the Eleventh Schedule's wrapped ``chapter 25``
tariff reference back into the invariant's path.
"""

from __future__ import annotations

import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages"), str(_ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from suite.invariants import _common  # noqa: E402

#: The real row, verbatim from the 01-01-2025 output.
_ROW_HTML = (
    "<table><tbody>"
    "<tr><td>72[44</td><td>Steel billets</td><td>M. Tons</td></tr>"
    "<tr><td>44A</td><td>Steel ingots / bala</td><td>M. Tons</td></tr>"
    "<tr><td>44B</td><td>Ship plates</td><td>M. Tons</td></tr>"
    "</tbody></table>"
)

#: A cell whose content WRAPS, the shape that already worked.
_WRAPPED_HTML = (
    "<table><tbody><tr><td>any kind of gypsum under\nchapter 25\n"
    "(PCT headings 2520.1010, ...)</td><td>Respective heading</td></tr>"
    "</tbody></table>"
)


def test_a_flattened_row_counts_as_table_content():
    """The row-join, which equals no single cell, must be excluded."""
    lines = _common._table_cell_lines(_ROW_HTML)
    assert "44A Steel ingots / bala M. Tons" in lines
    assert "44B Ship plates M. Tons" in lines


def test_wrapped_cell_lines_are_still_collected():
    """Adding the row shape must not replace the per-cell shape."""
    lines = _common._table_cell_lines(_WRAPPED_HTML)
    assert "chapter 25" in lines, "the wrapped tariff reference stopped being cell content"
    assert "any kind of gypsum under" in lines


def test_the_serial_cell_is_not_reported_as_a_foreign_section_start():
    """End to end: the invariant must not name rule 44A as started inside rule 13.

    Both leaves are present, because the invariant only reports a foreign start
    whose code resolves to a leaf that is ITSELF starved -- which 44A is.

    The container key must be ``sections``: ``loader._iter_leaves`` walks
    ``parts``/``divisions``/``sections`` and nothing else, so a fixture using
    ``children`` yields NO leaves and this test passes for the wrong reason --
    which is exactly what the first draft of it did.
    """
    doc = {
        "metadata": {"filename": "Sales Tax Rules, 2006 (Updated upto 01-01-2025).pdf"},
        "chapters": [{
            "code": "II", "title": "REGISTRATION", "sections": [
                {
                    "code": "13", "heading": "Application", "kind": "section",
                    "html": "<p>13. Application.- A person shall apply.</p>" + _ROW_HTML,
                    "plain_text": ("13. Application.- A person shall apply.\n"
                                   "72[44 Steel billets M. Tons\n"
                                   "44A Steel ingots / bala M. Tons\n"
                                   "44B Ship plates M. Tons"),
                },
                {
                    "code": "44A", "heading": "Selection and conduct of audit",
                    "kind": "section",
                    "html": "<p>44A. Selection and conduct of audit</p>",
                    "plain_text": "44A. Selection and conduct of audit",
                },
            ],
        }],
    }
    assert _common.inv_no_foreign_section_start_in_body(doc) == []
