"""End-to-end pipeline: PDF path in, target-format JSON dict out."""

from __future__ import annotations

import re
import re as _re

import pdfplumber

from .builder import LineRef, build_sections
from .calibrate import calibrate
from .discover import _omission_codes
from .footnotes import (
    BRACKETS_ONLY_RE,
    all_markers_anonymous,
    parse_footnotes,
    ref_sort_key,
)
from .pagemodel import build_page_model
from .profiles import ACTS, Profile
from .schedules import _kind, _sched_ordinal, build_schedules
from .toc import Node, parse_toc

# A TOC row that already reads as a body-less placeholder ("Omitted by the
# Finance Act, 2006", "Section re-numbered as 60C", "Inserted by ...") -- as
# opposed to an operative section title landing on an omitted section.
_PLACEHOLDER_TITLE_RE = re.compile(
    r"\b(?:[Oo]mitted|[Rr]epealed|re-?numbered|[Ii]nserted|[Ss]ubstituted)\b")


def _toc_lines(pdf, n_pages: int) -> list[str]:
    """Layout-preserving text of the first ``n_pages`` (the TOC)."""
    lines: list[str] = []
    for i in range(n_pages):
        txt = pdf.pages[i].extract_text(layout=True) or ""
        lines.extend(txt.split("\n"))
    return lines


def cover_footnote_collector_pages(leaves, pages, has_body, has_notes) -> int:
    """Extend ``end_page`` of the last leaf in each body run through its collector notes.

    Customs (and similar) print footnote-only pages after a body run.  Leaf
    ranges track body text, so PDF pages that hold only those notes sit in a
    hole between ``s.N.end_page`` and ``s.N+1.start_page`` -- portal
    ``/sections/by-page`` returns nothing even though the notes are attached.
    Extending ONLY the last leaf whose ``start_page`` falls in the body run
    keeps earlier leaves' spans tight (avoiding the 34-page inflation that
    broke orphan adoption / page-bleed when every citing leaf claimed its
    notes' pages).  Call AFTER ``adopt_orphan_footnotes`` so adoption still
    uses body-only ranges + ``note_body_pages``.
    """
    covered = [lf for lf in leaves
               if lf.get("start_page") is not None and lf.get("end_page") is not None]
    if not covered:
        return 0
    n_ext = 0
    for bodies, notes in footnote_runs(pages, has_body, has_notes):
        if not bodies or not notes:
            continue
        # pure collector pages after the body run (mixed body+notes pages
        # already sit inside some leaf's range)
        collectors = [p for p in notes
                      if p > max(bodies) and has_notes.get(p) and not has_body.get(p)]
        if not collectors:
            continue
        note_end = max(collectors)
        candidates = [lf for lf in covered
                      if bodies[0] <= lf["start_page"] <= bodies[-1]]
        if not candidates:
            continue
        last = max(candidates,
                   key=lambda lf: (lf["start_page"], lf.get("end_page") or 0))
        prev = last.get("end_page") or 0
        if prev >= note_end:
            continue
        last["end_page"] = note_end
        n_ext += 1
    return n_ext


def footnote_runs(pages, has_body, has_notes) -> list[tuple[list[int], list[int]]]:
    """Pair each run of body pages with the footnote pages that annotate it.

    Two layouts occur in this corpus and both must bind correctly:

      bottom-of-page (Sales Tax, Federal Excise, and the Ordinance) -- every
        page carries its own notes, so each page is its own run and this reduces
        exactly to the same-page lookup used before;

      collector pages (the Customs Act) -- a body run of six or so pages is
        followed by two or three pages that are ENTIRELY footnotes, and the
        markers restart per block.  A same-page lookup finds nothing for those
        (275 of 671 notes on this edition), so the by-citation binding drops them
        and only the orphan-adoption net catches some.

    A run closes on the page that carries notes AND body (self-contained), or at
    the end of a pure-footnote stretch.  Closing at the end of the stretch --
    rather than on the first footnote page -- is what keeps a block's notes
    together when it spans several collector pages.
    """
    runs: list[tuple[list[int], list[int]]] = []
    cur_body: list[int] = []
    cur_notes: list[int] = []
    for i, p in enumerate(pages):
        if has_body.get(p):
            cur_body.append(p)
        if has_notes.get(p):
            cur_notes.append(p)
        nxt = pages[i + 1] if i + 1 < len(pages) else None
        # A run ends only when the NEXT page resumes body text.  Closing on the
        # current page instead (because it carries notes of its own) was wrong:
        # the Customs Act's collector block opens on a mixed page whose bottom
        # already holds notes, so closing there consumed the body pages and the
        # pure-footnote pages that followed inherited an empty body run -- which
        # is why the orphan fallback had nothing to attach them to.
        # ponytail: a body run with no notes anywhere keeps accumulating, so a
        # marker could in principle resolve against a later block's note of the
        # same number.  Not reachable in this corpus (every block prints notes);
        # bound the run by chapter if an edition ever shows it.
        ends = nxt is None or has_body.get(nxt)
        if cur_notes and ends:
            runs.append((cur_body, cur_notes))
            cur_body, cur_notes = [], []
    if cur_body:
        runs.append((cur_body, cur_notes))
    return runs


def _citation_scope(page_footnotes, pages, has_body, has_notes):
    """``(footnote_map, cited_footnotes)`` keyed by the page that CITES a note.

    Keying the citation view by citing page -- rather than by the page the note
    is printed on -- lets the builder keep its same-page lookup unchanged while
    still resolving markers to notes collected pages later.  Each Footnote keeps
    its own ``pdf_page``, so refs still name where the note is printed.
    """
    from .footnotes import CONT_MARKER

    # Document-wide index, used ONLY for markers that occur exactly once in the
    # whole document.  Editions differ in how they number notes: the 2025 Customs
    # edition restarts numbering in every collector block (so a marker must be
    # resolved within its own run, or "5" binds to the wrong note), while the
    # 2014 edition numbers them globally into the 100s across many blocks (so
    # run-scoping alone left 196 citations unresolved -- their notes existed, two
    # collector blocks away).  A marker that is unique document-wide has exactly
    # one possible note, so binding it carries no ambiguity; a repeated marker is
    # never added here and stays run-scoped.
    occurrences: dict[str, list] = {}
    for pg, fns in page_footnotes.items():
        for fn in fns:
            if fn.marker == CONT_MARKER:
                continue
            occurrences.setdefault(fn.marker, []).append(fn)
    unique = {m: v[0] for m, v in occurrences.items() if len(v) == 1}

    fmap: dict[int, dict] = {}
    cited: dict[int, list] = {}
    for bodies, notes in footnote_runs(pages, has_body, has_notes):
        merged: dict = {}
        allf: list = []
        for np in notes:
            for fn in page_footnotes.get(np, []):
                # (title, page the note is printed on) -- the second half is what
                # lets the rendered <sup> ref agree with the attached footnote's
                # ref when the two live on different pages.
                merged.setdefault(fn.marker, (fn.text, fn.pdf_page or np))
                allf.append(fn)
        for marker, fn in unique.items():
            if marker not in merged:
                merged[marker] = (fn.text, fn.pdf_page)
                allf.append(fn)
        for bp in bodies:
            fmap[bp] = merged
            cited[bp] = allf
    return fmap, cited



#: "S.R.O. 450(I)/2001, dated 18.6.2001" and its many spacings/spellings. The number
#: and year are what identify it; the rest of the line varies by edition.
_SRO_RE = _re.compile(
    r"S\.?\s?R\.?\s?O\.?\s*(?P<num>\d{1,4})\s*\(\s*(?P<series>[IVX1]+)\s*\)\s*"
    r"[/\\_]\s*(?P<year>(?:19|20)\d{2})",
    _re.IGNORECASE,
)


def _notifying_sro(refs, scan_lines: int = 400) -> str | None:
    """The S.R.O. these rules were notified by, from the head of the body.

    Only the head: an S.R.O. deeper in the document is an amendment citation, of which
    there are hundreds (the Sales Tax Rules footnotes cite one per amendment), and
    taking the last or the commonest would name the wrong instrument.
    """
    for ref in refs[:scan_lines]:
        match = _SRO_RE.search(ref.line.text())
        if match:
            return (f"S.R.O. {match.group('num')}({match.group('series').upper()})"
                    f"/{match.group('year')}")
    return None


