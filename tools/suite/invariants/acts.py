"""Invariants specific to the Acts lane.

Only what differs from :mod:`._common`, which holds the 103 blocks this lane shares
verbatim. Every difference below is a real difference between what the
two printers do, not a fix one fork got and the other did not -- those were reconciled
in Phase 4.
"""

from __future__ import annotations

from ..loader import (
    iter_all_leaves,
    iter_section_leaves,
)
from . import _common
from ._common import (
    _BODY_LEAK_MARKER,
    _BODY_LEAK_NOTE,
    _CHAPTER_NUM_RE,
    _ROMAN_VALUES,
    _is_amendment_instrument,
    _schedule_ordinal,
)


def _chapter_numeral_value(code):
    """Sortable value of a chapter code ("CHAPTER XVI-A" -> 16.1), or None.

    A letter-suffixed chapter is an INSERTED one and sorts just after its base
    ("CHAPTER XVI" < "CHAPTER XVI-A" < "CHAPTER XVII"), which is the order the
    statute prints them in.
    """
    m = _CHAPTER_NUM_RE.match((code or "").strip())
    if not m:
        return None
    num, total, prev = 0, 0, 0
    for ch in reversed(m.group(1).upper()):
        v = _ROMAN_VALUES[ch]
        total += v if v >= prev else -v
        prev = max(prev, v)
    num = total
    suffix = m.group(2) or ""
    return num + sum(ord(c) - 64 for c in suffix.upper()) / 100.0


def inv_structure_counts(doc):
    """Edition-aware structural sanity.

    The chapter COUNT is act-dependent -- the Income Tax Ordinance has 13, the
    Customs Act 16, the Sales Tax Act 10 and the Federal Excise Act 6 -- so a
    fixed floor of 13 is an Ordinance constant that simply rejects two thirds of
    this corpus.  What IS act-independent is that chapter numerals never go
    BACKWARDS: a repeated or descending numeral means a chapter row was misparsed
    or the tree assembled out of order, which is the defect the floor was really
    proxying for.  (A chapter dropped *with* its sections is caught by the
    conservation gate, and one dropped without them by ``no_orphan_sections`` and
    the pipeline's parent-less-section refusal.)  Holes are NOT an error: the
    Customs TOC omits CHAPTERS IV / IX / XI, which the body prints (ledger O03).

    The schedule COUNT is likewise edition-dependent -- new
    schedules were added over the years (9 in the 30.06.2018 edition, 15 by
    31.07.2025) -- so instead of a fixed floor the ordinal-titled schedules must
    form a CONTIGUOUS run FIRST..Nth.  A gap means a schedule was dropped or its
    title went unrecognised (e.g. the 2020 Eleventh Schedule, printed as the
    freshly-inserted `1[“ELEVENTH SCHEDULE`); that is the real defect this guards.
    """
    bad = []
    md = doc.get("metadata", {})
    n_chapters = len(doc.get("chapters") or [])
    if n_chapters < 1:
        bad.append("no chapters in tree")
    seq = [_chapter_numeral_value(c.get("code")) for c in doc.get("chapters") or []]
    for a, b in zip(seq, seq[1:]):
        if a is not None and b is not None and b <= a:
            bad.append(f"chapter numerals not increasing: {a} then {b}")
    if md.get("chapters_count", -1) != n_chapters:
        bad.append(f"metadata chapters_count {md.get('chapters_count')} != "
                   f"chapters in tree {n_chapters}")
    schedules = doc.get("schedules") or []
    n_schedules = len(schedules)
    if md.get("schedules_count", -1) != n_schedules:
        bad.append(f"metadata schedules_count {md.get('schedules_count')} != "
                   f"schedules in tree {n_schedules}")
    ords = sorted(o for o in (_schedule_ordinal(s.get("code")) for s in schedules)
                  if o is not None)
    if not ords:
        # A document with NO schedules at all is not a defect -- it is most of
        # Phase 2.  Verified 2026-08-08 over the 17 corpus editions that emit
        # none: not one of their PDFs prints a schedule TITLE line (positive
        # control: Customs 2009 shows 4), and the schedule ordinals their text
        # does mention -- "the First Schedule to the Customs Act, 1969" -- belong
        # to the instruments they amend, which is what an amendment Act is for.
        # All 17 conserve their text, so nothing is hiding here.  This guard is
        # about a schedule run with a HOLE in it; requiring the run to exist
        # rejected every flat gazette Act (same class as the M3 work that made
        # these invariants act-independent).
        if schedules:
            bad.append(f"{len(schedules)} schedule(s) but none ordinal-titled")
    elif not _is_amendment_instrument(doc):
        # The contiguity rule is about a CONSOLIDATED act, which prints all of its
        # own schedules in order: a hole means one was dropped or its title went
        # unrecognised (the 2020 Eleventh Schedule, printed as the freshly-inserted
        # `1[“ELEVENTH SCHEDULE`), and Sales Tax July 2014 starting at THE THIRD is
        # a real defect that must keep failing.
        #
        # An AMENDMENT instrument prints only the schedules it amends.  Finance Act
        # 2019, 2021, 2022 and 2025 each carry the First, Second and Fifth of the
        # Act they amend and nothing between -- "missing [3, 4]" is the document
        # being faithful, not a drop, and Finance Act 2014 legitimately opens at the
        # Second.  Scoped by the same measured classifier as
        # ``inv_no_structural_heading_in_body`` and recorded as ``deliberate``.
        if ords[0] != 1:
            bad.append(f"schedules do not start at FIRST (lowest ordinal {ords[0]})")
        missing = sorted(set(range(ords[0], ords[-1] + 1)) - set(ords))
        if missing:
            bad.append(f"schedule ordinals not contiguous; missing {missing}")
    return bad


