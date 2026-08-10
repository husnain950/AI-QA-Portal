"""End-to-end pipeline: PDF path in, target-format JSON dict out."""

from __future__ import annotations

import re
from dataclasses import asdict

import pdfplumber

from .builder import LineRef, build_sections
from .discover import _omission_codes
from .footnotes import (BRACKETS_ONLY_RE, all_markers_anonymous,
                        parse_footnotes, ref_sort_key)
from .pagemodel import build_page_model
from .schedules import build_schedules, _kind
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


def _detect_toc_page_count(pdf, max_scan: int = 30) -> int:
    """Return the number of leading TOC pages.

    The body's first page carries the section-1 heading followed by its text
    (``...commencement.—(1) This Ordinance may be called...``).  We must not
    match the TOC row of the same name, which instead ends in a page number,
    so we key off the body-only signature.
    """
    body_sig = re.compile(r"commencement\s*\.\s*[—–-]|This Ordinance may be")
    for i in range(max_scan):
        txt = pdf.pages[i].extract_text() or ""
        if body_sig.search(txt):
            return i  # number of TOC pages preceding this body page
    return 19  # sensible default for this document family


def _calibrate_offset(pdf, toc_pages: int, first_printed: int = 1) -> int:
    """PDF page index (1-based) of body start minus its printed page number."""
    body_start_pdf_page = toc_pages + 1  # 1-based
    return body_start_pdf_page - first_printed


