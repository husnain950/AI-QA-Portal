"""Table-of-Contents parser.

The FBR ordinance PDFs open with a Table of Contents (TOC) that lists the full
hierarchy of the document:

    CHAPTER  ->  PART  ->  DIVISION  ->  SECTION

Every *section* row carries a printed page number.  Because the printed page
numbers are offset from the physical PDF page numbers by a constant (the TOC
pages themselves), we can turn a printed page number into a PDF page index by
adding ``page_offset`` (see :mod:`fbr_ingest.pipeline`).

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

# ---- line classification regexes -------------------------------------------

# A section row:  "12.   Salary                                   48"
#                 "175AA. Exchange of banking ...                 364"
#                 "29A    Provision regarding consumer loans      82"   (no dot)
SECTION_RE = re.compile(
    r"^\s*(?P<code>\d{1,3}[A-Z]{0,3})\.?\s+(?P<heading>.+?)\s+(?P<page>\d{1,4})\s*$"
)

# A continuation line for a wrapped heading (indented, no code, no page number).
CONT_RE = re.compile(r"^\s{4,}(?P<text>\S.*?)\s*$")

CHAPTER_RE = re.compile(r"^\s*CHAPTER[\s\-]+([IVXLC0-9]+)\s*$", re.IGNORECASE)

# The TOC's column headers ("SECTIONS", "PAGE", "NO.") are printed once, at the
# top of the first TOC page.  Depending on the edition's layout they extract
# either as standalone lines ("SECTIONS PAGE NO.") or merged onto the first
# chapter/heading row ("CHAPTER 1              PAGE", "PRELIMINARY  NO.") --
# the 30.06.2024 edition does the latter, which used to defeat CHAPTER_RE and
# silently drop CHAPTER I with sections 1-3.  They never appear again after
# the first section row, so the sanitizer deactivates there.
_HDR_TOKEN = r"(?:SECTIONS?|PAGE|NO\.?)"
TOC_HEADER_LINE_RE = re.compile(rf"^\s*{_HDR_TOKEN}(?:\s+{_HDR_TOKEN})*\s*$")
TOC_HEADER_TAIL_RE = re.compile(rf"(?:\s+{_HDR_TOKEN})+\s*$")
# A part row may carry its printed page inline ("Part IIB 503" -- First
# Schedule) exactly like the division rows below; without the optional page
# group it fails to classify and its text (and the following part's title) get
# glued into the PREVIOUS part's heading, and the inline-page part is dropped.
PART_RE = re.compile(r"^\s*PART\s+([IVXLC0-9]+[A-Z]?)(?:\s+\d{1,4})?\s*$",
                     re.IGNORECASE)
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
DIVISION_RE = re.compile(
    r"^\s*Division\s+([IVXLC0-9]+(?:\s?[A-Z]{1,2})?)(?:\s+\d{1,4})?\s*$",
    re.IGNORECASE)
SCHEDULE_RE = re.compile(r"^\s*(THE\s+)?[A-Z]+\s+SCHEDULE\b", re.IGNORECASE)


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


def _clean_heading(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    # keep a TRAILING hyphen: it marks a hyphenated compound broken across a TOC
    # line ("...of a Non-" + "resident Person" -> "Non-resident Person").  Only
    # leading dashes and trailing dots/em-dashes are decorative.
    return text.lstrip(" .-—").rstrip(" .—")


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

        # ---- column-header noise (only before the first section row) ------
        if not ordered_sections and not in_schedules:
            if TOC_HEADER_LINE_RE.match(line):
                continue
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
            code = m.group("code")
            heading = _clean_heading(m.group("heading"))
            page = int(m.group("page"))
            entry = SectionEntry(code=code, heading=heading,
                                 printed_page=page, parent=container_for_section())
            ordered_sections.append(entry)
            last_section = entry
            pending_heading_for = None
            continue

        # ---- heading continuation for a structural node ------------------
        if pending_heading_for is not None:
            stripped = line.strip()
            if stripped.isdigit():
                # a TOC page-number line after a division heading marks a boundary
                # to the next entry (a bare wrap has no intervening page number).
                if (in_schedules and pending_heading_for.kind == "division"
                        and pending_heading_for.heading):
                    pending_boundary = True
                continue
            txt = _clean_heading(line)
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
            if extra and (not extra.isdigit()
                          or _completes_heading_year(last_section.heading, extra)):
                last_section.heading = _join_heading(last_section.heading, extra)
            continue

    return chapters, schedules, ordered_sections
