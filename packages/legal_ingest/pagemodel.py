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

from .grammar import folio_value, is_marker_text, is_year_like

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
    s = s.replace("\uf0b7", "*").replace("\uf020", " ")
    # Symbol/Wingdings LIST bullets.  A census of the whole corpus finds exactly
    # two private-use code points surviving into the output -- U+F0FA (3
    # occurrences) and U+F0A7 (2) -- and both open an item in ordinary prose:
    # "with a tax-wise breakdown as follows: <B> Income Tax: Rs.399.7 billion",
    # "including the following: <B> The Organization for Economic Cooperation".
    # A private-use code point renders as a box or as nothing outside the font
    # that defined it, so it must not reach legally binding output; a bullet is
    # what the page prints.  Conservation is unaffected: the audit counts
    # alphabetic tokens and a fixed punctuation set, and a bullet is in neither.
    s = s.replace("\uf0fa", "\u2022").replace("\uf0a7", "\u2022")
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
    # OCR provenance, set only for words recognised from a scan (see
    # ``ocr.align``).  ``needs_review`` means the two engines read this token
    # DIFFERENTLY and the higher-confidence reading was taken; ``conf`` is
    # "agreed" or the accepted engine's score.  They are carried on the word so
    # a leaf can declare which of its tokens are uncertain -- without them the
    # flags die here and a file admitted at, say, 85.2% agreement ships ~1,300
    # doubted tokens with nothing in the JSON saying which.
    needs_review: bool = False
    conf: object = None
    #: The reading the dual-engine comparison REJECTED, kept only where the two
    #: engines disagreed.  Empty on a text-layer document and on every agreed
    #: token.  A disagreement is already recorded as ``needs_review``, but a flag
    #: alone cannot arbitrate a SECTION CODE -- see ``discover._alt_code``
    #: (ledger P42), where the rejected reading is what puts a document's clauses
    #: back in order.
    alt: str = ""
    # Per-document marker size cutoff, set from Calibration at construction.
    # Carried on the word rather than read from a module global because body
    # size ranges from 9pt (Ordinance) to 12pt (all three Acts) across the
    # corpus, and ``is_marker`` is consulted from a dozen call sites that have
    # no calibration in scope.  A field keeps it exact without global state,
    # which would leak between documents when several are converted in one run.
    marker_max: float = MARKER_MAX_SIZE

    @property
    def is_marker(self) -> bool:
        """True for an inline superscript footnote/amendment marker.

        Goes through the shared grammar so a letter-suffixed marker is
        recognised: the Customs Act cites ``12a[``, ``27a[``, ``36c[`` inline and
        prints matching notes, but a bare ``isdigit()`` test rejects them, so
        those citations were never recorded and their notes came out orphaned.

        A four-digit YEAR is never a marker.  ``footnotes.py`` has always applied
        ``is_year_like`` when reading the footnote zone, but this property -- the
        one the inline renderer consults -- did not, so a year printed small
        inside an instrument's citation became a citation of its own: the Benami
        Transactions Act 2017 shipped ``the Banking Companies Ordinance,
        <sup class="cite">1.1962</sup> (LVII of 1962)``, an invented reference to
        a note that does not exist.  Ten editions reported **0.0%** of their
        citations resolving for this reason alone -- the unbound "citations" were
        years.  Real markers in this corpus reach 1027 (the Sales Tax editions
        number their notes past a thousand), well clear of the 1900-2099 band.
        """
        if self.size > self.marker_max:
            return False
        t = self.text.strip()
        if is_year_like(t):
            return False
        # A trailing DOT means this is a numbered heading, not an inline marker.
        # ``marker_token`` strips it on purpose -- in the footnote ZONE a note
        # prints as "14. Substituted by the Finance Act, 2019" -- but inline a
        # citation prints bare ("14[" or a raised "14"), never "14.".  Sharing the
        # grammar between the two contexts made every SECTION CODE on a scanned
        # page a citation: the Benami Transactions Act 2017 rendered 27 of them
        # (``8.14.``, ``12.23.``, ``14.27.``), each pointing at no footnote.
        if t.endswith("."):
            return False
        return is_marker_text(t) or (t.endswith("*") and t[:-1].isdigit())


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


def _is_footnote_marker_line(ln, cal) -> bool:
    """A footnote marker at the footnote block's left margin.

    Both gates are calibrated rather than absolute.  The Ordinance's literals
    (``x0 <= 82``, ``size <= 7.8``, ``t.isdigit()``, 1-2 digits) each fail
    somewhere in this corpus: Customs sets its footnote block at x0 129.6 and
    9.0pt, prints markers with a trailing dot and a lowercase suffix (``27a.``),
    and Sales Tax numbers them into the 800s -- three digits.
    """
    ws = sorted(ln.words, key=lambda w: w.x0)
    if not ws:
        return False
    first = ws[0]
    return (first.x0 <= cal.footnote_marker_x_max
            and first.size <= cal.footnote_marker_max_size
            and is_marker_text(first.text))


