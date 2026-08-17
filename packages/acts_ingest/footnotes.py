"""Parse the footnote block at the bottom of each page.

Within the footnote zone (already separated by :mod:`acts_ingest.pagemodel`)
each footnote starts with a small superscript *marker* -- a digit or ``*`` --
at the left margin, followed by size-8 body text that may wrap over several
lines until the next marker.

Each footnote is rendered to three fields, matching the target JSON:

    text  : the raw footnote text, lines joined by "\\n"
    html  : the footnote as HTML -- one <p> per physical line, and, when the
            footnote embeds a "TABLE", a <div class="fn-table"> flex grid whose
            columns are recovered from the word x-positions on the page.

The globally-unique reference (``"{printed_page}.{marker}"``, e.g. ``"1.*"``)
is assembled later in :mod:`acts_ingest.builder`, which knows the printed-page
offset.
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass

from .grammar import is_marker_text, is_year_like, marker_sort_key, marker_token

LEFT_MARGIN_MAX = 95.0     # a marker starts a footnote if it sits near the left


def ref_sort_key(ref: str):
    """Numeric sort key for a ``"{printed_page}.{marker}"`` footnote ref.

    Refs are strings, so a plain sort puts "10.10" before "10.2".  Order by
    the printed page as a number, then the marker as a number; a non-numeric
    marker (``*``) sorts before the numbered notes of its page, matching the
    printed footer where the asterisk note appears first.
    """
    page, _, marker = str(ref).partition(".")
    page_n = int(page) if page.isdigit() else 0
    # Delegate the marker half to the shared grammar so a letter-suffixed marker
    # ("36a") orders after its base ("36") and before the next number -- Customs
    # prints 33a/36a/36b/36c, which a digits-only key drops to the front of the
    # page as non-numeric.
    return (page_n,) + marker_sort_key(marker)


# -- amendment-note classification -------------------------------------------
# a bracket-only body line ("1[  ]", "4[ 5[ ] ]") -- an amendment bracket
# whose content was removed
BRACKETS_ONLY_RE = re.compile(r"^[\d\s\[\]]+$")

# an anonymous amendment-history note ("Inserted by the Finance Act, 2016.")
# names no target element; a note that names ANY structural element
# (Section/Sub-section/Clause/Division/...) belongs where its marker anchors
# and must never be re-claimed
_ANON_HISTORY_RE = re.compile(
    r"^\s*(?:Inserted|Added|Substituted)\s+by\b", re.IGNORECASE)
_NAMED_TARGET_RE = re.compile(
    r"\b(?:sections?|sub-?sections?|clauses?|paras?|paragraphs?|divisions?|"
    r"parts?|provisos?|explanations?|schedules?|tables?)\b",
    re.IGNORECASE)


def is_anonymous_history_note(text: str) -> bool:
    """True for an amendment note that names no structural element."""
    t = text or ""
    return bool(_ANON_HISTORY_RE.match(t)) and not _NAMED_TARGET_RE.search(t)


def all_markers_anonymous(ref, page_footnotes) -> bool:
    """True when every superscript marker on the line anchors a footnote that
    is an anonymous history note (no structural element named)."""
    marks = [w.text.strip() for w in getattr(ref.line, "words", [])
             if w.text.strip().isdigit()]
    if not marks:
        return False
    by_marker = {fn.marker: (fn.text or "")
                 for fn in page_footnotes.get(ref.page, [])}
    return all(m in by_marker and is_anonymous_history_note(by_marker[m])
               for m in marks)


# exact style templates used by the target JSON for footnote tables
_FN_TABLE_OPEN = ('<div class="fn-table" style="display:flex; flex-wrap:wrap; '
                  'border:1px solid var(--color-border); margin:0.5em 0; '
                  'font-size:0.8rem; font-family:var(--font-mono);">')
_FN_HEAD_CELL = ('<div style="flex:0 0 {w}%; padding:4px 6px; font-weight:700; '
                 'background:var(--color-bg-tertiary); '
                 'border-bottom:1px solid var(--color-border); '
                 'border-right:1px solid var(--color-border); '
                 'box-sizing:border-box;">{c}</div>')
_FN_BODY_CELL = ('<div style="flex:0 0 {w}%; padding:4px 6px; '
                 'border-bottom:1px solid var(--color-border); '
                 'border-right:1px solid var(--color-border); '
                 'box-sizing:border-box;">{c}</div>')

_COL_TOL = 12.0            # x tolerance when snapping a word to a column edge


@dataclass
class Footnote:
    marker: str
    text: str
    html: str
    # raw (text, words) line records -- kept so a footnote that continues on
    # the next page can be re-rendered as ONE unit after splicing
    records: list = None
    pdf_page: int | None = None       # page the marker is printed on
    end_pdf_page: int | None = None   # last page the footnote's text reaches


def _is_marker_word(w, n_words_on_line: int = 99, max_size: float = 7.8) -> bool:
    """True for a footnote-block marker (a bare digit or ``*`` at the margin).

    Markers are usually superscripts (size ~7).  Some, however, are printed at
    body size (~8) on a line of their own -- so a bare digit that is the *only*
    word on its line is also accepted (this recovers footnotes like the 89.3
    rate table, whose "3" marker is size 8).
    """
    if not is_marker_text(w.text):
        return False
    return w.size <= max_size or n_words_on_line == 1


def _sorted_words(line):
    return sorted(line.words, key=lambda w: w.x0)


# ---------------------------------------------------------------------------
# table detection / rendering
# ---------------------------------------------------------------------------

def _looks_like_number_row(words) -> bool:
    """True for a "(1) (2) (3) ..." column-numbering row."""
    toks = [w.text.strip() for w in words]
    return len(toks) >= 2 and all(
        t.startswith("(") and t[1:-1].isdigit() and t.endswith(")") for t in toks)


def _bare_number_row(words) -> bool:
    """True for a bare "1 2 3 4" column-numbering row (consecutive from 1)."""
    toks = [w.text.strip() for w in words]
    return (len(toks) >= 2 and all(t.isdigit() for t in toks)
            and [int(t) for t in toks] == list(range(1, len(toks) + 1)))


def _edges_by_gap(words, gap=18.0) -> list[float]:
    """Column edges inferred from large horizontal gaps between words."""
    if not words:
        return []
    edges = [words[0].x0]
    for prev, cur in zip(words, words[1:]):
        if cur.x0 - prev.x1 >= gap:
            edges.append(cur.x0)
    return edges


import re as _re

# a substituted table may open with the "TABLE" keyword OR straight into an
# "S#" / "S. No." / "Sr. No." header row.
_FN_TABLE_HEADER = _re.compile(r"^S(\s*#|r?\.?\s*No\.?)", _re.IGNORECASE)
# a data row's leading serial cell: "1.", "(1)", "6A.", "12)" ...
_ROW_ANCHOR = _re.compile(r"^\(?\d{1,2}[A-Za-z]{0,2}[.)]?\]?$")
# an amendment marker + bracket prefix, e.g. "2 [TABLE"
_MARKER_PREFIX = _re.compile(r"^[\d*]{1,3}\s*\[?\s*")
# a marker digit separated from its bracket ("1 [12,000]" vs "1[12,000]")
_MARKER_GAP = _re.compile(r"(?<![\w.])(\d{1,3})\s+\[")


def _para(text):
    return f"<p>{_html.escape(text)}</p>" if text.strip() else ""


_ROMAN_ANCHOR = _re.compile(r"^[“\"(\[]{0,2}[IVXLC]{1,6}[.)\]]{0,2}$")
_ALPHA_ANCHOR = _re.compile(r"^[“\"]?\([a-z]{1,4}\)$")


def _is_anchor_word(w) -> bool:
    t = w.text.strip()
    if _ROMAN_ANCHOR.match(t) or _ALPHA_ANCHOR.match(t):
        return True    # Third Schedule class serials (I, II, ..., (a), (b))
    if not _ROW_ANCHOR.match(t):
        return False
    digits = "".join(ch for ch in t if ch.isdigit())
    return bool(digits) and int(digits) < 100      # "2015" is a year, not a serial


# a footnote's own INTRO can start with "S. No. 4A and entries ... omitted by
# the Finance Act": that is prose about the table, not the table's header row
_FN_INTRO = _re.compile(
    r"Finance Act|read as follows|substitut|omitt|insert|added", _re.IGNORECASE)


def _segments(words) -> int:
    return 1 + sum(1 for a, b in zip(words, words[1:])
                   if b.x0 - a.x1 >= _COL_GAP)


# an intro line announcing quoted material: the columnar run that follows it
# is a table ("... read as under.", "... shall be –", "... as follows:-")
_QUOTE_INTRO_END = _re.compile(r"(?:[:\-–—]|follows[.:]?|under[.:]?)\s*[”\"]?\s*$")


def _columnar_run_start(records, i) -> bool:
    """A gridless quoted table with no S.No / TABLE / numbering signature.

    Line ``i`` is a header-shaped line (>= 2 gap-separated segments, no
    amendment-history vocabulary) after a quote-intro line -- allowing up to
    three short centred heading lines between them ("Division IIA / Rates of
    Super Tax") -- and at least two of the next five lines show the same
    columnar structure.  The Third Schedule depreciation table (fn 698.1)
    and the Division IIA rate table (fn 495.3) print exactly this shape.
    """
    if i == 0:
        return False
    intro = False
    k = i - 1
    for _ in range(4):
        if k < 0:
            break
        ptext, pwords = records[k][0].strip(), records[k][1]
        if _QUOTE_INTRO_END.search(ptext):
            intro = True
            break
        # tolerate a short centred heading line, nothing else
        if not pwords or len(pwords) > 6 or _segments(pwords) != 1:
            break
        k -= 1
    if not intro:
        return False
    text, words = records[i][0], records[i][1]
    if len(words) < 2 or _FN_INTRO.search(text):
        return False
    if _is_anchor_word(words[0]):
        return False                     # a data row is not a header line
    segmented_header = _segments(words) >= 2
    # a full-width sentence header (fn 536.2's boxed "Rate of collection of
    # tax under section 235 ...") has no column gap of its own; accept it
    # only on STRONG evidence below (gap-segmented rows, not just serials)
    sentence_header = not segmented_header and len(words) >= 8
    if not segmented_header and not sentence_header:
        return False
    columnar = 0
    for k in range(i + 1, min(i + 6, len(records))):
        nwords = records[k][1]
        if not nwords:
            continue
        if _segments(nwords) >= 2:
            columnar += 1
        elif segmented_header and _is_anchor_word(nwords[0]):
            columnar += 1
    return columnar >= 2


def _find_table_start(records, start):
    """Next table start at/after ``start``: (index, skip_keyword_line) or None.

    A table opens with a "TABLE" keyword line (possibly behind an amendment
    marker, "2 [TABLE"), an "S#/S. No." header, a numbering row, or a
    columnar run after a quote-intro line (:func:`_columnar_run_start`).
    """
    for i in range(start, len(records)):
        text, words = records[i][0], records[i][1]
        t = text.strip()
        core = _MARKER_PREFIX.sub("", t).strip().lstrip("“\"'").strip()
        if core.upper() == "TABLE" or t.upper() == "TABLE":
            return i, True
        if (_FN_TABLE_HEADER.match(core) and not _FN_INTRO.search(t)) \
                or _looks_like_number_row(words) or _bare_number_row(words):
            return i, False
        if _columnar_run_start(records, i):
            return i, False
    return None


def _valley_blocks(lines, min_gap=6.5):
    """Coverage blocks [start, end] separated by whitespace VALLEYS.

    An x-range that (almost) no line's words cross is a column separation;
    header text centred over a column or a numbering row centred under it
    cannot fake one.  A single long line bridging two columns must not erase
    the boundary, so an x-position crossed by ~10% of the lines still counts
    as a valley."""
    rows = [words for words in lines if words]
    if not rows:
        return []
    # tolerance can never reach the row count itself: a SINGLE row's coverage
    # is exactly 1 everywhere, so allow must drop to 0 there or no block forms
    allow = min(max(1, round(0.12 * len(rows))), len(rows) - 1)
    lo = min(w.x0 for words in rows for w in words)
    hi = max(w.x1 for words in rows for w in words)
    n = int(hi - lo) + 2
    cover = [0] * n
    for words in rows:
        for w in words:
            for x in range(int(w.x0 - lo), min(n, int(w.x1 - lo) + 1)):
                cover[x] += 1
    blocks = []
    x = 0
    while x < n:
        if cover[x] > allow:
            start = x
            while x < n and cover[x] > allow:
                x += 1
            blocks.append([lo + start, lo + x])
        else:
            run = x
            while x < n and cover[x] <= allow:
                x += 1
            if blocks and x < n and (x - run) < min_gap:
                blocks[-1][1] = lo + x   # too narrow to be a real valley
    # re-merge blocks separated by sub-min_gap valleys
    merged = []
    for b in blocks:
        if merged and b[0] - merged[-1][1] < min_gap:
            merged[-1][1] = b[1]
        else:
            merged.append(b)
    return merged


def _pick_edges(numrow, lines):
    """Column left-edges for the table.

    Tolerant whitespace valleys over the table's lines give the positions; a
    "(1) (2) (3)" numbering row declares the column COUNT -- extra blocks are
    noise inside a column and are merged into their nearest neighbour until
    the declared count remains."""
    blocks = _valley_blocks(lines)
    num = [w.x0 for w in numrow] if numrow else None
    if len(blocks) < 2:
        return num or []
    # only a numbering row is AUTHORITATIVE for the column count (a header
    # line's gap count under-counts when adjacent headers nearly touch)
    if num and len(num) >= 2:
        # a numbering row can DECLARE more columns than the data carries: the
        # pre-2007 Seventh Schedule prints "(1) (2) (3)" over only two data
        # columns (fn 693.1).  A trailing "(n)" token sitting entirely to the
        # RIGHT of the last data-coverage block has no column under it -- drop
        # it so the real 2-column grid survives.  ONLY trailing empties are
        # removed: an INTERIOR column the valleys merged because justified text
        # touched it (fn 502.3's rent table, where every "(n)" lies inside the
        # one wide block) is still recovered by the centre fallback below.
        if len(blocks) < len(num):
            last_right = blocks[-1][1]
            kept = [x for x in num if x <= last_right + _COL_GAP]
            if len(kept) >= 2:
                num = kept
        while len(blocks) > len(num):
            gaps = [(blocks[i + 1][0] - blocks[i][1], i)
                    for i in range(len(blocks) - 1)]
            _, i = min(gaps)
            blocks[i][1] = blocks[i + 1][1]
            del blocks[i + 1]
        if len(blocks) < len(num):
            # valleys UNDER-count when justified text nearly touches the next
            # column (fn 502.3's rent table collapsed to one wide column and
            # interleaved "Nil" into the description) -- fall back to the
            # numbering tokens, which are centred under their columns:
            # boundaries at midpoints between token centres, the first column
            # opening at the table's left edge
            centers = sorted((w.x0 + w.x1) / 2 for w in numrow)
            mids = [(a + b) / 2 for a, b in zip(centers, centers[1:])]
            lo = min(w.x0 for ws in lines for w in ws if ws)
            return [lo] + mids
    return [b[0] for b in blocks]


def _assign(words, edges, cells, by_center=False):
    for w in sorted(words, key=lambda w: w.x0):
        x = (w.x0 + w.x1) / 2 if by_center else w.x0
        col = 0
        for i, e in enumerate(edges):
            if x + _COL_TOL >= e:
                col = i
        cells[col].append(w.text)


def _assign_nearest(words, edges, cells, by_center=False):
    """Assign each word to the NEAREST column edge by distance.

    Used for wrapped HEADER blocks only.  A right-aligned column's title
    ("Rate per cent of the written down value.") starts LEFT of that column's
    data-derived edge (the edge sits at the right-aligned rate numbers), so the
    x0+_COL_TOL snap in :func:`_assign` buckets it into the previous column and
    fuses "Rate" into the Description header.  Distance-nearest matching places
    the whole title phrase in its own column.  Data rows keep :func:`_assign` --
    their words start AT a column edge, where both agree."""
    for w in sorted(words, key=lambda w: w.x0):
        x = (w.x0 + w.x1) / 2 if by_center else w.x0
        col = min(range(len(edges)), key=lambda i: abs(x - edges[i]))
        cells[col].append(w.text)


def _row_cells(lines, edges, header=False) -> list[str]:
    """Assemble one row's cells from its (ordered) wrapped lines: words are
    accumulated per column line-by-line, preserving reading order.

    Continuation lines snap by word CENTRE: a parenthetical printed centred
    under its cell ("5 / (General rate)") starts left of the column edge and
    would otherwise leak into the neighbouring description cell.

    ``header=True`` assigns by NEAREST edge (:func:`_assign_nearest`) so a
    wrapped multi-line column TITLE whose words start left of their
    data-derived edge map to the right column.
    """
    cells: list[list] = [[] for _ in edges]
    assign = _assign_nearest if header else _assign
    for k, words in enumerate(lines):
        assign(words, edges, cells, by_center=(k > 0))
    return [" ".join(c) for c in cells]


# prose resuming after (or inside) a quoted table: a proviso / explanation, or
# the quoted section's next list item ("(b) The rate of tax ...")
_PROSE_VOCAB = _re.compile(r"^(Provided|Explanation|Illustration|Note[.:])",
                           _re.IGNORECASE)
# a formula LEGEND under a rate table: "where A is the amount of the gain
# determined under sub-section (2)."  Lowercase "where" + a single-capital
# formula variable -- a row's description always starts with capital "Where
# the holding period ...", so the case distinguishes them.  Absorbed as a row
# wrap, the legend fuses into the last row's cell (footnotes 89.1-89.3).
# CASE-SENSITIVE by design -- do not fold into _PROSE_VOCAB.
_FORMULA_LEGEND = _re.compile(r"^where\s+[A-Z]\b")
_CLAUSE_START = _re.compile(r"^\(?[a-z]{1,3}\)")


def _max_gap(words) -> float:
    return max((b.x0 - a.x1 for a, b in zip(words, words[1:])), default=0.0)


def _serial_no(word) -> int | None:
    m = _re.match(r"^\(?(\d{1,3})[.)\]]?$", word.text.strip())
    return int(m.group(1)) if m else None


def _line_ends_table(text, words, left_min, last_serial=None) -> bool:
    t = _MARKER_PREFIX.sub("", text.strip()).lstrip("[ ").strip()
    if _PROSE_VOCAB.match(t) or _FORMULA_LEGEND.match(t):
        return True
    # a row whose serial CONTINUES the table's sequence is never prose, even
    # when its description line runs wide with no gap (fn 504.1's "1. Where
    # holding period of a security is less" prints the year/rate cells on
    # separate physical lines)
    s = _serial_no(words[0])
    continues = s is not None and (s == 1 if last_serial is None
                                   else s == last_serial + 1)
    # a clause label opening a WIDE gap-less line is quoted prose resuming; a
    # clause label with real column gaps is a table row ((a) rate rows) --
    # the label's own hanging indent is not a column gap, so measure past it
    if _CLAUSE_START.match(t) and len(words) >= 5 \
            and _max_gap(words[1:]) < _COL_GAP and not continues:
        return True
    # a long justified line with no column gap at all is running prose, even
    # when it opens with a "(2)"-style number (the PEMRA "(2) The rate of tax
    # to be collected by ..." paragraph was absorbed as a data row)
    if len(words) >= 8 and _max_gap(words[1:]) < _COL_GAP \
            and (words[-1].x1 - words[0].x0) > 250 and not continues:
        return True
    if left_min is not None and words[0].x0 < left_min - 2 * _COL_TOL:
        return True                              # left of every row so far
    return False


def _numrow_continuation(numrow, words) -> bool:
    """True when ``words`` is the wrapped tail of the numbering row: every
    token is "(n)", the first continues the row's sequence, and it sits to the
    RIGHT of the row's last token (it finishes the same visual line)."""
    toks = [w.text.strip() for w in words]
    prev = [w.text.strip() for w in numrow]
    if not toks or not prev:
        return False
    if not all(_re.fullmatch(r"\(\d+\)", t) for t in toks + prev):
        return False
    if words[0].x0 <= numrow[-1].x0:
        return False
    return int(toks[0][1:-1]) == int(prev[-1][1:-1]) + 1


def _render_table_region(records, start):
    """Render one table starting at ``start``: returns (html, next_index).

    Layout: [multi-line header block] [numbering row] [data rows with wraps],
    ending where prose resumes (a proviso, an Explanation, the quoted text's
    next clause).  Returns ("", start) when no real multi-column structure is
    found."""
    n = len(records)
    j = start
    lines: list = []          # all table lines until prose resumes
    numrow_idx = None
    left_min = None
    last_serial = None
    while j < n:
        text, words = records[j][0], records[j][1]
        if not words:
            j += 1
            continue
        # a numbering row can WRAP: wide columns push "(3)" onto its own
        # physical line below "(1) (2)" (footnote 494.2's quoted company-rate
        # table).  A line of pure "(n)" tokens continuing the sequence is the
        # SAME logical row -- merged, it declares the true column count.
        # Treated as a data row instead, its far-right "(3)" would anchor
        # left_min and the prose test would cut the table before the real
        # data row ("50% 35% 45%" fell out of the grid).
        if (numrow_idx is not None and numrow_idx == len(lines) - 1
                and _numrow_continuation(lines[numrow_idx], words)):
            lines[numrow_idx] = list(lines[numrow_idx]) + list(words)
            j += 1
            continue
        if _line_ends_table(text, words, left_min, last_serial):
            break
        is_num = _looks_like_number_row(words) or _bare_number_row(words)
        if numrow_idx is None and is_num:
            numrow_idx = len(lines)
        # a numbering row's "(1)" is centred under its column, NOT at the
        # row-serial position -- it must not define the table's left edge
        if not is_num and _is_anchor_word(words[0]):
            x = words[0].x0
            left_min = x if left_min is None else min(left_min, x)
            s = _serial_no(words[0])
            if s is not None:
                last_serial = s
        lines.append(words)
        j += 1
    if len(lines) < 2:
        return "", start

    numrow = lines[numrow_idx] if numrow_idx is not None else None
    if numrow_idx is not None:
        header_lines = lines[:numrow_idx]
        data_lines = lines[numrow_idx + 1:]
    else:
        # no numbering row: the header ends at the first serial-anchored row,
        # or after the first line (tables like Division II's company-rate grid
        # have no serials at all)
        k = next((i for i, ws in enumerate(lines)
                  if i > 0 and _is_anchor_word(ws[0])), 1)
        header_lines, data_lines = lines[:k], lines[k:]

    # header lines split by y-jitter (two Line objects on one printed row,
    # fn 536.2's boxed sentence-header) are one line for rendering purposes
    merged_headers: list = []
    for ws in header_lines:
        if merged_headers and ws and merged_headers[-1] and \
                abs(ws[0].top - merged_headers[-1][0].top) < 3.0:
            merged_headers[-1] = sorted(list(merged_headers[-1]) + list(ws),
                                        key=lambda x: x.x0)
        else:
            merged_headers.append(list(ws))
    header_lines = merged_headers

    edges = _pick_edges(numrow, lines)
    if len(edges) < 2 or not data_lines:
        return "", start

    # group rows: by serial anchors when the table has them, else each line
    # starting at the first column edge opens a row (indented lines are
    # wraps); a lone ALL-CAPS gap-less line is a section band (the Third
    # Schedule's BUILDINGS / FURNITURE dividers) and gets its own row
    anchors = [ws for ws in data_lines
               if _is_anchor_word(ws[0]) and abs(ws[0].x0 - edges[0]) <= _COL_TOL]

    def _opens_row(ws) -> bool:
        # a serial at the FIRST column edge always opens a row; an indented
        # serial at a LATER column edge opens a sub-row ((a)/(b) age-band
        # rows inside the Third Schedule depreciation classes)
        return _is_anchor_word(ws[0]) and \
            any(abs(ws[0].x0 - e) <= _COL_TOL for e in edges)

    groups: list = []                    # ("band", [line]) | ("row", [lines])
    if len(anchors) >= 2:
        for words in data_lines:
            if _is_band_line(words):
                groups.append(("band", [words]))
            elif _opens_row(words):
                groups.append(("row", [words]))
            elif groups and groups[-1][0] == "row":
                groups[-1][1].append(words)
            elif groups:
                groups.append(("row", [words]))
            else:
                header_lines.append(words)       # stray pre-data line
    else:
        for words in data_lines:
            if _is_band_line(words):
                groups.append(("band", [words]))
            elif (words[0].x0 <= edges[0] + _COL_TOL or not groups
                  or groups[-1][0] == "band"):
                groups.append(("row", [words]))
            else:
                groups[-1][1].append(words)
    if not groups:
        return "", start

    ncol = len(edges)
    w = str(round(100 / ncol, 2))
    cells_html: list[str] = []
    # a wrapped header continuation starts lowercase ("Class / of / asset.")
    # and pools per-column with its opening line; a NEW header row (sub-
    # headers like "Filer Non-Filer") starts capitalised and stays its own
    # row so spanning headers never interleave
    hdr_blocks: list[list] = []
    for line in header_lines:
        first_alpha = next((ch for w_ in line for ch in w_.text if ch.isalpha()), "")
        if hdr_blocks and first_alpha and first_alpha.islower():
            hdr_blocks[-1].append(line)
        else:
            hdr_blocks.append([line])
    for block in hdr_blocks:
        if len(block) == 1 and _is_band_line(block[0]):
            # an ALL-CAPS gap-less divider in the HEADER region (the Third
            # Schedule's "BUILDINGS" printed before the first serial row) is a
            # full-width band, not a one-column header with empty siblings
            text = " ".join(x.text for x in block[0])
            cells_html.append(_FN_HEAD_CELL.format(w="100.0",
                                                   c=_html.escape(text)))
        elif len(block) == 1:
            cells_html += _header_row_cells(block[0], edges)
        else:
            for c in _row_cells(block, edges, header=True):
                cells_html.append(_FN_HEAD_CELL.format(w=w, c=_html.escape(c)))
    if numrow is not None:
        for c in _row_cells([numrow], edges):
            cells_html.append(_FN_HEAD_CELL.format(w=w, c=_html.escape(c)))
    for kind, g in groups:
        if kind == "band":
            text = " ".join(x.text for x in g[0])
            cells_html.append(_FN_BODY_CELL.format(w="100.0",
                                                   c=_html.escape(text)))
            continue
        for c in _row_cells(g, edges):
            cells_html.append(_FN_BODY_CELL.format(w=w, c=_html.escape(c)))
    return _FN_TABLE_OPEN + "".join(cells_html) + "</div>", j


def _is_band_line(words) -> bool:
    """A full-caps, gap-less divider line inside a table (its own row)."""
    if not words or len(words) > 6 or _max_gap(words) >= _COL_GAP:
        return False
    text = " ".join(w.text for w in words)
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters)


