"""Text that returns to the body margin closes an open clause list.

``_build_html``'s list loop absorbs every "text" row into the last ``<li>``
until a differently-kinded row arrives.  It has no geometry, so in Federal
Excise Act, 2005 (30-06-2025) s.38 the whole tail of subsection (1) ended up
inside clause (c):

    x0=162.0  (c) any other specific relief required to resolve the dispute,
    x0=126.0  may apply, except where criminal proceedings have been initiated,
    x0=162.0  Provided that where the aggrieved person is a state-owned
    x0=162.0  Explanation.- State-owned enterprise shall have the same meaning

"may apply, except where..." governs clauses (a), (b) AND (c) -- it is the
stem of subsection (1) resuming -- and both provisos and the Explanation
belong to the subsection too.  Nesting them under (c) makes generally
applicable text read as if it applied to one clause only, which changes the
legal meaning.

The PDF separates them cleanly and the parser was simply not looking: clause
items sit at x0 162 and their own wrapped lines at 180/186/198, while the
subsection stem resumes at 126, the calibrated body_left.  So a "text" row
more than 6pt left of the open list's own items closes it.

Only clause and roman lists are closed this way.  A subsec list must not be:
its items sit at 152-162 and its continuations legitimately run at 126, so a
plain margin test would destroy every subsection paragraph in the corpus.

Checked against the same document: s.47AB clause (e)'s two provisos sit at
x0 234.1 with continuations at 198.1, so they correctly stay inside clause (e).

QA Cycle 1 row CH5-05.
"""
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.builder import LineRef, _build_html, _render_line_run  # noqa: E402
from legal_ingest.pagemodel import Line, Word  # noqa: E402


def _ref(x0, text, top):
    words, x = [], float(x0)
    for tok in text.split(" "):
        words.append(Word(text=tok, x0=x, x1=x + 5.5 * len(tok), top=float(top),
                          size=12.0, fontname="TimesNewRomanPSMT",
                          marker_max=10.5, footnote_size=8.0,
                          footnote_marker_max=10.0))
        x += 5.5 * len(tok) + 3.0
    return LineRef(line=Line(top=float(top), words=words), page=55)


def html_for(layout):
    """layout = [(x0, text)] -> the rendered leaf html."""
    refs = [_ref(x0, t, 140 + 14 * i) for i, (x0, t) in enumerate(layout)]
    rows = _render_line_run(refs, {}, lambda p: 0, [])
    return _build_html("", rows)


#: s.38(1) as the PDF lays it out.
S38 = [
    (162.0, "(a) the liability of tax of fifty million rupees or above"),
    (162.0, "(b) the extent of waiver of default surcharge and penalty; or"),
    (162.0, "(c) any other specific relief required to resolve the dispute,"),
    (126.0, "may apply, except where criminal proceedings have been initiated,"),
    (162.0, "Provided that where the aggrieved person is a state-owned"),
    (162.0, "Explanation.- State-owned enterprise shall have the same meaning"),
]


def _clause_c(html):
    """The <li> that holds clause (c)."""
    for li in html.split("<li>")[1:]:
        if li.lstrip().startswith("(c)"):
            return li.split("</li>")[0]
    raise AssertionError("clause (c) not found in:\n" + html)


def test_the_subsection_stem_leaves_clause_c():
    assert "may apply" not in _clause_c(html_for(S38))


def test_the_proviso_and_explanation_leave_clause_c():
    li = _clause_c(html_for(S38))
    assert "Provided that" not in li
    assert "Explanation" not in li


def test_clause_c_keeps_its_own_words():
    li = _clause_c(html_for(S38))
    assert "any other specific relief required to resolve the dispute," in li


def test_nothing_is_dropped():
    html = html_for(S38)
    for _x0, text in S38:
        head = text.split(" ")[1] if text.startswith("(") else text.split(" ")[0]
        assert head in html, text


def test_a_clause_continuation_stays_inside_its_clause():
    # a wrapped clause line sits RIGHT of the item, not left of it
    layout = [
        (162.0, "(a) the liability of tax of fifty million rupees or above"),
        (180.0, "against the aggrieved person or admissibility of refund,"),
        (162.0, "(b) the extent of waiver of default surcharge and penalty; or"),
    ]
    html = html_for(layout)
    for li in html.split("<li>")[1:]:
        if li.lstrip().startswith("(a)"):
            assert "against the aggrieved person" in li
            return
    raise AssertionError("clause (a) not found")


def test_a_deeply_indented_proviso_stays_inside_its_clause():
    # s.47AB clause (e): provisos at 234.1, continuations at 198.1
    layout = [
        (162.0, "(e) all electricity suppliers and gas transmission companies"),
        (198.1, "consumer, the units consumed and the amount of bill charged:"),
        (234.1, "Provided that where the connection is shared or is used by"),
        (198.1, "of the owner and the user shall also be furnished:"),
    ]
    html = html_for(layout)
    for li in html.split("<li>")[1:]:
        if li.lstrip().startswith("(e)"):
            assert "Provided that where the connection" in li
            return
    raise AssertionError("clause (e) not found")


def test_a_subsection_continuation_is_never_treated_as_a_break():
    # subsec items sit at ~160 and their continuations at 126 -- the case a
    # plain margin test would destroy
    layout = [
        (160.0, "(6) If any one member of the special audit panel is absent"),
        (126.0, "from conducting an audit, the proceedings of the audit may"),
        (126.0, "continue and the audit shall not be invalid."),
        (160.0, "(7) The Board may prescribe rules in respect of constitution."),
    ]
    html = html_for(layout)
    for li in html.split("<li>")[1:]:
        if li.lstrip().startswith("(6)"):
            assert "from conducting an audit" in li
            assert "continue and the audit" in li
            return
    raise AssertionError("subsection (6) not found")