def _is_amendment_note(text: str) -> bool:
    """True if the line reads as an amendment NOTE -- it contains an edit verb
    ("Inserted by...", "The word ... substituted", "Clause ... omitted", "... read
    as follows").  97.7% of real footnotes match; a body rate/penalty TABLE cell
    ("Where any person fails to furnish...") never does, so this is the signal
    that a marker block is footnotes and not a table."""
    return bool(_AMEND_VERB_RE.search(text.split("\n")[0]))


def _footnote_note_marker_tops(ordered, cal) -> list[float]:
    """Tops of footnote-marker lines whose following line reads as an amendment
    NOTE.  This is footnote-specific: a body leading marker ("1[ 113. ...") is
    followed by body prose, and a penalty/rate table row by table text -- neither
    contains an edit verb -- so only genuine footnote markers qualify.
    """
    tops = []
    for i, ln in enumerate(ordered):
        if not _is_footnote_marker_line(ln, cal):
            continue
        # The note may begin on the marker's OWN line ("25. Inserted by the
        # Finance Act, 2003") rather than the next one -- that is how Customs
        # and Federal Excise set their footnotes, where the Ordinance always
        # broke the line after the marker.  Accept either.
        if _is_amendment_note(ln.text()):
            tops.append(ln.top)
            continue
        nxt = ordered[i + 1] if i + 1 < len(ordered) else None
        if (nxt is not None and _line_max_size(nxt) <= cal.footnote_text_max
                and _is_amendment_note(nxt.text())):
            tops.append(ln.top)
    return tops


def _size_zone_top(ordered, cal) -> float | None:
    """Zone split for documents that print NO separator rule (the Customs Act).

    Customs sets body at 12.0pt and footnotes at 9.0pt but draws no rule
    anywhere, and its footnotes routinely occupy WHOLE pages rather than a
    bottom strip -- so there is no separator to find and the marker-block
    anchor alone cannot tell a footnote-only page from a body page.

    A page reads body-first then footnotes, so the split is the single point that
    best separates body-size lines above from footnote-size lines below.  That is
    a one-dimensional changepoint fit: pick the ``k`` maximising

        (body-size lines before k) + (footnote-size lines from k on)

    A strict monotone suffix ("every line from here down is small") was the
    obvious formulation and it is wrong: footnotes quote the text they replaced,
    and a quotation is sometimes set at BODY size, so one such line near the
    bottom of a collector page defeated the whole test and the page came back as
    pure body -- page 37 of this edition leaked its entire footnote block
    (notes 10-24) into section 3AA's body, and every marker they annotate went
    unbound.  Scoring tolerates those intrusions without any tuned threshold,
    and still yields k=0 for a wholly-footnote page and k=n for a body page.

    The winning suffix must also LOOK like footnotes -- at least one amendment
    verb -- so a body page ending in a stray superscript cannot open a zone.
    """
    if not ordered:
        return None
    n = len(ordered)
    small = [_line_max_size(ln) <= cal.footnote_text_max for ln in ordered]
    # suffix_small[k] = number of footnote-size lines in ordered[k:]
    suffix_small = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix_small[i] = suffix_small[i + 1] + (1 if small[i] else 0)
    best_k, best_score, big_before = n, -1, 0
    for k in range(n + 1):
        score = big_before + suffix_small[k]
        if score > best_score:
            best_score, best_k = score, k
        if k < n and not small[k]:
            big_before += 1
    if best_k >= n:
        return None
    if not any(_is_amendment_note(ln.text()) for ln in ordered[best_k:]):
        return None
    return ordered[best_k].top


def _footnote_rule_tops(page, cal) -> list[float]:
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
        # Widened form of the calibrated window: accepts a full-width rule where
        # the narrow detector below wants the exact modal one.
        if (cal.rule_x0_lo - 4 <= x0 <= cal.rule_x0_hi + 4
                and cal.rule_w_lo <= width <= cal.rule_w_hi * 2.2
                and top > cal.header_max_top):
            cands.append(top)
    return sorted(cands)


def _narrow_separator_top(page, cal):
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
        if (cal.rule_x0_lo <= x0 <= cal.rule_x0_hi
                and cal.rule_w_lo <= width <= cal.rule_w_hi
                and top > cal.header_max_top):
            cands.append(top)
    return min(cands) if cands else None


def _footnote_zone_top(page, lines, cal):
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
    if cal.zone_mode == "none":
        # Calibration could not tell body from footnote text (two prose sizes
        # closer than SIZE_GAP_MIN and no margin rule).  Everything is body: the
        # 20 gazette Finance Acts genuinely print no footnotes, and where a
        # document does have some their text is misplaced rather than lost --
        # which ``no_footnote_text_in_body`` reports.
        return None
    if cal.zone_mode == "size":
        # No separator rule is printed anywhere in this document -- see
        # _size_zone_top.  The marker-block anchor below cannot substitute: it
        # finds the FIRST marker, which on a Customs footnote-only page is the
        # first line, and on a mixed page sits below body text it would then
        # have to guess the top of.
        return _size_zone_top(ordered, cal)
    note_tops = _footnote_note_marker_tops(ordered, cal)
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
        rules_above = [rt for rt in _footnote_rule_tops(page, cal) if rt <= first + 2]
        return max(rules_above) if rules_above else first
    # Fewer than 2 footnote markers: rely on the modern narrow separator rule,
    # rejected when it is really a table border above a bare structural heading
    # (RC-3, the Ninth Schedule return-form grid above "PART II").
    narrow = _narrow_separator_top(page, cal)
    if narrow is not None and not _has_bare_struct_heading_below(ordered, narrow, cal):
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