def _demo() -> None:
    """Self-check: the S.R.O. grammar, which identifies the instrument."""
    # Chapter ORDER is the contents page's, not a numeral arithmetic's.
    # _roman_value sums a suffix's letters, so XIV-AA and XIV-B both come to
    # 14.02 and XIV-AB, XIV-BA and XIV-C all to 14.03 -- sorting by it interleaved
    # two families of Sales Tax Rules 2006 and put chapters printed on pages
    # 123-125 after ones on 129-158.  A suffix is alphabetical, not additive.
    class _Ch:
        def __init__(self, code):
            self.code = code

    _src = ["CHAPTER XIV", "CHAPTER XIVA", "CHAPTER XIV-A", "CHAPTER XIV-AA",
            "CHAPTER XIV-AB", "CHAPTER XIV-AC", "CHAPTER XIV-AD", "CHAPTER XIV-B",
            "CHAPTER XIV-BA", "CHAPTER XIV-BB", "CHAPTER XIV-C", "CHAPTER XIV-D"]
    assert sorted(_src, key=lambda c: _chapter_sort_key(_Ch(c))) == _src, \
        sorted(_src, key=lambda c: _chapter_sort_key(_Ch(c)))
    # XIVA and XIV-A are two DIFFERENT chapters and share a key; the sort must
    # leave them in the order the contents page gave, not order them by
    # punctuation.  A code tiebreak puts "XIV-A" first and fails here.
    assert [c for c in sorted(["CHAPTER XIVA", "CHAPTER XIV-A"],
                              key=lambda c: _chapter_sort_key(_Ch(c)))] == \
        ["CHAPTER XIVA", "CHAPTER XIV-A"]

    cases = [
        ("CUSTOMS RULES, 2001 (S.R.O.450(I)/2001, DATED 18.6.2001)", "S.R.O. 450(I)/2001"),
        ("Notification No. S.R.O. 918(I)/2019, dated 7th August, 2019",
         "S.R.O. 918(I)/2019"),
        # the corpus writes the separator as an underscore in places
        ("S.R.O406(I)_2023 - PSW Trade Data Dissemination Rules", "S.R.O. 406(I)/2023"),
        ("SRO 1126(I)/2010 dated 27.11.2010", "S.R.O. 1126(I)/2010"),
        ("this line mentions no notification at all", None),
        ("section 450 of the Act", None),
    ]
    for text, want in cases:
        match = _SRO_RE.search(text)
        got = (f"S.R.O. {match.group('num')}({match.group('series').upper()})"
               f"/{match.group('year')}") if match else None
        assert got == want, (text, got, want)

    from .builder import LineRef
    from .pagemodel import Line, Word
    from .toc import parse_toc

    def _ln(text, page=40, top=100.0):
        words, x = [], 72.0
        for tok in text.split():
            words.append(Word(text=tok, x0=x, x1=x + len(tok) * 5, top=top,
                              size=12.0, fontname="Arial-BoldMT"))
            x += len(tok) * 5 + 3
        return LineRef(page=page, line=Line(top=top, words=words))

    # A body-discovered section is parented by WHERE IT IS, not by where its code
    # happens to be printed.  Sales Tax Act 1990 defines "supply chain" as clause
    # "[(33A)" inside section 2, so _codes_in_span puts 33A in CHAPTER I's span;
    # CHAPTER I is processed first and claimed it, and CHAPTER VII -- where s.33A
    # is actually printed, 55 pages later -- then found the parent already set.
    # section_codes_ordered reported that as "3 out of order after 33A".
    from .toc import SectionEntry as _SE

    # CHAPTER II sits between them on purpose: with only two chapters the second
    # pass reassigns 33A anyway (its parent IS the previous chapter), and the
    # defect does not reproduce.  In the real document ten chapters intervene.
    _refs = [_ln("CHAPTER I", page=2),
             _ln("2. Definitions.- In this Act, unless there is anything", page=2),
             _ln("3[(33A) supply chain means the series of transactions", page=3),
             _ln("CHAPTER II", page=5),
             _ln("5. Change in the rate of tax.- If there is a change in", page=5),
             _ln("CHAPTER VII", page=9),
             _ln("33A. Proceedings against authority.- Subject to section", page=9)]
    _e2 = _SE(code="2", heading="Definitions", printed_page=2, anchor=_refs[1])
    _e5 = _SE(code="5", heading="Change in the rate of tax", printed_page=5,
              anchor=_refs[4])
    _e33a = _SE(code="33A", heading="Proceedings against authority",
                printed_page=9, anchor=_refs[6])
    _chs: list = []
    insert_missing_body_chapters(_chs, [_e2, _e5, _e33a], _refs)
    _by = {c.code: c for c in _chs}
    assert set(_by) == {"CHAPTER I", "CHAPTER II", "CHAPTER VII"}, \
        [c.code for c in _chs]
    assert _e2.parent is _by["CHAPTER I"], getattr(_e2.parent, "code", None)
    assert _e5.parent is _by["CHAPTER II"], getattr(_e5.parent, "code", None)
    assert _e33a.parent is _by["CHAPTER VII"], getattr(_e33a.parent, "code", None)

    toc_lines = [
        "        CHAPTER III",
        "        DECLARATION OF PORTS, AIRPORTS, LAND CUSTOMS STATIONS, ETC.",
        "        14.  Stations for officers of customs to board and land.  39",
        "        14A. Provision of accommodation at customs ports, etc.    40",
        "             PROHIBITION AND RESTRICTION OF IMPORTATION AND EXPORTATION",
        "        15.  Prohibitions.                                        41",
        "        CHAPTER V",
        "        LEVY OF, EXEMPTION FROM AND REPAYMENT OF, CUSTOMS-DUTIES",
        "        18.  Goods dutiable.                                      45",
    ]
    chs, _sch, secs = parse_toc(toc_lines)
    body = [
        _ln("CHAPTER III", 39),
        _ln("DECLARATION OF PORTS, AIRPORTS, LAND CUSTOMS STATIONS, ETC.", 39),
        _ln("14. Stations for officers of customs to board and land.— Officers", 39),
        _ln("14A. Provision of security and accommodation at Customs-ports, etc.— Any", 40),
        _ln("CHAPTER IV", 41),
        _ln("PROHIBITION AND RESTRICTION OF IMPORTATION AND EXPORTATION", 41),
        _ln("15. Prohibitions.— The Federal Government may", 41),
        _ln("CHAPTER V", 45),
        _ln("LEVY OF, EXEMPTION FROM AND REPAYMENT OF, CUSTOMS-DUTIES", 45),
        _ln("18. Goods dutiable.— Except as otherwise provided", 45),
    ]
    n_ins = insert_missing_body_chapters(chs, secs, body)
    assert n_ins >= 1, n_ins
    assert [c.code for c in chs] == ["CHAPTER III", "CHAPTER IV", "CHAPTER V"], \
        [c.code for c in chs]
    ch4 = next(c for c in chs if c.code == "CHAPTER IV")
    assert ch4.heading == "PROHIBITION AND RESTRICTION OF IMPORTATION AND EXPORTATION"
    assert ch4.heading_source == "body"
    by = {e.code: e for e in secs}
    assert by["14A"].parent is chs[0]
    assert by["15"].parent is ch4, (by["15"].parent and by["15"].parent.code)
    assert by["18"].parent is chs[2]

    # A chapter heading wearing a footnote marker AND the amendment bracket is
    # still a chapter heading. The Sales Tax Act, 1990 prints its first one as
    # "4 [Chapter-I" and the rest bare, so CHAPTER I was invisible to the body
    # scan, sections 1 and 2 had no container, and the 30.06.2020 and 31.12.2019
    # editions refused to convert at all.
    assert [num for _i, num, _c in body_chapter_entries([_ln("4 [Chapter-I", 2)])] \
        == ["I"]
    assert [num for _i, num, _c in body_chapter_entries([_ln("1[CHAPTER XVI-A", 9)])] \
        == ["XVI-A"]

    # ...and a numeral is matched by VALUE, not spelling. The Customs Act 1969
    # prints "CHAPTER 1" on page 23 and roman everywhere else; matching as
    # strings inserted a second, EMPTY chapter beside the real CHAPTER I in 19
    # editions -- which is why they all reported 23 chapters against a contents
    # page that says 22.
    chs2, _s2, secs2 = parse_toc(["        CHAPTER I", "        PRELIMINARY",
                                  "        1.  Short title.   1"])
    before = [c.code for c in chs2]
    assert insert_missing_body_chapters(chs2, secs2, [
        _ln("CHAPTER 1", 23), _ln("PRELIMINARY", 23),
        _ln("1. Short title.— This Act may", 23)]) == 0
    assert [c.code for c in chs2] == before == ["CHAPTER I"], [c.code for c in chs2]

    # ...and ONLY that gap. Sales Tax Rules 2006 carries CHAPTER XIVA (omitted)
    # and CHAPTER XIV-A (monitoring) as two different chapters, which share a
    # _roman_value; a value-only match would have dropped one of them.
    chs3, _s3, secs3 = parse_toc(["        CHAPTER XIV-A", "        MONITORING",
                                  "        150.  Application.   9"])
    assert insert_missing_body_chapters(chs3, secs3, [
        _ln("CHAPTER XIVA", 12), _ln("OMITTED", 12)]) == 1
    assert sorted(c.code for c in chs3) == ["CHAPTER XIV-A", "CHAPTER XIVA"], \
        [c.code for c in chs3]

    # ---- amending-clause headings, pinned on the real corpus -------------
    # Every shape below is a verbatim clause heading from the 30 amending
    # documents on disk. They are the reason the pattern has five verbs, an
    # inner provision split and a body-glue cut, rather than one "Amendments
    # of the X Act" literal.
    class _N:
        def __init__(self, sections):
            self.sections, self.parts, self.divisions = sections, [], []

    for heading, instrument, citation, provision in (
        ("Amendments of the Customs Act, 1969 (IV of 1969)",
         "Customs Act, 1969", "IV of 1969", ""),
        ("Amendments in the Income Tax Ordinance, 2001 (XLIX of 2001). In the",
         "Income Tax Ordinance, 2001", "XLIX of 2001", ""),
        ("Amendment of section 7, Act VII of 2010", "Act VII of 2010", "", "section 7"),
        ("Insertion of new section 19C, Act XXVII of 1997",
         "Act XXVII of 1997", "", "section 19C"),
        ("Amendment of Ordinance XLIX of 2001", "Ordinance XLIX of 2001", "", ""),
        ("Amendments of the Federal Excise Act, 2005.ln the Federal Excise Act, "
         "2005, the following", "Federal Excise Act, 2005", "", ""),
    ):
        got = amended_instruments([_N([{"code": "4", "heading": heading}])])[0]
        assert (got["instrument"], got["citation"], got["provision"]) == \
               (instrument, citation, provision), (heading, got)
    # A consolidated act's own section titles must name nothing.
    assert amended_instruments([_N([{"code": "2", "heading": "Definitions"},
                                    {"code": "9", "heading": "Repeal"}])]) == []

    # ---- node identity ---------------------------------------------------
    tree = [{"code": "CHAPTER VII", "parts": [
        {"code": "PART I", "divisions": [], "parts": [],
         "sections": [{"code": "114"}, {"code": "114"}]}],
        "divisions": [], "sections": []}]
    stamp_identity(tree, "chapter")
    assert tree[0]["type"] == "chapter" and tree[0]["node_key"] == "ch:vii"
    assert tree[0]["parts"][0]["node_key"] == "ch:vii/pt:i"
    # by CODE, not by array index -- and a repeated sibling code still resolves
    assert [s["node_key"] for s in tree[0]["parts"][0]["sections"]] == \
           ["ch:vii/pt:i/s:114", "ch:vii/pt:i/s:114~2"]
    # the synthetic root a flat act gets is named as synthetic, not positioned
    root = [{"code": "", "parts": [], "divisions": [], "sections": [{"code": "1"}]}]
    stamp_identity(root, "chapter")
    assert root[0]["node_key"] == "ch:~root"
    assert _slug("CHAPTER XIV-A", "chapter") == "xiv-a"
    assert _slug("114A", "section") == "114a"

    print("pipeline self-check passed")