def _header_row_cells(words, edges) -> list[str]:
    """Render ONE header line as its own flex row of column-mapped cells.

    Pooling every header line into one set of column cells interleaved
    spanning headers with the sub-headers beneath them ("Rate applicable on
    the amount of payment." fused into "Filer", "Holding Period Open / Rate
    Plots").  Per line: words are assigned to columns, and adjacent non-empty
    columns whose boundary words run on with NO column gap are ONE spanning
    cell (fn 521.1's "Money market fund, income fund or REIT scheme or any
    other fund" over the Filer/Non-Filer pair).
    """
    ncol = len(edges)
    w = 100.0 / ncol
    # a long JUSTIFIED sentence-header spans the whole table in one drawn box
    # (fn 536.2's "Rate of collection of tax under section 235 ...") and its
    # stretched word gaps must not shred it into per-column fragments
    if len(words) >= 10 and words[0].x0 <= edges[0] + _COL_TOL \
            and words[-1].x1 >= edges[-1]:
        text = " ".join(x.text for x in words)
        return [_FN_HEAD_CELL.format(w="100.0", c=_html.escape(text))]
    cols: list[list] = [[] for _ in edges]
    for word in sorted(words, key=lambda x: x.x0):
        col = 0
        for i, e in enumerate(edges):
            if word.x0 + _COL_TOL >= e:
                col = i
        cols[col].append(word)
    # merge adjacent non-empty columns when the text flows across the border
    # (two headers with no detectable gap stay ONE ordered cell -- "Tax Year.
    # Rate of tax." -- which preserves reading order; splitting on guessed
    # boundaries produced "Tax Year. Rate | of tax.")
    spans: list[list[int]] = []
    for i, c in enumerate(cols):
        if not c:
            spans.append([i])
            continue
        if spans and cols[spans[-1][-1]] and \
                c[0].x0 - cols[spans[-1][-1]][-1].x1 < _COL_GAP:
            spans[-1].append(i)
        else:
            spans.append([i])
    out = []
    for span in spans:
        text = " ".join(x.text for i in span for x in cols[i])
        out.append(_FN_HEAD_CELL.format(w=round(w * len(span), 2),
                                        c=_html.escape(text)))
    return out


