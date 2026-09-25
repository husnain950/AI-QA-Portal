"""A heading whose terminator is printed twice keeps both dashes.

Federal Excise Act, 2005 (30-06-2025) p.66 prints section 47's heading and the
opening of its subsection (1) on one line, with the terminator doubled:

    1[47. Service of notices and other documents.–– (1)

``_words_after_heading_dash`` splits the dash token by ``rfind`` over an
ordered pattern list and returns on the FIRST hit.  ".–" matches at the first
en dash, so the heading side took "documents.–" and the second dash was left
at the head of the body: the leaf rendered

    <h4>47. Service of notices and other documents.–</h4>
    <p>– (1) Subject to this Act, ...</p>

and because that body line now began with a dash rather than "(1)",
``_classify`` returned "text" and subsection (1) rendered as a bare <p>
outside its own <ol> as well.

A terminator run belongs entirely to the heading.  412 leaves across 30
documents opened their body with an orphaned dash before this.

QA Cycle 1 rows CH5-04 (s.34) and CH6-03 (s.47).
"""
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.builder import _classify, _words_after_heading_dash  # noqa: E402
from legal_ingest.pagemodel import Word  # noqa: E402

DASHES = "—–―─"


def _words(text, bold=True):
    """One line of Words, laid out left to right; geometry is not read here."""
    font = "TimesNewRomanPS-BoldMT" if bold else "TimesNewRomanPSMT"
    out, x = [], 126.0
    for tok in text.split(" "):
        out.append(Word(text=tok, x0=x, x1=x + 6.0 * len(tok), top=140.0,
                        size=12.0, fontname=font))
        x += 6.0 * len(tok) + 3.0
    return out


def split(text):
    """(heading text, body text) for one heading line."""
    got = _words_after_heading_dash(_words(text), allow_first=True)
    assert got is not None, text
    before, rest = got
    return (" ".join(w.text for w in before), " ".join(w.text for w in rest))


def test_the_second_dash_stays_with_the_heading():
    head, body = split("47. Service of notices and other documents.–– (1)")
    assert head == "47. Service of notices and other documents.––"
    assert body == "(1)"


def test_the_body_line_is_then_a_subsection_again():
    _, body = split("47. Service of notices and other documents.–– (1)")
    assert _classify(body + " Subject to this Act, any notice") == "subsec"


def test_a_single_terminator_is_unchanged():
    head, body = split("30. Use of powers of subordinate officer.— (1)")
    assert head == "30. Use of powers of subordinate officer.—"
    assert body == "(1)"


def test_a_mixed_run_is_taken_whole():
    head, body = split("34. Appeals to the Appellate Tribunal.–— (1)")
    assert head.endswith(".–—"), head
    assert body == "(1)"


def test_the_heading_still_ends_in_a_dash():
    # the caller discards a split whose heading does not end in a dash
    for line in ("47. Service of notices and other documents.–– (1)",
                 "30. Use of powers of subordinate officer.— (1)",
                 "34. Appeals to the Appellate Tribunal.–— (1)"):
        head, _ = split(line)
        assert head[-1] in DASHES, head


def test_a_terminator_doubled_as_a_separate_token_also_stays():
    # Sales Tax 1990 (01-07-2014) p.14 prints three tokens -- "4[2." /
    # "Definitions." + U+2015 / U+2015 -- so the second dash is a WORD of its
    # own, not fused.  50 leaves of that document opened on it.
    head, body = split("2. Definitions.\u2015 \u2015 In this Act, unless there is anything")
    assert head == "2. Definitions.\u2015 \u2015"
    assert body.startswith("In this Act,")


def test_only_dash_tokens_are_absorbed():
    # a word after the terminator is body text, however short
    head, body = split("5. Change in the rate of tax. \u2013 If there is a change")
    assert head.rstrip().endswith("\u2013")
    assert body.startswith("If there is a change")


def test_operative_text_fused_to_the_dash_is_still_body():
    # the oper_suffix path must survive: only a DASH-ONLY remainder moves
    head, body = split("20. Delegation.—The Federal Government may")
    assert head == "20. Delegation.—"
    assert body.startswith("The Federal Government may")


def _seg(*lines):
    from legal_ingest.builder import LineRef
    from legal_ingest.pagemodel import Line
    return [LineRef(page=1, line=Line(top=140.0 + 14 * i, words=_words(t)))
            for i, t in enumerate(lines)]


def test_a_doubled_terminator_split_by_the_wrap_stays_with_the_heading():
    # Sales Tax Rules 31.08.2021 p.113: the heading line ends ".-" and the next
    # line OPENS with the second "-", so rule 150X's body began "- (1) ..."
    from legal_ingest.builder import _find_heading_split
    seg = _seg("150X. Same conditions to apply in respect of buyer for "
               "receiving electronic invoices.-",
               "- (1) The registered buyer who receives electronic invoices")
    li, before, after = _find_heading_split(seg, len(seg))
    assert li == 1 and [w.text for w in before] == ["-"], (li, before)
    assert " ".join(w.text for w in after).startswith("(1) The registered buyer")
    assert _classify(" ".join(w.text for w in after)) == "subsec"


def test_a_body_line_that_merely_starts_later_is_untouched():
    # no dash on the next line: the split stays on the heading line
    from legal_ingest.builder import _find_heading_split
    seg = _seg("30. Use of powers of subordinate officer.—",
               "(1) The Collector may")
    li, _, after = _find_heading_split(seg, len(seg))
    assert li == 0 and after == []


def test_the_heading_field_sheds_a_wrapped_doubled_terminator():
    from legal_ingest.discover import _heading_from_words
    words = _words("150X. Same conditions to apply in respect of buyer for "
                   "receiving electronic invoices.- -")
    assert _heading_from_words(words, "150X") == (
        "Same conditions to apply in respect of buyer for receiving electronic invoices")


def test_the_body_heading_title_sheds_a_wrapped_doubled_terminator():
    from legal_ingest.builder import _body_heading_title
    assert _body_heading_title(
        "150X. Same conditions to apply in respect of buyer for receiving "
        "electronic invoices.- -", "150X") == (
        "Same conditions to apply in respect of buyer for receiving electronic invoices")
    assert _body_heading_title("15. Prohibitions.-", "15") == "Prohibitions"