def inv_section_codes_ordered(doc):
    """Chapter-side section codes are non-decreasing in document order.

    Section codes advance monotonically through the ordinance (4 < 4A < 4AB
    < 4B < 5; the sole legitimate repeat is an omitted-then-reinserted code
    like 236Y, hence non-strict).  A violation means a body line was
    mistaken for a section start (cross-reference, definitions clause) or
    the tree was assembled out of order -- both silent-corruption modes of
    the body-driven discovery fallback and the TOC matcher alike.
    """
    from legal_ingest.discover import code_sort_key
    bad, prev, prev_code = [], None, None
    for leaf in iter_section_leaves(doc):
        code = str(leaf.get("code") or "")
        key = code_sort_key(code)
        if prev is not None and key < prev:
            bad.append(f"section {code!r} out of order after {prev_code!r}")
        prev, prev_code = key, code
    return bad


def inv_toc_first_chapter_parse(_doc):
    """Pure-function pin on the TOC column-header sanitizer.

    Exercises ``parse_toc`` on both first-chapter layouts observed in the
    wild -- headers merged onto the chapter/heading rows (30.06.2024) and
    headers on their own line (20.02.2026) -- so a regression in the
    sanitizer or the Roman-numeral normalisation fails every suite run,
    independent of which JSON is under test.
    """
    from legal_ingest.toc import parse_toc
    layouts = {
        "merged-headers (30.06.2024)": [
            "TABLE OF CONTENTS",
            "CHAPTER 1              PAGE",
            "SECTIONS",
            "PRELIMINARY            NO.",
            "1.  Short title, extent and commencement       1",
            "2.  Definitions                                1",
            "3.  Ordinance to override other laws          30",
            "CHAPTER II",
            "CHARGE OF TAX",
            "4.  Tax on taxable income                     31",
        ],
        "own-line headers (20.02.2026)": [
            "TABLE OF CONTENTS",
            "CHAPTER 1",
            "SECTIONS PAGE NO.",
            "PRELIMINARY",
            "1.  Short title, extent and commencement       1",
            "2.  Definitions                                1",
            "3.  Ordinance to override other laws          31",
            "CHAPTER II",
            "CHARGE OF TAX",
            "4.  Tax on taxable income                     32",
        ],
    }
    bad = []
    for label, lines in layouts.items():
        chapters, _scheds, secs = parse_toc(lines)
        if len(chapters) != 2 or chapters[0].code != "CHAPTER I":
            bad.append(f"{label}: first chapter not parsed as CHAPTER I "
                       f"(got {[c.code for c in chapters]})")
            continue
        if chapters[0].heading != "PRELIMINARY":
            bad.append(f"{label}: chapter heading {chapters[0].heading!r} "
                       f"!= 'PRELIMINARY'")
        firsts = [s for s in secs if s.code in ("1", "2", "3")]
        if len(firsts) != 3 or any(s.parent is not chapters[0] for s in firsts):
            bad.append(f"{label}: sections 1-3 not all parented to CHAPTER I")
    return bad


