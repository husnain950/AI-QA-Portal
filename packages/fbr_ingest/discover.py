"""Body-driven structure discovery for TOC-less editions.

The 31.07.2025 edition prints no table of contents: ``parse_toc`` sees only
the cover page and yields nothing, and the pipeline -- whose chapter tree and
ordered section list are otherwise 100% TOC-driven -- would emit a document
with zero chapters and zero sections.  This module reconstructs both directly
from the body:

  * CHAPTER / PART / Division headings are whole-line body headings,
    recognised by :func:`builder.is_structural_boundary` (tolerant of leading
    amendment decoration such as ``1 [PART IX``);
  * section starts are code-led lines (``2. Definitions.— ...``), accepted
    only behind three independent gates -- a BOLD title font, monotonically
    increasing section codes, and a heading terminator -- because clause
    definitions (``5[17A. "Developmental REIT Scheme" ...``), wrapped
    cross-references (a bare ``25.``) and inserted clauses (``3[(1A) ...``)
    all mimic the shape;
  * sections that survive only as an empty amendment bracket plus an
    omission/repeal footnote are synthesised as anchor-less placeholder
    entries; the pipeline's existing placeholder machinery
    (``claim_placeholder_lines`` / ``omission_footnotes``) renders them.

Discovery runs in TWO passes.  Real sections are found first, on their own
strict monotonic order.  Placeholders are then admitted only where their code
fits BETWEEN the real sections that physically surround their bracket line.
The passes must be separate: a renumbering footnote can sit at the section's
NEW location ("Section 64A is re-numbered ..." prints beside 60C, because
64A BECAME 60C) -- in a single pass that placeholder advances the monotonic
cursor to 64A and silently swallows every real section from 60D to 64.

Every discovered real section carries an exact body ANCHOR (the LineRef of
its heading line), which ``build_sections`` resolves by identity instead of
printed-page proximity.
"""

from __future__ import annotations

import re

from .builder import (_DOTFORM_RE, _STRUCT_DECOR_RE, _bold_title,
                      _code_token_index, _dotless_candidate_code,
                      _find_heading_split, is_structural_boundary)
from .footnotes import BRACKETS_ONLY_RE
from .toc import Node, SectionEntry, _chapter_numeral, _clean_heading, _join_heading


def code_sort_key(code: str):
    """Numeric-then-suffix key for a section code: ``"175AA" -> (175, "AA")``.

    Section codes advance monotonically through the body (``4 < 4A < 4AB <
    4B < 5``), which is the strongest cheap rejector of look-alike lines: a
    definitions clause ``17A.`` inside section 2, or a cross-reference ``25.``
    wrapped inside section 20, lands far out of sequence.
    """
    m = re.match(r"(\d{1,3})([A-Z]{0,3})$", code or "")
    if not m:
        return (0, "")
    return (int(m.group(1)), m.group(2))


# bracket-parenthesised inserted section ("4 [(4AB) Subject ...")
_BRACKETPAREN_START_RE = re.compile(
    r"^\s*(?P<marker>[\d*]{1,3})\s*\[\s*\((?P<code>\d{1,3}[A-Z]{1,3})\)")
# An omission/repeal/renumbering footnote naming its section.  The code's
# letter suffix may be quoted, parenthesised or spaced apart from the digits:
# 'Section 60C omitted', 'Section “64A” omitted', 'Section 148(A) omitted'.
# Case is explicit (no IGNORECASE): a case-blind [A-Z]{0,3} suffix group
# would greedily swallow the first letters of the verb ('Section 65A
# omitted ...' -> code '65omi') whenever no period ends the sentence.
_OMIT_FN_RE = re.compile(
    r"^[Ss]ection\s*[\(\"“”']{0,2}\s*(\d{1,3})\s*[\)\"“”']{0,2}\s*"
    r"[\(\"“”']{0,2}([A-Z]{0,3})[\)\"“”']{0,2}"
    r"[\s,]*(.*?\b(?:[Oo]mitted|[Rr]epealed|[Rr]e-?numbered)\b.*?)(?:\.|$)",
    re.DOTALL)
# trailing "... The omitted section(s) read as follows:" boilerplate that
# belongs to the reproduced text, not the heading
_OMIT_TRAILER_RE = re.compile(
    r"[\s,;]*(?:the\s+)?omitted\s+sections?\b.*$|[\s,;]*read[s]?\s+as\s+follows.*$",
    re.IGNORECASE | re.DOTALL)
