"""A gazette title is never the middle of a sentence.

``_gazette_block_class`` is a pure string-prefix classifier, and two of its
patterns match ordinary body prose:

  * ``_GAZETTE_TITLE_RE`` is compiled ``re.I``, so the word "An" matches the
    gazette title "AN".  Federal Excise Act, 2005 (30-06-2025) breaks s.43A's
    sentence across a page: p.60 ends "...documents.– An" and p.61 opens
    "officer of federal excise not below the rank of...".  The stray "An"
    rendered as <p class="act-title">, which the panel CSS centres, uppercases,
    sets at weight 800 and letter-spaces.
  * ``_GAZETTE_LONG_TITLE_RE`` matches any line opening "to provide|amend|
    levy|make|...".  s.47AB(1) wraps "...arrangements shall be made" /
    "to provide real-time access of information and database to the Board..."
    and the continuation rendered as <p class="act-long-title">, centred italic.

Neither can be fixed by dropping ``re.I`` or by restricting the classifier to
the preamble, and both were measured before being rejected:

  * 11 uppercase AN/ACT blocks sit inside numbered sections legitimately,
    because a Finance Act host clause reprints a whole Act (the case named in
    the comment above ``_GAZETTE_TITLE_RE``);
  * ``_GAZETTE_TABLE_CAPTION_RE`` also returns "act-title", and 109 of the
    253 non-preamble gazette blocks in the corpus are ``TABLE`` captions that
    must keep their centring.

What separates the false positives is that they CONTINUE a sentence.  A short
title whose next line opens lowercase is a continuation; a long title whose
previous block is ordinary body text is a continuation.  Context is optional,
so the preamble callers -- which legitimately have no neighbours to test --
keep the old behaviour.

QA Cycle 1 rows CH6-01 (s.43A) and CH6-05 (s.47AB).
"""
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.builder import GAZETTE_KINDS, _gazette_block_class  # noqa: E402


def test_the_page_break_An_is_not_a_title():
    # s.43A, p.60/61 -- the next line continues the sentence in lower case
    assert _gazette_block_class(
        "An", prev_kind="", next_plain="officer of federal excise not below"
    ) is None


def test_the_wrapped_long_title_is_not_a_title():
    # s.47AB(1), p.68 -- the previous block is the subsection it belongs to
    assert _gazette_block_class(
        "to provide real-time access of information and database to the Board",
        prev_kind="subsec", next_plain="(a) the National Database and",
    ) is None


def test_a_real_gazette_preamble_still_classifies():
    # AN -> ACT -> long title: each one's neighbour is itself a gazette line
    assert _gazette_block_class(
        "AN", prev_kind="enacting-clause", next_plain="ACT") == "act-title"
    assert _gazette_block_class(
        "ACT", prev_kind="act-title",
        next_plain="to provide for declaration and repatriation of assets",
    ) == "act-title"
    assert _gazette_block_class(
        "to provide for declaration and repatriation of assets",
        prev_kind="act-title", next_plain="WHEREAS it is expedient",
    ) == "act-long-title"


def test_a_table_caption_is_never_refused():
    # 109 of these in the corpus, all inside sections, all legitimate
    for nxt in ("1 Advertisement on closed circuit T.V.", "(EXCISABLE GOODS)",
                "quantities prescribed under the West Pakistan Pure Food"):
        assert _gazette_block_class(
            "TABLE", prev_kind="text", next_plain=nxt) == "act-title"
    assert _gazette_block_class(
        "TABLES", prev_kind="subsec", next_plain="s. no. description") == "act-title"


def test_without_context_the_old_behaviour_is_kept():
    # the preamble callers pass no neighbours and must not change
    assert _gazette_block_class("An") == "act-title"
    assert _gazette_block_class("AN") == "act-title"
    assert _gazette_block_class("to provide for declaration") == "act-long-title"
    assert _gazette_block_class("WHEREAS there is") == "recital"
    assert _gazette_block_class("(1) This Act") is None


def test_the_first_row_of_a_leaf_may_still_be_a_long_title():
    # prev_kind "" means "nothing before it", which is not a body row
    assert _gazette_block_class(
        "to provide for the levy of a duty", prev_kind="",
        next_plain="WHEREAS it is expedient") == "act-long-title"


def test_recitals_and_enacting_lines_are_untouched():
    for plain, want in (("WHEREAS there is", "recital"),
                        ("It is hereby enacted as follows:—", "enacting-formula"),
                        ("There is hereby enacted Foreign Assets", "enacting-clause")):
        assert _gazette_block_class(
            plain, prev_kind="subsec", next_plain="a lowercase line") == want
        assert want in GAZETTE_KINDS