def inv_toc_schedule_regexes(_doc):
    """Pure-function pin on three TOC-parse fixes behind the 2024 TOC QA audit,
    independent of which JSON is under test:

      * a wrapped section-heading continuation that is a bare year is joined,
        not dropped ("... 30th June," + "2020" -> "... 30th June, 2020"), so
        236U/236X keep their full omission year;
      * a Part row carrying an inline printed page ("Part IIB 503") classifies
        as its own Part instead of bleeding into the previous Part's heading;
      * a Division letter suffix printed with a space ("Division III A") keeps
        that spaced code instead of collapsing onto a "Division III" sibling.
    """
    from legal_ingest.toc import parse_toc
    lines = [
        "CHAPTER I",
        "PRELIMINARY",
        "236U.  omitted through Finance Act, 2020 dated 30th June, 464",
        "       2020",
        "237.  Power to make rules                                 467",
        "FIRST SCHEDULE",
        "PART I",
        "RATES OF TAX",
        "Division III                                              510",
        "Payments for Goods or Services",
        "Division III A",
        "(Omitted by the Finance Act, 2012)",
        "Division III B",
        "(Omitted by the Finance Act, 2012)",
        "PART II                                                   502",
        "Rates of Advance Tax",
        "Part IIB                                                  503",
        "Rates of Advance Tax",
    ]
    bad = []
    _chapters, scheds, secs = parse_toc(lines)
    by = {s.code: s.heading for s in secs}
    want = "omitted through Finance Act, 2020 dated 30th June, 2020"
    if by.get("236U") != want:
        bad.append(f"wrapped year dropped: 236U heading {by.get('236U')!r} != {want!r}")
    if not scheds:
        bad.append("no schedule parsed from FIRST SCHEDULE block")
    else:
        part_codes = [p.code for p in scheds[0].parts]
        if "PART IIB" not in part_codes:
            bad.append(f"inline-page Part not classified: parts={part_codes}")
        div_codes = [d.code for p in scheds[0].parts for d in p.divisions]
        for c in ("Division III A", "Division III B"):
            if c not in div_codes:
                bad.append(f"spaced division code {c!r} lost: divs={div_codes}")
    return bad


def inv_no_footnote_note_in_body(doc):
    """RC-1: a footnote's amendment NOTE must never sit in a leaf's body_text.

    The leak signature is a bare marker line ("1") immediately followed by an
    edit-verb note line ("Inserted by the Finance Act ...", "The word ...
    substituted") -- footnote apparatus that belongs in the footnotes[] array,
    not mid-section.  Guards the RC-1 class (2018-2020 editions leaked 25-71
    such blocks each) document-wide."""
    bad = []
    for leaf in iter_all_leaves(doc):
        lines = (leaf.get("plain_text", "") or "").split("\n")
        for i, ln in enumerate(lines):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if (_BODY_LEAK_MARKER.match(ln) and nxt[:1].isupper()
                    and _BODY_LEAK_NOTE.search(nxt)):
                bad.append(f"section {leaf.get('code')}: footnote note leaked into "
                           f"body -- {ln.strip()!r} / {nxt[:34]!r}")
                break
    return bad