def _resolve_profile(pdf_path: str, lane: "Profile", progress):
    """The profile to parse ``pdf_path`` with, when the caller asked for ``auto``.

    ``lane`` is the profile the corpus binding supplied -- ACTS from
    ``acts_ingest``, RULES from ``rules_ingest``. The family OVERRIDES it only
    when it names one, which today means only ``amending``.

    That fallback is the whole point, and it was the bug: ``families`` used to
    hardcode ``consolidated -> ACTS``, so ``--profile auto`` on the Rules lane
    resolved ACTS for all 34 of its consolidated documents and discarded eleven
    printer fields the Rules corpus needs (folio forms, raised ordinals,
    sub-chapter rows). A family knows what a document IS. Only the lane knows
    which printer set it.

    Split out of ``run`` so the resolution can be tested without a PDF --
    ``tools/tests/test_profile_auto_resolves_the_lane.py`` runs it over every
    record in the committed ``tools/discovery/signatures.json``.
    """
    from .families import BY_LABEL, classify
    from .signature import measure

    assignment = classify(measure(pdf_path))
    family = BY_LABEL.get(assignment.family) if assignment.family else None
    if family is None or not family.parseable:
        raise RuntimeError(
            f"refusing {pdf_path.split('/')[-1]!r}: "
            f"{assignment.family or 'no family'} is not parseable "
            f"({'; '.join(assignment.evidence)})")
    profile = family.profile or lane
    progress(f"family {assignment.family} "
             f"(confidence {assignment.confidence:.2f}) -> profile {profile.label}")
    return profile, assignment