def _render_grid_run(lines, min_rows: int = 2) -> str:
    """Render a run of column-structured footnote lines as an fn-table.

    These are quoted tables the text heuristics can't recognise (no "TABLE"
    keyword, no S.No header, no numbering row -- e.g. footnote 779.1's five
    omitted PCT-code rows, or 774.2's single omitted 72.04 row).  Columns
    come from the whitespace valleys; a line starting past the first column
    edge is a wrapped continuation of the previous row.  All rows are body
    cells -- with no header signature there is no reliable header row.
    """
    rows = [ws for ws in lines if ws]
    if len(rows) < min_rows:
        return ""
    edges = _pick_edges(None, rows)
    if len(edges) < 2:
        return ""
    groups: list[list] = []
    for ws in rows:
        if ws[0].x0 <= edges[0] + _COL_TOL or not groups:
            groups.append([ws])
        else:
            groups[-1].append(ws)
    row_cells = [_row_cells(g, edges) for g in groups]
    # a REAL grid's rows fill several columns; header fragments straggling
    # behind a heuristically-rendered table (a lone "S.No" line etc.) must
    # stay paragraphs, not become one-cell "tables"
    filled = sum(1 for cs in row_cells if sum(1 for c in cs if c.strip()) >= 2)
    if len(row_cells) < min_rows \
            or filled < max(min(2, len(row_cells)), round(0.6 * len(row_cells))):
        return ""
    ncol = len(edges)
    w = str(round(100 / ncol, 2))
    cells_html: list[str] = []
    for cs in row_cells:
        for c in cs:
            cells_html.append(_FN_BODY_CELL.format(w=w, c=_html.escape(c)))
    return _FN_TABLE_OPEN + "".join(cells_html) + "</div>"


