"""Invariants specific to the Ordinance lane.

Only what differs from :mod:`._common`, which holds the 71 blocks this lane shares
verbatim. This lane is a separate pipeline (`fbr_ingest`) reading a
differently printed document, so it diverges further than the Acts and the Rules do
from each other: 16 invariants and its own `_ref_key`, and it runs 43 of the checks
rather than 53.
"""

from __future__ import annotations

import re
from functools import partial

from ..loader import (
    iter_all_leaves,
    iter_section_leaves,
)
from . import _common
from ._common import (
    _BODY_LEAK_MARKER,
    _BODY_LEAK_NOTE,
    _BOLD_BODY_MARKER,
    _CELL_TEXT,
    _JAMMED_RUN,
    _LEADING_AMEND_MARKER,
    _NUM_ONLY,
    _QUOTE_CUE,
    _STRAY_SPACE_HYPHEN,
    _STRUCT_DECOR,
    _STRUCT_LINE,
    _TABLE_BLOCK,
    _TR_BLOCK,
    _TRAILING_NUM,
    _schedule_ordinal,
)


def inv_no_page_number_bleed(doc):
    """A running-footer page number must never bleed into the text.

    The footer number equals one of the leaf's own pages -- either the physical
    PDF page or its printed equivalent (pdf - 19 for the body).  We only flag a
    trailing number that matches one of those, so legitimate trailing numbers
    (rate amounts like "Rs. 800", cross-refs like "section 113") are not false
    positives.
    """
    bad = []
    for leaf in iter_all_leaves(doc):
        sp, ep = leaf.get("start_page"), leaf.get("end_page")
        if sp is None or ep is None:
            continue
        plausible = set()
        for p in range(sp, ep + 1):
            plausible.add(p)          # physical PDF page
            plausible.add(p - 19)     # printed page (body offset)
        for line in leaf.get("plain_text", "").split("\n"):
            m = _TRAILING_NUM.search(line.strip())
            if m and int(m.group(1)) in plausible:
                bad.append(f"section {leaf.get('code')}: footer page {m.group(1)} bled into text")
                break
    return bad


def _ref_key(ref: str):
    """Numeric order for a '<printed-page>.<marker>' ref; '*' notes come
    before the numbered notes of their page, as printed in the footer."""
    page, _, marker = str(ref).partition(".")
    page_n = int(page) if page.isdigit() else 0
    if marker.isdigit():
        return (page_n, 1, int(marker))
    return (page_n, 0, 0)


def inv_no_year_marker_refs(doc):
    """A footnote marker is a small serial (1..~30) or '*'.  A ref like
    '19.2020' means a year inside quoted footnote text was misread as a marker,
    splitting the footnote -- the parser must fold those lines instead."""
    bad = []
    for leaf in iter_all_leaves(doc):
        for fn in leaf.get("footnotes", []):
            m = re.match(r"^\d+\.(\d+)$", str(fn.get("ref", "")))
            if m and int(m.group(1)) >= 100:
                bad.append(f"section {leaf.get('code')}: year-like footnote ref {fn.get('ref')!r}")
    return bad


def inv_leading_marker_cited(doc):
    """Every leaf that opens with an amendment marker must render a citation.

    Guards the classes fixed on 2026-07-04: heading-region markers dropped
    from html (236Y/236Z/4AB), and omitted-section bracket lines rendered
    without their <sup> citations (236T's '4[5[ ]]')."""
    bad = []
    for leaf in iter_all_leaves(doc):
        first = (leaf.get("plain_text") or "").lstrip().split("\n", 1)[0]
        if _LEADING_AMEND_MARKER.match(first.replace(" ", "")) \
                and '<sup class="cite"' not in (leaf.get("html") or ""):
            bad.append(f"section {leaf.get('code')}: leading amendment marker "
                       f"with no <sup> citation in html")
    return bad


def inv_no_jammed_words(doc):
    """No leaf or footnote text may contain a jammed run of glued words.

    Guards the word-glue rule: fully-justified lines compress real word gaps
    below the glue threshold; the space characters in the PDF are the ground
    truth for word boundaries (pagemodel._mark_space_before)."""
    bad = []
    for leaf in iter_all_leaves(doc):
        m = _JAMMED_RUN.search(leaf.get("plain_text", ""))
        if m:
            bad.append(f"section {leaf.get('code')}: jammed words {m.group(0)[:40]!r}")
        for fn in leaf.get("footnotes", []):
            m = _JAMMED_RUN.search(fn.get("text", ""))
            if m:
                bad.append(f"footnote {fn.get('ref')}: jammed words {m.group(0)[:40]!r}")
    return bad