# verb-first omission notes ("Omitted by the Finance Act, 2014.  Section 4A
# was added by ..." / "Omitted by the Finance Act, 2002. The omitted section
# 157 read as follows: ...") -- the heading is the first clause, the section
# code is named LATER, in one of three places
_OMIT_LEAD_RE = re.compile(r"^((?:[Oo]mitted|[Rr]epealed)\b[^.\n]{0,90})")
_OMIT_NAMED_LATER_RE = re.compile(
    r"omitted\s+sections?\s+(\d{1,3}[A-Z]{0,3})\b"            # 'omitted section 157 read'
    r"|[Ss]ection\s+(\d{1,3}[A-Z]{0,3})\s+was\s+(?:added|inserted)"
    r"|follows?\s*:?\s*[\n\s\"“”']*(\d{1,3}[A-Z]{0,3})\s*\.")  # 'follows: "236E. ...'
# extra codes named before the verb ('Section 236D and 236F omitted ...')
_CODE_TOKEN_RE = re.compile(r"\b(\d{1,3}[A-Z]{0,3})\b")


def _omission_codes(fn_text: str, real_codes: set) -> list:
    """``[(code, heading), ...]`` named by an omission/repeal footnote.

    Handles the corpus's wording zoo: name-first notes (single- and
    multi-section), stray leading quotes, a 'The section ...' article, and
    verb-first notes whose section is named in a later sentence.  Verb-first
    extraction is restricted to codes that are NOT already discovered real
    sections -- those notes often reference the HOSTING section of a mere
    clause omission, which must not fabricate a duplicate placeholder.
    """
    t = (fn_text or "").lstrip(" \n\"“”'")
    t = re.sub(r"^[Tt]he\s+[Ss]ection\b", "Section", t)
    out = []
    m = _OMIT_FN_RE.match(t)
    if m:
        heading = _placeholder_heading(t)
        codes = [m.group(1) + m.group(2)]
        # names before the verb: 'Section 236D and 236F omitted ...'
        verb = re.search(r"\b(?:[Oo]mitted|[Rr]epealed|[Rr]e-?numbered)\b",
                         m.group(3))
        lead = m.group(3)[:verb.start()] if verb else ""
        codes += [c for c in _CODE_TOKEN_RE.findall(lead) if c not in codes]
        return [(c, heading) for c in codes]
    lead = _OMIT_LEAD_RE.match(t)
    if lead:
        nm = _OMIT_NAMED_LATER_RE.search(t)
        if nm:
            code = next(g for g in nm.groups() if g)
            if code not in real_codes:
                heading = lead.group(1).strip(" ,;")
                out.append((code, heading[:1].upper() + heading[1:]))
    return out


def _heading_from_words(before_words, code: str) -> str:
    """Section heading = the heading-side words minus decoration.

    Mirrors what the TOC would have carried: code token, superscript markers,
    amendment brackets and the trailing ``.—`` are stripped; interior
    amendment brackets go too (``[Default surcharge].`` -> ``Default
    surcharge``) since the heading field is navigational -- the html keeps
    the brackets.
    """
    txt = " ".join(w.text for w in before_words if not w.is_marker)
    txt = txt.replace("[", " ").replace("]", " ")
    txt = re.sub(r"\s+", " ", txt).strip()
    txt = re.sub(r"^\(?" + re.escape(code) + r"\)?\s*\.?\s*", "", txt)
    txt = re.sub(r"\.?\s*[—–―─-]+\s*$", "", txt).strip()
    return _clean_heading(txt)


def _multiline_heading(body_refs, idx: int, li: int, before, code: str) -> str:
    """Heading words spanning a wrapped title: full lines idx..idx+li-1 plus
    the dash line's heading-side words (``65E. Tax credit for industrial
    undertakings established before the first day of\\nJuly, 2011.—``)."""
    head_words = []
    for j in range(li):
        head_words.extend(sorted(body_refs[idx + j].line.words,
                                 key=lambda w: w.x0))
    head_words.extend(before)
    return _heading_from_words(head_words, code)


