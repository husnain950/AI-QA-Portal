"""A schedule's own title is rendered in its leaf, not only in the breadcrumb.

``build_schedules`` stores a schedule's title line out of band, in
``seg["head"]``, and builds the leaf from ``seg["lines"]`` alone.  So for

    p.72   FIRST SCHEDULE
    p.72   [See Section 3]
    p.72   TABLE 1

the peel loop in ``_finish_leaf`` sees ``[See Section 3]`` as its very first
line, breaks on ``_SEE_RE`` before collecting anything, and leaves
``heading`` empty.  The ``if not heading`` branch below it then promoted the
See line into the leaf's ``<h4>`` slot and removed it from the body -- and
because ``_render_line`` returns a bare fragment, the leaf shipped with **no
heading element at all**, its whole html being the seven words
``[See Section 3]``.

That branch's own comment says what should happen: *"keeps the title as its
<h4> and renders the [See ...] line in the body; promoting the See ref would
hide the title and drop the See text."*  Removing it lets ``head_html`` fall
through to the node's code, which is already correct, and leaves the See line
as the first body row.

237 leaves across 34 documents shipped with a bare ``[See ...]`` where their
heading should be: FIRST SCHEDULE x17, SIXTH SCHEDULE x17, EIGHTH SCHEDULE
x17, FIFTH SCHEDULE x17, THE THIRD SCHEDULE x20, PART II and PART III x12.

QA Cycle 1 row FS-01.
"""
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.builder import LineRef  # noqa: E402
from legal_ingest.pagemodel import Line, Word  # noqa: E402
from legal_ingest.schedules import _finish_leaf  # noqa: E402


def _line(text, top, size=10.0, bold=False):
    font = "TimesNewRomanPS-BoldMT" if bold else "TimesNewRomanPSMT"
    words, x = [], 126.0
    for tok in text.split(" "):
        words.append(Word(text=tok, x0=x, x1=x + 5.5 * len(tok), top=top,
                          size=size, fontname=font))
        x += 5.5 * len(tok) + 3.0
    return Line(top=top, words=words)


def _leaf(lines, code="FIRST SCHEDULE"):
    """Render one schedule leaf from its own body lines."""
    refs = [LineRef(line=_line(t, 140.0 + 14 * i), page=72)
            for i, t in enumerate(lines)]
    node = {"code": code, "heading": ""}
    _finish_leaf(node, {"lines": refs, "head": None}, {}, {}, {})
    return node


def test_the_schedule_title_is_the_leaf_heading():
    node = _leaf(["[See Section 3]", "Some body prose follows here."])
    assert '<h4 class="section-heading">FIRST SCHEDULE</h4>' in node["html"]


def test_the_see_reference_survives_in_the_body():
    node = _leaf(["[See Section 3]", "Some body prose follows here."])
    assert "[See Section 3]" in node["html"]
    assert "[See Section 3]" in node["plain_text"]


def test_the_heading_comes_first():
    node = _leaf(["[See Section 3]", "Some body prose follows here."])
    assert node["html"].lstrip().startswith("<h4")


def test_a_leaf_that_has_a_real_title_still_uses_it():
    # the case the branch's comment protects -- a peeled ALL-CAPS title wins
    node = _leaf(["RECOGNIZED PROVIDENT FUNDS",
                  "[See sections 2(48) and 21]",
                  "Some body prose follows here."])
    assert "RECOGNIZED PROVIDENT FUNDS" in node["html"]
    assert "[See sections 2(48) and 21]" in node["html"]
    assert node["html"].lstrip().startswith("<h4")


def test_a_leaf_with_no_see_line_is_unchanged():
    node = _leaf(["Some body prose follows here.", "And a second line."],
                 code="SECOND SCHEDULE")
    assert '<h4 class="section-heading">SECOND SCHEDULE</h4>' in node["html"]
