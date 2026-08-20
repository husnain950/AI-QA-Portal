"""The corpus's code and marker grammars, in ONE place.

The Ordinance pipeline spelled ``\\d{1,3}[A-Z]{0,3}`` out by hand in ten
different modules, and the copies had already drifted apart (``toc.py`` allowed
``[IVXLC0-9]`` for a Part numeral where ``schedules.py`` allowed only
``[IVXL]``, so the same heading classified differently depending on which
module asked).  Every one of those literals is wrong for the Acts anyway, so
they are consolidated here rather than widened ten times.

What the Acts actually print, and what the Ordinance grammar did to it:

  ``3AAA``, ``3CCE``, ``3CCD``   4 suffix letters -- ``[A-Z]{0,3}`` truncated
                                the match to ``3CC`` and two directorates
                                collapsed onto one code
  ``221-A``                     hyphenated -- matched as bare ``221``
  ``27a``, ``33a``, ``36b``     footnote markers with a LOWERCASE suffix; the
                                Ordinance's ``t.isdigit()`` test rejected them
                                outright, which alone would have dropped every
                                Customs footnote
  ``263`` ... ``831``           Sales Tax numbers footnotes globally into the
                                800s, where the Ordinance treated any marker
                                >= 100 as a misread year
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# section codes

#: A section code: up to three digits, an optional hyphen, up to four
#: uppercase suffix letters.  ``18``, ``18C``, ``3AAA``, ``3CCE``, ``221-A``.
CODE = r"\d{1,3}-?[A-Z]{0,4}"

#: Same, but requiring at least one suffix letter -- used where a bare number
#: would be ambiguous with a list serial.
CODE_SUFFIXED = r"\d{1,3}-?[A-Z]{1,4}"

#: The same code as printed in a table of contents, where these PDFs split
#: digits at kerning pairs: section 142 extracts as "14 2", 222 as "22 2", and
#: the page number 106 as "10 6".  Read with the plain CODE pattern, section 142
#: parsed as code "14" with page "6" -- a real section landed 100 pages from its
#: text and two codes collided.  Suffix letters are deliberately NOT allowed to
#: be spaced here: " B" would swallow the first letter of a title like
#: "141 Bona-fide baggage exempt from duty".
#: The suffix separator may also be a DOT in the older editions, which print
#: section 14A as "14.A." -- read without it, that row does not classify at all
#: and its title is swallowed into the previous section's heading.
CODE_TOC = r"\d(?:\s?\d){0,2}(?:[-.]\s?[A-Z]{1,4}|[A-Z]{1,4})?"
#: The printed page a TOC row ends with.  Sales Tax and Federal Excise print a
#: RANGE for a section that spans pages ("2. Definitions……7-29", "22 Power to
#: arrest and prosecute 35-39", "47. Reference to the High Court 106-107").
#: Without the range the row does not classify at all: section 2 and section 47
#: vanished from every Sales Tax edition and their titles were swallowed into
#: the neighbouring row's heading.  The row's page is the FIRST number -- where
#: the section starts -- which is what :func:`page_num` returns.
PAGE_TOC = r"\d(?:\s?\d){0,3}(?:\s*[-–—]\s*\d(?:\s?\d){0,3})?"


def unspace(token: str) -> str:
    """Drop the glyph-split spaces from a code or page number."""
    return re.sub(r"\s+", "", token or "")


def page_num(token: str) -> int:
    """The page a TOC folio names: the FIRST page of a range ("7-29" -> 7).

    ``int(unspace(...))`` was called at three sites and each would raise on a
    range, so this is the one place a folio becomes an integer.
    """
    return int(unspace(re.split(r"[-–—]", token or "", maxsplit=1)[0]))


def norm_code(token: str) -> str:
    """Canonical code from a TOC cell: ``14.A`` / ``14 A`` / ``221-A`` -> ``14A``.

    Folded to the fused form because ``code_sort_key`` already treats the
    separated and fused spellings as one code, and the same section is printed
    both ways across editions -- keeping them distinct would produce a duplicate
    section and break the monotonic-ordering gate.
    """
    return re.sub(r"[\s.\-]", "", token or "")


CODE_RE = re.compile(rf"^{CODE}$")
_CODE_PARTS_RE = re.compile(r"^(\d{1,3})-?([A-Z]{0,4})$")


def code_sort_key(code: str) -> tuple:
    """Order codes the way the statute does: ``4 < 4A < 4AB < 4B < 5``.

    The hyphen is folded away so ``221-A`` and ``221A`` are one code -- the
    Customs Act prints both forms for the same section across editions, and
    treating them as different codes would produce a duplicate section and break
    the monotonic-ordering gate that section discovery relies on.
    """
    m = _CODE_PARTS_RE.match((code or "").strip().upper())
    if not m:
        return (10 ** 6, code or "")
    return (int(m.group(1)), m.group(2))


# ---------------------------------------------------------------------------
# footnote markers

#: A footnote marker: digits with an optional lowercase letter suffix, or a
#: bare asterisk.  ``5``, ``27a``, ``263``, ``*``.
MARKER = r"(?:\d{1,4}[a-z]?|\*)"
MARKER_RE = re.compile(rf"^{MARKER}$")

#: A marker as printed at the head of a footnote NOTE, where it usually carries
#: a trailing dot: ``25.``, ``27a.``, ``36b.``
MARKER_NOTE_RE = re.compile(rf"^({MARKER})\.?$")

_MARKER_PARTS_RE = re.compile(r"^(\d{1,4})([a-z]?)$")

#: The run of superscript markers that can precede a section heading.
#:
#: The Ordinance allowed exactly one (``r"^\\s*(?:[\\d*]{1,3}\\s+)?"``), because a
#: heading there carries at most one amendment marker.  A section of the Customs
#: Act that has been amended repeatedly stacks all of its markers on the heading:
#:
#:     6,71,76,81[194. Appellate Tribunal.- (1) There shall be established ...
#:     9,81 [194A. Appeals to the Appellate Tribunal.- (1) Any person ...
#:
#: With a single-marker prefix neither line matches the heading forms, so the
#: section's boundary is never indexed and it survives only as a heading-only
#: stub with its entire text dropped -- sections 193-195 lost ~106 words this way.
#: The run must be CLOSED by whitespace or an opening bracket.  Without that
#: the pattern is greedy into the code itself -- "10. Power to approve landing
#: places" parses as marker "1" plus code "0", which silently renumbered a third
#: of the Act's sections and dropped 3,675 body words.
MARKER_PREFIX = (r"(?:[\d*]{1,4}[a-z]?(?:\s*,\s*[\d*]{1,4}[a-z]?)*"
                 r"(?:\s+|(?=\[)))?")


def marker_token(text: str) -> str | None:
    """The bare marker in ``text`` (dot stripped), or None if it is not one."""
    m = MARKER_NOTE_RE.match((text or "").strip())
    return m.group(1) if m else None


def is_marker_text(text: str) -> bool:
    return marker_token(text) is not None


def marker_sort_key(marker: str) -> tuple:
    """Sort markers numerically then by suffix: ``36 < 36a < 36b < 37``.

    Never lexically -- that orders ``10`` before ``9`` and ``36b`` before
    ``36a`` is fine but ``100`` before ``36`` is not, and Sales Tax reaches the
    800s so lexical order would scramble most of the document's footnotes.
    ``*`` sorts before every numbered note, as it is the unnumbered commencement
    note that is always printed first.
    """
    t = (marker or "").strip()
    if t == "*":
        return (-1, "")
    m = _MARKER_PARTS_RE.match(t)
    if not m:
        return (10 ** 6, t)
    return (int(m.group(1)), m.group(2))


def is_year_like(marker: str) -> bool:
    """True if a marker value is really a quoted year (1800-2099).

    The Ordinance rejected every marker >= 100 on this reasoning, which is
    correct there and catastrophic here: Sales Tax numbers its footnotes 1..800+
    globally, so that rule would discard the great majority of them.  Excluding
    only the four-digit year band keeps ``263`` and ``831`` as markers while
    still refusing ``1990`` and ``2025``.

    The band starts at 1800, not 1900: this corpus cites British-India statutes
    constantly, and the Benami Transactions Act 2017 alone rendered ``1860`` (the
    Pakistan Penal Code), ``1882`` (the Transfer of Property Act) and ``1898``
    (the Code of Criminal Procedure) as footnote citations pointing at nothing.
    The highest real marker in the corpus is 1027, so nothing legitimate is inside
    the band.
    """
    m = _MARKER_PARTS_RE.match((marker or "").strip())
    if not m or m.group(2):
        return False
    v = int(m.group(1))
    return 1800 <= v <= 2099


# ---------------------------------------------------------------------------
# structural headings
#
# One source for CHAPTER / PART / Division, so the body-side and TOC-side tests
# cannot drift apart again.  Numerals are Roman with an optional letter suffix
# ("PART IIB", "Division IIA", "CHAPTER XVI-A"), or Arabic where an edition
# numbers chapters that way.

def spaced(word: str) -> str:
    """Keyword pattern tolerating glyph-split spacing inside the word itself.

    These PDFs split words at kerning pairs, and the split lands inside the
    structural keywords: the Customs Act's contents page prints its first
    chapter as ``CHAP TER I`` (and its column header as ``N o.``).  Only that
    one chapter was affected, so CHAPTER_RE matched 15 of 16 chapters and
    sections 1 and 2 came out with no container at all -- which the pipeline
    correctly refuses to write, so the whole edition failed to convert.

    Interleaving ``\\s*`` is safe because these patterns are anchored to a whole
    line: nothing but the keyword can satisfy them.
    """
    return r"\s*".join(word)


#: A structural numeral: Roman with an optional letter suffix that may be fused
#: ("IIB", "XVI-A") or SPACED ("III A").  The spaced form must keep its space so
#: its code stays distinct from the fused one -- both occur, meaning different
#: divisions, and collapsing them merges two divisions into one.
ROMAN = r"[IVXLC]+(?:\s?-?[A-Z]{1,3})?"
NUMERAL = rf"(?:{ROMAN}|\d{{1,3}}[A-Z]{{0,3}})"

#: A chapter row.  Two things beyond the Customs/Ordinance form, both required
#: by Phase-1 editions:
#:
#:   * an inline printed page, as PART/Division rows already allowed -- Sales Tax
#:     runs its chapter rows out to a folio ("Chapter-II ....... 29") and without
#:     it NOT ONE of the ten chapters classified, leaving every section
#:     container-less and the whole edition refusing to convert;
#:   * an inline TITLE after an EN/EM DASH -- Federal Excise prints "Chapter I –
#:     Preliminary 5" where the other acts put the title on the next line.  Only
#:     the long dashes separate a title: a HYPHEN is the numeral's own suffix
#:     separator ("CHAPTER XVI-A"), so admitting it would split that numeral.
CHAPTER_RE = re.compile(
    rf"^\s*{spaced('CHAPTER')}[\s\-]+({NUMERAL})"
    rf"(?:\s*[–—]\s*(?P<title>\S.*?))?"
    rf"(?:\s+{PAGE_TOC})?\s*$",
    re.IGNORECASE)
PART_RE = re.compile(
    rf"^\s*{spaced('PART')}[\s\-]+({NUMERAL})(?:\s+{PAGE_TOC})?\s*$",
    re.IGNORECASE)
DIVISION_RE = re.compile(
    rf"^\s*{spaced('Division')}[\s\-]+({NUMERAL})(?:\s+{PAGE_TOC})?\s*$",
    re.IGNORECASE)
#: A tariff TABLE heading: the Federal Excise Act divides its First and Third
#: Schedules into "Table-I".."Table-III" where the other acts use PARTs, so these
#: are modelled as part-kind nodes (six tree walkers hardcode the child keys
#: ("parts", "divisions", "sections"), so a new Node.kind would be dropped
#: silently).  The numeral is Arabic in places -- the First Schedule's body prints
#: "TABLE 1" against the TOC's "Table-I" -- hence NUMERAL, not ROMAN.
TABLE_RE = re.compile(
    rf"^\s*{spaced('Table')}[\s\-]+({NUMERAL})(?:\s+{PAGE_TOC})?\s*$",
    re.IGNORECASE)
#: An ordinal schedule title ("THE FIRST SCHEDULE", "SECOND SCHEDULE").
SCHEDULE_RE = re.compile(rf"^\s*(THE\s+)?[A-Z]+\s+{spaced('SCHEDULE')}\b",
                         re.IGNORECASE)


def _demo() -> None:
    """Self-check: the cases that broke under the Ordinance grammar."""
    assert CODE_RE.match("3AAA") and CODE_RE.match("3CCE")
    assert CODE_RE.match("221-A") and CODE_RE.match("18C") and CODE_RE.match("2")

    # hyphen folds -- 221-A and 221A are ONE section
    assert code_sort_key("221-A") == code_sort_key("221A") == (221, "A")
    # statutory ordering
    codes = ["5", "4B", "4", "4AB", "4A", "3CCE", "3AAA"]
    assert sorted(codes, key=code_sort_key) == \
        ["3AAA", "3CCE", "4", "4A", "4AB", "4B", "5"], sorted(codes, key=code_sort_key)

    # markers: dotted, letter-suffixed, three-digit, asterisk
    assert marker_token("25.") == "25"
    assert marker_token("27a.") == "27a"
    assert marker_token("831") == "831"
    assert marker_token("*") == "*"
    assert marker_token("Inserted") is None
    assert marker_token("2.5") is None

    # numeric-then-suffix ordering, never lexical
    ms = ["36b", "9", "36", "100", "36a", "10", "*"]
    assert sorted(ms, key=marker_sort_key) == \
        ["*", "9", "10", "36", "36a", "36b", "100"], sorted(ms, key=marker_sort_key)

    # the year band is excluded, the 800s are not
    assert is_year_like("1990") and is_year_like("2025")
    assert not is_year_like("263") and not is_year_like("831")
    assert not is_year_like("99") and not is_year_like("27a")

    # structural headings, incl. the Customs "CHAPTER XVI-A" form
    assert CHAPTER_RE.match("CHAPTER XVI-A") and CHAPTER_RE.match("CHAPTER II")
    assert PART_RE.match("PART IIB") and PART_RE.match("PART I 503")
    assert not CHAPTER_RE.match("CHAPTER II APPOINTMENT OF OFFICERS")

    # the glyph-split keyword that cost the Customs Act sections 1 and 2
    assert CHAPTER_RE.match("CHAP TER I").group(1) == "I"
    assert CHAPTER_RE.match("CHAPTER I").group(1) == "I"

    # fused and spaced division suffixes are DIFFERENT divisions -- the space
    # must survive into the code
    assert DIVISION_RE.match("Division IIA").group(1) == "IIA"
    assert DIVISION_RE.match("Division III A").group(1) == "III A"
    assert SCHEDULE_RE.match("THE FIRST SCHEDULE")

    # Sales Tax chapter rows carry an inline folio; Federal Excise carries the
    # TITLE inline after an en dash.  Neither classified before, and for Sales
    # Tax that left all 113 sections without a container.
    m = CHAPTER_RE.match("Chapter I 7")
    assert m and m.group(1) == "I" and not m.group("title")
    m = CHAPTER_RE.match("Chapter-II 29")
    assert m and m.group(1) == "II"
    m = CHAPTER_RE.match("Chapter-II – Levy, Collection and Payment of duty 12")
    assert m and m.group(1) == "II" \
        and m.group("title") == "Levy, Collection and Payment of duty", m.groups()
    m = CHAPTER_RE.match("Chapter I – Preliminary 5")
    assert m and m.group("title") == "Preliminary"
    # the hyphen stays the numeral's suffix separator, never a title separator
    assert CHAPTER_RE.match("CHAPTER XVI-A").group(1) == "XVI-A"

    # TOC folios printed as page RANGES -- the row must classify and the page is
    # where the section STARTS
    row = re.compile(rf"^\s*(?P<code>{CODE_TOC})\.?\s+(?P<h>.+?)\s+(?P<page>{PAGE_TOC})\s*$")
    m = row.match("2. Definitions 7-29")
    assert m and m.group("h") == "Definitions" and page_num(m.group("page")) == 7
    m = row.match("22 Power to arrest and prosecute 35-39")
    assert m and page_num(m.group("page")) == 35
    assert page_num("10 6") == 106 and page_num("48") == 48

    # Federal Excise tariff tables, Roman and Arabic, body and TOC spellings
    assert TABLE_RE.match("Table-I 72-82").group(1) == "I"
    assert TABLE_RE.match("TABLE 1").group(1) == "1"
    assert TABLE_RE.match("TABLE-II").group(1) == "II"
    assert not TABLE_RE.match("TABLE-I AND TABLE-II))")
    assert not TABLE_RE.match("Table-1 of Sixth Schedule to the Sales Tax Act,")

    # the heading marker-run prefix: it must find the stacked markers but must
    # NOT eat the code's own leading digit
    dot = re.compile(rf"^\s*{MARKER_PREFIX}\[?\s*({CODE})\s*\.")
    # glyph-split TOC code and page
    toc_row = re.compile(rf"^\s*(?P<code>{CODE_TOC})\.?\s+(?P<h>.+?)\s+(?P<page>{PAGE_TOC})\s*$")
    m = toc_row.match("14 2    T emporary detention of baggage.            10 6")
    assert m and unspace(m.group("code")) == "142" and unspace(m.group("page")) == "106"
    m = toc_row.match("141      Bona-fide baggage exempt from duty.        106")
    assert m and unspace(m.group("code")) == "141", m and m.group("code")
    m = toc_row.match("3AAA. Directorate General of China Pakistan Economic Corridor 10")
    assert m and unspace(m.group("code")) == "3AAA"

    for line, want in [
        ("6,71,76,81[194. Appellate Tribunal.-", "194"),
        ("9,81 [194A. Appeals to the Appellate Tribunal.-", "194A"),
        ("1a,25 [3A. Directorate General of Intelligence", "3A"),
        ("2 [ 158.Time of ...", "158"),
        ("10. Power to approve landing places", "10"),      # not marker 1 + code 0
        ("12A. Power to appoint or licence common warehouses", "12A"),
        ("221-A. Validation.-", "221-A"),
    ]:
        m = dot.match(line)
        assert m and m.group(1) == want, (line, m and m.group(1), want)
    print("grammar self-check passed")


if __name__ == "__main__":
    _demo()
