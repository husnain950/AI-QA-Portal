"""A footnote marker kerned onto a list marker still opens a list item.

Federal Excise Act, 2005 (30-06-2025) prints three list items whose amendment
marker is set hard against the marker that follows it, with no space:

    p.44  4(1AB) The Commissioners Inland Revenue shall perform their
    p.66  2(d) sent electronically through email or to the e-folder maintained
    p.65  2[9] The audit of the registered person shall generally be a

(the leading digit is the superscript: 8.0pt against a 12.0pt body, at x0 139.3,
155.9 and 155.9 respectively).

``_classify`` probes three strings, all anchored with ``^``.  ``s3`` strips a
run of ``marker[`` groups, but its comment records that a ``[`` is *deliberately*
required so that a body line opening on a bare number -- "233 (2A) ..." -- is
left alone.  None of the three lines above carries that bracket in the right
place, so all three returned "text", and a "text" row is absorbed into the
previous ``<li>`` by ``_build_html``.  The portal therefore showed subsection
(1AB) inside (1AA), clause (d) inside (c), and subsection (9) inside (8).

The three probes added here are each anchored on what the source actually
prints, so the two lines the old comment protects still classify as "text".

QA Cycle 1 rows CH5-01, CH6-02 and CH6-04.
"""
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.builder import _classify  # noqa: E402

#: The lines the 30-06-2025 edition actually prints, verbatim, as they reach
#: ``_classify`` (the marker is a bare digit in the rendered plain text).
MERGED = [
    ("4(1AB) The Commissioners Inland Revenue shall perform their", "subsec"),
    ("2(d) sent electronically through email or to the e-folder maintained",
     "clause"),
    ("2[9] The audit of the registered person shall generally be a", "subsec"),
    ("3[***]", "subsec"),
]

#: Lines that must NOT move.  The first is the case ``_classify``'s own comment
#: protects; the second is pinned by test_bracketed_code_dot.py; the third is
#: claimed away by ``claim_placeholder_lines`` and must stay body text here.
UNCHANGED = [
    "233 (2A) Notwithstanding anything",
    "2[21].Where any person repeats an",
    "2[ 31***]",
]


def test_a_kerned_marker_does_not_hide_the_list_item():
    for text, want in MERGED:
        assert _classify(text) == want, text


def test_the_lines_the_bracket_rule_protects_are_untouched():
    for text in UNCHANGED:
        assert _classify(text) == "text", text


def test_the_shapes_that_already_classified_are_unchanged():
    assert _classify("1[(1AA) The Chief Commissioners Inland Revenue shall") == "subsec"
    assert _classify("(2) Notwithstanding the other designations of the officers") == "subsec"
    assert _classify("(a) the liability of tax of fifty million-rupees or above") == "clause"
    assert _classify("(i) Long routes Fifteen Hundred rupees") == "roman"


def test_a_bare_number_followed_by_a_space_is_never_a_list_item():
    # the strip is anchored on "(" with NO space -- a spaced number is prose
    assert _classify("233 (2A) Notwithstanding") == "text"
    assert _classify("55 (a) of cylinder capacity up to 1000cc") == "text"


def test_an_omission_bracket_needs_asterisks_only():
    # "3[***]" is an omitted subsection; "2[ 31***]" carries a section NUMBER
    # and belongs to claim_placeholder_lines, not to the subsection grammar.
    assert _classify("3[***]") == "subsec"
    assert _classify("2[ 31***]") == "text"
    assert _classify("6[8 ***]") == "text"