# a quoted table row's first token: a PCT/serial code ("72.04", "9405.1090",
# "19") or a clause label ("(d)", "(iii)"), optionally behind quote/bracket
_ROWCODE_RE = _re.compile(
    r'^[“"\(\[]{0,2}\d{1,4}(\.\d{1,4})?[.)\]]{0,2}$'
    r'|^[“"]?\([a-z]{1,4}\)$', _re.IGNORECASE)
# a PCT-style numeric code ("72.04", "9405.1090") -- NEVER the shape of a
# quoted clause/sub-section label ("(12)", "(d)", "121.")
_PCT_CODE_RE = _re.compile(r'^[“"]?\d{1,4}\.\d{2,4}$')
_COL_GAP = 15.0     # a real column separation; justified prose never gaps this wide


def _column_row(words) -> bool:
    """A quoted table ROW with no other table evidence.

    Quoted CLAUSE text also opens with a label + hanging-indent gap
    ("“(12)   The depreciation deductions..."), and legal prose must never
    be tabled -- so a two-column line qualifies only with a PCT-style
    decimal code ("“72.04   Ferrous waste..."), while a parenthesised or
    serial label needs three or more gap-separated columns (a real rate row
    like "(a)   Not more than ten years   10", never a prose clause).
    """
    if len(words) < 2:
        return False
    groups = 1 + sum(1 for a, b in zip(words, words[1:])
                     if b.x0 - a.x1 >= _COL_GAP)
    t = words[0].text.strip()
    if groups >= 3:
        return bool(_ROWCODE_RE.match(t))
    if groups == 2:
        return bool(_PCT_CODE_RE.match(t))
    return False


