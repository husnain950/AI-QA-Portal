"""Per-document geometry and typography calibration.

The Ordinance pipeline hardcoded every constant to a single 504x648 document
(``HEADER_MAX_TOP = 55.0``, ``FOOTER_MIN_TOP = 598.0``, a footnote separator rule
at ``68 <= x0 <= 78``, body text >= 9.6pt).  None of that survives contact with
the Acts corpus, which spans two page boxes and three unrelated footnote
layouts:

    Customs Act 1969    612x792  body 12.0pt  footnotes 9.0pt  NO separator rule
                                 -- footnotes occupy WHOLE pages, not a bottom
                                    zone, and are set at a size the Ordinance
                                    would read as body text
    Sales Tax Act 1990  612x792  body 12.0pt  footnotes 6.0pt  rule x0~126 w~144
    Federal Excise 2005 612x792  body 12.0pt  footnotes 8.0pt  rule x0~126 w~144
    Finance Acts        595x842  (phase 2)

So every literal is derived from the document itself and recorded in
``metadata.calibration``, where the ``calibration_sane`` invariant asserts it.
Deriving beats re-hardcoding per act for a plain reason: there are 56 editions
spanning 2007-2025 and their typesetting drifts *within* an act family, so a
per-family constant table would be wrong for some editions and we would not
find out.  A derived value that is also asserted cannot rot silently.

Run standalone to inspect what a document calibrates to::

    python -m legal_ingest.calibrate "Acts/Customs Act, 1969/....pdf"
"""

from __future__ import annotations

import collections
import re
import statistics
from dataclasses import asdict, dataclass

from .grammar import SCHEDULE_TOC_RE, folio_value
from .pagemodel import Word, _group_into_lines, normalize_text
from .profiles import ACTS, Profile

# A table-of-contents row: a section code, a title, then the printed page it
# starts on -- optionally a range ("2. Definitions.....7-29", Sales Tax) and
# optionally reached through dot leaders.  Used ONLY to measure TOC density, so
# it is deliberately looser than toc.SECTION_RE.
TOC_ROW_RE = re.compile(
    r"^\s*\d{1,3}-?[A-Z]{0,4}\.?\s+\S.*?[\s.…]+(\d{1,4})"
    r"(?:\s*[-–]\s*\d{1,4})?\s*$")

# A dot-leader row whose page number is absent or unextractable.  Several Sales
# Tax editions (30.06.2021) print a full contents list whose leaders simply run
# out with no folio at all, so TOC_ROW_RE -- which requires a trailing number --
# sees nothing and the TOC would be scanned as body, parsing contents rows into
# sections.  Anchoring on leaders that run to END of line is what keeps this from
# also matching body text: an omission bracket ("(d) 31[…….] 32[Provincial Sales
# Tax levied on...") carries a leader run but continues with prose afterwards.
# Dots are not the only leader. Income Tax Rules 2002 sets its contents with HYPHEN
# runs ("Valuation of accommodation ---------- ------ ---"), so a dot-only pattern saw
# no TOC at all in a 946-page document whose contents occupy pages 2-20 -- and
# `first_body_page = toc_pages + 1` then read all nineteen of them as body.
TOC_LEADER_RE = re.compile(r"(?:[.…]{5,}|[-_]{6,}|(?:[-_]{2,}[\s]){2,})[\s.…\-_]*\d{0,4}\s*$")
#: Dots only -- what the Acts corpus was calibrated against, kept so that widening
#: the leader charset for the Rules cannot change how an Act's contents is found.
TOC_DOT_LEADER_RE = re.compile(r"(?:[.…]{5,})[\s.…]*\d{0,4}\s*$")


# A contents row carrying NO rule code -- words, then the folio. The Income Tax Rules
# contents prints most of its rows this way ("Responsibilities of the Authority 71",
# "Valuation of conveyance 3"), and neither the coded pattern nor the leader pattern
# sees them: measured, its contents pages scored 16-40% against a 45% floor, so a
# 946-page document reported no TOC at all and read nineteen contents pages as body.
#
# Anchored at both ends and required to carry a word, so body prose does not qualify.
# Measured on this corpus with it: contents pages 69-97%, body pages 2-5%. The
# separation is what makes it safe -- a looser pattern would not have one.
TOC_CODELESS_RE = re.compile(
    r"^\s*(?=.*[A-Za-z]{3})[^\d\n].{3,90}?[\s.\-…]+\d{1,4}\s*$")