def run(pdf_path: str, progress=lambda *a: None, _max_body_page: int | None = None,
        admit_below_floor: bool = False,
        profile: "Profile" = ACTS, auto: bool = False) -> dict:
    """Convert one PDF to the document dict.

    ``profile`` says how this document is printed; see
    :mod:`legal_ingest.profiles` for what varies. It defaults to the Acts, whose
    profile turns every corpus-specific widening off.

    ``auto`` measures the document first and asks
    :mod:`legal_ingest.families` what it IS -- see :func:`_resolve_profile`.
    ``profile`` stays the lane's answer and stays the fallback; a family
    overrides it only when it names one, which is how an amending instrument
    gets the amending profile (the Acts folder holds both kinds and the corpus
    label cannot tell them apart). A family that is not parseable -- a legacy
    ``.doc``, an Urdu edition, a scan with no text layer -- is refused here
    rather than parsed into nonsense.

    ``admit_below_floor`` converts a scan whose inter-engine agreement is under
    ``ocr.AGREEMENT_FLOOR`` instead of refusing it, stamping
    ``metadata.ocr.provisional = True``.  Default off, so nothing about the
    existing corpus changes.

    It exists because the user decided 2026-08-07 that the sub-floor files
    should be available WITH their per-token ``needs_review`` flags rather than
    withheld entirely -- nine documents, the worst being Finance Act 2016-17 at
    52.0% agreement, where roughly half the tokens are disputed and the flag is
    better read as a property of the whole file than as a pointer to a few
    words.  So this is deliberately not a relaxation of the floor: the caller
    must write a provisional document to ``output/_provisional/``, the corpus
    stays defined as ``output/*.json``, and ``inv_provisional_is_flagged``
    asserts that a below-floor document is flagged and is not in the corpus
    directory.  The floor stops being a wall and becomes a label, and it still
    ratchets.
    """
    assignment = None
    if auto:
        profile, assignment = _resolve_profile(pdf_path, profile, progress)

    pdf = pdfplumber.open(pdf_path)
    total_pages = len(pdf.pages)

    cal = calibrate(pdf, profile=profile)
    toc_pages = cal.toc_pages
    progress(f"calibrated: box {cal.page_w:.0f}x{cal.page_h:.0f}, "
             f"zone={cal.zone_mode}, body={cal.body_size}pt, "
             f"footnote={cal.footnote_size}pt, TOC pages={toc_pages}, "
             f"offset={cal.page_offset}")

    chapters, schedules, ordered_sections = parse_toc(_toc_lines(pdf, toc_pages), profile)
    progress(f"TOC parsed: {len(chapters)} chapters, {len(schedules)} schedules, "
             f"{len(ordered_sections)} sections")

    offset = cal.page_offset

    # Body page range: from first section to just before the first schedule.
    # H5: the body begins right after the front matter, full stop.  Deriving it
    # from the TOC's own folios instead was wrong on 6 of the 56 editions and
    # right nowhere it mattered: Sales Tax 15.01.2022 is missing its first five
    # PDF pages so its footers run +5 and the expression yielded page 2 (a
    # contents page, which then became the "preamble"), while the Federal Excise
    # 2019/2020 editions ship a STALE TOC whose folios trail the body by 2-3
    # pages, so it yielded page 10 and PDF pages 7-9 were never read at all (41
    # body + 42 footnote words lost).  detect_toc_pages measures the front matter
    # from real TOC row density, so toc_pages + 1 is the body start by
    # construction and can never skip a page.  (m3-handoff H5: measured against
    # the real body start on all 46 converted editions -- no-op on 30, one extra
    # front-matter page into the preamble on 9, repairs 4, loses nothing.)
    first_body_page = toc_pages + 1
    last_body_printed = max(s.printed_page for s in ordered_sections) if ordered_sections else 0
    # extend a few pages past the last section start to capture its tail
    last_body_page = min(total_pages, last_body_printed + offset + 6)
    if _max_body_page is not None:
        last_body_page = min(last_body_page, _max_body_page)

    # Scan from the body start to the end of the document.  Sections live before
    # the first Schedule title; the schedules follow.  We collect body lines,
    # schedule lines, per-page footnotes and each page's printed number.
    scan_end = total_pages if _max_body_page is None else min(total_pages, _max_body_page)
    body_refs: list[LineRef] = []
    sched_refs: list[LineRef] = []
    page_footnotes: dict[int, list] = {}
    footnote_map: dict[int, dict] = {}
    printed_by_page: dict[int, int] = {}
    schedule_start: int | None = None

    has_body: dict[int, bool] = {}
    has_notes: dict[int, bool] = {}
    ocr_pages: list = []          # PageOCR per OCR'd page, for the fidelity gate

    for pidx in range(first_body_page, scan_end + 1):
        pm = build_page_model(pdf.pages[pidx - 1], pidx, cal, pdf_path, ocr_pages)
        if pm.printed_page:
            printed_by_page[pidx] = pm.printed_page
        if schedule_start is None and _page_starts_schedules(pm):
            schedule_start = pidx
        # H8: on the TRANSITION page the split is mid-page, so it must be made at
        # the title LINE, not at the page boundary.  Federal Excise prints the
        # tail of ss.48/49 and then FIRST SCHEDULE on one page (01.07.2017 p50,
        # both 2019 editions p68); bucketing that whole page as schedule content
        # dropped those sections' closing words, because build_schedules ignores
        # everything above the first schedule title ("... shall stand repealed",
        # "... for valuation, in respect of any other service or control
        # mechanism provided by any formation under the control of the Board").
        bucket = (sched_refs if schedule_start is not None and schedule_start < pidx
                  else body_refs)
        for ln in pm.body_blocks:
            if schedule_start == pidx and _opens_schedules(ln.text().strip()):
                bucket = sched_refs
            bucket.append(LineRef(page=pidx, line=ln))
        fns = parse_footnotes(pm.footnote_lines, pm.footnote_tables, cal)
        for fn in fns:
            fn.pdf_page = pidx
            fn.end_pdf_page = pidx
        page_footnotes[pidx] = fns
        footnote_map[pidx] = {fn.marker: (fn.text, pidx) for fn in fns}
        has_body[pidx] = bool(pm.body_blocks)
        has_notes[pidx] = bool(fns)
        if pidx % 50 == 0:
            progress(f"  scanned page {pidx}/{scan_end}")

    # THE FIDELITY GATE.  A scanned file may only be shipped above the floor.
    #
    # This is the decision the user took ("admit a scanned file only above a
    # fidelity floor; excluded files get a report, not bad text") and until now
    # nothing enforced it.  ocr.Fidelity.admitted was read at exactly two lines
    # in the repo -- inside scripts/ocr_review.py, to SORT A MARKDOWN TABLE --
    # while the conversion path never imported ocr at all.  So the Right of
    # Access to Information Act 2017 was measured at 80.49% agreement, recorded
    # as EXCLUDE, and then written to output/ ~39 hours later by a code path
    # with no way to learn the verdict existed, shipping "Right to have access
    # to information not to be denied.-(!)" and "in + the pre we am ambi or na
    # na ta bleandt" as statutory text.
    #
    # It sits HERE, straight after the scan loop, for two reasons: this is the
    # last point where every OCR'd page is still in hand (so the score costs no
    # second recognition pass), and refusing now skips the whole assembly.
    # run() is the single path convert_all.py -> acts_pdf_to_json.py -> run()
    # uses, and acts_pdf_to_json.py is the only writer, so raising here is what
    # stops the file being written -- no caller can bypass it.
    fidelity = None
    if ocr_pages:
        from . import ocr as _ocr
        fidelity = _ocr.fidelity_of(pdf_path, ocr_pages)
        progress(f"OCR fidelity: {len(ocr_pages)} page(s), "
                 f"{fidelity.mean_agreement:.2f}% inter-engine agreement, "
                 f"{fidelity.low_conf_share:.2f}% low-confidence tokens")
        if not fidelity.admitted and not admit_below_floor:
            raise RuntimeError(
                f"OCR fidelity below the floor for {pdf_path!r}: "
                f"{fidelity.reason}. Refusing to emit legally binding text from "
                f"a recognition this uncertain -- rerun scripts/ocr_review.py "
                f"for the per-token evidence, and request a clean source PDF.")
        if not fidelity.admitted:
            # Opt-in only, and it does NOT put the file in the corpus: the
            # caller writes a provisional document to output/_provisional/.
            # See the `admit_below_floor` note in this function's docstring.
            progress(f"ADMITTED BELOW THE FLOOR as provisional: "
                     f"{fidelity.reason}")

    # Repair the footer page numbers before ANY ref is minted.  The PDF
    # misprints several footers (e.g. pdf 188 prints "189" between "168" and
    # "170"; pdf 533 prints "517" between "513" and "515"), and every footnote
    # ref derives from the printed number -- an unrepaired misprint mints a
    # wrong ref AND breaks the (ref, text) dedup between the by-citation and
    # orphan-adoption paths, duplicating footnotes under two different refs.
    printed_by_page = sanitize_printed_pages(printed_by_page,
                                             first_body_page, scan_end)

    # The page-level split can start the schedule region on a title the schedule
    # BUILDER will not accept -- a quoted or out-of-order one.  Everything before
    # the first title it does accept is body text sitting in the wrong bucket, and
    # it used to be discarded (ledger P19: Finance Act 2014, 1,340 words, pages
    # 28-55).  Give it back to the body BEFORE sections are built, so a section
    # claims it and it is attributed as well as conserved.  Order is preserved:
    # every schedule ref follows every body ref in the document.
    if sched_refs:
        from .schedules import first_schedule_index
        cut = first_schedule_index(sched_refs)
        if cut is None:
            progress(f"no acceptable schedule title: {len(sched_refs)} line(s) "
                     f"returned to the body")
            body_refs.extend(sched_refs)
            sched_refs = []
        elif cut:
            progress(f"{cut} line(s) before the first schedule title returned "
                     f"to the body")
            body_refs.extend(sched_refs[:cut])
            sched_refs = sched_refs[cut:]

    # splice footnotes that continue across a page break before assembling,
    # then rebuild the citation-title map so titles carry the full text
    from .footnotes import merge_footnote_continuations
    merge_footnote_continuations(page_footnotes)
    # Build the CITATION view: which notes a given body page can resolve markers
    # against.  For a bottom-of-page layout this is the page's own notes; for the
    # Customs Act's collector pages it is the footnote run that follows the body
    # run.  ``page_footnotes`` itself stays keyed by the printing page, because
    # the orphan-adoption net and every ref depend on that.
    scan_pages = list(range(first_body_page, scan_end + 1))
    footnote_map, cited_footnotes = _citation_scope(
        page_footnotes, scan_pages, has_body, has_notes)
    # inverse view: which body pages a note page annotates, for the orphan net
    note_body_pages = {np: bodies
                       for bodies, notes in footnote_runs(scan_pages, has_body,
                                                          has_notes)
                       for np in notes}

    # TOC-less edition (31.07.2025 prints no table of contents): reconstruct
    # the chapter tree and ordered section list from the body itself.
    if not ordered_sections:
        from .discover import discover_structure
        chapters, ordered_sections = discover_structure(
            body_refs, printed_by_page, page_footnotes, profile=profile)
        progress(f"body-driven structure: {len(chapters)} chapters, "
                 f"{len(ordered_sections)} sections")

    n_bch = apply_body_chapter_headings(chapters, body_refs)
    if n_bch:
        progress(f"{n_bch} chapter heading(s) taken from the body caption")
    n_ins = insert_missing_body_chapters(chapters, ordered_sections, body_refs)
    if n_ins:
        progress(f"{n_ins} chapter(s) filled/inserted from body (omitted from TOC)")

    # Every container, flattened: both ``build_sections`` (which hands a cut region
    # to the section that follows the heading) and ``preamble_refs`` need to know
    # which lines a CHAPTER/PART/Division node already holds as its own title.
    def _flatten_containers(nodes):
        for n in nodes:
            yield n
            yield from _flatten_containers(getattr(n, "parts", []) or [])
            yield from _flatten_containers(getattr(n, "divisions", []) or [])
    containers = list(_flatten_containers(chapters))

    # ``footnote_map`` / ``cited_footnotes`` are the CITATION view (a Customs
    # body page resolves markers against the collector run that follows it).
    # ``page_footnotes`` stays keyed by the page that PRINTS each note -- that
    # is what same-page / +1 attach and the orphan net must see.  Collector
    # notes bind via ``cited_footnotes`` keyed by the CITING page only (never
    # via looking one page ahead into the citation view -- that is what put
    # ``139.4`` on 155Q from a heading marker ``4``).
    built = build_sections(body_refs, ordered_sections, footnote_map,
                           page_footnotes, page_offset=offset,
                           printed_by_page=printed_by_page,
                           containers=containers,
                           cited_footnotes=cited_footnotes)

    # An omitted section survives in the body only as an empty amendment
    # bracket line ("3[ ]", "4[ 5[ ] ]") that would otherwise be swallowed by
    # the PREVIOUS section's segment -- putting its citations and footnotes on
    # the wrong section.  Claim each such line for its placeholder (located by
    # the page+marker of the footnotes naming the section) and rebuild.
    missing = [e for e in ordered_sections if id(e) not in built]
    placeholder_lines, claimed_ids = claim_placeholder_lines(
        missing, body_refs, page_footnotes, offset)
    if claimed_ids:
        body_refs = [r for r in body_refs if id(r) not in claimed_ids]
        built = build_sections(body_refs, ordered_sections, footnote_map,
                               page_footnotes, page_offset=offset,
                               printed_by_page=printed_by_page,
                               containers=containers,
                               cited_footnotes=cited_footnotes)
        progress(f"claimed {len(claimed_ids)} bracket lines for "
                 f"{len(placeholder_lines)} omitted sections")
    progress(f"assembled {len(built)} / {len(ordered_sections)} sections")

    schedules_out = build_schedules(sched_refs, cited_footnotes, footnote_map,
                                    printed_by_page, toc_schedules=schedules)
    progress(f"assembled {len(schedules_out)} schedules")

    # Every section MUST have a container: a parent-less entry means the TOC
    # parse failed to create its chapter (e.g. a decorated/merged chapter row)
    # and the section would silently vanish from the output tree.  This is
    # legal text -- refuse to emit a document that omits it.
    orphans = [e for e in ordered_sections if e.parent is None]
    # "Flat act" means the document declares no real CHAPTER -- not merely that
    # the roots list is empty.  Body discovery promotes a bare gazette "PART I"
    # to a root container, so `chapters` is non-empty for the Finance Acts even
    # though they have no chapters at all, and sections printed BEFORE that PART
    # were still orphaned and took the whole document down with them.
    has_real_chapters = any(getattr(c, "kind", "") == "chapter" and c.code
                            for c in chapters)
    if orphans and not has_real_chapters:
        # M4: a FLAT act has no chapters at all -- the 20 Finance Acts are a
        # gazette preamble followed by numbered amendment clauses ("4. Amendments
        # of the Customs Act, 1969 ..."), and the 15 single gazette Acts are flat
        # sections.  There is no container to fix, so synthesise exactly one, and
        # only in that case: a parentless section in a document that DOES declare
        # chapters is the A01 defect (a mis-parsed chapter row) and must stay loud.
        root = next((c for c in chapters
                     if getattr(c, "kind", "") == "chapter" and not c.code), None)
        if root is None:
            root = Node(kind="chapter", code="", heading="")
            chapters.append(root)
        for e in orphans:
            e.parent = root
        progress(f"flat act: {len(orphans)} section(s) attached to a synthetic "
                 f"root container")
        orphans = []
    if orphans and all(
        (
            _before_first_chapter(e, chapters, body_refs)
            if getattr(e, "anchor", None) is not None
            else _precedes_first_chapter_in_toc(e, ordered_sections)
        )
        for e in orphans
    ):
        # A section printed BEFORE the document's first chapter has no container to
        # belong to, and that is not a mis-parsed chapter row -- it is a gazette
        # that reproduces another Act.  The Public Finance Management Act 2019 PDF
        # is a Finance Act 2019 gazette: its own clauses 1, 2 and 18 ("Enactment of
        # Public Finance Management Act, 2019.—There is hereby enacted ...") print
        # on pages 2-3, ahead of the reproduced Act's CHAPTER I, so all three were
        # parentless and the conversion refused -- the file produced NOTHING for
        # four sessions.  Give them a root container of their own, at the front.
        root = Node(kind="chapter", code="", heading="")
        chapters.insert(0, root)
        for e in orphans:
            e.parent = root
        progress(f"{len(orphans)} clause(s) printed before the first chapter "
                 f"attached to a synthetic root container")
        orphans = []
    if orphans:
        raise RuntimeError(
            f"TOC parse left {len(orphans)} section(s) without a chapter "
            f"container ({', '.join(e.code for e in orphans[:5])}...): refusing "
            f"to drop them. Fix the TOC chapter detection for this edition.")

    # Attach built sections back into the TOC tree, in TOC order.
    for entry in ordered_sections:
        bs = built.get(id(entry))
        if bs is None:
            # A section with no extractable body text -- almost always one that
            # was *omitted/repealed* and now survives only as an empty "[ ]"
            # amendment bracket (its name lives in a footnote).  We emit a
            # placeholder carrying the TOC heading, and -- when its bracket
            # line was claimed above -- the rendered bracket itself, so every
            # attached footnote keeps a visible <sup> citation.
            import html as _h

            from .builder import _build_html as _bhtml
            from .builder import _render_line
            exp = entry.printed_page + offset
            fns = omission_footnotes(entry.code, exp, page_footnotes, offset)
            # The TOC row of a body-less section can be shifted: the 2021/2022
            # prints label s.16 "Omitted by the Finance Act, 2021" (it is in fact
            # printed in full) and hang s.16's title on s.17 -- the section that
            # really is omitted, by the Finance Act, 2006.  A TOC row carrying an
            # operative title on a section whose whole body is an empty bracket
            # is that shift; the omission footnote names the section and is
            # authoritative, so take its wording (as the other ten editions do).
            heading = entry.heading
            if not _PLACEHOLDER_TITLE_RE.search(heading or ""):
                for fn in fns:
                    named = [h for (c, h) in _omission_codes(fn["text"], set())
                             if c == entry.code and h]
                    if named:
                        heading = named[0]
                        break
            # An omitted/repealed placeholder ("N. Omitted by the Finance Act,
            # ...") is synthetic and has no operative title dash in the PDF --
            # don't fabricate a trailing em-dash on it.
            _tail = "" if re.search(r"\b[Oo]mitted\b|\b[Rr]epealed\b",
                                    heading or "") else ".—"
            head_html = (f'<h4 class="section-heading">'
                         f'{_h.escape(entry.code + ". " + heading)}{_tail}</h4>')
            html_doc = head_html
            plain = f"{entry.code}. {heading}"
            page_number = sp = ep = exp
            claim = placeholder_lines.get(id(entry))
            if claim:
                cited, rows, extra = [], [], []
                for r in claim:
                    p, h = _render_line(r.line, r.page, footnote_map, offset,
                                        cited)
                    if p.strip():
                        rows.append(("text", p, h))
                        extra.append(p)
                # attach every footnote the bracket line cites ("4[5[ ]]" ->
                # both 476.4 and 476.5), beyond the code-matched ones
                seen = {(f["ref"], f["text"]) for f in fns}
                fn_end = None
                for (pg, marker) in cited:
                    ref_ = f"{pg - offset}.{marker}"
                    for fn in page_footnotes.get(pg, []):
                        if fn.marker != marker:
                            continue
                        e = getattr(fn, "end_pdf_page", None)
                        if e is not None:
                            fn_end = e if fn_end is None else max(fn_end, e)
                        if (ref_, fn.text) in seen:
                            continue
                        seen.add((ref_, fn.text))
                        fns.append({"ref": ref_, "marker": ref_,
                                    "text": fn.text, "html": fn.html,
                                    "page": pg})
                fns.sort(key=lambda x: ref_sort_key(x["ref"]))
                if rows:
                    html_doc = _bhtml(head_html, rows)
                    plain += "\n" + "\n".join(extra)
                pages = [r.page for r in claim]
                page_number, sp, ep = pages[0], min(pages), max(pages)
                if fn_end is not None:
                    ep = max(ep, fn_end)  # footnote text continuing overleaf
            bs_dict = {
                "code": entry.code, "heading": heading,
                "toc_heading": entry.heading or "",
                "heading_source": "toc",
                "page_number": page_number,
                "html": html_doc,
                "plain_text": plain,
                "start_page": sp, "end_page": ep, "footnotes": fns,
            }
        else:
            bs_dict = {
                "code": bs.code, "heading": bs.heading,
                "toc_heading": bs.toc_heading,
                "heading_source": bs.heading_source,
                "page_number": bs.page_number, "html": bs.html,
                "plain_text": bs.plain_text, "start_page": bs.start_page,
                "end_page": bs.end_page, "footnotes": bs.footnotes,
            }
            # Only present where the text came from a scan, so a text-layer
            # document's JSON is byte-identical to before.
            if bs.ocr_review:
                bs_dict["ocr_review"] = bs.ocr_review
        parent = entry.parent
        if parent is not None:
            parent.sections.append(bs_dict)

    sections_count = sum(1 for _ in ordered_sections)

    metadata = {
        "filename": pdf_path.split("/")[-1],
        "total_pages": total_pages,
        "toc_pages_scanned": toc_pages,
        "chapters_count": len(chapters),
        "schedules_count": len(schedules_out),
        "sections_count": sections_count,
        # Recorded so the derived constants are auditable rather than invisible:
        # every page number, footnote ref and zone split in this document follows
        # from them, and the ``calibration_sane`` invariant checks them each run.
        "calibration": cal.as_dict(),
    }
    body_nums = [num for _i, num, _c in body_chapter_entries(body_refs)]
    if body_nums:
        metadata["body_chapter_numerals"] = body_nums
    # What KIND of instrument this is. The leaf of a rule set is a Rule, not a
    # Section, and the portal labels leaves from one function -- without this it
    # would have to infer the instrument from the document's title. Only set where
    # the profile names one: the Acts corpus has never carried the key, and adding
    # it would change every Act's output.
    if profile.instrument_kind:
        metadata["instrument_kind"] = profile.instrument_kind
    # The S.R.O. that notified these rules. Every rule set in this corpus is made
    # under one, its number is the instrument's real identity (titles are
    # inconsistent across editions -- "Sales Tax Rules 2006" and "THE SALES TAX
    # RULES, 2006" are the same instrument), and the reviewer needs it to check an
    # amendment against the gazette. It is printed on the first body page.
    if profile.notifying_sro:
        sro = _notifying_sro(body_refs)
        if sro:
            metadata["notified_by"] = sro
    if fidelity is not None:
        # File-level OCR provenance.  A consumer of a scanned edition must be
        # able to see, from the JSON alone, that this text was recognised rather
        # than extracted, by what, how well the engines agreed, and how many
        # tokens are doubted -- previously none of that survived the conversion.
        metadata["ocr"] = {
            "engines": "tesseract+rapidocr",
            "pages": fidelity.pages,
            # WHICH pages, not just how many.  Without this a reader cannot tell
            # whether a given section's text was recognised or extracted, and no
            # check can reconcile the flagged-token count against the leaves:
            # Finance Act 2022 and 2023 each OCR exactly page 1 (the gazette
            # cover), whose tokens belong to no leaf at all because no section
            # starts before page 2 -- indistinguishable, from a bare count, from
            # provenance having been dropped on the way to the JSON.
            "pages_ocred": sorted(p for p, _, _ in fidelity.per_page),
            "tokens": fidelity.tokens,
            "mean_agreement": round(fidelity.mean_agreement, 2),
            "low_conf_share": round(fidelity.low_conf_share, 2),
            "needs_review_tokens": len(fidelity.disagreements),
            # "admitted" means it cleared AGREEMENT_FLOOR / LOW_CONF_SHARE_CEILING.
            # "provisional" means it did NOT and was admitted anyway under
            # admit_below_floor -- the reason is carried verbatim so a reader of
            # the JSON alone learns why, without going back to a run report.
            "floor": "admitted" if fidelity.admitted else "provisional",
        }
        if not fidelity.admitted:
            metadata["ocr"]["provisional"] = True
            metadata["ocr"]["provisional_reason"] = fidelity.reason

    # First-class document class for Library tags.  Same rules as portal
    # ``backend.services.document_provenance`` (OCR_FULL_RATIO = 0.9).
    ocr_meta = metadata.get("ocr")
    if assignment is not None:
        metadata["family"] = assignment.family
        metadata["family_confidence"] = round(assignment.confidence, 2)
    if profile.instrument_kind == "amending":
        # What this instrument changes, taken from the clause headings that
        # already parse ("4. Amendments of the Customs Act, 1969 (IV of 1969)").
        # No new extraction: it is the one fact that makes an amending document
        # navigable, and without it every Finance Act looks like nine untitled
        # blocks of quoted text.
        metadata["amends"] = amended_instruments(chapters)

    if not ocr_meta:
        metadata["source_kind"] = "native-digital"
    else:
        ocr_pages = int(ocr_meta.get("pages") or 0)
        if total_pages > 0 and (ocr_pages / total_pages) >= 0.9:
            metadata["source_kind"] = "scanned-ocr"
        elif ocr_pages >= 1:
            metadata["source_kind"] = "mixed-ocr"
        else:
            metadata["source_kind"] = "native-digital"

    result = {
        "metadata": metadata,
        "chapters": [_node_to_dict(c) for c in chapters],
        "schedules": schedules_out,
    }
    stamp_identity(result["chapters"], "chapter")
    stamp_identity(result["schedules"], "schedule")
    # the enacting preamble (text before section 1: "AN ORDINANCE ... WHEREAS ...")
    from .builder import _build_preamble_html, preamble_refs
    pre = preamble_refs(body_refs, ordered_sections, containers)
    if pre:
        pre_html, pre_plain = _build_preamble_html(pre, footnote_map, lambda p: offset)
        result["preamble"] = {
            "html": pre_html.lstrip("\n"),
            "plain_text": pre_plain,
        }

    # completeness safety net: adopt any uncited footnote into the leaf covering
    # its page, so no footnote text is dropped anywhere in the document.
    from .builder import adopt_orphan_footnotes, all_leaves
    leaves = [lf for root in ("chapters", "schedules")
              for node in result[root] for lf in all_leaves(node)]
    n = adopt_orphan_footnotes(leaves, page_footnotes, printed_by_page, offset,
                               note_body_pages=note_body_pages)
    progress(f"adopted {n} orphaned footnotes")

    # Close by-page holes on Customs-style footnote collector pages (after adopt).
    n_cov = cover_footnote_collector_pages(leaves, scan_pages, has_body, has_notes)
    if n_cov:
        progress(f"extended {n_cov} leaf end_page(s) through footnote collector pages")

    # RC-5 / RC-7: document-wide plain/html text repairs (marker de-fusion is done
    # inline in _render_words; bare-marker merging and line-break de-hyphenation
    # need the whole document, so run them once here over every leaf + preamble).
    from .builder import normalize_document_text
    normalize_document_text(result)

    # THE CONSERVATION BACKSTOP: never write a document that lost the statute.
    #
    # The parentless-section refusal above cannot catch this.  With ZERO sections
    # discovered, ordered_sections is empty, so orphans is empty, so that
    # RuntimeError is unreachable -- run() falls through, returns a dict, and
    # scripts/acts_pdf_to_json.py (the only writer) json.dumps it with exit 0.
    # That is how 935-1,297 byte "successful" JSONs were written for documents
    # whose text had been read perfectly well: on the Finance Act 2012
    # Explanation, ocr.ocr_page returns 252 clean words for page 2 alone --
    # "(a) Residential immovable property, (other than flats), situated in urban
    # area, measuring at least ..." -- and the emitted file carried 0 characters.
    # The OCR was working; the pipeline threw its output away and reported
    # success.  Silent loss is the one outcome legally binding text may never
    # have, so this fails loudly instead.
    #
    # The bar is deliberately at the floor.  Partial loss is the conservation
    # audit's job (body >= 99.99%, scripts/audit_completeness.py); this guard
    # only catches the class where essentially NOTHING made it through, so it
    # cannot fire on a document that merely converts imperfectly.
    # Count tag-stripped html as well as plain_text, exactly as
    # tests.invariants.inv_text_density_plausible does.  plain_text alone is
    # only ~49% of a leaf's content in this corpus (measured: Customs 2025
    # 425,033 of 860,337; STA 2025 311,023 of 638,917), because a tariff
    # schedule's words live in table cells that plain_text does not carry -- so
    # a table-only document could trip the guard while having lost nothing.
    _tags = re.compile(r"<[^>]+>")
    extracted = sum(len(r.line.text()) for r in body_refs) \
        + sum(len(r.line.text()) for r in sched_refs)
    carried = sum(len(lf.get("plain_text") or "")
                  + len(_tags.sub(" ", lf.get("html") or "")) for lf in leaves) \
        + len((result.get("preamble") or {}).get("plain_text") or "")
    if extracted >= 500 and carried < 0.10 * extracted:
        raise RuntimeError(
            f"refusing to write {pdf_path!r}: {extracted} characters were read "
            f"from the PDF but only {carried} reached the document "
            f"({sections_count} section(s), {len(schedules_out)} schedule(s)). "
            f"The text was extracted and then dropped -- writing this JSON would "
            f"silently omit the statute.")

    pdf.close()
    return result