def _col2_start(words):
    """x0 of the second column (the word after the widest gap)."""
    gaps = [(b.x0 - a.x1, b.x0) for a, b in zip(words, words[1:])]
    return max(gaps)[1]


def _paras_with_grids(recs) -> list[str]:
    """Emit a paragraph region, rendering table-shaped runs as fn-tables.

    Fallback only: this is reached for records the text-heuristic table
    detector did NOT claim, so every heuristically-detected table keeps its
    existing rendering exactly.  Two run shapes are recognised:

      * gridline-backed: >= 2 consecutive records inside a footnote-zone
        gridline bbox (the ``in_grid`` record flag);
      * colon-armed column rows: record(s) shaped like quoted table rows
        (:func:`_column_row`) directly after a line ending in ":" -- the
        "read as follows:" idiom that introduces every quoted amendment
        table.  This recovers one-row quotes that print no gridlines
        (footnote 774.2's single 72.04 row).  Wrapped description lines
        (starting at the second column) extend the run.
    """
    out: list[str] = []
    i, n = 0, len(recs)
    def flagged(k):
        return len(recs[k]) > 2 and recs[k][2]
    while i < n:
        armed = i > 0 and recs[i - 1][0].rstrip().endswith(":")
        grid_pair = flagged(i) and i + 1 < n and flagged(i + 1)
        col_start = armed and _column_row(recs[i][1])
        if grid_pair or col_start:
            j = i
            col2 = None
            while j < n:
                ws = recs[j][1]
                if flagged(j) or _column_row(ws):
                    col2 = _col2_start(ws) if _column_row(ws) else col2
                    j += 1
                elif col2 is not None and ws and ws[0].x0 >= col2 - _COL_TOL:
                    j += 1        # wrapped second-column continuation
                else:
                    break
            html = _render_grid_run([r[1] for r in recs[i:j]],
                                    min_rows=1 if col_start else 2)
            if html:
                out.append(html)
                i = j
                continue
        out.append(_para(recs[i][0]))
        i += 1
    return out