def _has_bare_struct_heading_below(ordered, y, cal) -> bool:
    """True if a bare >=11pt PART/Division heading sits below y -- the tell that a
    candidate "separator" is actually a table border clipping body structure."""
    for ln in ordered:
        if (ln.top > y and _line_max_size(ln) >= cal.body_size - 0.5
                and _BARE_STRUCT_RE.match(ln.text())):
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


def _reattach_raised_ordinals(raw_words: list) -> list:
    """Re-attach an ordinal suffix that sorted onto a NEIGHBOURING line.

    ``_merge_split_words`` compares STREAM-consecutive words, which is enough
    while the suffix stays next to its number.  It is not enough here.  Sales
    Tax Special Procedures 05.03.2015 p15 raises the "th" of "24th March" by
    3.48pt and draws it at FULL body size (8.04pt, not a reduced 5.04pt
    superscript).  Above pdfplumber's y-tolerance that raise makes the suffix
    its own line, so the stream order runs ``... '16.', 'th', 'Substituted'
    ...`` -- the "th" lands next to the footnote MARKER, 253pt away from the
    "24" it belongs to, and no stream-order rule can reach it.  The note then
    read "dated 24 March" and the orphan became a bare footnote continuation
    of its own ("14.^cont" = the single word "th").

    Position says what the stream cannot: the suffix's x0 (347.35) meets the
    number's x1 (347.38) to within 0.03pt, and their vertical boxes overlap.
    So this matches on geometry -- touching horizontally, overlapping
    vertically, and RAISED -- and leaves everything else to the caller.

    The raise requirement is what keeps a same-baseline "21 st" apart from a
    genuine superscript: FE 10.07.2014 p55 prints that one at dtop 0.00 with a
    real space glyph, and is rejected here on both counts.
    """
    nums = [w for w in raw_words if w["text"][-1:].isdigit()]
    if not nums:
        return raw_words
    dropped = set()
    for b in raw_words:
        if not _ORDINAL_RE.match(b["text"]) or b.get("_space_before"):
            continue
        b_x0, b_top = float(b["x0"]), float(b["top"])
        b_bot = float(b.get("bottom", b_top))
        best = None
        for a in nums:
            if a is b or id(a) in dropped:
                continue
            a_top = float(a["top"])
            a_bot = float(a.get("bottom", a_top))
            # touching horizontally, overlapping vertically, superscripted
            if abs(float(a["x1"]) - b_x0) > 1.5:
                continue
            # Superscript by SIZE or by RAISE -- the same disjunction the
            # stream-order rule uses, because the corpus prints both.  Sales Tax
            # Rules 2006 30-06-2025 p40 sets the table's "18th"/"21st" at
            # 6.48pt against 9.96pt body but lifts them only 0.75pt, so a raise
            # test alone misses them; STSP 05.03.2015 p15 lifts "24th" 3.48pt at
            # full 8.04pt size, so a size test alone misses that one.
            if not (float(b["size"]) < float(a["size"]) - 0.5
                    or b_top < a_top - 1.0):
                continue
            overlap = min(a_bot, b_bot) - max(a_top, b_top)
            if overlap <= 0 or overlap < 0.5 * max(1e-6, b_bot - b_top):
                continue
            best = a
            break
        if best is not None:
            best["text"] = best["text"] + b["text"]
            best["x1"] = b["x1"]
            best["_last_size"] = float(b["size"])
            best["_last_top"] = float(b["top"])
            dropped.add(id(b))
    if not dropped:
        return raw_words
    return [w for w in raw_words if id(w) not in dropped]