def inv_no_structural_heading_in_body(doc):
    """No leaf body line may be a (possibly marker-decorated) structural
    heading -- those lines are boundaries and live in the tree, not in text.

    Exception: a structural heading QUOTED inside a "... read as follows:"
    amendment note is repealed history, not a live boundary, so lines after
    that cue in the same leaf are skipped.  This is safe because a genuine
    active heading always starts a NEW leaf and so can never appear after the
    cue within one leaf's body.
    """
    bad = []
    for leaf in iter_all_leaves(doc):
        in_quote = False
        for ln in (leaf.get("plain_text") or "").split("\n"):
            if not in_quote and _QUOTE_CUE.search(ln):
                in_quote = True
            if in_quote:
                continue
            s = _STRUCT_DECOR.sub("", ln.strip())
            if _STRUCT_LINE.match(s):
                bad.append(f"section {leaf.get('code')}: structural heading "
                           f"in body: {ln.strip()!r}")
                break
    return bad


def inv_preamble_present(doc):
    """The enacting preamble (text before section 1) must be captured."""
    pre = (doc.get("preamble") or {}).get("plain_text", "")
    if "ORDINANCE" in pre and "WHEREAS" in pre:
        return []
    return ["preamble missing or incomplete (no 'AN ORDINANCE ... WHEREAS ...')"]


def inv_numbering_row_in_thead(doc):
    """A table's ``(1) (2) ...`` column-numbering row must sit inside <thead>.

    The QA screenshots of 2026-07-08 (First Schedule Division II super-tax
    table) showed the numbering row and the year sub-header rows rendered as
    DATA rows because thead was cut at the first physical row.  Any fbr-table
    whose tbody contains a row made only of "(n)" tokens has regressed."""
    bad = []
    for leaf in iter_all_leaves(doc):
        for table in _TABLE_BLOCK.findall(leaf.get("html") or ""):
            _, _, tbody = table.partition("</thead>")
            for tr in _TR_BLOCK.findall(tbody):
                cells = [c.strip() for c in _CELL_TEXT.findall(tr)]
                nonempty = [c for c in cells if c]
                if len(nonempty) >= 2 and all(_NUM_ONLY.match(c) for c in nonempty):
                    bad.append(f"section {leaf.get('code')}: numbering row "
                               f"{nonempty} rendered in tbody, not thead")
    return bad


def inv_structure_counts(doc):
    """Edition-aware structural sanity.

    The Ordinance has 13 chapters in every edition, and its metadata counts must
    match the tree.  The schedule COUNT, however, is edition-dependent -- new
    schedules were added over the years (9 in the 30.06.2018 edition, 15 by
    31.07.2025) -- so instead of a fixed floor the ordinal-titled schedules must
    form a CONTIGUOUS run FIRST..Nth.  A gap means a schedule was dropped or its
    title went unrecognised (e.g. the 2020 Eleventh Schedule, printed as the
    freshly-inserted `1[“ELEVENTH SCHEDULE`); that is the real defect this guards.
    """
    bad = []
    md = doc.get("metadata", {})
    n_chapters = len(doc.get("chapters") or [])
    if n_chapters < 13:
        bad.append(f"chapters in tree {n_chapters} < 13")
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
        bad.append("no ordinal-titled schedules in tree")
    else:
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
    from fbr_ingest.discover import code_sort_key
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
    from fbr_ingest.toc import parse_toc
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
    from fbr_ingest.toc import parse_toc
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


def inv_no_bold_body_subsection_marker(doc):
    bad = []
    for leaf in iter_section_leaves(doc):
        m = _BOLD_BODY_MARKER.search(leaf.get("html") or "")
        if m:
            bad.append(f"section {leaf.get('code')}: bold subsection marker "
                       f"{m.group(0)!r}")
    return bad