def sanitize_printed_pages(printed_by_page: dict, lo: int, hi: int,
                           window: int = 5) -> dict:
    """Repair misprinted / missing footer page numbers by local consensus.

    Printed page numbers advance by exactly 1 per PDF page within a run, so
    every nearby page q "votes" for page p's number as ``printed[q] + (p-q)``.
    A correct footer agrees with its neighbours (high support); a misprint
    (pdf 188 printing "189", pdf 533 printing "517", the consecutive pair
    537/538 printing "521"/"522") supports only itself and is outvoted, and a
    page with no footer at all (a title page) is filled in the same way.  On a
    tie the printed value is kept, so a genuine numbering discontinuity is
    never "repaired" away.
    """
    # A folio can never exceed the document's own page count, so anything above
    # ``hi`` is not a page number and must be dropped BEFORE it can vote.  The
    # 15.09.2021 Sales Tax edition prints no footer at all on almost every page,
    # and the two values its 292 pages did yield were both garbage -- 399 on pdf
    # 63 and the YEAR 2010 on pdf 68 (picked out of "... Finance Act, 2010").
    # Each lone seed then had no competition in the vote and propagated itself
    # across its whole +/-5 window, minting refs like "2010.428" ... "2015.463"
    # on 101 footnotes.  With both dropped those pages simply have no folio, and
    # every ref falls back to the calibrated offset.
    printed_by_page = {p: n for p, n in printed_by_page.items()
                       if n is not None and 0 < n <= hi}
    out = {}
    for p in range(lo, hi + 1):
        votes: dict[int, int] = {}
        for q in range(p - window, p + window + 1):
            n = printed_by_page.get(q)
            if n is not None:
                cand = n + (p - q)
                # A vote for a page that CANNOT EXIST is not evidence.  Extrapolating
                # across a NUMBERING DISCONTINUITY produces exactly that: Finance
                # Act, 2022 restarts its folios at the Schedules, so pdf 256 prints
                # folio 1 and votes for pdf 251 as `1 + (251-256)` = **-4** -- which
                # was stored and then minted into a footnote ref as printed page -4.
                #
                # Only NON-POSITIVE candidates are dropped, not "greater than hi".
                # Dropping the upper end too was tried and reverted: it changes the
                # folio map of documents that are not broken at all, and the
                # 15.09.2021 Sales Tax edition (which prints almost no footers) went
                # from 53/53 to 52/53 with a note bound across 90 pages.  A vote for
                # a page number larger than the document is odd but it is still a
                # consistent series, and ``sanitize`` owns that judgement -- this
                # only removes the arithmetic impossibility.
                if cand > 0:
                    votes[cand] = votes.get(cand, 0) + 1
        if not votes:
            continue
        cur = printed_by_page.get(p)
        best, best_n = max(votes.items(), key=lambda kv: kv[1])
        out[p] = cur if (cur is not None and votes.get(cur, 0) >= best_n) else best
    return out