def inv_calibration_sane(doc):
    """The auto-derived constants must be internally consistent.

    Every page number, footnote ref and body/footnote zone split in the document
    follows from these, and they are measured per document rather than hardcoded
    (page boxes here span 522x756, 595x841, 595x842 and 612x792, and body text
    runs 9-12pt).  Deriving them is only safe if a bad derivation fails loudly,
    which is what this check is for.
    """
    cal = ((doc.get("metadata") or {}).get("calibration") or {})
    if not cal:
        return ["metadata.calibration missing"]
    bad = []
    pw, ph = cal.get("page_w", 0), cal.get("page_h", 0)
    if not (100 < pw < 2000 and 100 < ph < 2000):
        bad.append(f"implausible page box {pw}x{ph}")
    hm, fm = cal.get("header_max_top", -1), cal.get("footer_min_top", -1)
    if not (0 < hm < fm < ph):
        bad.append(f"header/footer cutoffs do not bracket the text area: "
                   f"{hm} / {fm} (page height {ph})")
    bs, fs = cal.get("body_size", 0), cal.get("footnote_size", 0)
    bmin = cal.get("body_min_size", 0)
    if cal.get("zone_mode") == "none":
        # No footnote zone was derived, so there is no boundary to check; the
        # two sizes are legitimately within SIZE_GAP_MIN of each other.
        pass
    elif not (fs < bs):
        bad.append(f"footnote size {fs} not smaller than body size {bs}")
    elif not (fs < bmin < bs):
        bad.append(f"zone boundary {bmin} not strictly between {fs} and {bs}")
    if cal.get("zone_mode") not in ("rule", "size", "none"):
        bad.append(f"unknown zone_mode {cal.get('zone_mode')!r}")
    if cal.get("zone_mode") == "rule":
        if not (cal.get("rule_x0_lo", 0) < cal.get("rule_x0_hi", 0)
                and cal.get("rule_w_lo", 0) < cal.get("rule_w_hi", 0)):
            bad.append("rule mode with an empty separator window")
    # A large offset is only implausible when the document does not SUPPORT it.
    # The +/-60 bound was guarding against an offset derived from a single stray
    # folio -- the YEAR 2010 read as a page number, a 4-digit cross-reference read
    # as -688 -- and those have almost no support by construction.  But a document
    # can legitimately carry more than one folio SERIES: Finance Act, 2022 runs pdf
    # 2 -> folio 1 for 255 pages and then restarts at the Schedules, pdf 273 ->
    # folio 18, so its modal offset is 255 with **62.9% of sampled pages agreeing**.
    # Judge the evidence, not the magnitude.
    offset = cal.get("page_offset", 0)
    support = cal.get("page_offset_support")
    if abs(offset) > 60 and (support is None or support < 0.50):
        bad.append(f"implausible page offset {offset}"
                   + (f" (only {support:.0%} of sampled pages agree)"
                      if support is not None else ""))
    if not cal.get("pages_sampled"):
        # ``calibrate`` samples the TEXT LAYER (``_page_lines``), which a wholly
        # scanned document does not have, so it derives nothing and the document
        # converts on the defaults (12/9 pt, ``zone_mode="size"``).  That is a
        # legitimate fallback -- the five scanned editions it applies to conserve
        # their text and carry correct structure -- but it is only legitimate for
        # a SCAN.  Zero sampled pages on a document with a text layer means the
        # sampler found nothing where there was something to find, which is the
        # silent-corruption case this invariant exists for, so keep failing it.
        ocr = ((doc.get("metadata") or {}).get("ocr") or {})
        if not ocr.get("pages"):
            bad.append("no pages were sampled and this is not a scan -- the "
                       "calibration constants are defaults, not derived")
    # the offset must map this document's pages onto plausible printed pages
    total = (doc.get("metadata") or {}).get("total_pages") or 0
    if total and not (-total < cal.get("page_offset", 0) < total):
        bad.append("page offset larger than the document")
    return bad


ALL_INVARIANTS = _common.all_invariants(globals())
