"""A body-printed heading must lose its whole code, not just the digits.

``builder._body_heading_title`` reduces a rendered <h4> ("1[15. Prohibitions.-")
to the bare title so the ``heading`` field keeps the shape of the TOC heading it
replaces.  It took the section's ``code`` as an argument and never used it: the
strip ran off ``_HEAD_CODE_PREFIX_RE``, whose ``grammar.CODE`` is positional and
allows a hyphen but never a space.

The text layer splits the code on two real families -- ``150 ZQR.`` for 150ZQR
(the 18-section Sales Tax Rules run that ``_DOTSUFFIX_RE`` exists to catch) and
``156 A.`` for 156A -- so the match ended after the digits and the letters stayed
in the title.  Measured over the shipped corpus: 26 leaves in 10 documents across
the acts and rules lanes, every one of them ``heading_source="body"``.

The code the caller already passes now drives the strip, tolerating the
separators ``norm_code`` folds away -- the same fix, for the same reason, that
``discover._heading_from_words`` already carries.  The positional form stays as
the fallback it has always been, for a body that prints a code the TOC does not
list at all.
"""

from __future__ import annotations

import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legal_ingest.builder import _body_heading_title  # noqa: E402

#: (rendered h4 inner, code, expected title).  The first five are the shapes the
#: corpus actually prints, one per affected document family.
SPLIT_CODES = [
    ("150 ZQT. Goods to be monitored electronically through video cameras etc.-",
     "150ZQT", "Goods to be monitored electronically through video cameras etc"),
    ("150 ZQR. Application.-", "150ZQR", "Application"),
    ("156 A. Proceedings against authority and persons.-", "156A",
     "Proceedings against authority and persons"),
    ("25 AA. Transactions between associates.-", "25AA",
     "Transactions between associates"),
    ("37 D. Cognizance of offences by Special Judges.-", "37D",
     "Cognizance of offences by Special Judges"),
    ("14 A. Credit and debit notes.-", "14A", "Credit and debit notes"),
]

#: Shapes that already worked and must keep working -- the marker run, the
#: insertion bracket, the unclosed paren, the dot-less inserted section, and the
#: hyphenated Customs code.
UNCHANGED = [
    ("1[15. Prohibitions.-", "15", "Prohibitions"),
    ("6,71,76,81[194. Appeal to High Court.-", "194", "Appeal to High Court"),
    ("196-A. Statement of case to Supreme Court.-", "196A",
     "Statement of case to Supreme Court"),
    ("5[(14-A. Provision of accommodation.-", "14A", "Provision of accommodation"),
    ("1[230E Directorate of Law.-", "230E", "Directorate of Law"),
]


def test_split_code_is_stripped_whole():
    for h4, code, want in SPLIT_CODES:
        assert _body_heading_title(h4, code) == want, h4


def test_shapes_that_already_worked_are_unchanged():
    for h4, code, want in UNCHANGED:
        assert _body_heading_title(h4, code) == want, h4


def test_positional_fallback_survives_a_code_the_toc_does_not_carry():
    """Sales Tax Rules lists 39E where the body prints 39K with the same title.

    The code-driven pattern cannot match there, and the positional one must
    still strip -- otherwise this fix would turn a wrong-code heading into a
    heading carrying the code.
    """
    assert _body_heading_title("39K. Some other title.-", "39E") == "Some other title"


def test_the_strip_never_reaches_past_the_code():
    """The bound that makes this safe: separators only, never a title word.

    Without it the joined pattern could walk into the title on a short code.
    """
    assert _body_heading_title("1. A Baker's dozen.-", "1") == "A Baker's dozen"
    assert _body_heading_title("2. 3 year rule.-", "2") == "3 year rule"


def test_a_body_code_longer_than_the_toc_code_is_still_stripped_whole():
    """The other direction, and why the longest match wins.

    Where the body prints a suffix the TOC's code does not carry, a strip driven
    only by the TOC code matches the digits and leaves the suffix behind -- the
    exact shape this round removes.  The positional pattern spans it, so taking
    the longer of the two is what keeps both directions correct.
    """
    assert _body_heading_title("15A. Title of the thing.-", "15") == "Title of the thing"
    assert _body_heading_title("14A. Credit notes.-", "14") == "Credit notes"


def test_the_code_terminator_is_not_read_as_an_interior_separator():
    """Customs 193A prints ``193. Appeals to Collector``.

    The separator run between the code's characters must not swallow the code's
    own terminator: ``3`` + ``. `` + ``A`` would match and take the title's first
    letter with it, turning a correct heading into "ppeals to Collector".  The
    code token has to end on a boundary, which makes this fall through to the
    positional pattern -- the right answer here.
    """
    assert (_body_heading_title("193. Appeals to Collector (Appeals).-", "193A")
            == "Appeals to Collector (Appeals)")
    # and the shape it must NOT stop working on: the same code, printed in full
    assert (_body_heading_title("193A. Appeals to Collector (Appeals).-", "193A")
            == "Appeals to Collector (Appeals)")
    # the dot-less split, which the same run repaired: "18 A Special customs duty"
    assert (_body_heading_title("18 A Special customs duty on imported goods.-", "18A")
            == "Special customs duty on imported goods")


def test_no_recognisable_title_still_returns_empty():
    """"" means 'keep the TOC heading', and a caller depends on it."""
    assert _body_heading_title("150 ZQR. .-", "150ZQR") == ""