def run(pdf_path: str, progress=lambda *a: None, _max_body_page: int | None = None) -> dict:
    pdf = pdfplumber.open(pdf_path)
    total_pages = len(pdf.pages)

    toc_pages = _detect_toc_page_count(pdf)
    progress(f"TOC pages: {toc_pages}")

    chapters, schedules, ordered_sections = parse_toc(_toc_lines(pdf, toc_pages))
    progress(f"TOC parsed: {len(chapters)} chapters, {len(schedules)} schedules, "
             f"{len(ordered_sections)} sections")

    offset = _calibrate_offset(pdf, toc_pages)
    progress(f"printed->pdf page offset: {offset}")

    # Body page range: from first section to just before the first schedule.
    first_body_page = (min(s.printed_page for s in ordered_sections) + offset
                       if ordered_sections else toc_pages + 1)
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

    for pidx in range(first_body_page, scan_end + 1):
        pm = build_page_model(pdf.pages[pidx - 1], pidx)
        if pm.printed_page:
            printed_by_page[pidx] = pm.printed_page
        if schedule_start is None and _page_starts_schedules(pm):
            schedule_start = pidx
        bucket = sched_refs if schedule_start is not None else body_refs
        for ln in pm.body_blocks:
            bucket.append(LineRef(page=pidx, line=ln))
        fns = parse_footnotes(pm.footnote_lines, pm.footnote_tables)
        for fn in fns:
            fn.pdf_page = pidx
            fn.end_pdf_page = pidx
        page_footnotes[pidx] = fns
        footnote_map[pidx] = {fn.marker: fn.text for fn in fns}
        if pidx % 50 == 0:
            progress(f"  scanned page {pidx}/{scan_end}")

    # Repair the footer page numbers before ANY ref is minted.  The PDF
    # misprints several footers (e.g. pdf 188 prints "189" between "168" and
    # "170"; pdf 533 prints "517" between "513" and "515"), and every footnote
    # ref derives from the printed number -- an unrepaired misprint mints a
    # wrong ref AND breaks the (ref, text) dedup between the by-citation and
    # orphan-adoption paths, duplicating footnotes under two different refs.
    printed_by_page = sanitize_printed_pages(printed_by_page,
                                             first_body_page, scan_end)

    # splice footnotes that continue across a page break before assembling,
    # then rebuild the citation-title map so titles carry the full text
    from .footnotes import merge_footnote_continuations
    merge_footnote_continuations(page_footnotes)
    footnote_map = {pg: {fn.marker: fn.text for fn in fns}
                    for pg, fns in page_footnotes.items()}

    # TOC-less edition (31.07.2025 prints no table of contents): reconstruct
    # the chapter tree and ordered section list from the body itself.
    if not ordered_sections:
        from .discover import discover_structure
        chapters, ordered_sections = discover_structure(
            body_refs, printed_by_page, page_footnotes)
        progress(f"body-driven structure: {len(chapters)} chapters, "
                 f"{len(ordered_sections)} sections")

    built = build_sections(body_refs, ordered_sections, footnote_map,
                           page_footnotes, page_offset=offset)

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
                               page_footnotes, page_offset=offset)
        progress(f"claimed {len(claimed_ids)} bracket lines for "
                 f"{len(placeholder_lines)} omitted sections")
    progress(f"assembled {len(built)} / {len(ordered_sections)} sections")

    schedules_out = build_schedules(sched_refs, page_footnotes, footnote_map,
                                    printed_by_page, toc_schedules=schedules)
    progress(f"assembled {len(schedules_out)} schedules")

    # Every section MUST have a container: a parent-less entry means the TOC
    # parse failed to create its chapter (e.g. a decorated/merged chapter row)
    # and the section would silently vanish from the output tree.  This is
    # legal text -- refuse to emit a document that omits it.
    orphans = [e.code for e in ordered_sections if e.parent is None]
    if orphans:
        raise RuntimeError(
            f"TOC parse left {len(orphans)} section(s) without a chapter "
            f"container ({', '.join(orphans[:5])}...): refusing to drop them. "
            f"Fix the TOC chapter detection for this edition.")

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
                                    "text": fn.text, "html": fn.html})
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
                "page_number": page_number,
                "html": html_doc,
                "plain_text": plain,
                "start_page": sp, "end_page": ep, "footnotes": fns,
            }
        else:
            bs_dict = {
                "code": bs.code, "heading": bs.heading,
                "page_number": bs.page_number, "html": bs.html,
                "plain_text": bs.plain_text, "start_page": bs.start_page,
                "end_page": bs.end_page, "footnotes": bs.footnotes,
            }
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
    }

    result = {
        "metadata": metadata,
        "chapters": [_node_to_dict(c) for c in chapters],
        "schedules": schedules_out,
    }
    # the enacting preamble (text before section 1: "AN ORDINANCE ... WHEREAS ...")
    from .builder import preamble_refs, _build_preamble_html
    pre = preamble_refs(body_refs, ordered_sections)
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
    n = adopt_orphan_footnotes(leaves, page_footnotes, printed_by_page, offset)
    progress(f"adopted {n} orphaned footnotes")

    # RC-5 / RC-7: document-wide plain/html text repairs (marker de-fusion is done
    # inline in _render_words; bare-marker merging and line-break de-hyphenation
    # need the whole document, so run them once here over every leaf + preamble).
    from .builder import normalize_document_text
    normalize_document_text(result)
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
    out = {}
    for p in range(lo, hi + 1):
        votes: dict[int, int] = {}
        for q in range(p - window, p + window + 1):
            n = printed_by_page.get(q)
            if n is not None:
                cand = n + (p - q)
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
                            "html": fn.html})
        if out:
            break
    return out


def _page_starts_schedules(pm) -> bool:
    """True once a page's body carries a Schedule *title* heading."""
    for ln in pm.body_lines[:6]:
        if _kind(ln.text().strip()) == "schedule":
            return True
    return False


def _node_to_dict(node: Node) -> dict:
    d = {"code": node.code}
    if node.heading:
        d["heading"] = node.heading
    d["parts"] = [_node_to_dict(p) for p in node.parts]
    d["divisions"] = [_node_to_dict(dv) for dv in node.divisions]
    if node.sections:
        d["sections"] = node.sections
    elif not node.parts and not node.divisions:
        d["sections"] = []
    return d