def _placeholder_heading(fn_text: str) -> str:
    """Placeholder heading from the omission footnote, TOC-row style.

    ``Section "64A" omitted by the Finance Act, 2021. ...`` becomes
    ``Omitted by the Finance Act, 2021`` -- matching the wording TOC rows use
    for body-less sections, and carrying the Omitted/Repealed keyword the
    pipeline keys on to suppress the fabricated heading dash.
    """
    m = _OMIT_FN_RE.match(fn_text or "")
    if not m:
        return ""
    tail = re.sub(r"\s+", " ", m.group(3)).strip(" ,;")
    # start at the verb: a multi-section note ('Section 236D and 236F
    # omitted ...') otherwise yields 'And 236F omitted ...'
    verb = re.search(r"\b(?:[Oo]mitted|[Rr]epealed|[Rr]e-?numbered|[Ii]s re-numbered)\b",
                     tail)
    if verb:
        tail = tail[verb.start():]
    tail = _OMIT_TRAILER_RE.sub("", tail).strip(" ,;")
    return (tail[:1].upper() + tail[1:]) if tail else ""


def discover_structure(body_refs, printed_by_page, page_footnotes):
    """Reconstruct ``(chapters, ordered_sections)`` from the body stream.

    Same contract as :func:`toc.parse_toc` (schedules stay on their existing
    body-driven path), except every real section entry also carries
    ``anchor`` -- the LineRef of its heading line.
    """
    chapters: list[Node] = []
    reals: list[tuple[int, SectionEntry]] = []      # (body index, entry)
    container_at: list = [None] * len(body_refs)    # container per body index
    cur_chapter = cur_part = cur_division = None
    pending: Node | None = None      # structural node awaiting heading line(s)
    pending_left = 0
    last_key = None                  # code_sort_key of the last REAL section

    def container():
        if cur_division is not None:
            return cur_division
        if cur_part is not None:
            return cur_part
        return cur_chapter

    def printed(page: int) -> int:
        return printed_by_page.get(page, page - 1)

    # ---- pass 1: structural tree + real sections ---------------------------
    for idx, ref in enumerate(body_refs):
        container_at[idx] = container()
        if getattr(ref.line, "is_table", False):
            # a grid-extracted table can neither open a section nor carry a
            # structural heading, and it ends any pending heading capture
            pending, pending_left = None, 0
            continue
        text = ref.line.text().strip()
        if not text:
            continue

        # ---- structural heading (CHAPTER / PART / Division) ----------------
        if is_structural_boundary(text):
            core = re.sub(r"\s+", " ", _STRUCT_DECOR_RE.sub("", text)).strip()
            kw = core.split()[0].upper()
            numeral = core.split(None, 1)[1] if " " in core else ""
            if kw == "CHAPTER":
                node = Node(kind="chapter",
                            code="CHAPTER " + _chapter_numeral(numeral))
                chapters.append(node)
                cur_chapter, cur_part, cur_division = node, None, None
            elif kw == "PART":
                node = Node(kind="part", code="PART " + numeral.upper())
                if cur_chapter is not None:
                    cur_chapter.parts.append(node)
                cur_part, cur_division = node, None
            else:  # Division
                node = Node(kind="division", code="Division " + numeral)
                parent = cur_part if cur_part is not None else cur_chapter
                if parent is not None:
                    parent.divisions.append(node)
                cur_division = node
            pending, pending_left = node, 2
            container_at[idx] = container()
            continue

        words = sorted(ref.line.words, key=lambda w: w.x0)

        # ---- real section start --------------------------------------------
        entry = None
        m = _DOTFORM_RE.match(text[:40])
        if m:
            code = m.group(1)
            key = code_sort_key(code)
            if ((last_key is None or key > last_key)
                    and _bold_title(words, _code_token_index(words))):
                split = _find_heading_split(body_refs[idx:idx + 4],
                                            min(4, len(body_refs) - idx))
                if split is not None:
                    li, before, _after = split
                    entry = SectionEntry(
                        code=code,
                        heading=_multiline_heading(body_refs, idx, li,
                                                   before, code),
                        printed_page=printed(ref.page), parent=container(),
                        anchor=ref)
                else:
                    # colon-dash terminator ("99B. Special procedure for
                    # small traders and shopkeepers:-Notwithstanding ...")
                    # -- a shape _find_heading_split's period-dash rule
                    # can't see; same-line only, still behind the bold gate
                    cm = re.match(
                        r"^\s*(?:[\d*]{1,3}\s+)?\[?\s*" + re.escape(code)
                        + r"\s*\.\s*(.+?)\s*:\s*[-—–―─]", text)
                    if cm:
                        entry = SectionEntry(
                            code=code,
                            heading=_clean_heading(
                                cm.group(1).replace("[", " ").replace("]", " ")),
                            printed_page=printed(ref.page),
                            parent=container(), anchor=ref)
        if entry is None:
            m = _BRACKETPAREN_START_RE.match(text)
            if m:
                # a bracket-parenthesised code is an inserted sibling of the
                # section it extends ("4 [(4AB) Subject ..."): same numeric
                # family, strictly greater letter suffix, and its leading
                # marker's footnote must confirm the insertion/substitution --
                # this rejects inserted CLAUSES like "3[(1A) ..." inside sec 2.
                code = m.group("code")
                key = code_sort_key(code)
                if (last_key is not None and key > last_key
                        and key[0] == last_key[0]):
                    marker = m.group("marker")
                    conf = re.compile(
                        r"^Section\s*[\"“']?\s*\(?" + re.escape(code)
                        + r"\)?\s*[\"”']?\s.*\b(inserted|substituted)\b",
                        re.IGNORECASE | re.DOTALL)
                    if any(fn.marker == marker and conf.match(fn.text or "")
                           for fn in page_footnotes.get(ref.page, [])):
                        heading = _heading_from_words(
                            [w for w in words if not w.is_marker], code)
                        entry = SectionEntry(
                            code=code, heading=heading,
                            printed_page=printed(ref.page),
                            parent=container(), anchor=ref)
        if entry is None:
            # dot-less inserted start ("1 [230E Directorate General ...") --
            # bold gate + same-line dash live in _dotless_candidate_code
            code = _dotless_candidate_code(ref.line)
            if code:
                key = code_sort_key(code)
                if last_key is None or key > last_key:
                    split = _find_heading_split([ref], 1)
                    if split is not None:
                        _li, before, _after = split
                        entry = SectionEntry(
                            code=code,
                            heading=_heading_from_words(before, code),
                            printed_page=printed(ref.page),
                            parent=container(), anchor=ref)
        if entry is not None:
            reals.append((idx, entry))
            last_key = code_sort_key(entry.code)
            pending, pending_left = None, 0
            continue

        # ---- heading continuation for a structural node --------------------
        if pending is not None and pending_left > 0:
            t = text.strip()
            # a heading line, not body content: headings never open with a
            # lowercase word or a subsection marker
            if t[:1].islower() or t.startswith("("):
                pending, pending_left = None, 0
            else:
                pending.heading = _join_heading(pending.heading,
                                                _clean_heading(t))
                pending_left -= 1
            continue

    # ---- pass 2: omitted/repealed/renumbered placeholders ------------------
    # A placeholder is admitted only where its code fits between the REAL
    # sections physically surrounding its bracket line -- so a renumbering
    # note printed at the section's NEW location ("Section 64A is
    # re-numbered ..." beside 60C) is rejected there and accepted at the old
    # 64A position further down.  Bounds are non-strict: an omitted-then-
    # reinserted code (236Y) legitimately equals its real neighbour.
    real_positions = [i for i, _ in reals]
    real_keys = [code_sort_key(e.code) for _, e in reals]
    real_codes = {e.code for _, e in reals}
    placeholders: list[tuple[int, SectionEntry]] = []
    placeholder_codes: set[str] = set()
    import bisect
    for idx, ref in enumerate(body_refs):
        if getattr(ref.line, "is_table", False):
            continue
        text = ref.line.text().strip()
        if not text or "[" not in text or not BRACKETS_ONLY_RE.match(text):
            continue
        for w in sorted(ref.line.words, key=lambda w: w.x0):
            marker = w.text.strip()
            if not marker.isdigit():
                continue
            for fn in page_footnotes.get(ref.page, []):
                if fn.marker != marker:
                    continue
                for code, heading in _omission_codes(fn.text, real_codes):
                    key = code_sort_key(code)
                    j = bisect.bisect_left(real_positions, idx)
                    prev_key = real_keys[j - 1] if j > 0 else None
                    next_key = real_keys[j] if j < len(real_keys) else None
                    if prev_key is not None and key < prev_key:
                        continue
                    if next_key is not None and key > next_key:
                        continue
                    if code in placeholder_codes:
                        continue
                    placeholders.append((idx, SectionEntry(
                        code=code, heading=heading,
                        printed_page=printed(ref.page),
                        parent=container_at[idx])))
                    placeholder_codes.add(code)

    merged = sorted(reals + placeholders, key=lambda t: t[0])
    return chapters, [e for _, e in merged]