def _is_bare_num_cells(row) -> bool:
    """A normalised structure row that is a bare "1 2 3 4" numbering row."""
    texts = [c["text"].strip() for c in row
             if c is not None and c["text"].strip()]
    return (len(texts) >= 2 and all(t.isdigit() for t in texts)
            and [int(t) for t in texts] == list(range(1, len(texts) + 1)))


def _rec_grid(rec):
    """The footnote-zone gridline table a record's line falls inside, or None.

    Older records carried a plain ``in_grid`` bool; only a ``(top, bottom,
    cells[, rowcells])`` structure from
    :func:`pagemodel._extract_body_tables` counts as a renderable grid here.
    """
    g = rec[2] if len(rec) > 2 else None
    return g if isinstance(g, tuple) and len(g) >= 3 and g[2] else None


def _grid_rows(g):
    return g[3] if len(g) > 3 else None


def _grid_width(g) -> int:
    from .tables import _normalise_grid
    rows = _normalise_grid(g[2], _grid_rows(g))
    return len(rows[0]) if rows else 0


def _concat_grid(base_cells, base_rows, g):
    """Append a page-split fragment's cells (and y-offset bboxes) to a run."""
    base_cells.extend(list(r) for r in g[2])
    grows = _grid_rows(g)
    if base_rows is None or grows is None:
        return None
    prev_bottom = max((bb[3] for row in base_rows for bb in row
                       if bb is not None), default=0.0)
    frag_top = min((bb[1] for row in grows for bb in row
                    if bb is not None), default=0.0)
    off = prev_bottom + 10.0 - frag_top
    for row in grows:
        base_rows.append([(bb[0], bb[1] + off, bb[2], bb[3] + off)
                          if bb is not None else None for bb in row])
    return base_rows


def _fit_grid_to_records(cells, recs):
    """Match the grid's cell text against the claimed records.

    A footnote-zone grid box does not always contain its whole table: fn
    504.1's box covers only the header + numbering rows, and fn 510.1's
    closing ``]”`` prints just outside the ruled area but inside the claim
    tolerance.  Rendering from cells alone would silently DROP such text --
    the one failure this pipeline must never produce.  Boundary records (up
    to three at each end) whose words the cells do not carry are therefore
    TRIMMED back to the prose path, and the fit succeeds only when the
    remaining records and the cells carry exactly the same words.

    Returns ``(n_leading, n_trailing)`` records to trim, or None when the
    grid does not faithfully represent the run even after trimming.
    """
    from collections import Counter

    from .pagemodel import normalize_text

    def toks(text):
        # a superscript amendment marker and its bracket tokenize apart on
        # the line ("1 [12,000]") but fused in the extractor's cell text
        # ("1[12,000]") -- fuse both sides before comparing
        return _MARKER_GAP.sub(r"\1[", normalize_text(text)).split()

    have = Counter()
    for row in cells:
        for c in row:
            if c:
                have.update(toks(str(c)))
    needs = [Counter(toks(rec[0])) for rec in recs]

    def gap(lo, hi):
        need = Counter()
        for n in needs[lo:hi]:
            need.update(n)
        return (need - have), (have - need)

    lo, hi = 0, len(needs)
    for _ in range(3):
        miss, _extra = gap(lo, hi)
        if not miss or hi <= lo:
            break
        if hi > lo and needs[hi - 1] & miss:
            hi -= 1
            continue
        if needs[lo] & miss:
            lo += 1
            continue
        break
    miss, extra = gap(lo, hi)
    if hi <= lo or extra:
        return None
    if miss:
        # a closing bracket/quote printed just outside the ruled area on the
        # last table line ("0.5%] ]") cannot be trimmed away with its record
        # without orphaning the row -- append the stray punctuation to the
        # table instead so not a single glyph is dropped
        if sum(miss.values()) <= 2 and all(
                tok and all(ch in "[]”“\"'’‘" for ch in tok) for tok in miss):
            leak = " ".join(tok for tok in miss.elements())
            return lo, len(needs) - hi, leak
        return None
    return lo, len(needs) - hi, ""


def _render_fn_grid(cells, rowcells=None) -> str:
    """Render a footnote-zone gridline table from its extracted cells.

    The PDF draws these quoted amendment tables with real rules, so the cell
    matrix -- including merged (spanning) cells, which arrive as a value
    followed by ``None`` placeholders -- is authoritative.  Word-geometry
    heuristics cannot represent a spanning header ("Rate applicable on the
    amount of payment." over the Filer/Non-filer columns) and are only used
    for quoted tables that print no gridlines.

    Cells keep the established fn-table flex markup: equal column widths, a
    spanning cell as one wider div.  Rows up to and including a leading
    "(1) (2) ..." numbering row are header-styled.
    """
    from .pagemodel import normalize_text
    from .tables import _is_numbering_cells, _normalise_grid
    rows = _normalise_grid(cells, rowcells)
    if not rows:
        return ""
    width = len(rows[0])
    texts = [c["text"] for row in rows for c in row if c is not None and c["text"].strip()]
    if width < 2 or (len(rows) == 1 and len(texts) < 2):
        return ""                        # degenerate fragment -> keep as prose
    num_idx = next((i for i, r in enumerate(rows[:5])
                    if _is_numbering_cells(r) or _is_bare_num_cells(r)), None)
    if num_idx is not None and num_idx == len(rows) - 1:
        # a ruled HEADER BOX whose data rows print gridless below it (fn
        # 504.1, pdf p523): rendering just the box would orphan the data --
        # fall back so the text heuristics claim header and rows together
        return ""
    head_upto = num_idx if num_idx is not None else -1
    w = 100.0 / width
    out = [_FN_TABLE_OPEN]
    for ri, row in enumerate(rows):
        tpl = _FN_HEAD_CELL if ri <= head_upto else _FN_BODY_CELL
        ci = 0
        while ci < len(row):
            c = row[ci]
            if c is None:
                # a position covered by a rowspan from above: the flex grid
                # cannot merge vertically, so keep the row's widths summing
                # to 100% with an empty cell (the established fn-table look)
                out.append(tpl.format(w=round(w, 2), c=""))
                ci += 1
                continue
            cw = round(w * c["colspan"], 2)
            text = normalize_text(" ".join(c["text"].split()))
            out.append(tpl.format(w=cw, c=_html.escape(text)))
            ci += c["colspan"]
    out.append("</div>")
    return "".join(out)