def _is_toc_row(line: str, profile: Profile = ACTS) -> bool:
    """Whether ``line`` looks like a contents row, in the forms this corpus sets.

    The coded form is universal. The other two are opt-in: a hyphen-leader run and a
    codeless "words then folio" row are both shapes ordinary body prose can take, and
    the Acts contents needs neither, so admitting them there would only add ways for a
    body page to be mistaken for contents.
    """
    if TOC_ROW_RE.match(line):
        return True
    # A SCHEDULE contents row carries no section code, so the coded form above
    # cannot see it -- and a contents page whose tail is nothing but schedule
    # rows therefore measured 0 rows and was not counted as front matter.  The
    # body then started one page early, and everything on that page before the
    # first section's anchor became the preamble: four Customs Act editions
    # shipped their contents tail glued in front of the enacting formula.
    #
    # ``SCHEDULE_TOC_RE`` is reused rather than rewritten.  It is already the
    # narrowed, anchored form -- its own note records the wrapped citation
    # ("THE FIFTH SCHEDULE TO THE ACT......... 45") that the unanchored pattern
    # read as a schedule title, and it still rejects it here.  Measured over both
    # profiles and all 90 resolvable documents: 4 changed, 86 unchanged.
    if SCHEDULE_TOC_RE.match(line):
        return True
    if profile.toc_hyphen_leaders and TOC_LEADER_RE.search(line):
        return True
    if not profile.toc_hyphen_leaders and TOC_DOT_LEADER_RE.search(line):
        return True
    if profile.toc_codeless_rows and TOC_CODELESS_RE.match(line):
        return True
    return False

# Folio grammar lives in `grammar` -- `pagemodel` reads the same forms per page and
# cannot import this module (this module imports it).
_ROMAN_RE = re.compile(r"^\(?[ivxlcdm]{1,7}\)?$", re.IGNORECASE)

# Heading terminators seen across the corpus: em dash, en dash, hyphen.
_DASH_RE = re.compile(r"\.\s*(—|–|-)")
# How much of the document must print a thin left-margin rule before we trust it
# as the footnote separator.  Customs prints none (0%); Sales Tax and Federal
# Excise print one on essentially every page.  Anything in between is ambiguous
# and falls through to size-based zoning, which is the safer failure mode: a
# missed rule costs us nothing, a table border mistaken for a rule truncates the
# body mid-section.
RULE_COVERAGE_MIN = 0.30

# Minimum body-size / footnote-size separation before size-based zoning is
# allowed.  Customs is 12.0 vs 9.0 (3.0pt); the Ordinance's body tables sit at
# 8-9pt against 10pt body (1.0pt) and would be misclassified -- which is exactly
# why the Ordinance refuses size zoning.  Requiring a real gap is what keeps this
# from being the same mistake.
SIZE_GAP_MIN = 2.0


@dataclass(frozen=True)
class Calibration:
    """Everything the Ordinance pipeline hardcoded, measured per document."""

    page_w: float
    page_h: float

    header_max_top: float
    footer_min_top: float
    running_header: str

    body_size: float
    footnote_size: float
    body_min_size: float
    footnote_text_max: float
    marker_max_size: float
    footnote_marker_max_size: float
    footnote_marker_x_max: float

    zone_mode: str          # "rule" | "size" | "none" (no footnote zone)
    rule_x0_lo: float
    rule_x0_hi: float
    rule_w_lo: float
    rule_w_hi: float
    rule_coverage: float

    body_left: float
    heading_dash: str
    marker_max_value: int

    toc_pages: int
    page_offset: int
    page_offset_support: float
    #: How many folios the sample actually read. Distinguishes a document
    #: that prints none (support is 0.0 because there is no evidence either
    #: way) from one whose folios disagree with the derived offset (support
    #: is 0.0 because the evidence contradicts it). Both were 0.0 before.
    page_offset_samples: int
    pages_sampled: int

    #: every folio-normalised header line that cleared the recurrence threshold
    #: (a gazette alternates recto and verso, so there can be two).  ``pagemodel``
    #: strips a line in the header BAND only when its text is one of these --
    #: position alone is not enough, see ledger P37 and ``_is_header_line``.
    #: Last field, with a default, so nothing that constructs a Calibration
    #: positionally has to change.
    header_keys: tuple = ()

    #: Which corpus this document belongs to. Carried here because `pagemodel`
    #: already receives a `Calibration` everywhere it needs the profile, so this
    #: saves threading a second argument through every page-model call site.
    #: Excluded from `as_dict`, which is emitted as `metadata.calibration`.
    profile: Profile = ACTS

    def as_dict(self) -> dict:
        # `profile` is configuration, not a measurement, and this dict is emitted as
        # `metadata.calibration` -- adding it would change every document's output.
        return {k: v for k, v in asdict(self).items() if k != "profile"}


