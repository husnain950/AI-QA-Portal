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

#: A rule code: up to FOUR digits, an optional hyphen, up to four uppercase suffix
#: letters.  ``18``, ``18C``, ``3AAA``, ``221-A``, ``150ZQC``, ``1110``.
#:
#: Four digits, not the Acts' three.  The Customs Rules 2001 is a compilation of
#: forty-four separately notified rule sets under one continuous numbering, and it
#: runs past a thousand -- 1010, 1027, 1043, 1065, 1108, 1110 are all real rules in
#: that document.  Read with ``\d{1,3}`` the line ``1110. Application.-`` parses as
#: code ``111`` followed by a stray ``0``, which is the same class of silent
#: renumbering the MARKER_PREFIX docstring below describes costing the Customs Act a
#: third of its sections.
CODE = r"\d{1,4}-?[A-Z]{0,4}"

#: Same, but requiring at least one suffix letter -- used where a bare number
#: would be ambiguous with a list serial.
CODE_SUFFIXED = r"\d{1,4}-?[A-Z]{1,4}"

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
CODE_TOC = r"\d(?:\s?\d){0,3}(?:[-.]\s?[A-Z]{1,4}|[A-Z]{1,4})?"
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

#: The highest rule number this corpus actually reaches, plus headroom. Widening CODE
#: to four digits let a YEAR parse as a rule: the Withholding Rules' title line
#: "SALES TAX SPECIAL PROCEDURE (WITHHOLDING) RULES, 2007" produced a leaf coded 2007
#: ahead of rule 1, and `clause_codes_plausible` reported the opening clauses missing.
#: Customs Rules 2001 tops out at 1110, and no year is below 1800, so the two bands do
#: not overlap -- the same reasoning `is_year_like` already applies to markers and
#: folios.
MAX_CODE_VALUE = 1799


def is_code_like(code: str) -> bool:
    """True when ``code`` is a plausible rule code rather than a year or a quantity."""
    m = _CODE_PARTS_RE.match((code or "").strip().upper())
    return bool(m) and int(m.group(1)) <= MAX_CODE_VALUE
_CODE_PARTS_RE = re.compile(r"^(\d{1,4})-?([A-Z]{0,4})$")


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

#: A footnote marker: digits with an optional LOWERCASE letter suffix, or a
#: bare asterisk.  ``5``, ``27a``, ``263``, ``*``.
#:
#: **The lowercase restriction is load-bearing, and it is not about markers --
#: it is about SECTION CODES.** A code is uppercase (``72A``, ``79A``, ``150S``,
#: ``39O``), and codes are quoted constantly in prose: "by virtue of section 72A
#: of the Sales Tax Act, 1990".  Inside a FOOTNOTE that prose is set at the
#: document's footnote size, which is below ``cal.marker_max_size``
#: (``body_size - 1.5``), so the size gate cannot separate the two: widening this
#: class globally lifted 56 section cross-references in Sales Tax Rules 2006
#: (01-01-2025) alone into ``<sup>``, ``72A`` x30 among them.  Measured
#: 2026-09-14, and it is why ``open-work.md`` said "do not widen MARKER globally".
MARKER = r"(?:\d{1,4}[a-z]?|\*)"
MARKER_RE = re.compile(rf"^{MARKER}$")

#: The same class with an UPPERCASE suffix admitted, for the two positions where
#: a section code cannot be confused with a marker.  Never the default.
#:
#: Customs 1969 (30.06.2025) prints 22 markers with an uppercase suffix --
#: ``59&59A`` x6, ``27/27A`` x3, ``2/2A`` x3, ``59/59A`` x2, ``2A`` x2, and
#: ``66A``, ``66B``, ``30A``, ``36/36A``, ``14/14A``, ``18/18A`` once each -- at
#: **8.04pt** where that document's footnote prose is 9.0pt and its body is 12.0.
#: Their notes print to match (``66A.``, ``66B.``, ``59B.`` at 9.0pt on p77), so
#: the join needs no case-fold.  The two safe positions are:
#:
#:   * INLINE, only when the word is strictly SMALLER than the document's
#:     footnote prose size -- i.e. genuinely raised, not merely small.  That is
#:     the test ``pagemodel.Word.marker_run`` applies, and it is what 9.0pt
#:     footnote prose in the rules lane fails.
#:   * At the head of a footnote NOTE, where the token stands alone at the
#:     block's left margin followed by the note text.  There is no prose there to
#:     confuse it with, so case carries no risk.
_MARKER_UPPER = r"(?:\d{1,4}[A-Za-z]?|\*)"
_MARKER_RE_UPPER = re.compile(rf"^{_MARKER_UPPER}$")