def inv_preamble_no_chapter_heading(doc):
    """The enacting preamble must not contain the first chapter's heading.

    "CHAPTER I" / "PRELIMINARY" sit between the recitals and section 1; they
    belong to the chapter node (its code/heading) and must not ALSO be emitted
    as trailing text in ``preamble.html`` (they used to appear twice -- once in
    the preamble body, once as the chapter title).
    """
    pre = doc.get("preamble") or {}
    html = pre.get("html", "") or ""
    plain = pre.get("plain_text", "") or ""
    chapters = doc.get("chapters") or []
    code = str(chapters[0].get("code", "")).strip() if chapters else ""
    if code and (code in html or code in plain):
        return [f"preamble contains first chapter code {code!r}"]
    return []


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


def inv_schedule_parts_contiguous(doc):
    """RC-3: a schedule's PART codes must be contiguous roman numerals (I, II,
    III, ...).  A gap (PART I + PART III, no PART II) means a mid-page PART
    heading was missed and its rules merged into a neighbour (Ninth Schedule
    PART II, 2020)."""
    roman = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
             "VIII": 8, "IX": 9, "X": 10}
    bad = []
    for sch in doc.get("schedules", []):
        nums = []
        for p in sch.get("parts", []):
            m = re.match(r"PART\s+([IVX]+)$", str(p.get("code") or "").strip(), re.I)
            if m and m.group(1).upper() in roman:
                nums.append(roman[m.group(1).upper()])
        if len(nums) >= 2:
            want = list(range(min(nums), max(nums) + 1))
            missing = sorted(set(want) - set(nums))
            if missing:
                bad.append(f"{sch.get('code')}: PART numbers {sorted(nums)} "
                           f"skip {missing} (a mid-page PART heading was lost)")
    return bad


def inv_no_stray_space_hyphen(doc):
    """RC-7: a line-wrapped compound must rejoin without a stray space, in
    plain_text OR html ("sub-section", never "sub- section")."""
    bad = []
    for leaf in iter_all_leaves(doc):
        for field in ("plain_text", "html"):
            m = _STRAY_SPACE_HYPHEN.search(leaf.get(field, "") or "")
            if m:
                t = leaf.get(field) or ""
                bad.append(f"section {leaf.get('code')} [{field}]: "
                           f"stray-space hyphen {t[max(0, m.start() - 6):m.start() + 6]!r}")
                break
    return bad


#: This lane's footnote refs sort differently, so it rebinds the one shared invariant
#: that reads `_ref_key` -- see the `_common` module docstring.
inv_footnotes_in_numeric_order = partial(_common.inv_footnotes_in_numeric_order,
                                         ref_key=_ref_key)

#: 43 checks, not the Acts/Rules 53. The other ten assert things this pipeline has no
#: concept of (an OCR stage, provisional flagging, text-density floors), so they would
#: have nothing to read here.
_ORDER = [
    "no_glued_marker_digit",
    "no_bare_footnote_marker_line",
    "no_stray_space_hyphen",
    "no_duplicate_division_code_within_part",
    "no_glyph_spaced_cell",
    "no_footnote_note_in_body",
    "division_iia_non_empty",
    "schedule_parts_contiguous",
    "no_pua_glyphs",
    "no_bold_body_subsection_marker",
    "preamble_no_chapter_heading",
    "no_page_number_bleed",
    "no_stray_dotnumber",
    "no_orphan_marker_li",
    "no_omitted_heading_emdash",
    "footnote_schema",
    "footnote_refs_printed_page",
    "footnotes_in_numeric_order",
    "no_year_marker_refs",
    "no_split_ordinals",
    "leading_marker_cited",
    "no_jammed_words",
    "html_well_formed",
    "strong_balanced",
    "no_heading_word_duplication",
    "schedules_have_content",
    "no_structural_heading_in_body",
    "no_footnote_text_in_body",
    "footnote_on_citing_leaf",
    "insertion_note_paired_with_omission",
    "no_dropped_table_row_paragraph",
    "numbering_row_in_thead",
    "no_serial_first_row_in_thead",
    "no_formula_legend_inside_cell",
    "no_inline_formula_legend",
    "no_control_chars",
    "preamble_present",
    "no_toc_row_in_heading",
    "structure_counts",
    "no_orphan_sections",
    "section_carries_its_body",
    "no_foreign_section_start_in_body",
    "section_codes_ordered",
    "toc_first_chapter_parse",
    "toc_schedule_regexes",
    "contract_complete",
]

ALL_INVARIANTS = _common.all_invariants(globals(), _ORDER)