_BRACKETS_ONLY_RE = BRACKETS_ONLY_RE
_all_markers_anonymous = all_markers_anonymous


def claim_placeholder_lines(missing, body_refs, page_footnotes, offset):
    """Locate each omitted (body-less) TOC entry's empty bracket line(s).

    The bracket's superscript marker equals the marker of the footnote naming
    the section ("Section “236T” omitted by ..." has marker 5 -> the "5[" in
    "4[ 5[ ] ]"), and footnote markers are unique per page -- so the mapping
    is exact, never positional guesswork.  A claimed line is removed from the
    running body (it must not stay inside the previous section) and rendered
    as the placeholder's own body with live citations.

    A section that was inserted and later omitted renders as a NESTED bracket
    pair which may span two physical lines: an outer bracket for the insertion
    note directly above the inner bracket for the omission note (printed page
    477 renders 236V as "1[ ]" over "2[ ]", footnote 1 being "Inserted by the
    Finance Act, 2016.").  The insertion note names no section, so the named
    pass cannot see it; a second pass walks upward from each claimed line and
    claims every adjacent bracket-only line whose footnotes are all anonymous
    history notes -- otherwise those lines (and their footnotes) would stay
    inside the PREVIOUS section's body.

    Returns ``({id(entry): [LineRef]}, {claimed LineRef ids})``.
    """
    by_pg_marker: dict = {}
    for ref in body_refs:
        t = ref.line.text().strip()
        if t and "[" in t and _BRACKETS_ONLY_RE.match(t):
            for w in getattr(ref.line, "words", []):
                tok = w.text.strip()
                if tok.isdigit():
                    by_pg_marker.setdefault((ref.page, tok), ref)
    claims: dict = {}
    claimed: set = set()
    for entry in missing:
        exp = entry.printed_page + offset
        sec_re = re.compile(r"^\s*Section\b[^0-9A-Za-z]{0,10}"
                            + re.escape(entry.code) + r"\b")
        got = []
        for pg in (exp, exp + 1, exp - 1):
            for fn in page_footnotes.get(pg, []):
                if fn.marker.isdigit() and sec_re.match(fn.text or ""):
                    ref = by_pg_marker.get((pg, fn.marker))
                    if ref is not None and id(ref) not in claimed:
                        claimed.add(id(ref))
                        got.append(ref)
            if got:
                break
        if got:
            got.sort(key=lambda r: (r.page, getattr(r.line, "top", 0.0)))
            claims[id(entry)] = got

    # second pass: adopt the anonymous half of a split bracket pair (see
    # docstring).  Runs after ALL named claims so the upward walk stops at a
    # line already claimed by a neighbouring omitted section.
    idx_of = {id(r): i for i, r in enumerate(body_refs)}
    for got in claims.values():
        while True:
            first = min(got, key=lambda r: idx_of[id(r)])
            i = idx_of[id(first)] - 1
            while i >= 0 and not body_refs[i].line.text().strip():
                i -= 1                       # blank lines are not a boundary
            if i < 0:
                break
            cand = body_refs[i]
            t = cand.line.text().strip()
            if (cand.page != first.page or id(cand) in claimed
                    or "[" not in t or not _BRACKETS_ONLY_RE.match(t)
                    or not _all_markers_anonymous(cand, page_footnotes)):
                break
            claimed.add(id(cand))
            got.insert(0, cand)
        got.sort(key=lambda r: (r.page, getattr(r.line, "top", 0.0)))
    return claims, claimed


def omission_footnotes(code: str, exp_page: int, page_footnotes: dict,
                       offset: int) -> list:
    """Footnote(s) describing an omitted/repealed section, keyed to that section.

    An omitted section survives in the body only as an empty "[ ]" bracket; the
    text explaining the omission (and often reproducing the repealed text with
    its proviso) lives in a footnote on the same page, e.g. "... Section 4A ...
    read as follows: ... Provided that ...".  We locate that footnote by the
    section code plus omission wording and attach it to the placeholder, so the
    history travels with the right section.
    """
    code_re = re.compile(r"\b" + re.escape(code) + r"\b")
    out, seen = [], set()
    for pg in (exp_page, exp_page + 1, exp_page - 1):
        for fn in page_footnotes.get(pg, []):
            t = fn.text or ""
            low = t.lower()
            if code_re.search(t) and ("read as follows" in low or "omitted" in low
                                      or "substituted" in low):
                ref = f"{pg - offset}.{fn.marker}"
                if ref in seen:
                    continue
                seen.add(ref)
                out.append({"ref": ref, "marker": ref, "text": fn.text,
                            "html": fn.html, "page": pg})
        if out:
            break
    return out


_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def _roman_value(raw: str) -> float:
    """Sortable value of a chapter numeral ("XVI-A" -> 16.1)."""
    raw = re.sub(r"\s+", "", (raw or "").upper())
    m = re.match(r"^([IVXLC]+)(?:-?([A-Z]{1,3}))?$", raw)
    if not m:
        if raw.isdigit():
            return float(raw)
        return 9999.0
    total, prev = 0, 0
    for ch in reversed(m.group(1)):
        v = _ROMAN_VALUES[ch]
        total += v if v >= prev else -v
        prev = max(prev, v)
    suffix = m.group(2) or ""
    return total + sum(ord(c) - 64 for c in suffix) / 100.0


def _chapter_sort_key(ch) -> tuple:
    """Ordering key for a chapter: the base numeral, then the suffix LETTERS.

    ``_roman_value`` folds a suffix into two decimal places by SUMMING its letter
    values, which is fine for the nearest-previous-chapter search it was written
    for and wrong as an ordering.  It collides:

        XIV-AA -> 14.02   XIV-B  -> 14.02
        XIV-AB -> 14.03   XIV-BA -> 14.03   XIV-C -> 14.03

    so sorting Sales Tax Rules 2006's chapters by it interleaved two families --
    XIV-B, XIV-AB, XIV-BA, XIV-C, XIV-AC, XIV-BB, XIV-D, XIV-AD -- against a
    contents page that lists AB, AC and AD (printed pages 105-107) BEFORE XIV-B
    (111).  Chapters printed on pages 123-125 came out after ones on 129-158,
    which is what ``structure_counts`` reports.

    A suffix is an alphabetical sequence, not a sum: the source's own order is
    A, AA, AB, AC, AD, B, BA, BB, C, D.  Comparing the letters as a string is
    exactly that, and it leaves a numeral with no suffix first.

    The code itself is deliberately NOT a tiebreak.  ``XIVA`` and ``XIV-A`` are
    two different chapters of this document -- round 1 established that -- and
    they share a key, so a string tiebreak would order them by their punctuation
    ("-" sorts before "A") rather than by the contents page, which lists XIVA
    first.  ``list.sort`` is stable, so equal keys keep the TOC's own order,
    which is the authority here.
    """
    numeral = _chapter_numeral_of(ch) or ""
    raw = re.sub(r"\s+", "", numeral.upper())
    m = re.match(r"^([IVXLC]+|\d+)(?:-?([A-Z]{1,3}))?$", raw)
    if not m:
        return (_roman_value(numeral), "")
    base = m.group(1)
    value = float(base) if base.isdigit() else _roman_value(base)
    return (value, m.group(2) or "")


def body_chapter_entries(body_refs) -> list:
    """``(body_ref index, numeral, caption)`` for each CHAPTER line in the body.

    The line is read through ``_STRUCT_DECOR_RE`` first, exactly as
    ``is_structural_boundary`` -- called three lines below -- already reads it.
    ``CHAPTER_RE`` tolerates the amendment bracket but not the footnote marker in
    front of it, and an inserted chapter wears both: The Sales Tax Act, 1990
    prints its first chapter as ``4 [Chapter-I``, so CHAPTER I was invisible here
    while ``Chapter-II`` through ``Chapter-X`` were not. Sections 1 and 2 then had
    no container, and ``run`` refused the whole document rather than drop them --
    the 30.06.2020 and 31.12.2019 editions produced nothing at all.
    """
    from .builder import _STRUCT_DECOR_RE, _candidate_code, is_structural_boundary
    from .grammar import CHAPTER_RE

    out: list = []
    for i, ref in enumerate(body_refs):
        m = CHAPTER_RE.match(_STRUCT_DECOR_RE.sub("", ref.line.text().strip()))
        if not m:
            continue
        num = re.sub(r"\s+", " ", m.group(1).strip().upper())
        parts: list[str] = []
        for j in range(i + 1, min(i + 4, len(body_refs))):
            nxt = body_refs[j]
            t = nxt.line.text().strip()
            if (nxt.page != ref.page or not t
                    or any(c.islower() for c in t)
                    or sum(c.isalpha() for c in t) < 3
                    or _candidate_code(nxt.line)
                    or is_structural_boundary(t)):
                break
            if parts and parts[-1].endswith("-"):
                parts[-1] += t
            else:
                parts.append(t)
        out.append((i, num, " ".join(parts)))
    return out