#: A marker as printed at the head of a footnote NOTE, where it usually carries
#: a trailing dot: ``25.``, ``27a.``, ``36b.``, ``66A.``
MARKER_NOTE_RE = re.compile(rf"^({MARKER})\.{{0,2}}$")
#: An uppercase note head must CARRY ITS DOT.  ``marker_token`` treats the dot as
#: optional because a lowercase marker is unambiguous without it, but a bare
#: ``72A`` at the head of a footnote line is far more likely to be a section code
#: opening the note's prose -- admitting it read 56 of them as note heads in Sales
#: Tax Rules 2006 (01-01-2025) and destroyed that document's footnote blocks
#: outright: 0 records where there had been hundreds.  Real note heads print the
#: dot (p77: ``66A.``, ``66B.``, ``59B.``).
_MARKER_NOTE_RE_UPPER = re.compile(rf"^(?:({MARKER})\.{{0,2}}|({_MARKER_UPPER})\.{{1,2}})$")

#: Splits a marker into its number and suffix for sorting.  Carries the WIDER
#: case class on purpose: it only ever sees a marker something already accepted,
#: and if it refused ``66A`` then ``marker_sort_key`` would fall to its
#: ``(10**6, t)`` catch-all and every uppercase-suffixed note would sort to the
#: end of the document instead of beside its numeric sibling -- a silent ordering
#: bug behind a fixed rendering one, and invisible to
#: ``inv_footnotes_in_numeric_order``, which sees order and not the key.
_MARKER_PARTS_RE = re.compile(r"^(\d{1,4})([A-Za-z]?)$")

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
#: The separator between stacked markers is a COMMA in most editions and an
#: AMPERSAND in some: the 30.06.2025 Customs edition prints s.14A's heading as
#: ``5&7[(14A. Provision of security and accommodation at Customs-ports``.  With
#: comma only, the run matched the empty string, the line matched no heading form,
#: and the section survived as a heading-only stub -- the same loss A07 records
#: for the comma form.  ``&`` can neither open nor close a run, so admitting it
#: adds no greedy path: the protection against ``10.`` parsing as marker ``1``
#: plus code ``0`` is the closing ``(?:\s+|(?=\[))``, which is untouched.
#: The run may also end on a DANGLING separator, because the printer drops a
#: marker and leaves its comma behind: the 30.06.2022 Customs edition prints
#: s.194 as ``6,71,76,[194. Appellate Tribunal.-`` -- four markers' worth of
#: punctuation for three markers.  Unconsumed, the trailing comma stops the run
#: from closing and the section became a heading-only stub in five editions.
#: The optional trailing separator cannot weaken the closing guard: on
#: ``10. Power to approve landing places`` there is no separator to consume, so
#: the run still has to close on whitespace or ``[`` and still matches empty.
#: A run may also be separated by nothing but WHITESPACE.  The 2022-2025 Customs
#: editions print s.202B as ``42 53[202B. Reward to officers and officials ...``
#: -- two markers, one space, no comma -- so the run never closed and the section
#: was a heading-only stub in four editions, with its body left inside s.202A.
#:
#: The space is on BOTH sides of the run's tail: the parser's own line text is
#: ``42 53 [202B.`` while the rendered plain_text collapses it to ``42 53[202B.``,
#: which is why a lookahead anchored hard on ``[`` matched the JSON and missed the
#: document.  Measure against the parser's line text, not the rendered output.
#:
#: A bare space is a far weaker separator than ``,`` or ``&``, so this branch is
#: admitted ONLY when the run ends at ``[`` and what follows is unmistakably a
#: section heading: a code, a dot, and a capitalised word.  Measured over 153,736
#: distinct corpus lines that lookahead matches exactly ONE line -- the one above.
#: Without it, allowing whitespace generally gains 18 lines of which 17 are
#: penalty-table rows ("25, 38 1[38A or 40B].") and statistics rows
#: ("1,314,273 1,482,319 12.8").
MARKER_PREFIX = (r"(?:[\d*]{1,4}[a-z]?(?:\s+[\d*]{1,4}[a-z]?)+\s*"
                 rf"(?=\[\s*{CODE}\s*\.\s+[A-Z])"
                 r"|[\d*]{1,4}[a-z]?(?:\s*[,&]\s*[\d*]{1,4}[a-z]?)*"
                 r"(?:\s*[,&])?(?:\s+|(?=\[)))?")