# --------------------------------------------------------------------------
# helpers


def _modal(values, default=None, ndigits=1):
    """Most common value, rounded -- the workhorse for "what does this document
    usually do".  A mean would be dragged around by headings and tables."""
    vals = [round(float(v), ndigits) for v in values]
    if not vals:
        return default
    return collections.Counter(vals).most_common(1)[0][0]


def _leftmost_mode(values, default, share=0.08, ndigits=0):
    """Smallest x-position that recurs on at least ``share`` of the lines.

    The plain mode answers "where is most text", which for a footnote block is
    the continuation indent.  The margin is where the *marker* sits -- leftmost
    among the positions that recur often enough not to be a stray.
    """
    if not values:
        return default
    counts = collections.Counter(round(float(v), ndigits) for v in values)
    floor = max(2, int(len(values) * share))
    frequent = [v for v, c in counts.items() if c >= floor]
    return min(frequent) if frequent else min(counts)


def _page_lines(page):
    """Grouped lines for one page, using the same machinery as the real page
    model so calibration measures what the pipeline will actually see."""
    raw = page.extract_words(use_text_flow=False, keep_blank_chars=False,
                             extra_attrs=["size", "fontname"])
    words = [
        Word(text=normalize_text(w["text"]), x0=float(w["x0"]), x1=float(w["x1"]),
             top=float(w["top"]), size=round(float(w["size"]), 1),
             fontname=w.get("fontname", ""))
        for w in raw if normalize_text(w["text"]).strip()
    ]
    return _group_into_lines(words)


def _thin_ink(page):
    """Thin horizontal rules on the page as ``(top, x0, width)``.

    Covers all three object families -- a separator is drawn as a ``line`` in
    some editions and as a zero-height ``rect`` in others, and missing the rect
    form is what would silently push a document onto the wrong zoning mode.
    """
    out = []
    segs = list(page.lines) + list(page.curves)
    for r in page.rects:
        if r.get("height", 9) < 2.5:
            segs.append(r)
    for s in segs:
        if abs(s.get("y0", 0) - s.get("y1", 0)) > 2.0:
            continue
        out.append((float(s["top"]), float(s["x0"]), float(s["x1"]) - float(s["x0"])))
    return out


def detect_toc_pages(pdf, max_scan: int = 40, profile: Profile = ACTS) -> int:
    """Number of leading pages before the body starts (title pages + TOC).

    Replaces the Ordinance's ``commencement.-|This Ordinance may be`` signature,
    which is specific to that statute's section 1 and, when it matched nothing,
    silently returned a hardcoded 19.  Here the TOC is recognised by what a table
    of contents structurally *is* -- a run of pages dense in "code, title, page
    number" rows -- so it works for every act, and correctly returns 0 for the
    Phase 2 documents that print no TOC at all (a result the old signature could
    never produce).
    """
    limit = min(max_scan, len(pdf.pages))
    rows, ratio = [], []
    for i in range(limit):
        lns = [ln for ln in (pdf.pages[i].extract_text() or "").split("\n")
               if ln.strip()]
        r = sum(1 for ln in lns if _is_toc_row(ln, profile))
        rows.append(r)
        ratio.append(r / max(1, len(lns)))

    # A page is TOC-dense when most of its lines ARE rows.  The absolute count
    # alone is not enough: a footnote page ("25. Inserted by the Finance Act,
    # 2003 (I of 2003), S.5(1)(d), page 21.") matches the row shape a dozen
    # times over, and counting those made the Customs TOC appear to run 37 pages
    # deep into the body.  The ratio separates them cleanly -- measured, real TOC
    # pages sit at 0.48-0.80 and the densest footnote page at 0.11.
    dense = [i for i in range(limit) if rows[i] >= 4 and ratio[i] >= 0.45]
    if not dense or dense[0] > 6:
        return 0                      # no front-matter TOC (phase 2 documents)

    end = dense[0]
    while end + 1 < limit and (end + 1) in dense:
        end += 1
    # Extend over the TOC's final short page: contents commonly end mid-page, so
    # the tail carries only a handful of rows and falls under the ratio floor
    # while still being TOC.
    #
    # A row count alone is not enough here. The Income Tax Rules prints a body TITLE
    # page ("GOVERNMENT OF PAKISTAN / FEDERAL BOARD OF REVENUE / ...") straight after
    # its contents, and three of its 38 lines match the row shape -- so a `rows >= 3`
    # tail rule swallowed it, and `first_body_page = toc_pages + 1` then started the
    # body one page late, dropping the title block entirely.
    #
    # A real contents tail is SHORT but still DENSE: few lines, most of them rows.
    # The title page is long and sparse (8%). Requiring both separates them.
    floor = profile.toc_tail_density_floor
    while (end + 1 < limit and rows[end + 1] >= 3
           and (floor is None or ratio[end + 1] >= floor)):
        end += 1
    return end + 1