def body_chapter_headings(body_refs) -> dict:
    """The CHAPTER captions as PRINTED IN THE BODY, keyed by chapter numeral.

    A chapter's title is printed as one or two ALL-CAPS lines directly under its
    "CHAPTER N" line.  Those lines reach no leaf -- a section segment is cut at
    the structural boundary (`builder._build_one`) -- so the only chapter title
    that ever reached the output was the TOC's, and the two differ.  The body is
    authoritative, and here it is also the *only* copy of four words: the 2008
    edition prints "GENERAL PROVISIONS AFFFECTING ..." (p82), "DISCHARGE OF
    CAERGO ..." (p86) and "... POWER OF SEARCH ..." (p173) where its TOC prints
    the corrected spellings, and those, with the 2025 edition's
    "TRANSSHIPMENT", were that family's entire body-conservation shortfall.

    A caption line is recognised structurally, never by matching the TOC: it
    carries no lowercase letter, sits on the same page as its CHAPTER line, and
    stops at the first line that is a section start or has lowercase text (a
    section heading always does).  At most three lines, so a mis-zoned page can
    never fold a paragraph into a chapter title.
    """
    out: dict = {}
    for _i, num, cap in body_chapter_entries(body_refs):
        if cap:
            out.setdefault(num, cap)
    return out


def _norm_caption(text: str) -> list[str]:
    return re.sub(r"\s+", " ", (text or "").upper()).strip().split()


def _captions_match(a: str, b: str) -> bool:
    aw, bw = _norm_caption(a), _norm_caption(b)
    if not aw or not bw:
        return False
    if aw == bw:
        return True
    n = min(len(aw), len(bw), 6)
    return sum(1 for x, y in zip(aw[:n], bw[:n]) if x == y) >= min(3, n)


def _chapter_numeral_of(ch) -> str | None:
    from .grammar import CHAPTER_RE
    m = CHAPTER_RE.match(ch.code or "")
    return re.sub(r"\s+", " ", m.group(1).strip().upper()) if m else None


def _previous_chapter(chapters, numeral: str):
    val = _roman_value(numeral)
    best, best_ch = -1.0, None
    for ch in chapters:
        n = _chapter_numeral_of(ch)
        if not n:
            continue
        v = _roman_value(n)
        if v < val and v > best:
            best, best_ch = v, ch
    return best_ch


def insert_missing_body_chapters(chapters, ordered_sections, body_refs) -> int:
    """Insert CHAPTER nodes the body prints that the TOC omitted (ledger O03).

    Customs contents skip CHAPTERS IV / IX / XI.  ``parse_toc`` now opens a
    numeral-less node from the ALL-CAPS caption so following rows parent here;
    this function fills that numeral from the body (and inserts a node from
    scratch when the caption never classified).  Sections whose first body
    hit sits after the new CHAPTER line are reparented.
    """
    from .builder import _candidate_code, _dotless_candidate_code

    entries = body_chapter_entries(body_refs)
    if not entries:
        return 0
    body_by_num = {num: (idx, cap) for idx, num, cap in entries}
    taken = {n for ch in chapters if (n := _chapter_numeral_of(ch))}
    n_changed = 0

    def _taken(num: str) -> bool:
        """Whether ``chapters`` already holds this numeral, in EITHER notation.

        A document that prints its first chapter as an Arabic ``1`` while its
        contents page and every other chapter say ``I`` is not missing a chapter.
        The Customs Act 1969 does exactly that on page 23, and matching as strings
        inserted a second, EMPTY "CHAPTER 1 / PRELIMINARY" beside the real
        "CHAPTER I / PRELIMINARY" in 19 editions -- which is also why every one of
        them reported 23 chapters where the contents page says 22.

        **Only the Arabic/roman notation gap is bridged**, and the guard below is
        what keeps it that way: ``XIVA`` and ``XIV-A`` share a ``_roman_value``
        but are two DIFFERENT chapters of Sales Tax Rules 2006 -- the first
        omitted, the second the monitoring chapter -- and collapsing them would
        drop one from the tree. Same-notation numerals still compare as strings.

        ``_roman_value``'s 9999.0 is "cannot read this numeral"; two unreadable
        numerals must not become equal through it.
        """
        if num in taken:
            return True
        value = _roman_value(num)
        if value == 9999.0:
            return False
        return any(t.isdigit() != num.isdigit() and _roman_value(t) == value
                   for t in taken)

    def _fill(ch, num: str) -> None:
        nonlocal n_changed
        _idx, cap = body_by_num[num]
        ch.toc_heading = ch.heading or ""
        ch.code = "CHAPTER " + num
        if cap:
            ch.heading = cap
        ch.heading_source = "body"
        taken.add(num)
        n_changed += 1

    for ch in chapters:
        if ch.code:
            continue
        match = next((num for num, (_i, cap) in body_by_num.items()
                      if not _taken(num) and _captions_match(ch.heading, cap)),
                     None)
        if match:
            _fill(ch, match)

    unused = [num for _i, num, _c in entries if not _taken(num)]
    empties = [ch for ch in chapters if not ch.code]
    for ch, num in zip(empties, unused):
        _fill(ch, num)

    pos_of_anchor = {id(r): i for i, r in enumerate(body_refs)}

    def _codes_in_span(lo: int, hi: int) -> set:
        seen: set = set()
        for j in range(lo + 1, hi):
            cc = (_candidate_code(body_refs[j].line)
                  or _dotless_candidate_code(body_refs[j].line))
            if cc:
                seen.add(cc)
        return seen

    remaining = [(idx, num, cap) for idx, num, cap in entries if not _taken(num)]
    for idx, num, cap in remaining:
        node = Node(kind="chapter", code="CHAPTER " + num, heading=cap or "")
        node.toc_heading = ""
        node.heading_source = "body"
        chapters.append(node)
        taken.add(num)
        n_changed += 1
        next_idx = len(body_refs)
        for j, (nidx, nnum, _c) in enumerate(entries):
            if nidx > idx:
                next_idx = nidx
                break
        span = _codes_in_span(idx, next_idx)
        prev = _previous_chapter(chapters, num)
        for entry in ordered_sections:
            # An entry that carries an ANCHOR knows where it actually is, so place
            # it by position and never by code membership.  ``_codes_in_span``
            # reads every candidate code printed in the span, and a section's code
            # is printed in more places than its own heading: the Sales Tax Act
            # 1990 defines "supply chain" as clause ``[(33A)`` inside section 2,
            # which puts 33A in CHAPTER I's span.  CHAPTER I is processed first,
            # claims it, and CHAPTER VII -- where s.33A is actually printed, 55
            # pages later -- then finds its parent already set and skips it.
            # ``section_codes_ordered`` reports the result as "3 out of order
            # after 33A".
            #
            # Only body-discovered entries have an anchor; TOC entries have none
            # and keep the code-span behaviour they have always had.
            anchor = getattr(entry, "anchor", None)
            if anchor is not None:
                pos = pos_of_anchor.get(id(anchor))
                if pos is not None:
                    if (idx < pos < next_idx
                            and (entry.parent is prev or entry.parent is None)):
                        entry.parent = node
                    continue
            if entry.code in span and (entry.parent is prev or entry.parent is None):
                entry.parent = node

    chapters.sort(key=_chapter_sort_key)
    return n_changed


def apply_body_chapter_headings(chapters, body_refs) -> int:
    """Override each chapter's TOC title with the one the body prints.

    Same decision as for section headings (``builder._build_one``): the printed
    heading is the operative one.  The TOC wording is kept in ``toc_heading``.
    Only chapters whose numeral the body actually prints a caption for are
    touched -- everything else keeps the TOC title as the fallback.
    """
    from .grammar import CHAPTER_RE

    body = body_chapter_headings(body_refs)
    n = 0
    for ch in chapters:
        m = CHAPTER_RE.match(ch.code or "")
        num = re.sub(r"\s+", " ", m.group(1).strip().upper()) if m else None
        ch.toc_heading = ch.heading or ""
        ch.heading_source = "toc"
        got = body.get(num)
        if got and got != ch.heading:
            ch.heading = got
            ch.heading_source = "body"
            n += 1
        elif got:
            ch.heading_source = "body"
    return n


_QUOTE_OPENS = '"“”‘’«'


def _before_first_chapter(entry, chapters, body_refs) -> bool:
    """Whether this section's anchor line precedes the first CHAPTER heading.

    Distinguishes the two ways a section can end up parentless.  Printed BEFORE
    any chapter, it belongs to no chapter because none had opened yet -- the host
    clauses of a gazette that reproduces another Act.  Printed AFTER one, its
    container exists and was mis-parsed, which is the A01 defect and must stay
    loud rather than be papered over with a synthetic root.
    """
    from .builder import _STRUCT_DECOR_RE, is_structural_boundary
    first_chapter_idx = None
    for i, ref in enumerate(body_refs):
        t = ref.line.text().strip()
        if is_structural_boundary(t) and _STRUCT_DECOR_RE.sub("", t).upper().startswith("CHAPTER"):
            first_chapter_idx = i
            break
    if first_chapter_idx is None:
        return False
    anchor = getattr(entry, "anchor", None)
    for i, ref in enumerate(body_refs):
        if ref is anchor:
            return i < first_chapter_idx
    return False


def _precedes_first_chapter_in_toc(entry, ordered_sections) -> bool:
    """Whether a TOC-derived entry is listed before the first entry that has a chapter.

    ``_before_first_chapter`` needs a body ANCHOR, which only body-driven discovery
    sets; a section that came from a parsed TOC has none, so that test always said no.
    On the Acts that was harmless -- their opening sections sit inside CHAPTER I. It is
    not harmless here: a rule set conventionally prints "1. Short title and
    commencement" and "2. Definitions" BEFORE its first chapter, so on the Sales Tax
    Special Procedures Rules the conversion refused outright over rule 1.

    The TOC lists entries in document order, so position in that list answers the
    question directly -- and unlike a printed page it cannot be thrown off by the
    folio problems these documents have.
    """
    parented = [
        i for i, e in enumerate(ordered_sections) if getattr(e, "parent", None) is not None
    ]
    if not parented:
        return False
    try:
        return ordered_sections.index(entry) < parented[0]
    except ValueError:
        return False