def marker_token(text: str, upper: bool = False) -> str | None:
    """The bare marker in ``text`` (dot stripped), or None if it is not one.

    ``upper`` admits an uppercase suffix.  Pass it only from a position where a
    section code cannot appear -- see ``_MARKER_UPPER``.
    """
    rx = _MARKER_NOTE_RE_UPPER if upper else MARKER_NOTE_RE
    m = rx.match((text or "").strip())
    if not m:
        return None
    return next((g for g in m.groups() if g), None)


#: The separators that fuse several markers into ONE extracted word.  Kept in
#: step with ``builder._MARKER_RUN_SEPS_RE``, which rebuilds them for rendering.
_MARKER_RUN_SEP_RE = re.compile(r"\s*[,&/]\s*")


def marker_run(text: str, upper: bool = False) -> list[str]:
    """Every marker carried by one inline citation token, in printed order.

    ``MARKER_NOTE_RE`` anchors the WHOLE token, so a marker that the text layer
    hands over fused with punctuation is not a marker at all: it renders as
    literal body text, never reaches the ``cited`` list, and therefore builds no
    footnote record.  Four fusion shapes occur, and the 30.06.2025 Customs
    edition prints all four:

        11[        the bracket kerned onto the digits   (s.2, footnote 11)
        7,45[      a comma-separated run                (s.2)
        5&7[       an ampersand-separated run           (s.14A)
        1/2[       a slash-separated run                (s.35)

    Measured over the shipped acts output before this function existed: 420
    comma-fused, 78 ampersand-fused and 80 slash-fused occurrences in 59 distinct
    forms, none of which produced a ``<sup>`` or a note.  ``MARKER_PREFIX`` above
    already understands ``,`` and ``&`` runs, but only to STRIP them so a section
    code can parse -- it never emitted a citation, which is why s.14A parsed as a
    section and still printed ``5&7[`` inside its own heading.

    A trailing dot still disqualifies the token: inline a citation prints bare,
    and sharing the note grammar with the inline one turned every numbered
    heading on a scanned page into a citation (see ``Word.is_marker``).

    Returns ``[]`` for anything that is not a marker run, so the caller's
    behaviour on today's tokens is unchanged.

    The obvious hazard -- splitting a thousands-grouped number (``100,000``) or a
    PCT tariff code (``1005.9000,5[``) on its comma -- is answered by the SIZE
    gate that runs FIRST, in ``Word.marker_run``, and not by any shape test here.
    Both are body-size words.  ``1005.9000,5[`` only looks fused: in the text
    layer it is two words, ``'0101.9000,'`` at 12pt and ``'5'`` at 8pt, so the
    tariff code never reaches this function at all.

    A shape test WAS tried here first and had to be removed: refusing a run whose
    head is shorter than its three-digit tail rejects ``100,000`` but also
    rejects ``35,106``, ``91,118``, ``79,104``, ``8,137`` and ``7&110`` -- five
    genuine runs in the 30.06.2025 Customs edition alone.  No shape separates
    them, because there is no difference in shape; the difference is type size,
    which the caller has already measured.  Verified on that edition after the
    guard came out: no ``<sup>`` in the converted output carries a grouped
    number, and ``50,001 to US $ 100,000`` in s.156 stays plain text.
    """
    t = (text or "").strip()
    if t.endswith("["):
        t = t[:-1].rstrip()
    if not t or t.endswith("."):
        return []
    parts = _MARKER_RUN_SEP_RE.split(t)
    rx = _MARKER_RE_UPPER if upper else MARKER_RE
    if not all(rx.match(p) for p in parts):
        return []
    if any(is_year_like(p) for p in parts):
        return []
    return parts


def is_marker_text(text: str, upper: bool = False) -> bool:
    return marker_token(text, upper) is not None