def _merge_split_words(raw_words: list, profile) -> list:
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
            # The Rules corpus raises its ordinal superscripts higher, and sets
            # them looser, than the Acts corpus these bounds were measured on.
            # Sales Tax Special Procedures 05.03.2015 draws them at dtop 3.34-5.69
            # (body 8.04pt, suffix 3.96-6.48pt) and one at gap 2.22 -- 19 ordinals
            # on 12 pages fell outside `dtop <= 2.5` / `gap <= 1.0`, and because a
            # raised "th" that misses this merge drags onto a NEIGHBOURING line it
            # did not merely read "11 th": it left a bare "th" as its own footnote
            # continuation (14.^cont) and stripped the suffix off "w.e.f. 1 st day".
            # What actually separates a superscript from a same-size "21 st" typo
            # is the size drop and the absence of a space GLYPH, both required
            # below and both unchanged -- FE 10.07.2014 p55 ("21 st June", equal
            # 8.04pt, dtop 0.00, a real space) and the "PTCL 2008 St. 1872"
            # citations are still rejected on those two tests, not on geometry.
            ordinal = (bool(_ORDINAL_RE.match(bt))
                       and float(b["size"]) < a_size - 0.5
                       and at[-1:].isdigit()
                       and not b.get("_space_before")
                       # Lower bound is fixed at -1.0 for every corpus: a NEGATIVE
                       # gap is overlap, and no corpus overlaps a suffix further.
                       # Only the upper bound and the raise vary -- see `profiles`.
                       and -1.0 <= gap <= profile.ordinal_gap_max
                       and dtop <= profile.ordinal_dtop_max)
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

    The space is matched against the word's whole vertical BOX (top..bottom,
    plus 3pt of slack above for a raised neighbour), not a fixed row window:
    the space that FOLLOWS A SUPERSCRIPT is drawn at the superscript's own
    raised baseline and intermediate size, so a +/-3 row window misses it --
    on p185 of the 2008 Customs edition "31st day" has its space at top 279.6
    size 8 while "day" sits at top 276.5 size 12, and missing it left the
    1.98pt gap under the 2pt glue threshold: the output read "31stday".

    Horizontally the space is matched by its RIGHT EDGE, because the space that
    precedes a word ENDS where the word begins -- that is exact and independent
    of the point size, where the old "centre within 4pt to the left" reach was
    calibrated on 12pt prose and far too wide for the 6pt footnotes of the Sales
    Tax editions: there (STA 30-06-2025 p25) the space preceding "2" has its
    centre 4.0pt left of the superscript "nd", so "nd" was marked
    ``_space_before`` and ``_merge_split_words`` refused to rejoin the ordinal --
    25 footnotes read "dated 2 nd November" / "w.e.f 1 st day".

    The +/-1.5pt slack is a real metric, not a fudge: some editions draw the
    space glyph WIDER than its advance, so it overruns the following word by a
    consistent 0.6pt (FEA 07.05.2024 p15, "correct any omission ..." -- with a
    tighter upper bound every word on such a line jams into one token), while
    the 6pt Sales Tax case it must still reject is 3.2pt away.
    """
    from collections import defaultdict
    spaces = defaultdict(list)          # rounded top -> [(x right edge, exact top)]
    for c in page.chars:
        if str(c.get("text", "")).isspace():
            t = float(c["top"])
            spaces[round(t)].append((float(c["x1"]), t))
    for w in raw_words:
        x0 = float(w["x0"])
        lo = float(w["top"]) - 3.0
        hi = max(float(w.get("bottom", w["top"])), float(w["top"]) + 3.0)
        w["_space_before"] = any(
            lo <= ct <= hi and x0 - 1.5 <= x1 <= x0 + 1.5
            for dt in range(round(lo), round(hi) + 1)
            for (x1, ct) in spaces.get(dt, ()))


def _page_is_scan(page, cover: float = 0.5,
                  ink_cover: float = 0.9, min_page: float = 0.2) -> bool:
    """True when the page's CONTENT is an image, i.e. OCR can add something.

    ``ocr.page_needs_ocr`` only measures how LITTLE text a page carries, so it
    also fires on a legitimately sparse text-layer page -- and there OCR is not
    a recovery but a loss: rasterising the page and re-reading it REPLACES an
    exact text layer with a recogniser's guess.  Measured on the 2008 Customs
    edition, whose four "needs OCR" pages (23, 71, 198, 241) carry 139/76/160/24
    characters of real text and **zero images**: p23 is the last TOC page, p241
    the closing page.  Nothing there is scanned, and OCR of p23 already came
    back with "ACT,1969" glued.  So an image is required -- that is what a scan
    is -- and a page with no image can never reach either test below.

    Two tests, because "half the SHEET" alone missed the largest scanned file in
    the corpus.  Finance Act 2025 is 292 scanned pages, and on every one the
    image covers 38-40% of the sheet: measured on p5, page 612x792, image
    x127-484 / y108-633, while the page's entire text layer is 11 words at
    y85-95 -- the running header, sitting ABOVE the image.  The image is the
    whole content and covers 95% of the page's INK, but only 0.39 of its paper,
    because a gazette page is mostly margin.  At ``cover=0.5`` that returned
    False 292 times, so the pipeline never OCR'd a page, wrote 0 characters, and
    NEW-1's abort never fired -- an abort on failed OCR cannot fire when OCR is
    never attempted.  ``ocr.scanned_pages`` shares this function, so the
    fidelity sweep was blind to the same 292 pages.

    Hence the second test: images covering ``ink_cover`` of the page's ink
    bounding box (the union of its words and images) are the content, whatever
    fraction of the paper they happen to occupy.  They are taken TOGETHER, since
    a scanner may slice one body into stacked strips -- Finance Act 2025 p291
    carries the same x127-485 body block as its neighbours cut at y327 into two
    images of 0.16 and 0.26 of the sheet, and tested one at a time neither is
    the content while together they are all of it.  ``min_page`` applies to
    their SUMMED area, so a few scattered small marks cannot qualify merely by
    spanning a wide union box, and a page whose only mark is a small decorative
    image cannot qualify merely by being trivially 100% of its own ink -- OCR
    would return nothing there and ``build_page_model`` would abort the
    document.

    Note the CALLER ands this with ``page_needs_ocr`` (< 200 chars), so a page
    carrying a big figure AND real body text is already excluded by text volume;
    this function only has to answer "is the content an image".
    """
    try:
        area = float(page.width) * float(page.height)
        boxes = []
        for im in page.images:
            boxes.append((float(im["x0"]), float(im["top"]),
                          float(im["x1"]), float(im["bottom"])))
        if not boxes:
            return False
        for x0, top, x1, bottom in boxes:
            if abs(x1 - x0) * abs(bottom - top) >= cover * area:
                return True
        ink = list(boxes)
        for w in page.extract_words():
            ink.append((float(w["x0"]), float(w["top"]),
                        float(w["x1"]), float(w["bottom"])))
        ink_area = ((max(b[2] for b in ink) - min(b[0] for b in ink))
                    * (max(b[3] for b in ink) - min(b[1] for b in ink)))
        if ink_area <= 0:
            return False
        union = ((max(b[2] for b in boxes) - min(b[0] for b in boxes))
                 * (max(b[3] for b in boxes) - min(b[1] for b in boxes)))
        summed = sum(abs(b[2] - b[0]) * abs(b[3] - b[1]) for b in boxes)
        if union >= ink_cover * ink_area and summed >= min_page * area:
            return True
    except Exception:                                   # pragma: no cover
        return False
    return False


_FOLIO_RE = _re.compile(r"\d+")


def _is_header_line(ln, cal) -> bool:
    """Whether a line in the header BAND is really the running header.

    Position alone is not enough, and ledger **P37** is what that costs.  The
    band is derived from where the running header prints (``header_max_top`` is
    the median header top plus 6pt), and every line above it used to be dropped
    unconditionally.  On a page that prints NO running header the content starts
    higher, so the band eats real statute: page 61 of Federal Excise 01.07.2017
    opens

        THIRD SCHEDULE                     top = 26.3
        (Conditional exemptions) [See      top = 38.6
        Sub-section (1) of section 16]     top = 51.3

    against ``header_max_top = 42.6``, so **the schedule's whole title block was
    discarded** and its content was appended to the SECOND SCHEDULE.  The same
    two pages in the 11th March 2019 edition do it too.

    That loss is invisible to the conservation audit, which strips the identical
    band on the source side and therefore never counts the words as missing --
    the exact inverse of P16, where an UNDETECTED header sat in the body zone and
    was counted as lost law.  Both are the same mistake: deciding what a line is
    from where it sits instead of from what it says.

    So a band line is dropped only when it IS the header: its folio-normalised
    text is one of the recurring header strings the calibration measured, or it
    is a bare folio.  When no header was detected at all, ``header_keys`` is
    empty and the positional fallback stands unchanged -- there is nothing to
    match against, and that path is already the conservative 5.5% band.
    """
    if ln.top >= cal.header_max_top:
        return False
    keys = getattr(cal, "header_keys", ()) or ()
    if not keys:
        return True                       # no header detected: positional band
    txt = ln.text().strip()
    if not txt:
        return True
    return _FOLIO_RE.sub("#", txt) in keys or not any(c.isalpha() for c in txt)


def build_page_model(page, index: int, cal, pdf_path: str | None = None,
                     ocr_sink: list | None = None) -> PageModel:
    """Turn a pdfplumber page into a zoned :class:`PageModel`.

    ``pdf_path`` enables OCR for SCANNED pages (``legal_ingest.ocr``).  The
    trigger is per PAGE, not per file: Finance Act 2025 lays a real text layer
    (its running header) over a scanned body, so a per-file test misclassifies
    it, and six Customs/FEA editions are text-layer documents with three or four
    scanned pages in the middle whose text is otherwise simply absent.

    ``ocr_sink`` collects the :class:`ocr.PageOCR` of every page OCR'd here, so
    the caller can score the file's fidelity from THIS pass instead of running
    a second one.  ``ocr.page_fidelity`` re-OCRs every page from scratch, which
    on Finance Act 2025 would mean 584 page recognitions to ship 292.
    """
    ocr_words = None
    if pdf_path and _page_is_scan(page):
        # An image-backed page is OCR'd REGARDLESS of how much text it carries.
        # The condition here used to be ocr.page_needs_ocr (< 200 chars), which
        # asks "is text missing?" -- but when the content is an image, any text
        # present is not typesetting, it is somebody else's OCR, and its VOLUME
        # says nothing about whether it is right.  The three Finance
        # (Supplementary) Acts are full-page scans (coverage 1.0) shipping
        # 800-1552 characters per page of a bad embedded recognition: "Sales Tax
        # Act, 1S90", "unless specified othenvise", "N o.F.22 (61 I 2O23-Legis",
        # "Februaqr", "THE FINANCE (SUPPLEMENTARYI ACT. 2023".  Being over the
        # 200-char line, they were never OCR'd and that was trusted as statute.
        #
        # The embedded layer does NOT get a vote.  The standing decision is
        # dual-engine BY AGREEMENT, and an unknown third-party recognition
        # carrying no per-token confidence cannot be weighed against two engines
        # that do.  So the two engines decide the text, and if they cannot agree
        # well enough the fidelity gate in pipeline.run refuses the file -- the
        # failure mode is "refuse", never "ship worse".
        from . import ocr as _ocr
        # A page selected for OCR that then fails must ABORT the document.
        # Swallowing the error and falling through to extract_words() is silent
        # data loss of the worst kind: on a scan that call returns almost
        # nothing, so the conversion "succeeds" and writes a JSON with the
        # statute missing.  Finance Act 2025 wrote 0 characters from 292 pages
        # exactly this way, and reported success.
        try:
            page_ocr = _ocr.ocr_page(pdf_path, index)
        except Exception as exc:
            raise RuntimeError(
                f"OCR failed on page {index} of {pdf_path!r}: {exc}. This "
                f"page carries no usable text layer, so refusing to emit a "
                f"document that would silently omit it."
            ) from exc
        ocr_words = page_ocr.words
        if ocr_sink is not None:
            ocr_sink.append(page_ocr)
        if not ocr_words:
            raise RuntimeError(
                f"OCR returned no words for page {index} of {pdf_path!r}, "
                f"which has no text layer either -- refusing to emit a "
                f"document that would silently omit this page.")
    if ocr_words is not None:
        # ocr.align already set _space_before from the bbox gaps; _mark_space_before
        # reads page.chars, which a scan does not have, and would clear them all.
        raw_words = ocr_words
    else:
        raw_words = page.extract_words(
            use_text_flow=False,
            keep_blank_chars=False,
            extra_attrs=["size", "fontname"],
        )
        _mark_space_before(raw_words, page)
    if cal.profile.reattach_raised_ordinals:
        raw_words = _reattach_raised_ordinals(raw_words)
    raw_words = _merge_split_words(raw_words, cal.profile)
    words = [
        Word(
            text=normalize_text(w["text"]),
            x0=float(w["x0"]),
            x1=float(w["x1"]),
            top=float(w["top"]),
            size=round(float(w["size"]), 1),
            fontname=w.get("fontname", ""),
            space_before=bool(w.get("_space_before")),
            marker_max=cal.marker_max_size,
            needs_review=bool(w.get("needs_review")),
            conf=w.get("conf"),
            alt=_rejected_reading(w),
        )
        for w in raw_words
        if normalize_text(w["text"]).strip()
    ]

    lines = _group_into_lines(words)
    page_w = float(page.width)

    def _centred_int(ln) -> int | None:
        """The folio this line carries, in any form this corpus prints, else None.

        Must agree with ``calibrate.folio_value``, which derives the document's page
        offset from the same lines: if the two read different forms, the offset comes
        from one set of pages and the per-page number from another, and the mismatch
        shows up as wrong footnote refs on exactly the pages where they differ.

        Centring is required only of the BARE form. A running title plus a folio
        ("Income Tax Rules, 2002    289") spans the text width and is centred by
        accident at best; that form is identified by its shape instead.
        """
        txt = ln.text().strip()
        value = folio_value(txt, cal.profile)
        if value is None:
            return None
        if txt.isdigit():
            center = (ln.min_x0 + max(w.x1 for w in ln.words)) / 2
            if abs(center - page_w / 2) >= page_w * 0.30:
                return None
        return value

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
        if ln.top < cal.header_max_top:
            v = _centred_int(ln)
            if v is not None:
                header_printed = v
                break
    lines = [ln for ln in lines if not _is_header_line(ln, cal)]

    # 2) capture + strip footer page number (centred bare integer near bottom)
    printed_page = None
    kept: list[Line] = []
    for ln in lines:
        if ln.top >= cal.footer_min_top:
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
    # On an OCR'd page the SIZE signal does not exist.  hOCR reports one size per
    # token, derived from its bounding box, so a line without descenders measures
    # smaller than one with them -- there is no body/footnote bimodality to split
    # on, only noise.  ``_size_zone_top``'s own amendment-verb guard cannot catch
    # this on an amending Act, because its clauses genuinely say "shall be
    # substituted": Finance Act 2025 put **208 lines in the footnote zone against
    # 70 in the body** over its first 12 pages, median height 0.43 of the page and
    # 60% of them above the middle, so its own clauses never became sections
    # (2 from 292 pages) and 446 words never reached a leaf (ledger P14).
    #
    # Measured across the corpus, this changes almost nothing else: of the wholly
    # scanned editions, Benami 2017, FA2023, Tax Laws (Amdt) 2023 emit ZERO
    # footnotes already, FA2013 emits 37 characters, Tax Laws 2020 136, ITA (3rd
    # Amdt) 2016 150, FSupp 2022 28, FA2011-12 4 KB and FA2014 6.8 KB -- against
    # FA2025's 134 KB.  Where a scan does carry real notes their text becomes
    # MISPLACED rather than lost (conservation stays 100%) and
    # ``no_footnote_text_in_body`` reports it, which is the same trade
    # ``zone_mode="none"`` already makes.  A printed separator RULE is still
    # honoured on a scan -- that is geometry, not size.
    if ocr_words is not None and cal.zone_mode == "size":
        sep_top = None
    else:
        sep_top = _footnote_zone_top(page, lines, cal)
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
    body_blocks, footnote_tables = _extract_body_tables(
        page, body_lines, sep_top, folio=printed_page,
        footer_min_top=cal.footer_min_top)

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


def _rejected_reading(w: dict) -> str:
    """The engine reading that lost the dual-engine comparison, or "".

    ``ocr.align`` records both engines' text on every word it emits and keeps the
    higher-confidence one.  Only a DISAGREEMENT is interesting here, and only its
    losing side: the winner is already ``w["text"]``.
    """
    if not w.get("needs_review"):
        return ""
    accepted = (w.get("text") or "").strip()
    for key in ("tesseract", "rapidocr"):
        other = (w.get(key) or "").strip()
        if other and other != accepted:
            return other
    return ""


#: A drawn rule is a hair thick.  Measured over every real ruled table in
#: the corpus: the thickest visible-ink object is 1.2pt in its short
#: dimension, while a per-line highlight box is ~14pt (ledger P40).
_RULE_MAX_THICKNESS = 2.5


def _is_visible_ink(o) -> bool:
    """A drawn object that actually marks the page.

    Real ruled tables draw their gridlines/shading as stroked lines, curves,
    or filled rects in a non-white colour (the FBR grids render borders as
    thin black-filled rects).  Some source PDFs also lay per-line *white*
    fills behind justified paragraphs -- ``stroke=False, fill=True,
    non_stroking_color=1`` -- which are invisible but still expose four edges
    to ``find_tables()``.  Those must never count as gridlines.

    Neither must a HIGHLIGHT.  Ledger **P40**: the Federal Excise 11-03-2019 and
    01-07-2014 editions mark their amended passages in yellow, and a yellow box
    is a filled unstroked rect in a very non-white colour.  Page 30 draws 49
    per-line background boxes; 12 of them are yellow highlights, so every one of
    the six phantom grids ``find_tables`` built there "proved" its gridlines and
    survived -- turning four pages of prose into `fbr-table`s that scrambled the
    citation markers and dropped ``beverages] or cigarettes 2`` from section 26's
    html altogether.

    A gridline is THIN.  Measured over the corpus's real ruled tables -- Sales
    Tax 30.06.2022 pages 78 and 80 (67 of 67 and 100 of 100 drawn objects),
    Federal Excise 30-06-2025 page 89 (2 of 2) -- every visible-ink object is at
    most 1.2pt in its short dimension; the highlights are ~14pt, the height of a
    line of type.  So an unstroked fill counts only when one of its sides is
    within a rule's width.  A stroked object keeps counting whatever its size:
    there the PDF has declared it a drawn border.
    """
    kind = o.get("object_type")
    if kind in ("line", "curve"):
        return True
    if kind == "rect":
        if o.get("stroke"):
            return True
        if not o.get("fill") or _is_white_fill(o):
            return False
        try:
            short = min(abs(float(o["x1"]) - float(o["x0"])),
                        abs(float(o["bottom"]) - float(o["top"])))
        except (KeyError, TypeError, ValueError):       # pragma: no cover
            return True
        return short <= _RULE_MAX_THICKNESS
    return False


def _region_has_gridline_ink(page, bbox, pad: float = 2.0,
                             sep_top: float | None = None) -> bool:
    """True when some visible-ink object overlaps the candidate table's bbox.

    A ``find_tables()`` region assembled purely from invisible white fills has
    no real gridlines and is a false positive -- e.g. the section 114 (6A)
    sub-section and its provisos (pdf pp246-247), whose justified body text
    sits on per-line white background boxes and was otherwise shredded into
    phantom ``fbr-table``s.  The overlap test favours *keeping* genuine tables:
    a table can only be dropped when nothing visible is drawn anywhere across
    its whole area.

    ``sep_top`` (given for BODY candidates only) excludes the footnote separator
    rule from counting as gridline ink.  That rule is drawn a few points below
    the last body line, so a phantom table whose bbox reaches the bottom of the
    body zone "proved" its gridlines with it: on p69 of FEA 07.05.2024, 21 rows
    of white per-paragraph fills became one 2-column table that swallowed the
    whole of ss.48, 49 and 50 into a single cell -- s.48's html lost its entire
    body, ss.49/50 became stubs, and all six of the page's notes piled onto s.48.
    """
    x0, top, x1, bottom = bbox
    for o in page.rects + page.lines + page.curves:
        if not _is_visible_ink(o):
            continue
        if sep_top is not None and float(o["top"]) >= sep_top - 2:
            continue
        if (o["x1"] >= x0 - pad and o["x0"] <= x1 + pad and
                o["bottom"] >= top - pad and o["top"] <= bottom + pad):
            return True
    return False


def _is_folio_row(row, rowcells, page_w, folio, footer_min_top) -> bool:
    """Whether a table row is just the page's running FOLIO, not statute.

    The line-level footer strip above cannot see this: ``find_tables`` re-reads
    the page, so a grid whose last row reaches into the bottom margin picks the
    folio back up as a cell.  Measured on the Sales Tax section 33 penalty table,
    which spans pages 72-82: page 73's folio landed between "...whichever is
    higher." and row 17, and ``inv_no_page_number_bleed`` reports it on four
    editions.

    Deliberately narrow, because a tariff table's own cells are numbers too: the
    row must sit in the footer margin, carry exactly one non-empty cell, that cell
    must be the folio this page printed, and it must be centred -- the same three
    conditions ``_centred_int`` and the line strip already use together.
    """
    if folio is None or footer_min_top is None:
        return False
    if row.bbox[1] < footer_min_top:
        return False
    texts = [(c or "").strip() for c in rowcells if (c or "").strip()]
    if len(texts) != 1 or not texts[0].isdigit() or int(texts[0]) != folio:
        return False
    x0, x1 = row.bbox[0], row.bbox[2]
    return abs((x0 + x1) / 2 - page_w / 2) < page_w * 0.30


# Never swallow a numbered section/clause heading into a table.  Ledger: Finance
# Act 2022 page 3 -- ``2. Amendments of Customs Act, 1969 ...`` sits just below
# the continued Petroleum Levy schedule table; ``cand_of`` grazed it into the
# bbox and the clause vanished from ``body_refs`` (same fate for clauses 5 and 6
# later in the Act).  The PART/Division guard below already covers structural
# captions; this covers ``N. Title.—`` clause starts of the same size as body.
_CLAUSE_HEAD_RE = _re.compile(
    r"^\s*(?:[\d*]{1,3}\s+)?\[?\s*\d{1,3}[A-Z]{0,3}\s*\.\s+\S"
)
_CLAUSE_HEAD_DASH_RE = _re.compile(r"[.,]\s*[—–―─\-]")


def _is_clause_heading_line(ln) -> bool:
    t = (ln.text() or "").strip()
    return bool(_CLAUSE_HEAD_RE.match(t) and _CLAUSE_HEAD_DASH_RE.search(t[:160]))


def _extract_body_tables(page, body_lines, sep_top, folio=None,
                         footer_min_top=None):
    """Split gridline tables into body blocks and footnote-zone bboxes.

    Returns ``(body_blocks, footnote_table_boxes)``: body blocks are Lines +
    Table objects in reading order; footnote-zone tables (quoted amendment
    tables below the separator rule) are returned as ``(top, bottom)`` bboxes
    for :func:`legal_ingest.footnotes.parse_footnotes` to render as fn-tables.
    """
    from .tables import render_grid
    try:
        found = page.find_tables()
    except Exception:
        found = []
    found = _heal_sliver_tables(page, found)
    # drop phantom grids built only from invisible white background boxes:
    # they have no drawn gridline anywhere in their region (see s.114 (6A)).
    found = [t for t in found
             if _region_has_gridline_ink(
                 page, t.bbox,
                 # a candidate that STARTS in the body must show its ink in the
                 # body zone; a footnote-zone table keeps the unrestricted test
                 sep_top=(sep_top if sep_top is not None
                          and t.bbox[1] < sep_top - 2 else None))]
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
        rows = list(t.rows)
        if len(rows) == len(cells):
            keep = [i for i, r in enumerate(rows)
                    if not _is_folio_row(r, cells[i], page.width, folio,
                                         footer_min_top)]
            if len(keep) != len(rows):
                cells = [cells[i] for i in keep]
                rows = [rows[i] for i in keep]
                if not cells:
                    continue
        rowcells = [list(r.cells) for r in rows]
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
        # Same for ``N. Title.—`` clause starts (FA2022 clauses 2/5/6).
        if (k is None
                or (_line_max_size(ln) >= 11.0
                    and _BARE_STRUCT_RE.match(ln.text().strip()))
                or _is_clause_heading_line(ln)):
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


def _demo() -> None:
    """Self-check for the word-boundary metrics, on measured PDF geometry.

    ``_mark_space_before`` is a three-way calibration, and each of the three
    cases below broke the other two at some point.  Every number here was read
    off the source with ``page.chars``; the fake page is just a carrier.
    """
    class _P:
        def __init__(self, chars):
            self.chars = chars

    def sp(x0, x1, top, bottom=None):
        return {"text": " ", "x0": x0, "x1": x1, "top": top,
                "bottom": bottom if bottom is not None else top + 12.0}

    def wd(x0, x1, top, bottom, size):
        return {"text": "w", "x0": x0, "x1": x1, "top": top, "bottom": bottom,
                "size": size}

    # 1) Customs 2008 p185 "31st day": the space after the superscript "st" is
    #    drawn at the SUPERSCRIPT's raised baseline (279.6) and an intermediate
    #    size, 3.15pt off "day"'s own top -- outside any +/-3 row window.
    w = wd(110.88, 128.22, 276.49, 288.49, 12.0)
    _mark_space_before([w], _P([sp(108.90, 110.90, 279.64, 287.62)]))
    assert w["_space_before"], "31st|day: raised space missed -> '31stday'"

    # 2) Sales Tax 30-06-2025 p25, 6pt footnote "2nd November": the space that
    #    precedes "2" must NOT be attributed to the superscript "nd", or the
    #    ordinal never rejoins ("dated 2 nd November").
    w = wd(228.65, 232.55, 563.13, 567.09, 3.96)
    _mark_space_before([w], _P([sp(223.98, 225.48, 563.57, 569.57)]))
    assert not w["_space_before"], "2nd: previous word's space claimed by 'nd'"

    # 3) FEA 07.05.2024 p15: this edition draws the space glyph 0.6pt WIDER than
    #    its advance, so it overruns the next word; too tight an upper bound
    #    jams the whole line ("correctanyomissionorwrong...").
    w = wd(157.22, 173.18, 232.65, 244.65, 12.0)
    _mark_space_before([w], _P([sp(154.82, 157.82, 232.65, 244.65)]))
    assert w["_space_before"], "overrunning space glyph rejected -> jammed line"

    print("pagemodel self-check passed")


if __name__ == "__main__":
    _demo()
