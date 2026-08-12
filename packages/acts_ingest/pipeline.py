"""End-to-end pipeline: PDF path in, target-format JSON dict out."""

from __future__ import annotations

import re
from dataclasses import asdict

import pdfplumber

from .builder import LineRef, build_sections
from .calibrate import calibrate
from .discover import _omission_codes
from .footnotes import (BRACKETS_ONLY_RE, all_markers_anonymous,
                        parse_footnotes, ref_sort_key)
from .pagemodel import build_page_model
from .schedules import build_schedules, _kind, _sched_ordinal
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
        # #region agent log
        try:
            import json as _json, time as _time
            open("/Users/muhammad.husnain/Downloads/code/crx/.cursor/debug-661395.log", "a").write(
                _json.dumps({"sessionId": "661395", "runId": "customs-gap", "hypothesisId": "G",
                             "location": "pipeline.py:cover_footnote_collector_pages",
                             "message": "extend_end_page_through_collectors",
                             "data": {"code": last.get("code"), "from": prev, "to": note_end,
                                      "collectors": collectors[:12], "body_run": [bodies[0], bodies[-1]]},
                             "timestamp": int(_time.time() * 1000)}) + "\n")
        except Exception:
            pass
        # #endregion
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


def run(pdf_path: str, progress=lambda *a: None, _max_body_page: int | None = None,
        admit_below_floor: bool = False) -> dict:
    """Convert one PDF to the document dict.

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
    pdf = pdfplumber.open(pdf_path)
    total_pages = len(pdf.pages)

    cal = calibrate(pdf)
    toc_pages = cal.toc_pages
    progress(f"calibrated: box {cal.page_w:.0f}x{cal.page_h:.0f}, "
             f"zone={cal.zone_mode}, body={cal.body_size}pt, "
             f"footnote={cal.footnote_size}pt, TOC pages={toc_pages}, "
             f"offset={cal.page_offset}")

    chapters, schedules, ordered_sections = parse_toc(_toc_lines(pdf, toc_pages))
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
            body_refs, printed_by_page, page_footnotes)
        progress(f"body-driven structure: {len(chapters)} chapters, "
                 f"{len(ordered_sections)} sections")

    n_bch = apply_body_chapter_headings(chapters, body_refs)
    if n_bch:
        progress(f"{n_bch} chapter heading(s) taken from the body caption")

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
    if orphans and all(getattr(e, "anchor", None) is not None
                       and _before_first_chapter(e, chapters, body_refs)
                       for e in orphans):
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
    # the enacting preamble (text before section 1: "AN ORDINANCE ... WHEREAS ...")
    from .builder import preamble_refs, _build_preamble_html
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
    from .grammar import CHAPTER_RE
    from .builder import _candidate_code, is_structural_boundary

    out: dict = {}
    for i, ref in enumerate(body_refs):
        m = CHAPTER_RE.match(ref.line.text().strip())
        if not m:
            continue
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
            # a caption wrapped mid-compound keeps the compound whole:
            # "... AT CUSTOMS-" + "STATIONS" -> "... AT CUSTOMS-STATIONS"
            if parts and parts[-1].endswith("-"):
                parts[-1] += t
            else:
                parts.append(t)
        if parts:
            out.setdefault(re.sub(r"\s+", " ", m.group(1).strip().upper()),
                           " ".join(parts))
    return out


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