# --------------------------------------------------------------------------


def calibrate(pdf, sample: int = 36, profile: Profile = ACTS) -> Calibration:
    """Derive this document's geometry and typography from a page sample."""
    n = len(pdf.pages)
    page_w = _modal((p.width for p in pdf.pages[: min(n, 8)]), 612.0)
    page_h = _modal((p.height for p in pdf.pages[: min(n, 8)]), 792.0)

    toc_pages = detect_toc_pages(pdf, profile=profile)

    # Sample body pages evenly.  Front matter is skipped: its typography (title
    # blocks, TOC leaders, roman folios) is not the body's and would skew every
    # mode we measure.
    lo = min(toc_pages, max(0, n - 1))
    idx = sorted({lo + round(i * (n - 1 - lo) / max(1, sample - 1))
                  for i in range(sample)}) if n > lo else [0]
    idx = [i for i in idx if 0 <= i < n]

    top_lines: list[tuple[str, float]] = []
    foot_tops: list[float] = []
    printed: list[tuple[int, int]] = []      # (pdf_index_1based, printed_page)
    ink: list[tuple[float, float]] = []      # (x0, width) of thin rules
    ink_pages = 0
    page_rules: list[list] = []              # per-page rules, for margin coverage
    per_page_lines = []
    all_sizes: collections.Counter = collections.Counter()
    dash_counts: collections.Counter = collections.Counter()

    for i in idx:
        page = pdf.pages[i]
        lines = _page_lines(page)
        if not lines:
            continue
        per_page_lines.append((i, lines))
        for ln in lines:
            for w in ln.words:
                all_sizes[round(w.size, 1)] += 1
        ordered = sorted(lines, key=lambda ln: ln.top)
        top_lines.append((ordered[0].text().strip(), ordered[0].top))

        # printed page number: a lone Arabic/Roman integer in the bottom margin
        for ln in reversed(ordered):
            if ln.top < page_h * 0.75:
                break
            t = ln.text().strip()
            value = folio_value(t, profile)
            if value is not None:
                foot_tops.append(ln.top)
                # A folio must be a plausible page of THIS document.  One Sales
                # Tax edition prints a four-digit reference in the bottom margin
                # that read as page "700+" and dragged the derived offset to
                # -688, which would have minted a wrong printed page into every
                # footnote ref on every leaf.
                if 1 <= value <= n + 40:
                    printed.append((i + 1, value))
                break
            if _ROMAN_RE.match(t):
                foot_tops.append(ln.top)
                break

        rules = [(x0, wd, top / page_h) for (top, x0, wd) in _thin_ink(page)
                 if wd >= 60 and top > page_h * 0.06]
        if rules:
            ink_pages += 1
            ink.extend(rules)
            page_rules.append(rules)

        for m in _DASH_RE.finditer("\n".join(ln.text() for ln in ordered)):
            dash_counts["." + m.group(1)] += 1

    sampled = len(per_page_lines)

    # ---- running header ------------------------------------------------
    # Count the header line with its FOLIO NORMALISED AWAY, and accept every
    # variant that clears the threshold rather than only the commonest.
    #
    # Matching exact strings cannot see a gazette header, because the header
    # carries the page number: Finance Act 2019 prints
    # "P ART I] THE GAZETTE OF PAKISTAN, EXTRA., JUNE 30, 2019 101" on odd pages
    # and "102 THE GAZETTE ... [P ART I" on even ones, so every header line is a
    # unique string, nothing reaches 40%, and `header_max_top` fell back to a
    # flat 5.5% of the page -- above the header, which therefore stayed in the
    # BODY zone.  The conservation audit then counts those headers as statutory
    # text the output failed to conserve: of Finance Act 2019's 903 "missing"
    # body words, **258 are the token `ART`** (a glyph-split "P ART"), and
    # Finance Act 2021 shows 240 of the same.  That is measurement noise
    # standing in for lost law, and it also leaves running-header lines in the
    # stream that section discovery has to walk past.
    #
    # Two variants are accepted because a gazette alternates recto and verso;
    # each lands near 50%, so taking only `most_common(1)` would strip the
    # header from half the document.  Measured over both families: Customs,
    # Sales Tax and Federal Excise already sit at 100% under exact matching and
    # are **unchanged** by normalising (their headers carry no folio), while
    # Finance Act 2019/2021/2024 go 2% -> 50% and become detectable.
    # A key must still be TEXT.  Normalising digits makes every bare top-of-page
    # folio collapse to the same key: The Tax Laws (Amendment) Act 2020 prints
    # "2", "3", "4" at the top of successive pages, which normalise to "#",
    # clear 40% easily, and produced a "running header" of `'#'` -- cutting at
    # 61.1pt and eating the first real line of text (measured: that edition went
    # from body 100.000% to 99.984%, and page 6 lost an "S"). A running header
    # carries words; a folio does not.
    _folio = re.compile(r"\d+")
    keyed = [(_folio.sub("#", t), top) for t, top in top_lines if t]
    header_texts = collections.Counter(k for k, _ in keyed)
    keys = {k for k, n in header_texts.items()
            if sampled and n / sampled >= 0.4
            and sum(c.isalpha() for c in k) >= 8}
    if keys:
        running_header = header_texts.most_common(1)[0][0]
        htops = [top for k, top in keyed if k in keys]
        # cut just below the header line; the first body line sits lower still
        header_max_top = statistics.median(htops) + 6.0
    else:
        # Nothing clears 40%, so there is no ONE header to measure a band from.
        # The band therefore stays positional -- 5.5% is the only figure
        # available -- but "no header was DETECTED" is not "there is no header",
        # and what the band DROPS is decided by recurrence instead of by
        # position alone.  Measured over the 50 documents in this corpus that
        # reach this branch, five of them do have a header the 40% test missed:
        #
        #   Public Finance Management Act 2019   '#(cid:#) THE GAZETTE OF
        #                                         PAKISTAN, EXTRA., JU...' and
        #                                        'PART I](cid:#) THE GAZETTE...'
        #                                        -- a gazette alternating recto
        #                                        and verso, so each variant sits
        #                                        near half and neither clears
        #   Finance Act 2023                     'NATIONAL ASSEMBLY SECRETARIAT'
        #   Income Tax Rules 2002                per-CHAPTER headers, six of them
        #   Sales Tax Act 15.9.2021              repeated table column headers
        #
        # and the other 45 have none.  Sales Tax Rules 2006 (01-01-2025) is what
        # that buys: every one of its top lines is unique, because the document
        # prints no header and the top of a page is simply where the next rule
        # begins.  Rule 35 opens at top=41.1, rule 76 at 41.0, rule 101 at 41.1
        # and rule 150X at 41.5, against a flat 43.6pt band -- all four were
        # discarded as furniture and reported as heading-only stubs.
        #
        # This is the principle ``pagemodel._is_header_line`` already states for
        # the detected case: decide what a line is from what it says, not from
        # where it sits.
        running_header, header_max_top = "", page_h * 0.055
        keys = {k for k, cnt in header_texts.items()
                if cnt >= 2 and sum(c.isalpha() for c in k) >= 8}

    # ---- footer --------------------------------------------------------
    footer_min_top = (statistics.median(foot_tops) - 8.0 if foot_tops
                      else page_h * 0.90)

    # ---- body / footnote sizes -----------------------------------------
    # The two dominant text sizes are body and footnote.  Headings, folios and
    # inline superscript markers are all present but individually rare, so the
    # top-2 modes are the two prose sizes.
    ranked = [s for s, _ in all_sizes.most_common() if all_sizes[s] >= 4]
    body_size = ranked[0] if ranked else 12.0
    footnote_size = next((s for s in ranked[1:] if s < body_size), body_size - 3.0)

    boundary = (body_size + footnote_size) / 2.0
    body_min_size = boundary
    footnote_text_max = boundary
    # Superscript amendment markers run 60-70% of body size, so cut well below
    # body rather than just under it: body_size - 0.8 would have admitted 11pt
    # prose as a "marker".
    marker_max_size = body_size - 1.5
    # A footnote's own marker numeral is NOT bounded by the footnote text size:
    # the 2014 Customs edition sets its notes at 9.0pt but their markers at
    # 10.0pt, so a ``footnote_size + 0.6`` cutoff rejected every marker on the
    # page and the whole footnote block collapsed into a single unmarked
    # continuation -- 158 citations lost their notes.  Inside the footnote zone
    # the only real constraint is that a marker is smaller than BODY text (or it
    # would be body text), and the marker test additionally requires a bare
    # marker token at the block's left margin, so the zone boundary is the
    # correct, and safe, cutoff.
    footnote_marker_max_size = boundary

    # ---- margins -------------------------------------------------------
    # Take the LEFTMOST recurring indent, not the modal one.  Footnote
    # continuation lines are more numerous than footnote marker lines, so the
    # mode lands on the continuation indent (Customs: 165.6) and a marker at the
    # real margin (129.6) would still pass an x0 test built from it -- but so
    # would half the body.  The leftmost recurring value is the margin itself.
    body_lefts, fn_lefts = [], []
    for _, lines in per_page_lines:
        for ln in lines:
            if ln.top < header_max_top or ln.top >= footer_min_top:
                continue
            (body_lefts if ln.max_size > boundary else fn_lefts).append(ln.min_x0)
    body_left = _leftmost_mode(body_lefts, 72.0)
    footnote_marker_x_max = _leftmost_mode(fn_lefts, body_left) + 12.0

    # ---- separator rule ------------------------------------------------
    # Constrain candidates to the LEFT MARGIN before clustering.  Sales Tax
    # draws its footnote separator at x0~126 (= body_left) but also draws wider
    # table borders further right; unconstrained, the modal cluster landed on a
    # border at x0~348 and the zone split would have been taken from a table.
    margin_ink = [(x0, wd, fy) for x0, wd, fy in ink
                  if abs(x0 - body_left) <= 25.0]
    # Coverage must count pages carrying a MARGIN-ALIGNED rule, not pages
    # carrying any wide rule at all.  Counting `ink_pages` overstated it and let
    # gazette TABLE BORDERS elect "rule" mode: Finance Act 2021 came out
    # body=8.0 / footnote=7.6 -- a 0.4pt gap that would have been rejected -- yet
    # was zoned by a border it had mistaken for a footnote separator.
    margin_pages = sum(1 for rules in page_rules
                       if any(abs(x0 - body_left) <= 25.0 for x0, _, _ in rules))
    rule_coverage = (margin_pages / sampled) if sampled else 0.0
    if margin_ink and rule_coverage >= RULE_COVERAGE_MIN:
        # modal (x0, width) cluster -- bucket loosely, the rule is redrawn per
        # page and wanders a point or two
        cx0, cw = collections.Counter(
            (round(x0 / 4) * 4, round(wd / 8) * 8)
            for x0, wd, _ in margin_ink).most_common(1)[0][0]
        # A footnote separator sits LOW on the page.  Measured: every genuine one
        # in this corpus clusters at 0.74-0.82 of page height (Federal Excise, one
        # rule per page).  The gazette Finance Acts instead draw a rule under
        # their running header and dozens of table borders -- 201-341 rules per
        # sample spread over 0.12-0.86 -- and the modal cluster landed near the
        # TOP.  Taken as a separator that made the whole page "footnotes":
        # Finance Act 2019 came out with body=1 line (the header) and 32-44
        # footnote lines on EVERY page, so the entire statute was zoned away.
        fys = sorted(fy for x0, wd, fy in margin_ink
                     if abs(x0 - cx0) <= 8.0 and abs(wd - cw) <= max(8.0, cw * 0.4))
        cluster_fy = fys[len(fys) // 2] if fys else 0.0
        if cluster_fy >= 0.50:
            rule_x0_lo, rule_x0_hi = cx0 - 8.0, cx0 + 8.0
            rule_w_lo, rule_w_hi = max(40.0, cw * 0.6), cw * 1.6
            zone_mode = "rule"
        else:
            rule_x0_lo = rule_x0_hi = rule_w_lo = rule_w_hi = 0.0
            zone_mode = "size"
    else:
        rule_x0_lo = rule_x0_hi = rule_w_lo = rule_w_hi = 0.0
        zone_mode = "size"

    gap = body_size - footnote_size
    if zone_mode == "size" and gap < SIZE_GAP_MIN:
        # No rule AND no clean size split -- the two text sizes are too close to
        # tell body from footnote (measured across the gazette Acts: 10.0/9.5,
        # 9.5/9.0, 11.5/11.0, 9.0/8.5).  Those are two BODY sizes, not
        # body-vs-footnote, and 11 documents raised here and converted to nothing.
        #
        # Refusing was the wrong failure direction.  Zone everything as body
        # instead: if the document truly has no footnotes (the 20 gazette Finance
        # Acts print none) that is exactly right, and if it does have some, their
        # text is MISPLACED rather than LOST -- conservation still reaches 100%,
        # and the ``no_footnote_text_in_body`` invariant makes the misplacement
        # loud instead of silent, which was the guard's real purpose.
        zone_mode = "none"
        footnote_text_max = footnote_marker_max_size = 0.0

    # ---- printed-page offset -------------------------------------------
    # The MODE, not the median: the offset is genuinely constant across a body
    # (pdf index minus folio), so the most common value is the exact answer and
    # is immune to the misprinted folios these documents are full of.  A median
    # would interpolate between two wrong values and land on a page that exists
    # nowhere.  Every footnote ref is minted from this, so it has to be exact.
    _offsets = [p - pr for p, pr in printed]
    page_offset = (_modal(_offsets, toc_pages, ndigits=0) if printed else toc_pages)
    page_offset = int(page_offset)
    # How much of the document actually agrees with that offset.  A single number
    # cannot describe a document with more than one folio SERIES -- Finance Act,
    # 2022 runs pdf 2 -> folio 1 for 255 pages and then restarts at the Schedules,
    # pdf 273 -> folio 18 -- and the mode picks whichever series is longer (255,
    # agreed by 22 of its 35 sampled pages).  Recording the support lets
    # ``inv_calibration_sane`` tell a large-but-real offset from one derived out of
    # a single stray folio, which is what its fixed +/-60 bound was really guarding
    # against (the YEAR 2010 read as a page number, a 4-digit cross-reference read
    # as -688).
    page_offset_support = (round(_offsets.count(page_offset) / len(_offsets), 3)
                           if _offsets else 0.0)
    page_offset_samples = len(_offsets)

    heading_dash = (dash_counts.most_common(1)[0][0] if dash_counts
                    else ".—")

    # Sales Tax numbers its footnotes globally into the 800s, so the Ordinance's
    # "a marker >= 100 is really a quoted year" rule would reject almost all of
    # them.  Cap by what the document actually reaches instead, leaving the
    # 4-digit year band to be excluded by value.
    marker_max_value = 9999 if footnote_size < body_size else 999

    return Calibration(
        profile=profile,
        page_w=page_w, page_h=page_h,
        header_max_top=round(header_max_top, 1),
        footer_min_top=round(footer_min_top, 1),
        running_header=running_header,
        header_keys=tuple(sorted(keys)),
        body_size=body_size, footnote_size=footnote_size,
        body_min_size=round(body_min_size, 1),
        footnote_text_max=round(footnote_text_max, 1),
        marker_max_size=round(marker_max_size, 1),
        footnote_marker_max_size=round(footnote_marker_max_size, 1),
        footnote_marker_x_max=round(footnote_marker_x_max, 1),
        zone_mode=zone_mode,
        rule_x0_lo=round(rule_x0_lo, 1), rule_x0_hi=round(rule_x0_hi, 1),
        rule_w_lo=round(rule_w_lo, 1), rule_w_hi=round(rule_w_hi, 1),
        rule_coverage=round(rule_coverage, 3),
        body_left=round(body_left, 1),
        heading_dash=heading_dash,
        marker_max_value=marker_max_value,
        toc_pages=toc_pages, page_offset=page_offset,
        page_offset_support=page_offset_support,
        page_offset_samples=page_offset_samples,
        pages_sampled=sampled,
    )


def _demo() -> None:
    """Self-check: the folio and TOC grammars, then any PDF given as an argument.

    The pure part runs with no arguments -- it used to be a no-op without a PDF, which
    meant the pipeline gate exercised none of this.
    """
    # round 14: a SCHEDULE contents row is a contents row.  Without it the tail
    # page of a contents whose last rows are all schedules measures ZERO rows,
    # detect_toc_pages stops one page short, and that page's lines become the
    # preamble -- four Customs editions shipped their contents tail in front of
    # the enacting formula.  Measured: 4 documents changed, 86 unchanged.
    for _r in ("THE FIRST SCHEDULE 213", "THE THIRD SCHEDULE 213",
               "THE FIFTH SCHEDULE 219"):
        assert _is_toc_row(_r, ACTS), _r
    # ...and the wrapped CITATION SCHEDULE_TOC_RE was narrowed to reject, which
    # this must not re-admit: reading it as a schedule title switched the parser
    # into schedule mode mid-body and lost two chapters (see grammar.py).
    for _r in ("THE FIFTH SCHEDULE TO THE ACT\u2026\u2026\u2026 45",
               "THE CUSTOMS ACT,1969", "Section Page", "No."):
        assert not _is_toc_row(_r, ACTS), _r

    import sys

    import pdfplumber

    # The three folio forms this corpus prints, all measured.
    from .profiles import ACTS as _ACTS
    from .profiles import RULES as _RULES
    assert folio_value("226", _RULES) == 226                    # Customs Rules: bare
    assert folio_value("(104)", _RULES) == 104                  # Sales Tax: bracketed
    assert folio_value("Income Tax Rules, 2002 289", _RULES) == 289  # title, then folio
    assert folio_value("Customs Rules 1969 42", _RULES) == 42
    # The Acts read the plain form only: a centred subsection marker in a footer
    # band must not be mistaken for a folio, which is what `str.isdigit()` used to
    # guarantee before the two pipelines merged.
    assert folio_value("226", _ACTS) == 226
    assert folio_value("(104)", _ACTS) is None
    assert folio_value("(2)", _ACTS) is None
    assert folio_value("Income Tax Rules, 2002 289", _ACTS) is None
    # ... and what is NOT a folio
    assert folio_value("Sales Tax Rules, 2006", _RULES) is None   # the title's own year
    assert folio_value("Federal Excise Rules, 2005", _RULES) is None
    assert folio_value("(i)", _RULES) is None             # roman front matter
    assert folio_value("12 34", _RULES) is None           # two numbers, no words
    assert folio_value("", _RULES) is None

    # Contents rows. The coded form and dot leaders are read for every corpus; hyphen
    # leaders and codeless rows are Rules-only, the former being why a 946-page
    # document reported toc_pages 0.
    for _p in (_ACTS, _RULES):
        assert _is_toc_row("2. Definitions. ....................... 1", _p)
        assert not _is_toc_row("the licensee shall ensure that each factory premises", _p)
        assert not _is_toc_row("(2) The licensee shall arrange testing for all equipment.", _p)
        assert not _is_toc_row("(f) the amount of capital expenditure incurred in the year", _p)
        assert not _is_toc_row("41", _p)     # a bare folio is not a contents row
    assert _is_toc_row("Valuation of accommodation ---------- ------ ----------- 3", _RULES)
    assert _is_toc_row("13A. Acquisition of securities---------------- 11", _RULES)
    # codeless contents rows -- most of the Income Tax Rules contents looks like this
    assert _is_toc_row("Responsibilities of the Authority 71", _RULES)
    assert _is_toc_row("Valuation of conveyance 3", _RULES)
    # ...and none of those three shapes may pull an Acts body line into the contents
    assert not _is_toc_row("Responsibilities of the Authority 71", _ACTS)
    assert not _is_toc_row("Valuation of accommodation ---------- ------ --- 3", _ACTS)
    print("calibrate self-check passed")

    for path in sys.argv[1:] or []:
        with pdfplumber.open(path) as pdf:
            cal = calibrate(pdf)
        print(f"\n=== {path.split('/')[-1]}")
        for k, v in cal.as_dict().items():
            print(f"    {k:26s} {v}")
        assert cal.page_h > 0 and cal.page_w > 0
        assert 0 < cal.header_max_top < cal.footer_min_top < cal.page_h, \
            "header/footer cutoffs must bracket the text area"
        if cal.zone_mode != "none":
            assert cal.footnote_size < cal.body_size, \
                "footnotes must be smaller than body"
            assert cal.footnote_size < cal.body_min_size < cal.body_size, \
                "the zone boundary must sit strictly between the two prose sizes"
        assert cal.zone_mode in ("rule", "size", "none")
        if cal.zone_mode == "rule":
            assert cal.rule_w_lo < cal.rule_w_hi and cal.rule_x0_lo < cal.rule_x0_hi
        assert cal.pages_sampled > 0
        print("    [ok] calibration self-check passed")


if __name__ == "__main__":
    _demo()