def marker_sort_key(marker: str) -> tuple:
    """Sort markers numerically then by suffix: ``36 < 36a < 36b < 37``.

    The suffix is compared case-insensitively, so ``66A`` sorts where ``66a``
    would rather than ahead of every lowercase suffix in the document.

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
    # Case-folded: ``59A`` and ``59a`` are the same position, not two.  Raw, the
    # suffix sorts by ASCII and every uppercase suffix lands before every
    # lowercase one, so a document printing both would interleave its notes.
    return (int(m.group(1)), m.group(2).lower())


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
# printed page numbers (folios)

# The Acts print a lone integer in the bottom margin. The Rules print three forms,
# and two of them are not lone integers at all -- measured across the corpus:
#
#   Customs Rules 2001        "226"                        a bare integer
#   Sales Tax Rules 2006      "(104)"                      parenthesised
#   Income Tax Rules 2002     "Income Tax Rules, 2002 9"   a running title, then the folio
#
# Reading only the bare form, Sales Tax Rules derived page offset 16 with 0% support
# -- no evidence for it at all, and wrong: the real offset is 17. Every footnote ref
# is minted as "{printed_page}.{n}", so that ships a plausible, wrong ref on every
# leaf of a 224-page document.
#
# This lives in `grammar` because BOTH `calibrate` (deriving the document's offset)
# and `pagemodel` (reading each page's own folio) must agree on what a folio is, and
# `calibrate` imports `pagemodel`, so it cannot be the shared home.
_FOLIO_PLAIN_RE = re.compile(r"^(\d{1,4})$")
_FOLIO_PAREN_RE = re.compile(r"^\((\d{1,4})\)$")
#: A running title whose last token is the folio, with real words before it. Requiring
#: letters keeps this off a bare "12 34" and off a two-column numeric footer.
_FOLIO_TITLED_RE = re.compile(r"^(?=.*[A-Za-z]{3}).*?\b\(?(\d{1,4})\)?$")


#: A FRONT-MATTER folio: lowercase roman, optionally parenthesised.  Front matter
#: numbers its pages in roman and the body in arabic, which is why ``folio_value``
#: -- whose job is to derive the document's page OFFSET -- reads arabic only and
#: must keep doing so: a roman folio read as a page number would set the offset
#: from a page outside the numbering it is meant to describe.
#:
#: It lives here because two modules need the same answer and disagreed about it.
#: ``calibrate`` has always recognised a roman folio when measuring where the
#: footer band sits; ``pagemodel``'s footer strip read ``_centred_int`` only, so a
#: roman folio was never dropped as furniture.  It survived into ``body_refs``,
#: and everything before the first section's anchor becomes the preamble -- so
#: nine documents shipped a preamble opening on a bare ``xxi`` / ``(xxii)`` /
#: ``vi``, and two Federal Excise editions shipped a preamble that is ONLY that.
#:
#: Strict roman grammar, and lowercase.  ``calibrate``'s own looser test stays as
#: it is, deliberately: it is asking "where is the footer band", where a false
#: positive costs one sample; this one is asking "delete this line", where a
#: false positive deletes text.  A loose ``[ivxlcdm]+`` matches ``mix``, ``i``
#: and an uppercase ``I`` drop cap.
#: Bounded at ccxcix.  ``M`` and ``D`` are excluded, not for elegance but because
#: ``mix`` is a valid roman numeral (MIX = 1009) and is an ordinary English word;
#: no front matter runs to 1,009 pages, and the longest in this corpus is xxii.
_ROMAN_299 = r"(?=[clxvi])c{0,2}(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})"
ROMAN_FOLIO_RE = re.compile(
    rf"^(?:{_ROMAN_299}|\(\s*{_ROMAN_299}\s*\))$")


def folio_value(text: str, profile) -> int | None:
    """The printed page number a margin line carries, in the forms this corpus prints.

    The plain form is always read. The other two are opt-in per corpus, because each
    can capture something that is not a folio: a parenthesised number is also how a
    subsection marker is printed, and a trailing number is also how a running title
    ends.

    The titled form additionally refuses a YEAR. Every one of these documents titles
    itself with its year -- "Sales Tax Rules, 2006", "Federal Excise Rules, 2005" --
    and on a page whose footer is the title alone, the trailing token IS that year.
    Read as a folio it sets the offset from a number in the 2000s. No document in this
    corpus is 1,800 pages long, so nothing real is refused.
    """
    stripped = (text or "").strip()
    plain = _FOLIO_PLAIN_RE.match(stripped)
    if plain:
        return int(plain.group(1))
    if profile.folio_parenthesised:
        paren = _FOLIO_PAREN_RE.match(stripped)
        if paren:
            return int(paren.group(1))
    if profile.folio_running_title:
        titled = _FOLIO_TITLED_RE.match(stripped)
        if titled and not is_year_like(titled.group(1)):
            return int(titled.group(1))
    return None


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
#:   * an EN DASH may separate the keyword from the numeral -- Customs prints
#:     "CHAPTER – VI" where the caption follows on the next line.  Position keeps
#:     that distinct from an inline TITLE after an EN/EM DASH: Federal Excise
#:     prints "Chapter I – Preliminary 5".  A HYPHEN after the numeral remains
#:     the numeral's own suffix separator ("CHAPTER XVI-A").
#:   * an optional leading INSERTION BRACKET.  A chapter added by amendment is
#:     printed "[CHAPTER XIV-A" (and once "[ CHAPTER XV"), the same square
#:     bracket the amendment markers use.  Anchoring hard on the keyword left 15
#:     of the 39 chapters in Sales Tax Rules 2006 01-01-2025 unclassified -- XII,
#:     XIVA, XIV-A, XIV-AA, XIV-AB, XIV-AD, XIV-B, XIV-BA, XIV-BB, XIV-C, XIV-D,
#:     XV, V-A, VIIA and VIII-A -- so their rows fell through to
#:     heading-continuation and glued themselves onto the preceding section's
#:     title, and the sections under them were parented to the wrong chapter.
CHAPTER_RE = re.compile(
    rf"^\s*\[?\s*{spaced('CHAPTER')}[\s\-–]+({NUMERAL})"
    rf"(?:\s*[–—]\s*(?P<title>\S.*?))?"
    rf"(?:\s+{PAGE_TOC})?\s*$",
    re.IGNORECASE)
#: A PART row may print its CAPTION on the same line, which the numeral-only form
#: rejected outright.  Sales Tax Rules 2006 contents:
#:
#:     PART-I RECOVERY ..................................................... 71
#:     PART-II ATTACHMENT AND SALE OF MOVABLE PROPERTY ..................... 73
#:     PART-III ATTACHMENT AND SALE OF IMMOVABLE PROPERTY .................. 78
#:
#: Those rows fell through to the heading-continuation branch, where their
#: ALL-CAPS text satisfies ``is_foreign_caption`` and opened an anonymous CHAPTER
#: for each -- lifting 64 rules out of their real chapter into two top-level
#: containers, which is what put CHAPTER XIV-AB (page 123) after XIV-B (129).
#:
#: Two narrowings, both measured over 212,547 distinct corpus lines:
#:
#: * The caption group is ``(?-i:...)``.  The pattern is IGNORECASE for the
#:   keyword's sake, and without the scoped flag the caption class matches
#:   lowercase too -- "Part 1 of Second China Overseas Ports" and 47 sibling
#:   schedule table rows.
#: * A caption is only accepted when contents LEADERS or a page number follow it.
#:   Without that, ``PART_RE`` matches a running page HEADER: Income Tax Rules
#:   2002 prints "PART-I   SECOND SCHEDULE" at the top of 457 pages, which took
#:   its measured ``part_lines`` from 43 to 595.  A contents row carries leaders
#:   or a folio; a running header carries neither.
#:
#: Together: 13 lines gained, 0 lost, and every gain is a real contents row.
PART_RE = re.compile(
    rf"^\s*{spaced('PART')}[\s\-]+({NUMERAL})"
    rf"(?:\s+(?P<caption>(?-i:[A-Z][A-Z\s,'&\-]{{3,}}?))"
    rf"(?=\s*\.{{2,}}|\s+{PAGE_TOC}\s*$))?"
    rf"(?:\s*\.{{2,}}\s*)?(?:\s+{PAGE_TOC})?\s*$",
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
#: A schedule title as a CONTENTS row: the title and then nothing but leaders and a
#: folio.
#:
#: The unanchored form above is wrong in a table of contents for this corpus, because
#: rule sets cite their parent Act's schedules constantly and the citation wraps. The
#: Sales Tax Special Procedures Rules names its Chapter XIV "SPECIAL PROCEDURE FOR THE
#: GOODS SPECIFIED IN S. NO.13 OF THE FIFTH SCHEDULE TO THE ACT", and its contents
#: wraps that onto a second line reading "THE FIFTH SCHEDULE TO THE ACT……… 45" -- which
#: the unanchored pattern reads as a schedule title. The parser then switched into
#: schedule mode there and everything after it stopped being body: Chapter XIV's
#: heading was truncated mid-sentence, Chapter XV vanished entirely, its two chapter
#: headings ended up inside rule 58T's text, and rules 58U/58V were filed under a
#: schedule that does not exist.
#:
#: ``schedules._SCH_RE`` already anchors the body-side test this way. This is the same
#: rule, applied on the TOC side, where it had never been added.
SCHEDULE_TOC_RE = re.compile(
    rf"^\s*[\[\(\"“]?\s*(THE\s+)?[A-Z]+\s+{spaced('SCHEDULE')}"
    rf"\s*[\]\)\"”]?[\s.·•…\-_]*(?:{PAGE_TOC})?\s*$",
    re.IGNORECASE)


def _demo() -> None:
    """Self-check: the cases that broke under the Ordinance grammar."""
    # round 14: a FRONT-MATTER folio.  pagemodel deletes the line this matches,
    # so a false positive deletes text -- hence strict roman and lowercase.
    for _t in ("vi", "xxi", "(xxii)", "(xvii)", "i", "(iv)"):
        assert ROMAN_FOLIO_RE.match(_t), _t
    # ...and what a loose [ivxlcdm]+ would have eaten.  `calibrate`'s own test IS
    # that loose form and stays so: it asks where the footer band is, where a
    # false positive costs one sample, not a line of text.
    for _t in ("mix", "civil", "dill", "mid", "lid", "did", "I", "XXI", "Vi",
               "vi.", "vi 3", "vii)"):
        assert not ROMAN_FOLIO_RE.match(_t), _t

    assert CODE_RE.match("3AAA") and CODE_RE.match("3CCE")
    assert CODE_RE.match("221-A") and CODE_RE.match("18C") and CODE_RE.match("2")

    # Rules: four-digit codes, measured in Customs Rules 2001 (Updated 30.06.2023)
    for code in ("1010", "1027", "1043", "1065", "1108", "1110"):
        assert CODE_RE.match(code), code
    assert not CODE_RE.match("11101")            # five digits is not a rule code
    # a YEAR is not a rule code, though it is four digits
    assert is_code_like("1110") and is_code_like("1") and is_code_like("150ZQC")
    assert not is_code_like("2007") and not is_code_like("1990") and not is_code_like("2025")
    # Sales Tax Rules 2006 stacks three suffix letters on a three-digit code
    for code in ("150ZQC", "150ZEK", "150ZER", "150ZEQ"):
        assert CODE_RE.match(code), code
    # ordering must stay numeric across the thousand boundary
    assert sorted(["1000", "999", "1010A", "1010"], key=code_sort_key) == \
        ["999", "1000", "1010", "1010A"]
    # a four-digit code parses whole, not as three digits plus a stray
    dot4 = re.compile(rf"^\s*{MARKER_PREFIX}\[?\s*({CODE})\s*\.")
    for line, want in [("1110. Application.-", "1110"),
                       ("150ZQC. Requirements to be met.", "150ZQC"),
                       ("13ZH. General provisions", "13ZH")]:
        m = dot4.match(line)
        assert m and m.group(1) == want, (line, m and m.group(1), want)

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

    # marker_run: the four fusion shapes the text layer produces
    assert marker_run("12") == ["12"]
    assert marker_run("27a") == ["27a"]
    assert marker_run("*") == ["*"]
    assert marker_run("11[") == ["11"]
    assert marker_run("7,45[") == ["7", "45"]
    assert marker_run("1a,25[") == ["1a", "25"]
    assert marker_run("5&7[") == ["5", "7"]
    assert marker_run("5&7") == ["5", "7"]
    assert marker_run("1/2[") == ["1", "2"]
    assert marker_run("12/13") == ["12", "13"]
    assert marker_run("7&110[") == ["7", "110"]
    assert marker_run("120,122,129,130,133,135") == [
        "120", "122", "129", "130", "133", "135"]
    # and what the token grammar must refuse
    assert marker_run("14.") == []          # a numbered heading, not a citation
    assert marker_run("1962") == []         # a year
    assert marker_run("0101.9000,") == []   # a PCT tariff code -- the dot
    assert marker_run("Inserted") == []
    assert marker_run("") == []
    assert marker_run("[") == []
    # A grouped number IS run-shaped.  Only the caller's size gate separates
    # them, which is why this function must not try: see the docstring.
    assert marker_run("100,000") == ["100", "000"]

    # numeric-then-suffix ordering, never lexical
    ms = ["36b", "9", "36", "100", "36a", "10", "*"]
    assert sorted(ms, key=marker_sort_key) == \
        ["*", "9", "10", "36", "36a", "36b", "100"], sorted(ms, key=marker_sort_key)

    # the year band is excluded, the 800s are not
    assert is_year_like("1990") and is_year_like("2025")
    assert not is_year_like("263") and not is_year_like("831")
    assert not is_year_like("99") and not is_year_like("27a")

    # structural headings, incl. the Customs "CHAPTER XVI-A" suffix and
    # "CHAPTER – VI" en-dash separator forms
    assert CHAPTER_RE.match("CHAPTER XVI-A") and CHAPTER_RE.match("CHAPTER II")
    m = CHAPTER_RE.match("CHAPTER – VI")
    assert m and m.group(1) == "VI" and not m.group("title")
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

    # A contents row naming a schedule, versus a wrapped CITATION of the parent Act's
    # schedule. Rule sets cite those constantly; reading one as a title truncates the
    # body at that point.
    assert SCHEDULE_TOC_RE.match("THE FIRST SCHEDULE")
    assert SCHEDULE_TOC_RE.match("SECOND SCHEDULE ......... 45")
    assert SCHEDULE_TOC_RE.match("THE FIFTH SCHEDULE 45")
    assert not SCHEDULE_TOC_RE.match("THE FIFTH SCHEDULE TO THE ACT……………… 45")
    assert not SCHEDULE_TOC_RE.match("SPECIAL PROCEDURE FOR GOODS IN THE FIFTH SCHEDULE TO THE ACT")
    assert not SCHEDULE_TOC_RE.match("of the Fifth Schedule to the Act;")

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
    # the "[(" insertion pair and the "&" marker separator, on the shape the
    # builder actually uses (_HEAD + _OPEN + CODE + dot)
    ins = re.compile(rf"^\s*{MARKER_PREFIX}(?:\[\s*\(\s*|\[?\s*)({CODE})\s*\.")
    for line, want in [
        ("5[(14-A. Provision of accommodation", "14-A"),
        ("5&7[(14A. Provision of security", "14A"),
        ("24[(21A. Power to defer collection", "21A"),
        # a DANGLING separator: three markers, four commas' worth of punctuation
        ("6,71,76,[194. Appellate Tribunal.-", "194"),
        ("10. Power to approve landing places", "10"),
        ("6,71,76,81[194. Appellate Tribunal.-", "194"),
    ]:
        m = ins.match(line)
        assert m and m.group(1) == want, (line, m and m.group(1), want)
    # the paren is admitted ONLY inside the bracket: a bare "(" reads a PCT
    # tariff heading as a section, and an inserted SUBSECTION as one
    for line in ("(90.22).",
                 "2 [ (5) The Federal Government may, by notification",
                 "16&39[(1) Subject to sub-section (2), in cases"):
        assert not ins.match(line), line

    # norm_code is what makes the body and the TOC agree on ONE code
    assert norm_code("155-I") == norm_code("155 I") == norm_code("155.I") == "155I"
    assert norm_code("38-") == "38"          # Federal Excise prints s.38 as "38-"
    assert norm_code("25 AA") == "25AA" and norm_code("18.A") == "18A"
    # ...and never merges two genuinely different sections
    assert norm_code("221") == "221" != norm_code("221-A")

    # --- marker suffix case, and the gate that makes it safe ---------------
    # DEFAULT IS LOWERCASE-ONLY, because a section code is uppercase and gets
    # quoted in footnote prose at exactly footnote size.
    for _t in ("66A", "72A", "150S", "39O"):
        assert marker_run(_t) == [], _t
        assert marker_token(_t) is None, _t
    # ...admitted only where a section code cannot appear.  The 22 from Customs
    # 1969 (30.06.2025), every literal copied from the page.
    for _t in ("66A", "66B", "30A", "2A", "59A", "14A", "18A", "27A"):
        assert marker_run(_t, upper=True) == [_t], _t
    for _run, _want in (("59&59A", ["59", "59A"]), ("59/59A", ["59", "59A"]),
                        ("27/27A", ["27", "27A"]), ("2/2A", ["2", "2A"]),
                        ("36/36A", ["36", "36A"]), ("14/14A", ["14", "14A"]),
                        ("18/18A", ["18", "18A"])):
        assert marker_run(_run, upper=True) == _want, (_run, marker_run(_run, True))
    # The note heads they bind to, p77's consolidated block.  Uppercase there
    # too, which is why the join needs no case-fold.
    for _t, _want in (("66A.", "66A"), ("66B.", "66B"), ("59B.", "59B"),
                      ("55A.", "55A")):
        assert marker_token(_t, upper=True) == _want, _t
    # ...but a BARE uppercase token is not a note head.  Without the dot this
    # read 56 section codes as note heads in one rules document and collapsed its
    # footnote blocks to nothing.
    for _t in ("72A", "150S", "39O", "164A"):
        assert marker_token(_t, upper=True) is None, _t
    # The lowercase side keeps its optional dot, both ways.
    assert marker_token("27a", upper=True) == "27a"
    assert marker_token("25", upper=True) == "25"
    # The lowercase side must not have moved, with or without the flag.
    for _u in (False, True):
        assert marker_run("1a,25[", upper=_u) == ["1a", "25"], _u
        assert marker_token("27a.", upper=_u) == "27a", _u
        assert marker_run("2018", upper=_u) == [], _u
    # Sorting: an uppercase suffix sorts where its lowercase twin would, not
    # ahead of every lowercase suffix, and not at the 10**6 catch-all a narrower
    # _MARKER_PARTS_RE would have sent it to.
    assert marker_sort_key("66A") == (66, "a")
    assert sorted(["66B", "66", "67", "66A", "*"], key=marker_sort_key) == \
        ["*", "66", "66A", "66B", "67"]
    assert not is_year_like("66A")

    # --- note heads printed with a DOUBLE dot -----------------------------
    # The Customs Act source prints a few of its note heads with two dots where
    # 732 print one.  Every literal below is copied from the 30.06.2025 edition,
    # found by scanning the FIRST WORD of every line of all 279 pages:
    #
    #     p75  40..   Amended by the Finance Act, 2006.
    #     p77  59A..  Omitted the words "bill of entry or" by the Finance Act, 2006.
    #     p127 5..    By the Finance Act, 2006, the words "bill of export or" ...
    #     p245 1b..   Substituted for the words "Central Government" ...
    #     p274 26..   Inserted section 211A by the Finance Act, 2006.
    #     p275 39..   Added by the Finance Act, 1975 (L of 1975), S.7(7), page 10.
    #
    # Read with one dot each of these opened no note, and ``parse_footnotes``
    # folded its line into the PREVIOUS note's body (footnotes.py:1242) -- so the
    # real note had no record and its neighbour carried text that was never its
    # own.  ``59A`` alone left 8 citations rendering <sup class="marker">.
    #
    # BOTH classes widen together, the round-35 lesson: ``59A..`` is on the
    # uppercase branch and ``40..`` on the lowercase one, and ``_is_marker_word``
    # and the note-head key read the SAME word (footnotes.py:1229-1233).
    for _t, _want in (("40..", "40"), ("5..", "5"), ("26..", "26"),
                      ("39..", "39"), ("1b..", "1b")):
        assert marker_token(_t) == _want, _t
        # the note-head path always passes upper=True, so the wider branch has
        # to admit everything the narrow one does or the key and the candidate
        # test disagree and the citation never finds the note
        assert marker_token(_t, upper=True) == _want, _t
        assert is_marker_text(_t, upper=True), _t
    assert marker_token("59A..", upper=True) == "59A"
    # ...and the uppercase branch keeps its MANDATORY dot.  ``\.{1,2}``, never
    # ``\.{0,2}``: a bare 72A read as a note head collapsed one rules document's
    # footnote blocks from hundreds to zero.
    assert marker_token("59A..") is None
    for _t in ("72A", "150S", "39O", "164A"):
        assert marker_token(_t, upper=True) is None, _t
    # Exactly two.  Three dots is not a note head in this corpus and nothing asks
    # for it, so the bound stays where the evidence is.
    for _t in ("40...", "59A...", "..", "."):
        assert marker_token(_t) is None, _t
        assert marker_token(_t, upper=True) is None, _t
    # The INLINE side is untouched, and structurally so: ``Word.marker_run``
    # refuses any trailing dot before this grammar is consulted
    # (pagemodel.py:185).  A wider note-head dot class cannot lift body text.
    for _t in ("40..", "59A..", "5.."):
        assert marker_run(_t) == [] and marker_run(_t, upper=True) == [], _t

    print("grammar self-check passed")


if __name__ == "__main__":
    _demo()