def _build_html(line_records) -> str:
    """Build footnote html from ``line_records`` = (text, words, grid) rows.

    Records inside a footnote-zone gridline table render from that table's
    real cell structure (:func:`_render_fn_grid`); directly adjacent grids of
    the same width are one table split by a page break (fn 535.4's row 7) and
    are re-joined.  Everything else goes through the text heuristics
    (:func:`_build_html_run`).
    """
    parts: list[str] = []
    plain: list = []

    def flush():
        if plain:
            parts.append(_build_html_run(plain))
            del plain[:]

    i, n = 0, len(line_records)
    consumed: set[int] = set()            # grids already rendered (by id)
    while i < n:
        g = _rec_grid(line_records[i])
        if g is None or id(g) in consumed:
            plain.append(line_records[i])
            i += 1
            continue
        cells = [list(r) for r in g[2]]
        rowsgeo = ([list(r) for r in _grid_rows(g)]
                   if _grid_rows(g) is not None else None)
        w0 = _grid_width(g)
        run_grids = [g]
        j = i
        while j < n and _rec_grid(line_records[j]) is g:
            j += 1
        while j < n:                      # page-split continuation fragments
            g2 = _rec_grid(line_records[j])
            if g2 is None or g2 is g or id(g2) in consumed \
                    or _grid_width(g2) != w0:
                break
            rowsgeo = _concat_grid(cells, rowsgeo, g2)
            run_grids.append(g2)
            g = g2
            while j < n and _rec_grid(line_records[j]) is g:
                j += 1
        fit = _fit_grid_to_records(cells, line_records[i:j])
        if fit is not None and fit[2]:
            # re-attach leaked closing punctuation to the last non-empty cell
            for r in range(len(cells) - 1, -1, -1):
                ci = next((k for k in range(len(cells[r]) - 1, -1, -1)
                           if cells[r][k] and str(cells[r][k]).strip()), None)
                if ci is not None:
                    cells[r][ci] = f"{cells[r][ci]} {fit[2]}"
                    break
        html = _render_fn_grid(cells, rowsgeo) if fit is not None else ""
        if html:
            pre, post = fit[0], fit[1]
            flush()
            plain.extend(line_records[i:i + pre])
            flush()                       # trimmed boundary lines stay prose
            parts.append(html)
            consumed.update(id(x) for x in run_grids)
            i = j - post                  # trailing trimmed lines re-enter
        else:                             # degenerate -> back to the heuristics
            consumed.update(id(x) for x in run_grids)
            plain.append(line_records[i])
            i += 1
    flush()
    return "\n".join(p for p in parts if p)


def _build_html_run(line_records) -> str:
    """Text-heuristic rendering for records not claimed by a gridline table.

    Prose lines become <p>; every table region (a footnote can quote SEVERAL
    rate tables, e.g. Division VI's individual + company tables) renders as a
    <div class="fn-table"> grid with its multi-line header assembled into
    header cells and each row's wrapped lines joined in reading order.
    Paragraph regions are additionally scanned for gridline-backed runs
    (see :func:`_render_grid_run`).
    """
    parts: list[str] = []
    i, n = 0, len(line_records)
    while i < n:
        found = _find_table_start(line_records, i)
        if found is None:
            parts += _paras_with_grids(line_records[i:])
            break
        tstart, skip_kw = found
        region_start = tstart + 1 if skip_kw else tstart
        # a table anchored on its NUMBERING row prints its column headers on
        # the immediately preceding lines (fn 521.1's "Person | Stock Fund |
        # Money market fund ..." block) -- pull column-shaped lines back into
        # the region so they render as header cells, not stray paragraphs
        words0 = line_records[tstart][1]
        if not skip_kw and words0 and \
                (_looks_like_number_row(words0) or _bare_number_row(words0)):
            while region_start > i:
                prev = line_records[region_start - 1]
                ptext, pwords = prev[0].strip(), prev[1]
                if (not pwords or _FN_INTRO.search(ptext)
                        or _QUOTE_INTRO_END.search(ptext)
                        or _segments(pwords) < 2):
                    break
                region_start -= 1
        parts += _paras_with_grids(line_records[i:region_start])
        table_html, nxt = _render_table_region(line_records, region_start)
        if table_html:
            parts.append(table_html)
            i = nxt
        else:   # not a real table after all -> the start line is a paragraph
            parts += _paras_with_grids(line_records[region_start:tstart])
            parts.append(_para(line_records[tstart][0]))
            i = tstart + 1
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# public entry
# ---------------------------------------------------------------------------

CONT_MARKER = "^cont"   # footnote text continued from the previous page


def _accept_marker(t: str, rest, accepted: set, has_lead: bool) -> bool:
    """Decide whether a candidate marker word really *starts* a footnote.

    Quoted amendment text inside a footnote carries its own superscript
    markers ("2[Provided that ...", "1[(ii) the rate ..."), and those can open
    a line at the left margin -- indistinguishable from a real marker by
    geometry alone.  Three evidence-backed rules separate them (verified
    against every anomalous marker sequence in the 802-page ordinance):

      * a "year" number (2019, 2020, ...) is quoted text, never a marker;
      * a bracketed marker whose number already appeared on this page is a
        nested citation inside quoted text (real markers never repeat with a
        bracket -- but *unbracketed* repeats do occur as misprints in the PDF
        and are kept, e.g. printed page 92's two "5" footnotes);
      * a bracketed marker before ANY real footnote on a page that opened
        mid-continuation is still inside the quotation (e.g. the exemption
        lists quoted across printed pages 573-577).

    Everything rejected here is folded into the footnote (or continuation)
    being read, so no text is ever dropped.
    """
    if is_year_like(t):
        return False                       # a quoted year, not a marker
    # A note's text begins with an edit verb ("Substituted", "Omitted", "Section
    # 36 omitted by ...").  It never begins with a conjunction or a preposition --
    # that is a WRAPPED PAGE RANGE whose leading number the geometry cannot tell
    # from a marker.  Measured on the Sales Tax 1st July 2015 edition, page 62:
    # notes 2 and 3 each wrap onto a third line reading
    #
    #     23 to 53 and this amendment was made through Finance (Amendment) ...
    #
    # -- the tail of "published in the Gazette ... at pages 23 to 53" -- so "23"
    # opened a bogus note TWICE, truncating both real notes.  The two impostors
    # carried identical text, the ``(ref, text)`` dedup then collapsed them into
    # one, and the edition reported 5 missing footnote words: this looked exactly
    # like a repeated-citation counting policy question and was not one.
    if rest:
        head = rest[0].text.strip().strip("―‖\"'([").lower()
        if head in ("to", "and", "or", "of", "at"):
            return False
    bracket = bool(rest) and rest[0].text.lstrip().startswith("[")
    if bracket and t in accepted:
        return False                       # nested repeat of an existing marker
    if bracket and not accepted and has_lead:
        return False                       # still inside a continuing quotation
    return True


