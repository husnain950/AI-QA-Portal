"""Per-page geometric model and text-zone separation.

This module is where the four biggest QA defects are fixed, all of which come
from *not* separating the page into its real zones before reading text:

  * Running header  (top of page, e.g. "Chapter I - Preliminary______")
  * Body            (the actual legal text, font size ~10-12)
  * Footnote block  (bottom of page, font size ~7-8)
  * Footer page no. (very bottom, centred bare number, font size ~12)

Observed geometry (page box 504 x 648 pts):
    header   : top  < ~55
    footer #  : top  > ~600 and horizontally centred, pure integer
    footnotes : trailing lines whose max font size <= ~8.5
    body      : everything else (max line font size >= ~9.5)

Inline amendment markers such as the ``1`` in ``1[distribution]`` are font
size ~6-6.5 but they *share a line* with size-10 body text, so a line is
classified by its **maximum** font size -- keeping markers inside the body
while the pure size-8 footnote lines fall into the footnote zone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Private-use glyph the PDF uses for the footnote asterisk. QA: "Different
# Asterisk symbol is shown in JSON" -> normalise it to a plain "*".
PUA_ASTERISK = ""

HEADER_MAX_TOP = 55.0
FOOTER_MIN_TOP = 598.0
BODY_MIN_SIZE = 9.6        # a line with a word >= this is body
FOOTNOTE_MAX_SIZE = 9.5    # (informational) footnote text runs 7-8pt; zone
                           # splitting itself is done ONLY by the printed
                           # separator rule -- see build_page_model
MARKER_MAX_SIZE = 9.4      # an inline digit/* smaller than body text (10pt) is a
                           # superscript amendment marker.  Markers appear at
                           # 6.5-9pt (incl. bold ones); the old 7.6 cutoff missed
                           # the 8-9pt ones, which then leaked in as bold text.
LINE_TOL = 3.0             # vertical tolerance when grouping words into lines


def normalize_text(s: str) -> str:
    """Normalise problem glyphs and quotes coming out of the PDF."""
    if not s:
        return s
    s = s.replace(PUA_ASTERISK, "*")
    # a few other private-use bullets seen in these documents
    s = s.replace("", "*").replace("", " ")
    return s


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    size: float
    fontname: str
    space_before: bool = False   # a real space CHARACTER precedes this word

    @property
    def is_marker(self) -> bool:
        """True for an inline superscript footnote/amendment marker."""
        if self.size > MARKER_MAX_SIZE:
            return False
        t = self.text.strip()
        return t == "*" or t.isdigit() or (t.endswith("*") and t[:-1].isdigit())


@dataclass
class Line:
    top: float
    words: list = field(default_factory=list)

    @property
    def max_size(self) -> float:
        return max((w.size for w in self.words), default=0.0)

    @property
    def min_x0(self) -> float:
        return min((w.x0 for w in self.words), default=0.0)

    def text(self) -> str:
        return " ".join(w.text for w in sorted(self.words, key=lambda w: w.x0))


@dataclass
class Table:
    """A body table extracted from real gridlines (pdfplumber find_tables)."""
    top: float
    bottom: float
    html: str
    plain: str
    is_table: bool = True
    words: list = field(default_factory=list)   # empty -> duck-types as a Line
    # superscript citation markers found on the swallowed table lines: the
    # cell text loses word geometry, but the footnote CITATIONS anchored inside
    # the table must still bind their footnotes to the owning section/division
    marker_words: list = field(default_factory=list)

    @property
    def max_size(self) -> float:
        return 10.0

    @property
    def min_x0(self) -> float:
        return 0.0

    def text(self) -> str:
        return self.plain


@dataclass
class PageModel:
    index: int                 # 1-based PDF page number
    printed_page: int | None   # number shown in the footer, if any
    body_lines: list = field(default_factory=list)      # list[Line] (text only)
    footnote_lines: list = field(default_factory=list)   # list[Line]
    body_blocks: list = field(default_factory=list)      # list[Line | Table] in order
    footnote_tables: list = field(default_factory=list)  # [(top, bottom, cells)] of
                               # gridline tables inside the footnote zone --
                               # quoted amendment tables; used by footnotes.py
                               # to render those lines as fn-table grids


def _group_into_lines(words: list[Word]) -> list[Line]:
    # Membership compares against the NEAREST word already in the line, not the
    # line's first word: a raised superscript marker sorts first and would
    # otherwise anchor the line ~3pt high, pushing same-baseline words that
    # follow just past LINE_TOL onto a phantom second line (30.06.2024 p430:
    # "1[ 207. Income tax authorities.— (1) There shall ..." split so the
    # operative words landed before the heading and got lost to the previous
    # section).  Real line spacing (~12pt) keeps distinct lines unchainable.
    lines: list[Line] = []
    for w in sorted(words, key=lambda w: (w.top, w.x0)):
        placed = False
        for ln in lines:
            if min(abs(x.top - w.top) for x in ln.words) <= LINE_TOL:
                ln.words.append(w)
                placed = True
                break
        if not placed:
            lines.append(Line(top=w.top, words=[w]))
    lines.sort(key=lambda l: l.top)
    return lines


# footnote markers (7pt) + footnote text (8pt) sit at/below this; body prose is
# ~10pt, so it is what distinguishes a footnote-marker's following line from a
# body leading-amendment marker's (whose next line is 10pt body text).
FOOTNOTE_TEXT_MAX = 8.6


def _line_max_size(ln) -> float:
    return max((w.size for w in ln.words), default=99.0)


def _is_footnote_marker_line(ln) -> bool:
    """A lone small superscript digit at the left margin -- the "1"/"2"/... that
    introduces each footnote.  A body-table serial ("1.") carries a dot and sits
    at 8-9pt, so the bare-digit + <=7.8pt + left-margin triple test never mistakes
    a table row for a footnote."""
    ws = sorted(ln.words, key=lambda w: w.x0)
    if not ws:
        return False
    first, t = ws[0], ws[0].text.strip()
    return (first.x0 <= 82 and first.size <= 7.8
            and t.isdigit() and 1 <= len(t) <= 2)


def _is_amendment_note(text: str) -> bool:
    """True if the line reads as an amendment NOTE -- it contains an edit verb
    ("Inserted by...", "The word ... substituted", "Clause ... omitted", "... read
    as follows").  97.7% of real footnotes match; a body rate/penalty TABLE cell
    ("Where any person fails to furnish...") never does, so this is the signal
    that a marker block is footnotes and not a table."""
    return bool(_AMEND_VERB_RE.search(text.split("\n")[0]))


def _footnote_note_marker_tops(ordered) -> list[float]:
    """Tops of footnote-marker lines whose following line reads as an amendment
    NOTE.  This is footnote-specific: a body leading marker ("1[ 113. ...") is
    followed by body prose, and a penalty/rate table row by table text -- neither
    contains an edit verb -- so only genuine footnote markers qualify.
    """
    tops = []
    for i, ln in enumerate(ordered):
        if not _is_footnote_marker_line(ln):
            continue
        nxt = ordered[i + 1] if i + 1 < len(ordered) else None
        if (nxt is not None and _line_max_size(nxt) <= FOOTNOTE_TEXT_MAX
                and _is_amendment_note(nxt.text())):
            tops.append(ln.top)
    return tops


def _footnote_rule_tops(page) -> list[float]:
    """Candidate footnote-separator rule tops: a left-margin horizontal rule
    below the running header.  Widened from the old 100-235pt window to also
    accept the FULL-WIDTH (~360pt) rule the 2018-2020 editions draw; the header
    rule (top<=60) and indented table-cell borders (x0>80) are excluded.  Every
    candidate is VALIDATED against a marker block by ``_footnote_zone_top``."""
    cands = []
    segments = list(page.lines)
    for r in page.rects:
        if r.get("height", 9) < 2.0:
            segments.append({"x0": r["x0"], "x1": r["x1"], "top": r["top"],
                             "y0": r["y0"], "y1": r["y1"]})
    for s in segments:
        if abs(s["y0"] - s["y1"]) > 1.5:
            continue  # not horizontal
        x0, width, top = s["x0"], s["x1"] - s["x0"], s["top"]
        if 66 <= x0 <= 80 and 100 <= width <= 380 and top > 60:
            cands.append(top)
    return sorted(cands)


def _narrow_separator_top(page):
    """The modern footnote-separator rule: a left-margin (x0≈72) horizontal line
    ~1/3 text-width (100-235pt) below the header.  This is the ORIGINAL detector,
    preserved unchanged -- every 2018+ edition that prints this rule zones exactly
    as before, so the RC-1 fallback below can never perturb a working page."""
    cands = []
    segments = list(page.lines)
    for r in page.rects:
        if r.get("height", 9) < 2.0:
            segments.append({"x0": r["x0"], "x1": r["x1"], "top": r["top"],
                             "y0": r["y0"], "y1": r["y1"]})
    for s in segments:
        if abs(s["y0"] - s["y1"]) > 1.5:
            continue
        x0, width, top = s["x0"], s["x1"] - s["x0"], s["top"]
        if 68 <= x0 <= 78 and 100 <= width <= 235 and top > 60:
            cands.append(top)
    return min(cands) if cands else None


def _footnote_zone_top(page, lines):
    """The y at which the footnote zone begins, or None (whole page is body).

    PRIMARY: the modern narrow-margin separator rule (``_narrow_separator_top``),
    unchanged -- so editions that print it (all of 2021+, most 2018-2020 pages)
    zone exactly as before and cannot regress.

    FALLBACK (RC-1), only when NO narrow rule is found: the older editions either
    draw the separator FULL-WIDTH (~360pt, rejected by the narrow gate) or omit it
    entirely, leaking the footnote block into the body.  Recover it from a
    footnote-MARKER block at the page bottom -- honour a widened/full-width rule
    when a marker follows within ~60pt, else anchor at the topmost marker.  The
    marker test is strict (bare <=7.8pt left-margin digit whose next line is
    footnote text), so a rate table or a body leading-marker never triggers it.
    """
    ordered = sorted(lines, key=lambda ln: ln.top) if lines else []
    note_tops = _footnote_note_marker_tops(ordered)
    if note_tops:
        # A genuine footnote marker (a bare <=7.8pt left-margin digit whose next
        # line is an amendment NOTE -- an edit verb) anchors the zone directly: it
        # begins at the first marker, or -- to swallow the separator itself -- the
        # closest rule sitting AT/ABOVE it.  A rule BELOW the first marker is a
        # border of a footnote-quoted TABLE *inside* the zone and must never be
        # taken as the separator (real footnotes would leak into body, e.g.
        # Division XVII 31.12.2019, Division XIV 30.06.2020).  The amendment-note
        # requirement is what keeps a body penalty/rate table -- whose cells never
        # start with an edit verb -- from being mistaken for footnotes, so even a
        # SINGLE such marker is a reliable footnote signal.
        first = note_tops[0]
        rules_above = [rt for rt in _footnote_rule_tops(page) if rt <= first + 2]
        return max(rules_above) if rules_above else first
    # Fewer than 2 footnote markers: rely on the modern narrow separator rule,
    # rejected when it is really a table border above a bare structural heading
    # (RC-3, the Ninth Schedule return-form grid above "PART II").
    narrow = _narrow_separator_top(page)
    if narrow is not None and not _has_bare_struct_heading_below(ordered, narrow):
        return narrow
    return None


import re as _re

# edit verbs that mark a footnote NOTE (see _is_amendment_note)
_AMEND_VERB_RE = _re.compile(
    r"\b(?:substituted|inserted|omitted|added|deleted|re-?numbered|re-?lettered|"
    r"re-?cast|read as follows|shall be read)\b", _re.IGNORECASE)

# a BARE structural heading -- "PART II", "[Division IIA", "2[Division IIA]" --
# with NOTHING after the numeral.  A footnote that merely QUOTES such a heading
# continues with prose ("Division XIV substituted by...") and is small-font, so
# only a real body heading matches this at >=11pt.
_BARE_STRUCT_RE = _re.compile(
    r'^\s*[\d*\[\]“”"\s]{0,12}(?:PART|Division)[\s\-]+[IVXLC]+[A-Z]{0,3}\s*\]?$',
    _re.IGNORECASE)


def _has_bare_struct_heading_below(ordered, y) -> bool:
    """True if a bare >=11pt PART/Division heading sits below y -- the tell that a
    candidate "separator" is actually a table border clipping body structure."""
    for ln in ordered:
        if ln.top > y and _line_max_size(ln) >= 11.0 and _BARE_STRUCT_RE.match(ln.text()):
            return True
    return False

# A body line that is nothing but a leading-dot number (e.g. ".9230", the sole
# stray on printed page 1 inside section 2) is a PDF extraction artifact, not
# legal text: it is absent from the reference and matches no citation, value or
# code form.  Such a standalone line is dropped from the body zone so it never
# leaks into a section (guarded by the ``no_stray_dotnumber`` invariant).
_ARTIFACT_DOTNUM_RE = _re.compile(r"\.\d{2,}$")

# the raised "st/nd/rd/th" of "1st/2nd/3rd/30th", optionally carrying a closing
# quote extracted into the same tiny word ('th”')
_ORDINAL_RE = _re.compile(r'^(st|nd|rd|th)[”"’\']?$', _re.IGNORECASE)


def _is_bare_marker_token(t: str) -> bool:
    return t == "*" or t.isdigit()


_NUM_FRAG_RE = _re.compile(r"\d+[.,]?")


def _is_number_continuation(at: str, bt: str) -> bool:
    """A single number split mid-way by a font-subset flip ("200"+"5." -> "2005.").

    Passing ``extra_attrs=["fontname"]`` makes ``extract_words`` break a word
    wherever the embedded subset changes, and some editions scatter a year's
    glyphs across two ArialMT subsets ("200" in one, "5" in another), so the
    year is emitted as two touching fragments.  The all-digit LEFT fragment
    otherwise trips the bare-marker guard and the fragments never rejoin,
    leaving a spurious space ("Finance Act, 200 5.").  This lets the kern-merge
    bypass that guard when the left is all digits and the right is digits plus
    optional trailing punctuation -- a number, not two markers.  Real citation
    markers are raised/smaller superscripts already excluded by the geometry
    (``dtop``/``dsize``) test, and bracketed clause codes ("3[") are not pure
    digits, so both stay separate.
    """
    return at.isdigit() and bool(_NUM_FRAG_RE.fullmatch(bt))


def _merge_split_words(raw_words: list) -> list:
    """Re-join word fragments that pdfplumber splits apart.

    Passing ``extra_attrs`` makes ``extract_words`` split a word wherever the
    embedded font subset changes MID-WORD (this PDF flips between two ArialMT
    subsets constantly), yielding fragments like ``b|y`` and ``developmen|t``
    that sit at zero horizontal gap.  Ordinal superscripts (the small raised
    "th" of "30th") are likewise emitted as their own tiny word, and their
    raised ``top`` can drag them onto a neighbouring *line* (e.g. a footnote
    marker's), leaving a stray "th" paragraph and a "30 June" missing it.

    Two evidence-backed merges, applied before any line grouping:

      * kerning/font-split: same baseline, same size, touching (gap ~0);
      * ordinal superscript: "st|nd|rd|th" at smaller size, touching a word
        that ends in a digit.

    Bare digit / ``*`` tokens are never merged on either side -- they are (or
    neighbour) citation markers, which must stay separate words.
    """
    out = []
    for w in raw_words:
        if out:
            a, b = out[-1], w
            gap = float(b["x0"]) - float(a["x1"])
            # compare against A's LAST glyph run: after "31"+"st" the word's
            # trailing metrics are the superscript's, so "day" right after the
            # raised "st" is a genuine word boundary, not a kerning split
            a_size = a.get("_last_size", float(a["size"]))
            a_top = a.get("_last_top", float(a["top"]))
            dtop = abs(float(b["top"]) - a_top)
            at, bt = a["text"], b["text"]
            kern = (-1.0 <= gap <= 0.5 and dtop <= 0.3
                    and abs(a_size - float(b["size"])) <= 0.3
                    and not b.get("_space_before")
                    and (_is_number_continuation(at, bt)
                         or (not _is_bare_marker_token(at)
                             and not _is_bare_marker_token(bt))))
            ordinal = (bool(_ORDINAL_RE.match(bt))
                       and float(b["size"]) < a_size - 0.5
                       and at[-1:].isdigit()
                       and not b.get("_space_before")
                       and -1.0 <= gap <= 1.0 and dtop <= 2.5)
            if kern or ordinal:
                # a leading punctuation-only fragment ("(") can be drawn from a
                # bold font subset while the token's real glyphs are regular:
                # the marker "(1)" arrives split as bold "(" + regular "1)" and
                # would otherwise inherit the bracket's bold, rendering a
                # spurious <strong>(1)</strong> (s.8, 203G).  A token's weight
                # follows its first alphanumeric fragment, not a stray bracket;
                # a genuinely-bold marker keeps its bold because its DIGITS are
                # bold.
                if not any(c.isalnum() for c in at) and any(c.isalnum() for c in bt):
                    a["fontname"] = b.get("fontname", a.get("fontname", ""))
                a["text"] = at + bt
                a["x1"] = b["x1"]
                a["_last_size"] = float(b["size"])
                a["_last_top"] = float(b["top"])
                continue
        out.append(dict(w))
    return out


def _mark_space_before(raw_words: list, page) -> None:
    """Set ``_space_before`` on each raw word that a space CHARACTER precedes.

    Fully-justified lines compress inter-word gaps below the 2pt glue
    threshold ("credited to a suspense account ..." at ~1.6pt gaps), which
    used to jam whole lines into one run of letters.  The PDF's own space
    glyphs say exactly where word boundaries are -- a word with a real space
    in front of it must never be glued or merged to its predecessor.
    """
    from collections import defaultdict
    spaces = defaultdict(list)          # rounded top -> [x centers]
    for c in page.chars:
        if str(c.get("text", "")).isspace():
            spaces[round(float(c["top"]))].append(
                (float(c["x0"]) + float(c["x1"])) / 2.0)
    for w in raw_words:
        x0 = float(w["x0"])
        t = round(float(w["top"]))
        w["_space_before"] = any(
            x0 - 4.0 <= x <= x0 + 0.5
            for dt in (0, -1, 1, -2, 2, -3, 3)
            for x in spaces.get(t + dt, ()))


def build_page_model(page, index: int) -> PageModel:
    """Turn a pdfplumber page into a zoned :class:`PageModel`."""
    raw_words = page.extract_words(
        use_text_flow=False,
        keep_blank_chars=False,
        extra_attrs=["size", "fontname"],
    )
    _mark_space_before(raw_words, page)
    raw_words = _merge_split_words(raw_words)
    words = [
        Word(
            text=normalize_text(w["text"]),
            x0=float(w["x0"]),
            x1=float(w["x1"]),
            top=float(w["top"]),
            size=round(float(w["size"]), 1),
            fontname=w.get("fontname", ""),
            space_before=bool(w.get("_space_before")),
        )
        for w in raw_words
        if normalize_text(w["text"]).strip()
    ]

    lines = _group_into_lines(words)
    page_w = float(page.width)

    def _centred_int(ln) -> int | None:
        """The line's value if it is a centred bare integer, else None."""
        txt = ln.text().strip()
        if not txt.isdigit():
            return None
        center = (ln.min_x0 + max(w.x1 for w in ln.words)) / 2
        return int(txt) if abs(center - page_w / 2) < page_w * 0.30 else None

    # 1) strip running header.  First capture a centred bare-integer page number
    #    printed in the TOP margin: the pre-2021 editions (and the old
    #    TABLE-OF-CONTENTS-format ones) number their pages in the header, not the
    #    footer, so the footer scan below finds nothing and printed_by_page would
    #    be empty for the whole document -- collapsing every footnote ref onto the
    #    raw PDF-index fallback and duplicating schedule footnotes across leaves.
    #    Kept as a fallback only: modern editions have a text running-header (no
    #    bare integer) and a real footer number, so this never fires for them.
    header_printed = None
    for ln in lines:
        if ln.top < HEADER_MAX_TOP:
            v = _centred_int(ln)
            if v is not None:
                header_printed = v
                break
    lines = [ln for ln in lines if ln.top >= HEADER_MAX_TOP]

    # 2) capture + strip footer page number (centred bare integer near bottom)
    printed_page = None
    kept: list[Line] = []
    for ln in lines:
        if ln.top >= FOOTER_MIN_TOP:
            v = _centred_int(ln)
            if v is not None:
                printed_page = v
                continue  # drop the page-number line entirely
        kept.append(ln)
    lines = kept

    # 3) fall back to the header page number when the footer carried none
    if printed_page is None:
        printed_page = header_printed

    # 3) split body from footnotes.  Prefer the printed FOOTNOTE SEPARATOR RULE
    #    (a left-margin ~1/3-width horizontal line): everything above it is body,
    #    everything below is footnotes.  This is robust even when footnote tables
    #    are set at body font size (e.g. substituted rate tables spanning pages),
    #    which the font-size heuristic below cannot handle.
    # Footnotes exist on a page IF AND ONLY IF the printed separator rule
    # does (verified across all 802 pages: every one of the 713 pages with a
    # real footnote block prints the rule).  There is deliberately NO
    # font-size fallback: body tables are set at 8-9pt -- the same sizes as
    # footnote text -- so any size heuristic wholesale-misclassifies table
    # pages (the Twelfth Schedule and the section-182 penalty grid used to
    # walk into the footnote zone and splice themselves into the previous
    # page's footnotes as garbage legal text).
    sep_top = _footnote_zone_top(page, lines)
    if sep_top is not None:
        body_lines = [ln for ln in lines if ln.top < sep_top]
        footnote_lines = [ln for ln in lines if ln.top >= sep_top]
    else:
        body_lines = lines
        footnote_lines = []

    # 3b) drop stray leading-dot-number artifacts (".9230") from the body -- a
    #     standalone line that is not legal text and appears in no citation /
    #     value / code form.  Everything else is kept verbatim.
    body_lines = [ln for ln in body_lines
                  if not _ARTIFACT_DOTNUM_RE.fullmatch(ln.text().strip())]

    # 4) extract BODY tables from real gridlines.  Footnote-zone tables are
    #    not rendered here, but their bboxes are kept so footnotes.py can
    #    render the quoted lines inside them as fn-table grids.  Body table
    #    lines are removed from the line flow and replaced by a Table block.
    body_blocks, footnote_tables = _extract_body_tables(page, body_lines, sep_top)

    return PageModel(
        index=index,
        printed_page=printed_page,
        body_lines=body_lines,
        footnote_lines=footnote_lines,
        body_blocks=body_blocks,
        footnote_tables=footnote_tables,
    )


# Sentinel wrapping a citation marker inside table-cell text: it survives the
# html escaping and continuation-table merging that cell text goes through,
# and is expanded to a real <sup class="cite"> by builder._expand_table_cites
# once the footnote map is available.  Format: "\x01{pdf_page}.{marker}\x02".
CITE_SENT_RE_TEXT = r"\x01(\d+)\.([0-9*]{1,3})\x02"


def cite_sentinel(pdf_page: int, marker: str) -> str:
    return f"\x01{pdf_page}.{marker}\x02"


def _true_table_marker(w, dominant_size: float) -> bool:
    """A genuine superscript citation marker inside a table.

    Dense tables are set at 9pt -- below the absolute body-marker cutoff -- so
    every content digit ("650", "280", serial "85") would false-match.  Real
    markers are visibly SMALLER than the table's own text (6-6.5pt against
    9pt), so the test is relative; and footnote markers are small serials,
    never >= 100.
    """
    if not w.is_marker or w.size > dominant_size - 0.8:
        return False
    t = w.text.strip()
    return t == "*" or (t.isdigit() and int(t) < 100)


def _mark_cell_citations(t_obj, cells, markers, pdf_page):
    """Replace each marker's literal digit inside its cell with a sentinel.

    The marker word is located in the pdfplumber cell grid by geometry; inside
    the cell text the digit is glued to its amendment bracket ("1[ ]",
    "2[9405.1090"), so the bracket-adjacent occurrence is replaced.  When the
    occurrence can't be found the sentinel is prepended -- the citation stays
    visible, nothing is deleted.
    """
    import re as _re2
    for w in markers:
        tok = w.text.strip()
        cx, cy = (w.x0 + w.x1) / 2.0, w.top + 1.0
        loc = None
        for ri, row in enumerate(t_obj.rows):
            for ci, cbox in enumerate(row.cells):
                if cbox and cbox[0] <= cx <= cbox[2] and cbox[1] <= cy <= cbox[3]:
                    loc = (ri, ci)
                    break
            if loc:
                break
        if loc is None:
            continue
        ri, ci = loc
        if ri >= len(cells) or ci >= len(cells[ri]) or not cells[ri][ci]:
            continue
        cell = cells[ri][ci]
        sent = cite_sentinel(pdf_page, tok)
        pat = _re2.compile(r"(?<![\d.])" + _re2.escape(tok) + r"\s*(?=\[)")
        new, n = pat.subn(sent, cell, count=1)
        if n == 0:
            if cell.lstrip().startswith(tok):
                new = cell.replace(tok, sent, 1)
            else:
                new = sent + cell
        cells[ri][ci] = new


def _is_white_fill(o) -> bool:
    """A fill whose colour is pure white (invisible on the white page)."""
    c = o.get("non_stroking_color")
    if isinstance(c, (list, tuple)):
        vals = list(c)
    elif isinstance(c, (int, float)):
        vals = [c]
    else:
        return False
    return bool(vals) and all(abs(float(v) - 1.0) < 1e-6 for v in vals)


def _is_visible_ink(o) -> bool:
    """A drawn object that actually marks the page.

    Real ruled tables draw their gridlines/shading as stroked lines, curves,
    or filled rects in a non-white colour (the FBR grids render borders as
    thin black-filled rects).  Some source PDFs also lay per-line *white*
    fills behind justified paragraphs -- ``stroke=False, fill=True,
    non_stroking_color=1`` -- which are invisible but still expose four edges
    to ``find_tables()``.  Those must never count as gridlines.
    """
    kind = o.get("object_type")
    if kind in ("line", "curve"):
        return True
    if kind == "rect":
        if o.get("stroke"):
            return True
        return bool(o.get("fill")) and not _is_white_fill(o)
    return False


def _region_has_gridline_ink(page, bbox, pad: float = 2.0) -> bool:
    """True when some visible-ink object overlaps the candidate table's bbox.

    A ``find_tables()`` region assembled purely from invisible white fills has
    no real gridlines and is a false positive -- e.g. the section 114 (6A)
    sub-section and its provisos (pdf pp246-247), whose justified body text
    sits on per-line white background boxes and was otherwise shredded into
    phantom ``fbr-table``s.  The overlap test favours *keeping* genuine tables:
    a table can only be dropped when nothing visible is drawn anywhere across
    its whole area.
    """
    x0, top, x1, bottom = bbox
    for o in page.rects + page.lines + page.curves:
        if not _is_visible_ink(o):
            continue
        if (o["x1"] >= x0 - pad and o["x0"] <= x1 + pad and
                o["bottom"] >= top - pad and o["top"] <= bottom + pad):
            return True
    return False


def _extract_body_tables(page, body_lines, sep_top):
    """Split gridline tables into body blocks and footnote-zone bboxes.

    Returns ``(body_blocks, footnote_table_boxes)``: body blocks are Lines +
    Table objects in reading order; footnote-zone tables (quoted amendment
    tables below the separator rule) are returned as ``(top, bottom)`` bboxes
    for :func:`fbr_ingest.footnotes.parse_footnotes` to render as fn-tables.
    """
    from .tables import render_grid, is_header_signature
    try:
        found = page.find_tables()
    except Exception:
        found = []
    found = _heal_sliver_tables(page, found)
    # drop phantom grids built only from invisible white background boxes:
    # they have no drawn gridline anywhere in their region (see s.114 (6A)).
    found = [t for t in found if _region_has_gridline_ink(page, t.bbox)]
    cands = []      # (t_obj, cells, rowcells, top, bottom)
    fn_boxes = []   # footnote-zone table structures: (top, bottom, cells, rowcells)
    for t in found:
        x0, top, x1, bottom = t.bbox
        try:
            cells = t.extract()
        except Exception:
            continue
        ncol = max((len(r) for r in cells), default=0)
        if ncol < 2:
            continue  # not a real multi-cell table
        rowcells = [list(r.cells) for r in t.rows]
        if sep_top is not None and top >= sep_top - 2:
            # keep even single-row fragments: a quoted table's last row can
            # sit alone on the continuation page (fn 535.4 row 7, pdf p555)
            # and is re-joined to its table by footnotes._build_html
            fn_boxes.append((top, bottom, [list(r) for r in cells], rowcells))
            continue
        if len(cells) < 2:
            # a lone ruled row in the body is a table when it is a header box
            # whose data continues on the next page (the "S. No | Engine
            # capacity | Tax" box at the foot of pdf p554) OR a data-row
            # fragment that the continuation merge re-joins to the previous
            # page's table (the s.182 row-35 box, pdf p413); a fragment that
            # merges with neither is demoted back to text by the builder
            if not any((c or "").strip() for c in cells[0]):
                continue
        cands.append((t, [list(r) for r in cells], rowcells, top, bottom))

    if not cands:
        return list(body_lines), fn_boxes

    def cand_of(ln):
        for k, (_t, _c, _rc, t0, b0) in enumerate(cands):
            if t0 - 2 <= ln.top <= b0 + 2:
                return k
        return None

    # split swallowed line words per table; keep citation markers (relative
    # size test against the table's own dominant text size)
    swallowed_words: list[list] = [[] for _ in cands]
    kept = []
    for ln in body_lines:
        k = cand_of(ln)
        # never swallow a structural heading (a >=11pt PART/Division line) into a
        # table just because it grazes the bbox: it is a division boundary, not a
        # cell.  The First Schedule's "Division IIA" heading sits ~1pt below the
        # previous division's rate-table box (30.06.2019 / 31.12.2019, RC-3) and
        # was being consumed and dropped.
        if k is None or (_line_max_size(ln) >= 11.0
                         and _BARE_STRUCT_RE.match(ln.text().strip())):
            kept.append(ln)
        else:
            swallowed_words[k].extend(ln.words)

    tables = []
    for k, (t_obj, cells, rowcells, top, bottom) in enumerate(cands):
        words = swallowed_words[k]
        sizes = [w.size for w in words if any(c.isalpha() for c in w.text)]
        dominant = max(set(sizes), key=sizes.count) if sizes else 10.0
        markers = sorted((w for w in words if _true_table_marker(w, dominant)),
                         key=lambda w: (w.top, w.x0))
        # plain text stays pristine; the html cells carry the sentinels
        plain = "\n".join(" ".join((c or "") for c in row) for row in cells)
        _mark_cell_citations(t_obj, cells, markers, page.page_number)
        html = render_grid(cells, rowcells)
        if not html:
            kept.extend(ln for ln in body_lines
                        if cand_of(ln) == k)   # give its lines back to the body
            continue
        tables.append(Table(top=top, bottom=bottom, html=html, plain=plain,
                            marker_words=markers))
    return sorted(kept + tables, key=lambda b: b.top), fn_boxes


_SNAP_SETTINGS = {"snap_x_tolerance": 8, "snap_y_tolerance": 5}


def _sliver_count(t, min_w: float = 10.0) -> int:
    xs = sorted({e for row in t.rows for c in row.cells if c
                 for e in (c[0], c[2])})
    return sum(1 for a, b in zip(xs, xs[1:]) if b - a < min_w)


def _heal_sliver_tables(page, found):
    """Re-detect tables whose borders split into twin-stroke sliver columns.

    The builders/developers grids (pdf pp530-531) draw each border as two
    parallel ~7pt strokes, which the default strategy turns into 9/18-column
    grids with one row per text line.  Re-running detection inside the
    table's own bbox with snapped tolerances heals exactly those tables while
    leaving every well-formed table on the page untouched (page-wide snapping
    corrupts neighbouring healthy grids -- verified on p530's CGT table).
    """
    healed = []
    for t in found:
        if _sliver_count(t) < 2:
            healed.append(t)
            continue
        x0, top, x1, bottom = t.bbox
        try:
            crop = page.crop((max(0, x0 - 3), max(0, top - 3),
                              min(page.width, x1 + 3),
                              min(page.height, bottom + 3)))
            retries = [rt for rt in crop.find_tables(_SNAP_SETTINGS)
                       if _sliver_count(rt) == 0]
        except Exception:
            retries = []
        healed.extend(retries if retries else [t])
    return healed