def _opens_schedules(text: str) -> bool:
    """True for a Schedule title that opens THIS act's own schedules.

    A Finance Act is an amending instrument: most "SCHEDULE" titles it prints
    are not its own, they are schedules it QUOTES verbatim into some other Act,
    and they are printed inside quotation marks exactly as any substituted text
    is.  Treating one as the start of this document's schedules truncates the
    body at that point, and these appear on the FIRST body page.

    Measured: Finance Act 2022's clause 1A substitutes a schedule into the
    Petroleum Products (Petroleum Levy) Ordinance 1961, so PDF page 2 -- the
    opening page of the statute -- prints ``“The Fifth Schedule``.  That set
    ``schedule_start = 2``, every page from there went into ``sched_refs``,
    ``body_refs`` was left empty, and a 952-page Act converted to 0 sections
    with all 10.5 MB of its text filed under a synthetic ``SCHEDULE`` node.

    The opening quote is the discriminator the source itself provides, and it is
    free of risk for the consolidated families: across all 56 Customs / Sales
    Tax / Federal Excise editions, **0 of 286** schedule titles begin with a
    quote mark, because an act printing its own schedule has no reason to quote
    it.

    ...but the quote is not always ON the title's line, so the ORDINAL has to
    agree too.  Finance Act 2014 quotes the Sales Tax Act's Eighth Schedule into
    its clause 4, and prints ``EIGHTH SCHEDULE`` on page 28 with the ``“`` that
    opens the insertion alone on page 27.  That started the schedule region 28
    pages early, so pages 28-55 -- the Act's own Income Tax Ordinance amendment
    clauses, ``231B. Advance tax on private motor vehicles``, the bonus-shares
    provisions -- went to ``sched_refs``, where ``build_schedules`` rejected the
    out-of-order title and then DROPPED every line before the first title it did
    accept: 1,340 body words, conservation 95.2%.

    A document's schedules open at its LOWEST ordinal, so require the same
    plausibility ``build_schedules`` already applies to the first title it takes
    (``_sched_ordinal`` is 0-based, tolerance 2, i.e. First..Third).  Measured
    over the corpus: 61 of the 62 editions carrying schedules open at
    FIRST/SCHEDULE and the 62nd at THE THIRD SCHEDULE, so nothing legitimate sits
    outside that window -- while a quoted insertion of a Fourth-or-later schedule
    no longer truncates the body.  Refusing to open the region is the safe
    direction: the text stays in the body, where a section claims it, and
    ``inv_structure_counts`` reports the missing ordinals.
    """
    if _kind(text) != "schedule" or text.lstrip()[:1] in _QUOTE_OPENS:
        return False
    o = _sched_ordinal(text)
    return o is None or o <= 2


def _page_starts_schedules(pm) -> bool:
    """True once a page's body carries a Schedule *title* heading.

    H6: the WHOLE page, not its first six lines.  Sales Tax stacks "The / FIRST
    SCHEDULE / ... / SECOND SCHEDULE / ... / THIRD SCHEDULE" mid-page directly
    under the end of section 77 -- on pdf 136 of the 15.01.2022 edition the first
    title is at ``body_lines[14]`` and on pdf 140 at [10], so only pdf 145's
    SIXTH SCHEDULE at [1] fell inside the slice: the First-to-Fifth Schedules
    stayed in ``body_refs`` and were welded into section 77's body.  A prose
    mention of "the Sixth Schedule" cannot false-positive here because ``_kind``
    is anchored to a WHOLE line (``schedules._SCH_RE`` ends ``SCHEDULE\\s*[\\]"]?$``).

    Quoted titles are skipped -- see ``_opens_schedules``.
    """
    return any(_opens_schedules(ln.text().strip()) for ln in pm.body_lines)


#: Node type -> the abbreviation used in ``node_key``.
_KEY_ABBREV = {"chapter": "ch", "part": "pt", "division": "dv",
               "schedule": "sch", "section": "s"}

#: Where a child list sits in the tree, and what a node in it IS. This is the
#: convention the output has always followed positionally; stamping it makes a
#: consumer stop having to infer a node's kind from which keys happen to exist.
_CHILD_KINDS = (("parts", "part"), ("divisions", "division"), ("sections", "section"))

#: An amending clause's heading. Measured over every clause heading in the 30
#: amending documents on disk, the grammar is
#:
#:     <verb> (of|in|to) [the] <target>
#:
#: with five verbs, and a target that is either the amended law
#: ("the Customs Act, 1969 (IV of 1969)"), a bare statute citation ("Ordinance
#: XLIX of 2001"), or a provision inside one ("section 7, Act VII of 2010").
_AMENDS_RE = re.compile(
    r"^(?P<verb>Amendments?|Insertion|Substitution|Omission|Addition|Enactment)"
    r"\s+(?:of|in|to)\s+(?:new\s+)?(?:the\s+)?(?P<target>.+)$", re.IGNORECASE)

#: A provision named ahead of the law it sits in: "section 7, Act VII of 2010".
_AMENDS_TARGET_RE = re.compile(
    r"^(?P<provision>(?:new\s+)?(?:sections?|sub-sections?|clauses?|rules?|"
    r"schedules?|tables?)\b[^,]*),\s*(?P<instrument>.+)$", re.IGNORECASE)

#: A trailing statute citation: "(IV of 1969)", "(Ordinance XLIX of 2001)".
_AMENDS_CITE_RE = re.compile(r"\s*\(([^()]*\bof\b[^()]*)\)\s*$", re.IGNORECASE)

#: Where the clause's BODY has been glued onto its heading. Real, and common:
#: "Amendments of the Federal Excise Act, 2005.ln the Federal Excise Act, 2005,
#: the followin...". Cut there or the instrument name swallows a paragraph.
_AMENDS_BODY_RE = re.compile(
    r"\.\s*(?:[IiLl]n\s+the\b|There\s+is\s+hereby\b|the\s+following\b).*$")


def amended_instruments(chapters) -> list[dict]:
    """Which laws an amending instrument changes, and in which of its clauses.

    Read off the clause headings, which already parse: an amending act numbers
    its clauses and titles each one for the law it changes. Nothing new is
    extracted -- this only stops the one fact that makes such a document
    navigable from being spread across nine untitled blocks of quoted text. On
    ``The Tax Laws (Amendment) Act, 2024`` it names all three targets; on a
    Finance Act it names every act that year's budget touched.

    Deliberately NOT a parse of the directives themselves. Splitting a clause
    into per-amendment sub-nodes is a parser feature, and the clause is not
    wrong as it stands -- Finance Act 2023's clause 4 is 12,470 characters of
    quoted Customs Act text because clause 4 IS that long. This names the target
    so that work has somewhere to attach.
    """
    found: list[dict] = []

    def record(leaf) -> None:
        m = _AMENDS_RE.match((leaf.get("heading") or "").strip())
        if not m:
            return
        target = _AMENDS_BODY_RE.sub("", m.group("target")).strip(" .,")
        provision = ""
        inner = _AMENDS_TARGET_RE.match(target)
        if inner:
            provision = re.sub(r"^new\s+", "", inner.group("provision"), flags=re.I)
            target = inner.group("instrument").strip(" .,")
        citation = ""
        cite = _AMENDS_CITE_RE.search(target)
        if cite:
            citation = cite.group(1).strip()
            target = target[:cite.start()].strip(" .,")
        found.append({"section": leaf.get("code"),
                      "verb": m.group("verb").lower().rstrip("s"),
                      "instrument": target,
                      "citation": citation,
                      "provision": provision})

    def walk(nodes) -> None:
        for node in nodes:
            for leaf in node.sections:
                record(leaf)
            walk(node.parts)
            walk(node.divisions)

    walk(chapters)
    return found


def stamp_identity(nodes, kind: str, prefix: str = "") -> None:
    """Give every node its ``type`` and its ``node_key``, in place.

    Two additive keys, on containers and leaves alike:

    ``type``      what the node IS. ``toc.Node.kind`` has always computed this
                  and ``_node_to_dict`` has always thrown it away, so the output
                  used one dict shape for a chapter, a schedule part and a
                  section leaf and left a consumer to tell them apart by which
                  keys happened to be present.

    ``node_key``  the ancestor chain BY CODE -- ``ch:vii/pt:i/s:114`` -- not by
                  array index. It sits beside the ``source_key`` that
                  ``json_parser._stable_id`` mints (``/chapters/0/sections/3``),
                  changes no id, and costs nothing now; what it buys is that a
                  later leaf-level diff has a handle that survives a node being
                  inserted above it. Sibling codes that repeat get an ordinal, so
                  the key is unique within its parent.
    """
    seen: dict[str, int] = {}
    for node in nodes:
        code = _slug(node.get("code") or "", kind)
        seen[code] = seen.get(code, 0) + 1
        if seen[code] > 1:
            code = f"{code}~{seen[code]}"
        node["type"] = kind
        node["node_key"] = f"{prefix}{_KEY_ABBREV.get(kind, kind)}:{code}"
        for key, child_kind in _CHILD_KINDS:
            if node.get(key):
                stamp_identity(node[key], child_kind, node["node_key"] + "/")


def _slug(code: str, kind: str) -> str:
    """``"CHAPTER XIV-A"`` -> ``"xiv-a"``; ``"114A"`` -> ``"114a"``.

    An empty code is the synthetic root a flat act gets (the 20 Finance Acts and
    the single gazette Acts have no containers at all, so ``run`` makes one to
    parent their clauses). It is named as synthetic rather than given a position,
    because a position is exactly the kind of identity ``node_key`` exists to
    avoid depending on.
    """
    text = re.sub(rf"^\s*{kind}\b[\s\-]*", "", code.strip(), flags=re.IGNORECASE)
    return re.sub(r"\s+", "-", text.strip()).lower() or "~root"


def _node_to_dict(node: Node) -> dict:
    d = {"code": node.code}
    if node.heading:
        d["heading"] = node.heading
    # set by apply_body_chapter_headings for chapters (absent elsewhere)
    for k in ("toc_heading", "heading_source"):
        v = getattr(node, k, None)
        if v:
            d[k] = v
    d["parts"] = [_node_to_dict(p) for p in node.parts]
    d["divisions"] = [_node_to_dict(dv) for dv in node.divisions]
    if node.sections:
        d["sections"] = node.sections
    elif not node.parts and not node.divisions:
        d["sections"] = []
    return d


if __name__ == "__main__":
    _demo()
