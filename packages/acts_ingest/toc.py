"""Table-of-Contents parser.

The FBR ordinance PDFs open with a Table of Contents (TOC) that lists the full
hierarchy of the document:

    CHAPTER  ->  PART  ->  DIVISION  ->  SECTION

Every *section* row carries a printed page number.  Because the printed page
numbers are offset from the physical PDF page numbers by a constant (the TOC
pages themselves), we can turn a printed page number into a PDF page index by
adding ``page_offset`` (see :mod:`acts_ingest.pipeline`).

This module is deliberately conservative: it only classifies a line as a
section row when it starts with a section *code* (e.g. ``12``, ``15A``,
``175AA``) and ends with a page number.  Everything else that looks like a
heading (all-caps lines, ``PART II``, ``Division IV`` ...) becomes a structural
node.  The result is an ordered tree plus a flat, ordered list of section
codes that the body splitter uses to find section boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .grammar import (  # noqa: F401
    CHAPTER_RE,
    CODE,
    CODE_TOC,
    DIVISION_RE,
    PAGE_TOC,
    PART_RE,
    SCHEDULE_RE,
    TABLE_RE,
    code_sort_key,
    norm_code,
    page_num,
    spaced,
    unspace,
)

# em dash / en dash / hyphen -- same set as builder.HEAD_SPLIT_RE
_DASHES = "—–-"
# Same idiom as builder._find_heading_split: operative body glued after ".-".
_TOC_BODY_AFTER_DASH_RE = re.compile(
    rf"[.,]\s*[{re.escape(_DASHES)}]\s+(?=[A-Za-z(])"
)


# ---- line classification regexes -------------------------------------------

# DOT LEADERS.  Customs and the Ordinance set their contents in whitespace
# columns; Sales Tax runs a leader to the folio on EVERY row, chapter rows
# included:
#
#     Chapter-II ..................................................... ……....29
#     2.   Definitions……………………………………………………          ..7-29
#     erronously refunded............... ........................... …..… .48
#
# The leader run sits exactly where every pattern here expects plain spaces, so
# not one row classified: all ten chapters were lost (leaving 113 sections with
# no container, which the pipeline correctly refuses to emit) and the rows that
# did match glued their neighbours' titles together.  Collapsing each run to a
# single space before classification makes one line shape serve all three
# families, which is why it is done here rather than per-pattern.
#
# A run needs TWO leader glyphs: a single dot is the row code's own "2." or an
# abbreviation ("S.R.O."), and collapsing those would destroy the code.  The run
# may mix ASCII dots, the ellipsis glyph and the spaces between them, because
# these PDFs typeset the leader as a mixture of all three.
#: A dot-leader run: starts and ends with a leader glyph, spaces allowed inside.
#: Written with ONE quantifier over the interior.  The earlier form,
#: ``[.…](?:[\s.…]*[.…])+``, describes exactly the same strings but nests a
#: quantifier inside a quantifier, so when the overall match FAILS the engine
#: retries every way of partitioning the run -- catastrophic backtracking, and
#: the cause of ledger P07: four Sales Tax conversions that ran for 25 hours and
#: were recorded as "hangs" for three sessions.  Measured on the failing form:
#: 24 dots took 1.2s and every further 2 dots cost 4x, while the real trigger is
#: Sales Tax's ``Chapter I....(89 dots, no folio)`` row, i.e. 4**32 times that.
#: Those conversions were never going to finish.  Keep this shape linear.
_LEADERS_RE = re.compile(r"[.…][\s.…]*[.…]")
# ... and the folio the leaders point at.  Where the parser reads a line as free
# HEADING text (a chapter's own title row) there is no page group to consume the
# folio, and it was joined into the heading -- "PRELIMINARY 7", "REGISTRATION
# 54".  Recognising the leader is what makes the trailing number provably a
# folio and not part of the title.
# Same linear shape as _LEADERS_RE, and this is the one that actually spun: it
# requires a folio AFTER the leaders, so on the many heading rows that end in
# leaders with NO page number the match fails and the nested form backtracked
# forever.  _LEADERS_RE alone never blew up because nothing follows it to force
# a retry -- which is why the defect hid in the *stricter* of the two patterns.
_LEADER_FOLIO_RE = re.compile(r"[.…][\s.…]*[.…]\s*"
                              rf"{PAGE_TOC}\s*$")
_FOLIO_TAIL_RE = re.compile(rf"\s+{PAGE_TOC}\s*$")

# The bare "SCHEDULES" divider Sales Tax prints between its last section row and
# its schedule rows.  It is a caption, not text: read as a wrapped heading
# continuation it was appended to section 77's title ("Uniform SCHEDULES 137").
_SCHEDULES_CAPTION_RE = re.compile(r"^\s*SCHEDULES\s*(?:\d{1,4})?\s*$",
                                   re.IGNORECASE)

# A section row:  "12.   Salary                                   48"
#                 "175AA. Exchange of banking ...                 364"
#                 "29A    Provision regarding consumer loans      82"   (no dot)
#                 "(10). Refund of input tax......................24"  (paren code)
# Optional parentheses: Sales Tax 2009 TOC prints "(10)." for section 10; without
# them the row never classified, section 10 vanished, and its body was absorbed
# into section 9 as a bold ``<li>(10) Refund...`` (inv_no_bold_body_subsection_marker).
SECTION_RE = re.compile(
    rf"^\s*\(?(?P<code>{CODE_TOC})\)?\.?\s+(?P<heading>.+?)\s+(?P<page>{PAGE_TOC})\s*$"
)

# A continuation line for a wrapped heading (indented, no code, no page number).
CONT_RE = re.compile(r"^\s{4,}(?P<text>\S.*?)\s*$")

# A code-led row whose printed page is NOT on this line: the title wrapped, so
# the page sits on the continuation line below it.
#
#     10.  Power to approve landing places and specify limits of
#          customs-stations.                       12
#
# Without this the code line is read as a continuation of the PREVIOUS row and
# glued onto its heading, and the section it opens is never created at all --
# sections 10 and 14A vanished from every edition before 2012 this way.  The
# title must open with a letter or quote so a stray numeric fragment ("1996).")
# cannot masquerade as a section row.
SECTION_NOPAGE_RE = re.compile(
    rf"^\s*\(?(?P<code>{CODE_TOC})\)?\.?\s+(?P<heading>[A-Za-z\"“\[][^\n]*?)\s*$")
# a continuation line that ENDS in the page number, completing the row above
CONT_PAGE_RE = re.compile(rf"^\s+(?P<text>\S.*?)\s+(?P<page>{PAGE_TOC})\s*$")

# CHAPTER / PART / Division / SCHEDULE all come from grammar.py -- the body-side
# copies in builder/pagemodel/schedules had already drifted from these
# (schedules.py accepted only [IVXL] where this accepted [IVXLC0-9]), so the
# same heading classified differently depending on which module asked.

# The TOC's column headers ("SECTIONS", "PAGE", "NO.") are printed once, at the
# top of the first TOC page.  Depending on the edition's layout they extract
# either as standalone lines ("SECTIONS PAGE NO.") or merged onto the first
# chapter/heading row ("CHAPTER 1              PAGE", "PRELIMINARY  NO.") --
# the 30.06.2024 edition does the latter, which used to defeat CHAPTER_RE and
# silently drop CHAPTER I with sections 1-3.  They never appear again after
# the first section row, so the sanitizer deactivates there.
# Glyph-split spelling is tolerated in each token: these PDFs break words at
# kerning pairs, and the TOC column header extracts as "Section Page N o".  With
# a literal "NO\.?" the tail no longer matched, so the header was left in place
# and glued onto the first chapter's title ("PRELIMINARY Section Page N o") and
# became the entire heading of CHAPTER XVI-A.
# "Description" is the Federal Excise column label ("Section Description Page",
# reprinted at the top of all three of its TOC pages).
_HDR_TOKEN = (rf"(?:{spaced('SECTION')}S?|{spaced('PAGE')}|{spaced('NO')}\.?"
              rf"|{spaced('DESCRIPTION')})")
# Case-insensitive: the Ordinance sets these labels in caps ("SECTIONS PAGE
# NO."), the Customs Act in title case ("Section Page N o"), and an
# uppercase-only pattern silently passes the latter through as heading text.
TOC_HEADER_LINE_RE = re.compile(rf"^\s*{_HDR_TOKEN}(?:\s+{_HDR_TOKEN})*\s*$",
                                re.IGNORECASE)
TOC_HEADER_TAIL_RE = re.compile(rf"(?:\s+{_HDR_TOKEN})+\s*$", re.IGNORECASE)
# A part row may carry its printed page inline ("Part IIB 503" -- First
# Schedule) exactly like the division rows below; without the optional page
# group it fails to classify and its text (and the following part's title) get
# glued into the PREVIOUS part's heading, and the inline-page part is dropped.

# A division row may carry its printed page inline ("Division I 533" -- First
# Schedule Part IV's TOC block) instead of on the following line.  Without the
# optional page group those rows fail to classify and get glued into the
# enclosing PART's heading as plain continuation text.
#
# The letter suffix may be printed FUSED ("Division IIIA") or SPACED
# ("Division III A" -- First Schedule Part III's omitted sub-divisions); both
# must classify, and the spaced form must keep its space so its code stays
# distinct from the fused "Division IIIA" of Part I.  Allowing only an adjacent
# letter dropped the spaced form onto the previous division as heading text.




@dataclass
class Node:
    """A structural node in the TOC tree (chapter/part/division/schedule)."""

    kind: str            # 'chapter' | 'part' | 'division' | 'schedule'
    code: str            # e.g. 'CHAPTER 1', 'PART I', 'Division IV'
    heading: str = ""    # the title line(s) beneath the code
    parts: list = field(default_factory=list)
    divisions: list = field(default_factory=list)
    sections: list = field(default_factory=list)


@dataclass
class SectionEntry:
    code: str
    heading: str
    printed_page: int
    parent: object = None   # the Node this section attaches to
    # exact body anchor (a builder.LineRef) set by body-driven discovery for
    # TOC-less editions; None for TOC-parsed entries, which build_sections
    # locates by printed-page proximity instead
    anchor: object = None


_ROMAN_PAIRS = ((50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
                (5, "V"), (4, "IV"), (1, "I"))


def _arabic_to_roman(num: int) -> str:
    out = []
    for val, sym in _ROMAN_PAIRS:
        while num >= val:
            out.append(sym)
            num -= val
    return "".join(out)


def _chapter_numeral(raw: str) -> str:
    """Chapter numeral, normalised to Roman.

    The ordinance numbers chapters in Roman throughout the body and in every
    TOC row but the first, which prints "CHAPTER 1" -- normalise so the first
    chapter's code matches its siblings and the authoritative body text.
    """
    raw = raw.upper()
    return _arabic_to_roman(int(raw)) if raw.isdigit() else raw


def _truncate_heading_body_bleed(text: str) -> str:
    """Drop operative body text glued onto a TOC heading after a statutory dash.

    The body builder splits at ``.-`` / ``.—``; the TOC parser used to keep the
    whole span, so a row like ``12. Power to appoint public warehouse.- At any
    warehousing station... 45`` stored the opening body as the heading.
    """
    m = _TOC_BODY_AFTER_DASH_RE.search(text)
    if m is None:
        return text
    return text[: m.start()].rstrip(" .,;:")


def _clean_heading(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = _truncate_heading_body_bleed(text)
    # keep a TRAILING hyphen: it marks a hyphenated compound broken across a TOC
    # line ("...of a Non-" + "resident Person" -> "Non-resident Person").  Only
    # leading dashes and trailing dots/em-dashes are decorative.
    return text.lstrip(" .-—").rstrip(" .—")


def _shared_prefix_words(a: str, b: str) -> int:
    aw, bw = a.split(), b.split()
    n = 0
    while n < len(aw) and n < len(bw) and aw[n].lower() == bw[n].lower():
        n += 1
    return n


def _is_legitimate_duplicate_pair(a: SectionEntry, b: SectionEntry) -> bool:
    """True when two same-code rows are both real (omitted + re-inserted)."""
    ha = (a.heading or "").strip().lower()
    hb = (b.heading or "").strip().lower()
    if any(token in ha or token in hb for token in ("omitted", "***", "repealed")):
        return True
    # Distinct titles with little shared prefix -> re-insertion under old number
    if ha and hb and _shared_prefix_words(ha, hb) < 3:
        return True
    return False


def _dedupe_toc_sections(sections: list[SectionEntry]) -> list[SectionEntry]:
    """Drop phantom duplicate-code rows superseded by a cleaner sibling."""
    if len(sections) < 2:
        return sections

    by_code: dict[str, list[SectionEntry]] = {}
    for entry in sections:
        by_code.setdefault(entry.code, []).append(entry)

    order = {id(entry): index for index, entry in enumerate(sections)}
    drop: set[int] = set()
    for entries in by_code.values():
        if len(entries) < 2:
            continue
        if any(
            _is_legitimate_duplicate_pair(a, b)
            for i, a in enumerate(entries)
            for b in entries[i + 1 :]
        ):
            continue
        # Same title family: keep the first row in TOC order (the real entry).
        first = min(entries, key=lambda entry: order[id(entry)])
        for entry in entries:
            if entry is not first:
                drop.add(id(entry))

    return [entry for entry in sections if id(entry) not in drop]


def _join_heading(prev: str, cont: str) -> str:
    """Join a wrapped heading fragment onto the previous text.

    A previous fragment ending in "-" is a hyphenated compound split across the
    line break, so join directly ("Non-" + "resident" -> "Non-resident");
    otherwise separate with a space.
    """
    if not prev:
        return cont
    if prev.endswith("-"):
        return (prev + cont).strip()
    return (prev + " " + cont).strip()


def _merge_parallel_titles(a: str, b: str):
    """Merge two TOC title lines that are parallel halves of ONE division heading.

    The TOC sometimes splits a heading into halves sharing a leading phrase
    ("Rates of Tax for Individuals" + "Rates of Tax for Association of Persons"
    -> "Rates of Tax for Individuals and Association of Persons").  Merge on a
    shared word-prefix of length >= 2.  Returns ``None`` when the two lines are
    NOT parallel halves (too little shared prefix, or one contains the other),
    so the caller can treat them as distinct entries instead.
    """
    aw, bw = a.split(), b.split()
    n = 0
    while n < len(aw) and n < len(bw) and aw[n] == bw[n]:
        n += 1
    if n < 2 or n >= len(aw) or n >= len(bw):
        return None
    prefix = " ".join(aw[:n])
    return f"{prefix} {' '.join(aw[n:])} and {' '.join(bw[n:])}"


_YEAR_TAIL_RE = re.compile(r"(?:19|20)\d\d")


def _completes_heading_year(heading: str, extra: str) -> bool:
    """True when a digit-only continuation line completes a wrapped date.

    A wrapped section row ends its *printed* line with the page number (which
    SECTION_RE consumes), so the overflow line carries the rest of the heading.
    When that overflow is a bare four-digit year and the heading so far ends on
    an incomplete clause -- a trailing comma, e.g. "...dated 30th June," (236U,
    236X) -- the year belongs to the heading and must be joined.  A stray page
    number never follows a comma-terminated heading, so this never reabsorbs a
    page number as heading text.
    """
    return (heading.rstrip().endswith(",")
            and _YEAR_TAIL_RE.fullmatch(extra) is not None)


def parse_toc(lines: list[str]):
    """Parse TOC text lines into (chapters, schedules, ordered_sections)."""
    chapters: list[Node] = []
    schedules: list[Node] = []
    ordered_sections: list[SectionEntry] = []

    cur_chapter: Optional[Node] = None
    cur_part: Optional[Node] = None
    cur_division: Optional[Node] = None
    cur_schedule: Optional[Node] = None
    in_schedules = False

    pending_heading_for: Optional[Node] = None
    last_section: Optional[SectionEntry] = None
    pending_page: Optional[SectionEntry] = None
    # True once a TOC page-number line follows a division's first title: the next
    # title line begins a NEW entry rather than wrapping the current heading.  At
    # that title we decide, by the shared leading phrase, whether the two lines
    # are parallel halves of ONE heading ("Rates of Tax for Individuals" + "Rates
    # of Tax for Association of Persons" -> merge) or a genuine second same-code
    # division (-> sibling).  (Printed page numbers around these rows are noisy
    # in some editions, so the decision cannot rely on them.)
    pending_boundary = False

    def container_for_section():
        if cur_division is not None:
            return cur_division
        if cur_part is not None:
            return cur_part
        if cur_chapter is not None:
            return cur_chapter
        return None

    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip():
            continue

        # ---- dot leaders --------------------------------------------------
        # Collapse the leader run to a space BEFORE any classification (see
        # _LEADERS_RE), remembering whether the line ended in "leaders + folio"
        # so a heading row can drop that folio later.
        leadered = bool(_LEADER_FOLIO_RE.search(line))
        line = _LEADERS_RE.sub(" ", line)

        if _SCHEDULES_CAPTION_RE.match(line):
            continue

        # ---- column-header noise ------------------------------------------
        # Active for the WHOLE table of contents, not just before the first
        # section row.  The Ordinance prints its column header once, so
        # deactivating early was safe there; the Customs Act reprints
        # "Section Page No." at the top of all 20 of its TOC pages, and every
        # reprint after the first was taken as heading text -- it became the
        # entire heading of CHAPTER XVI-A and the tail of CHAPTER I's.
        # A whole line of nothing but column labels is never legal text, and a
        # heading never ends in them, so this is safe to leave on.
        if TOC_HEADER_LINE_RE.match(line):
            continue
        if not SECTION_RE.match(line):
            line = TOC_HEADER_TAIL_RE.sub("", line)

        # ---- schedule marker (switches us into schedule mode) -------------
        if SCHEDULE_RE.match(line) and not SECTION_RE.match(line):
            in_schedules = True
            code = re.sub(r"\s+", " ", line.strip())
            node = Node(kind="schedule", code=code)
            schedules.append(node)
            cur_schedule, cur_part, cur_division = node, None, None
            pending_heading_for = node
            last_section = None
            continue

        # ---- chapter ------------------------------------------------------
        m = CHAPTER_RE.match(line)
        if m and not in_schedules:
            node = Node(kind="chapter", code="CHAPTER " + _chapter_numeral(m.group(1)))
            chapters.append(node)
            cur_chapter, cur_part, cur_division = node, None, None
            # Federal Excise prints the title ON the chapter row ("Chapter-II –
            # Levy, Collection and Payment of duty 12"); the other acts put it on
            # the line below.  With the title already in hand nothing is pending,
            # so the next line cannot be absorbed into this heading.
            title = m.group("title")
            if title:
                node.heading = _clean_heading(title)
                pending_heading_for = None
            else:
                pending_heading_for = node
            last_section = None
            continue

        # ---- table (a Federal Excise schedule's Table-I / Table-II) --------
        m = TABLE_RE.match(line) if in_schedules else None
        if m:
            node = Node(kind="part", code="Table-" + m.group(1).upper())
            parent = cur_schedule
            if parent is not None:
                parent.parts.append(node)
            cur_part, cur_division = node, None
            pending_heading_for = node
            last_section = None
            continue

        # ---- part ---------------------------------------------------------
        m = PART_RE.match(line)
        if m:
            node = Node(kind="part", code="PART " + m.group(1).upper())
            parent = cur_schedule if in_schedules else cur_chapter
            if parent is not None:
                parent.parts.append(node)
            cur_part, cur_division = node, None
            pending_heading_for = node
            last_section = None
            continue

        # ---- division -----------------------------------------------------
        m = DIVISION_RE.match(line)
        if m:
            code = "Division " + re.sub(r"\s+", " ", m.group(1).strip())
            # A TOC that repeats the SAME division code CONSECUTIVELY within a
            # part is duplicated in the source (e.g. First Schedule Part IV lists
            # "Division XXVII" three times: active / "Omitted" / active again).
            # Keep the first and ignore the repeats -- their title lines must not
            # fabricate phantom same-code sibling leaves.
            if (cur_division is not None
                    and cur_division.code.upper() == code.upper()):
                pending_heading_for = None
                pending_boundary = False
                continue
            node = Node(kind="division", code=code)
            parent = cur_part if cur_part is not None else (
                cur_schedule if in_schedules else cur_chapter)
            if parent is not None:
                parent.divisions.append(node)
            cur_division = node
            pending_heading_for = node
            last_section = None
            pending_boundary = False
            continue

        # ---- section row --------------------------------------------------
        m = SECTION_RE.match(line)
        if m and not in_schedules:
            code = norm_code(m.group("code"))
            heading = _clean_heading(m.group("heading"))
            page = page_num(m.group("page"))
            entry = SectionEntry(code=code, heading=heading,
                                 printed_page=page, parent=container_for_section())
            ordered_sections.append(entry)
            last_section = entry
            pending_heading_for = None
            continue

        # ---- a continuation line completing a page-less section row -------
        if pending_page is not None:
            cp = CONT_PAGE_RE.match(line)
            if cp and not SECTION_NOPAGE_RE.match(line):
                extra = _clean_heading(cp.group("text"))
                if extra:
                    pending_page.heading = _join_heading(pending_page.heading, extra)
                pending_page.printed_page = page_num(cp.group("page"))
                last_section = pending_page
                pending_page = None
                continue

        # ---- a code-led section row with no page number on its line -------
        nm = SECTION_NOPAGE_RE.match(line) if not in_schedules else None
        if nm:
            code = norm_code(nm.group("code"))
            prev = last_section.code if last_section is not None else None
            # only when it continues the sequence -- otherwise an indented
            # numeric fragment inside a wrapped title would open a phantom
            # section
            if prev is None or code_sort_key(code) > code_sort_key(prev):
                entry = SectionEntry(code=code,
                                     heading=_clean_heading(nm.group("heading")),
                                     printed_page=0,
                                     parent=container_for_section())
                ordered_sections.append(entry)
                pending_page = entry
                pending_heading_for = None
                continue

        # ---- heading continuation for a structural node ------------------
        if pending_heading_for is not None:
            stripped = line.strip()
            # A bare ROMAN numeral is the contents page's own folio, not heading
            # text -- the Federal Excise contents number their front matter i..iv
            # and the LAST structural row on a page ("FOURTH SCHEDULE [Omitted]
            # 105") is immediately followed by that folio, which became the
            # schedule's entire heading and then, via apply_toc_headings, the
            # emitted node's heading: `'FOURTH SCHEDULE' heading 'iv'`.  The
            # wrapped-section-heading branch below has always guarded this; the
            # structural branch never did.
            if re.fullmatch(r"[ivxlcdm]+", stripped, re.IGNORECASE):
                continue
            if stripped.isdigit():
                # a TOC page-number line after a division heading marks a boundary
                # to the next entry (a bare wrap has no intervening page number).
                if (in_schedules and pending_heading_for.kind == "division"
                        and pending_heading_for.heading):
                    pending_boundary = True
                continue
            txt = _clean_heading(line)
            # A leadered title row carries its folio at the end of the leader run
            # ("Preliminary……7", "REGISTRATION ....... 54"); once the leaders are
            # collapsed the folio is a bare trailing number with nothing to
            # consume it, and it was joined into the heading.  Only strip it when
            # a leader was actually present, so a title that genuinely ends in a
            # number is never truncated.
            if leadered:
                txt = _clean_heading(_FOLIO_TAIL_RE.sub("", txt))
            if not txt:
                continue
            if (pending_boundary and in_schedules
                    and pending_heading_for.kind == "division"):
                pending_boundary = False
                merged = _merge_parallel_titles(pending_heading_for.heading, txt)
                if merged is not None:
                    # parallel halves of ONE heading -> merge, no sibling leaf
                    pending_heading_for.heading = merged
                else:
                    # a genuine second same-code division -> new sibling entry
                    sib = Node(kind="division", code=pending_heading_for.code,
                               heading=txt)
                    parent = cur_part if cur_part is not None else (
                        cur_schedule if in_schedules else cur_chapter)
                    if parent is not None:
                        parent.divisions.append(sib)
                    cur_division = sib
                    pending_heading_for = sib
            else:
                pending_heading_for.heading = _join_heading(
                    pending_heading_for.heading, txt)
            continue

        # ---- wrapped section heading continuation ------------------------
        cm = CONT_RE.match(line)
        if cm and last_section is not None and not SECTION_RE.match(line):
            extra = _clean_heading(cm.group("text"))
            # A bare ROMAN numeral is the TOC page's own folio (these editions
            # number their front matter i..xxii), not heading text -- it leaked
            # into headings as "Power to declare warehousing stations ii".
            if extra and re.fullmatch(r"[ivxlcdm]+", extra, re.IGNORECASE):
                continue
            if extra and (not extra.isdigit()
                          or _completes_heading_year(last_section.heading, extra)):
                last_section.heading = _join_heading(last_section.heading, extra)
            continue

    # A page-less row whose continuation never arrived keeps printed_page 0,
    # which would poison min(printed_page) in the pipeline (body scan starting at
    # page 0 + offset) and anchor the section at the wrong place.  A wrapped row
    # sits on the same printed page as its neighbour, so inherit it.
    last_page = 0
    for e in ordered_sections:
        if e.printed_page:
            last_page = e.printed_page
        elif last_page:
            e.printed_page = last_page
    # ... and BACKWARD, for the rows at the head of the list.  "A wrapped row
    # sits on the same printed page as its neighbour" is a symmetric argument,
    # but only the forward half was implemented, so an entry with no EARLIER
    # page to inherit kept 0 and was deleted by the filter below.
    #
    # That is not a corner case: `Sales Tax Act, 1990 as amended up to
    # 30.06.2021` prints its contents with NO folio column at all on the first
    # pages, so sections 1-17 were constructed and then silently dropped -- the
    # edition shipped starting at section 18, missing 35 sections and 363
    # footnotes against its own adjacent-year edition.  A section that the TOC
    # lists must not vanish because the contents page lost its page numbers.
    nxt_page = 0
    for e in reversed(ordered_sections):
        if e.printed_page:
            nxt_page = e.printed_page
        elif nxt_page:
            e.printed_page = nxt_page
    ordered_sections = [e for e in ordered_sections if e.printed_page]
    ordered_sections = _dedupe_toc_sections(ordered_sections)

    return chapters, schedules, ordered_sections


def _demo() -> None:
    """Pure-function pin: real TOC fragments in, tree out, no PDF involved.

    Every literal below is copied verbatim from ``extract_text(layout=True)`` of
    the edition named, so a regression in leader handling, page ranges, the
    inline chapter title or the Federal Excise table rows fails here first --
    before a 230-page conversion has to be run to notice.
    """
    # --- Sales Tax Act 1990, 30-06-2025, contents pages 2 and 6 --------------
    sta = [
        "                 Chapter I…………………………………………………………………...7",
        "                 Preliminary…………………………………………………………            …….7",
        "                 1.   Short title, extent and commencement. ......................... ………..7",
        "                 2.   Definitions……………………………………………………          ..7-29",
        "                 Chapter-II ................................................................ ……....29",
        "                 SCOPE AND PAYMENT OF TAX………………..…………………....29",
        "                 3.   Scope of tax. ................................................ ..……..29",
        "                 8A.  Joint and several liability of registered persons in supply chain where",
        "                      tax unpaid.-………………………………………………….........44",
        "                 47.  Reference to the High Court.........................................….…106-107",
        "                 77.  Uniform…………….  .................................................... …….…..137",
        "                 SCHEDULES ........................................................... ………...137",
        "                 THE THIRD SCHEDULE ............................................ ……..137",
    ]
    chapters, schedules, secs = parse_toc(sta)
    assert [c.code for c in chapters] == ["CHAPTER I", "CHAPTER II"], \
        [c.code for c in chapters]
    # the folio the leaders point at is NOT part of the chapter's title
    assert chapters[0].heading == "Preliminary", repr(chapters[0].heading)
    assert chapters[1].heading == "SCOPE AND PAYMENT OF TAX", \
        repr(chapters[1].heading)
    got = {e.code: (e.heading, e.printed_page) for e in secs}
    assert got["1"] == ("Short title, extent and commencement", 7), got["1"]
    # a page RANGE resolves to the page the section STARTS on
    assert got["2"] == ("Definitions", 7), got["2"]
    assert got["47"][1] == 106, got["47"]
    # a wrapped row whose folio arrives on the continuation line
    assert got["8A"] == ("Joint and several liability of registered persons in "
                         "supply chain where tax unpaid.-", 44), got["8A"]
    # the bare "SCHEDULES" divider is a caption, not s.77's heading
    assert got["77"] == ("Uniform", 137), got["77"]
    assert [s.code for s in schedules] == ["THE THIRD SCHEDULE 137"], \
        [s.code for s in schedules]

    # --- Sales Tax Act 1990, 30.06.2021: a contents page with NO folios ------
    # Verbatim from that edition, whose contents print dot leaders that simply
    # run to the margin -- no page number anywhere on the early rows.  Page
    # inheritance used to run FORWARD only, so these head-of-list rows had no
    # earlier page to inherit, kept printed_page 0, and were deleted by the
    # filter: the edition shipped starting at section 18, missing 35 sections
    # and 363 footnotes against its own adjacent-year edition, at a reported
    # footnote conservation of 90.112%.  A section the TOC lists must not
    # vanish because the contents page lost its page-number column.
    nofolio = [
        "Chapter I.........................................................................................",
        "Preliminary .....................................................................................",
        "1.   Short title, extent and commencement. ..............................",
        "2.   Definitions..........................................................................",
        "Chapter-II .......................................................................................",
        "SCOPE AND PAYMENT OF TAX ..............................................",
        "3.   Scope of tax........................................................................",
        "17.  Omitted ..............................................................................",
        "18.  Omitted ..............................................................................",
        "22.  Records. .............................................................................  57",
    ]
    _ch, _sch, nf = parse_toc(nofolio)
    codes = [e.code for e in nf]
    assert codes == ["1", "2", "3", "17", "18", "22"], codes
    # every page-less row inherits the only folio on the page, backwards
    assert all(e.printed_page == 57 for e in nf), \
        [(e.code, e.printed_page) for e in nf]

    # --- Federal Excise Act 2005, 30-06-2025, contents pages 2 and 4 ---------
    fea = [
        "                 Section              Description              Page",
        "                       Chapter I – Preliminary                  5",
        "                   1   Short title, extent and commencement.    5",
        "                   2   Definitions.                            5-11",
        "                       Chapter-II – Levy, Collection and Payment of duty 12",
        "                   3A  ***] omitted                            14",
        "                  45AA Licensing of brand name.                63",
        "                       FIRST SCHEDULE                          72",
        "                       Table-I                                72-82",
        "                       Table-II                               83-87",
        "                       SECOND SCHEDULE                         89",
    ]
    chapters, schedules, secs = parse_toc(fea)
    # the column header is noise, and the chapter title is INLINE on its row
    assert [(c.code, c.heading) for c in chapters] == [
        ("CHAPTER I", "Preliminary"),
        ("CHAPTER II", "Levy, Collection and Payment of duty")], \
        [(c.code, c.heading) for c in chapters]
    got = {e.code: e.printed_page for e in secs}
    assert got == {"1": 5, "2": 5, "3A": 14, "45AA": 63}, got
    # the schedules' TABLEs are part-kind nodes (no new Node.kind -- six walkers
    # hardcode ("parts", "divisions", "sections"))
    assert [s.code for s in schedules] == ["FIRST SCHEDULE 72",
                                           "SECOND SCHEDULE 89"], \
        [s.code for s in schedules]
    assert [(p.kind, p.code) for p in schedules[0].parts] == \
        [("part", "Table-I"), ("part", "Table-II")], schedules[0].parts

    # --- Customs Act 1969: the whitespace-column form must be untouched ------
    customs = [
        "        CHAP TER I                                              ",
        "        PRELIMINARY                              Section Page N o",
        "        1.      Short title, extent and commencement.         1",
        "        10.  Power to approve landing places and specify limits of",
        "             customs-stations.                       12",
        "        14 2    T emporary detention of baggage.            10 6",
    ]
    chapters, _sch, secs = parse_toc(customs)
    assert [(c.code, c.heading) for c in chapters] == \
        [("CHAPTER I", "PRELIMINARY")], [(c.code, c.heading) for c in chapters]
    got = {e.code: e.printed_page for e in secs}
    assert got == {"1": 1, "142": 106, "10": 12}, got

    # --- Customs Act 1969 (30.06.2007): body text glued onto a TOC heading ----
    # Verbatim shape from the edition's contents: section 12's title and opening
    # body landed on one row, producing a duplicate "Section 12" in the portal
    # with body prose in the sidebar title.
    customs_s12_bleed = [
        "        CHAPTER III",
        "        DECLARATION OF PORTS, AIRPORTS AND WAREHOUSING STATIONS",
        "        11.  Power to declare warehousing stations.              35",
        "        12.  Power to appoint or licence public warehouses.     35",
        "        13.  Power to license private warehouses.               36",
        "        14.  Licensing of warehouses in special areas.          36",
        "        12.  Power to appoint public warehouse.- At any warehousing station, the Collector of Customs may, from time to time, appoint   52",
    ]
    _ch, _sch, bleed_secs = parse_toc(customs_s12_bleed)
    bleed_codes = [e.code for e in bleed_secs]
    assert bleed_codes == ["11", "12", "13", "14"], bleed_codes
    s12 = next(e for e in bleed_secs if e.code == "12")
    assert s12.heading == "Power to appoint or licence public warehouses", \
        repr(s12.heading)
    assert s12.printed_page == 35, s12.printed_page

    # --- Legitimate duplicate-code rows must both survive --------------------
    legit_dup = [
        "        CHAPTER XVI",
        "        236Y.  Omitted                                           401",
        "        236Y.  Recovery of tax by the department                 415",
    ]
    _ch, _sch, dup_secs = parse_toc(legit_dup)
    assert [e.code for e in dup_secs] == ["236Y", "236Y"], \
        [e.code for e in dup_secs]
    assert [e.heading for e in dup_secs] == [
        "Omitted",
        "Recovery of tax by the department",
    ], [e.heading for e in dup_secs]

    print("toc self-check passed")


if __name__ == "__main__":
    _demo()