def parse_footnotes(footnote_lines, grid_boxes=(), cal=None) -> list[Footnote]:
    """Turn footnote-zone lines into an ordered list of :class:`Footnote`.

    Lines that appear *before* the first marker are the tail of a footnote that
    began on the previous page; they are returned as a leading footnote with
    marker ``^cont`` so the caller can splice them onto the prior page's last
    footnote (see :func:`merge_footnote_continuations`).

    ``grid_boxes`` are the ``(top, bottom, cells)`` structures of gridline
    tables inside the footnote zone (quoted amendment tables); each record
    line carries the grid it falls inside, so :func:`_build_html` renders the
    run from the grid's real cell matrix instead of paragraphs.  The grid
    lives ON the record, so a footnote spliced across pages keeps it through
    re-rendering.
    """
    def in_grid(ln):
        for box in grid_boxes:
            if box[0] - 2 <= ln.top <= box[1] + 2:
                return box
        return None

    groups: list[dict] = []
    current: dict | None = None
    lead: list = []
    accepted: set = set()
    for ln in footnote_lines:
        words = _sorted_words(ln)
        if not words:
            continue
        first = words[0]
        left_max = cal.footnote_marker_x_max if cal else LEFT_MARGIN_MAX
        size_max = cal.footnote_marker_max_size if cal else 7.8
        is_cand = (_is_marker_word(first, len(words), size_max)
                   and first.x0 <= left_max)
        # Strip the trailing dot Customs and Federal Excise print after the
        # marker ("25.", "27a.") so the marker recorded here is the same token
        # the body cites inline ("27a[").  Without this the citation and the
        # note carry different keys and every footnote is orphaned.
        tok = marker_token(first.text) or first.text.strip()
        if is_cand and _accept_marker(tok, words[1:], accepted, bool(lead)):
            rest = words[1:]
            current = {"marker": tok, "lines": []}
            accepted.add(current["marker"])
            if rest:
                current["lines"].append((_join(rest), rest, in_grid(ln)))
            groups.append(current)
        elif current is not None:
            current["lines"].append((_join(words), words, in_grid(ln)))
        else:
            lead.append((_join(words), words, in_grid(ln)))  # pre-marker -> continuation

    footnotes: list[Footnote] = []
    if lead:
        footnotes.append(Footnote(marker=CONT_MARKER,
                                  text="\n".join(t for (t, *_) in lead).strip(),
                                  html=_build_html(lead), records=lead))
    for g in groups:
        text = "\n".join(t for (t, *_) in g["lines"]).strip()
        html = _build_html(g["lines"])
        footnotes.append(Footnote(marker=g["marker"], text=text, html=html,
                                  records=g["lines"]))
    return footnotes


def merge_footnote_continuations(page_footnotes: dict) -> None:
    """Splice each page's leading ``^cont`` fragment onto the previous page's
    last footnote, so footnotes spanning a page break aren't dropped.

    The merged footnote is re-rendered from its combined line records, so a
    table whose last row wraps onto the next page comes out as one table (row
    text joined) instead of a table followed by orphan paragraphs, and
    ``end_pdf_page`` records how far the footnote's text physically reaches --
    used to extend the owning section's ``end_page``.
    """
    last_fns = None
    last_pg = None
    for pg in sorted(page_footnotes):
        fns = page_footnotes[pg]
        if fns and fns[0].marker == CONT_MARKER:
            cont = fns.pop(0)
            # A continuation belongs to the PHYSICALLY PRECEDING page, not merely
            # to the previous page that happened to carry footnotes.  Where
            # footnotes are collected onto their own pages (the Customs Act), the
            # gap between two footnote-bearing pages can be 70 pages of body, and
            # splicing across it attached page 199's notes to a footnote on page
            # 129 -- which then dragged sections 144 and 145 to end_page 199 and
            # let the orphan net adopt four unrelated notes into them.
            adjacent = last_pg is not None and pg - last_pg <= 1
            target = _continuation_target(last_fns) if adjacent else None
            if target is not None:
                target.records = list(target.records or []) + list(cont.records or [])
                target.text = "\n".join(t for (t, *_) in target.records).strip()
                target.html = _build_html(target.records)
                target.end_pdf_page = pg
            else:            # nothing to splice onto -- keep the text visible
                fns.insert(0, cont)
        if fns:
            last_fns = fns
            last_pg = pg


_OPEN_CUE_RE = re.compile(r'(?:as follows|as under|namely|the following)\s*:?-?\s*["“]?\s*$',
                          re.IGNORECASE)


def _ends_open(fn) -> bool:
    """True if a footnote's text ends mid-quotation -- an "as follows:" cue with
    nothing after, or an unbalanced opening curly-quote / bracket.  Such a
    footnote is the one a following page's continuation belongs to (RC-4)."""
    t = (getattr(fn, "text", "") or "").rstrip()
    if not t:
        return False
    if _OPEN_CUE_RE.search(t):
        return True
    if t.count("“") > t.count("”"):
        return True
    return False


def _continuation_target(last_fns):
    """Pick which footnote of the previous page a continuation belongs to (RC-4).

    A cross-page footnote quote resumes the footnote that was left OPEN, which is
    not always the page's LAST footnote: on First-Schedule substitution pages a
    later, self-contained note ("Division VIII substituted ... 15%") can sit
    below the open one ("... read as follows:") whose quoted table overflows the
    page.  Prefer the last footnote that ends open; fall back to the last one."""
    if not last_fns:
        return None
    for fn in reversed(last_fns):
        if _ends_open(fn):
            return fn
    return last_fns[-1]


def _join(words) -> str:
    return " ".join(w.text for w in words).strip()
