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

from .builder import (
    _DOTFORM_RE,
    _HEADING_DASH_RE,
    _STRUCT_DECOR_RE,
    _bold_title,
    _code_token_index,
    _dotless_candidate_code,
    _find_heading_split,
    is_structural_boundary,
)
from .footnotes import BRACKETS_ONLY_RE
from .grammar import CODE, CODE_SUFFIXED, MARKER_PREFIX  # noqa: F401
from .grammar import code_sort_key as _grammar_code_sort_key
from .toc import Node, SectionEntry, _chapter_numeral, _clean_heading, _join_heading


def code_sort_key(code: str):
    """Numeric-then-suffix key for a section code: ``"175AA" -> (175, "AA")``.

    Section codes advance monotonically through the body (``4 < 4A < 4AB <
    4B < 5``), which is the strongest cheap rejector of look-alike lines: a
    definitions clause ``17A.`` inside section 2, or a cross-reference ``25.``
    wrapped inside section 20, lands far out of sequence.
    """
    return _grammar_code_sort_key(code)


# bracket-parenthesised inserted section ("4 [(4AB) Subject ...")
_BRACKETPAREN_START_RE = re.compile(
    rf"^\s*(?P<marker>[\d*]{{1,4}}[a-z]?(?:\s*,\s*[\d*]{{1,4}}[a-z]?)*)"
    rf"\s*\[\s*\((?P<code>{CODE_SUFFIXED})\)")
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


#: Language only an AMENDING instrument uses about itself.  Measured over the
#: 22 flat-act editions in ``output/``: per 10,000 characters of body AND
#: footnote text, amendment instruments score 4.63 (Finance Act 2025) to 29.71
#: while substantive Acts -- Sales Tax, Pakistan Single Window, VDDA, the FBR
#: Act, Foreign Assets -- score 0.00 to 0.32, a 14x separation.
_AMENDING_RE = re.compile(
    r"shall be (?:substituted|inserted|omitted|added|renumbered|re-numbered)"
    r"|the following (?:new )?(?:section|sub-section|clause|schedule|table|"
    r"division|part|proviso|entry|entries|words|amendments)"
    r"|the following amendments shall be made"
    r"|for the (?:words|figures|expression|semicolon|full stop|comma)",
    re.IGNORECASE)

#: A clause of an amendment instrument either names what it does to another
#: instrument, or names that instrument.  Both halves measured 2026-08-07: inside
#: a Finance Act this separates its own clauses from the sections it reproduces.
#: ``Repeal``, ``Definitions``, ``Commencement`` and ``Extent`` were in this list
#: and are NOT: standing alone they are the section titles of a SUBSTANTIVE Act,
#: which is exactly the material an amendment instrument reproduces.  Ledger P33:
#: Finance Act 2019 quotes the Assets Declaration Act, 2019 inside its clause 17,
#: and that Act's own ``19. Repeal`` (page 130) was accepted as clause 19 of the
#: Finance Act, blocking the real clause 18 (``Enactment of Public Finance
#: Management Act, 2019``, page 131) on the monotonic cursor.  Measured over
#: every clause title accepted in the corpus's flat acts: the four words carry
#: **7 titles, and all 7 are in substantive Acts the classifier never gates**
#: (Foreign Assets 2018, VDDA 2018, the FBR Act 2007 and three Sales Tax
#: editions, whose amending density is 0.00-0.11 against a 2.0 threshold).  A
#: real clause that repeals something names the instrument -- "Repeal of the
#: Petroleum Products Ordinance, 1961" -- and still passes on
#: ``_INSTRUMENT_TITLE_RE``.
_AMEND_TITLE_RE = re.compile(
    r"^\s*(?:Short title|Amendment|Amendments|Substitution|Insertion|Omission|"
    r"Enactment|Addition|Renumbering|Capital value tax)\b",
    re.IGNORECASE)
_INSTRUMENT_TITLE_RE = re.compile(
    r"\b(?:Act|Ordinance)\b[^.]{0,40}?\b(?:19|20)\d\d\b"      # "the Sales Tax Act, 1990"
    r"|\b(?:Act|Ordinance)\s+(?:No\.?\s*)?[IVXLC]+\s+of\s+(?:19|20)\d\d\b"  # "Act IV of 1969"
    r"|\(\s*[IVXLC]+\s+of\s+(?:19|20)\d\d\s*\)",              # "(II of 1899)"
    re.IGNORECASE)
#: A SCHEDULE entry of the instrument being amended, which the Stamp Act sets in
#: full capitals: "ACKNOWLEDGMENT of a debt", "CUSTOMS BOND", "ENTRY AS AN
#: ADVOCATE, OR ATTORNEY ON THE ROLL OF ANY HIGH COURT".  Two capitalised words
#: of two or more letters, at the very start of the title.
_CAPS_SCHEDULE_ENTRY_RE = re.compile(r"\s*[A-Z][A-Z'’-]+\s+[A-Z][A-Z'’-]+")

#: below this density a document is NOT treated as an amendment instrument, so it
#: keeps the ungated behaviour -- the safe direction for a substantive Act
AMENDING_DENSITY_MIN = 2.0

#: a clause code with NO dot after it ("2 Amendment in the Stamp Act, 1899"), which
#: some gazettes set.  Used ONLY inside a classified amendment instrument and only
#: behind the heading terminator and the clause-title gate -- see the call site.
_DOTLESS_NUMERIC_RE = re.compile(r"^\s*(?:[\d*]{1,3}\s+)?\[?\s*(\d{1,3})\s+(?=[A-Z])")


def amending_density(body_refs, page_footnotes=None) -> float:
    """Occurrences of amending language per 10,000 characters of the BODY zone.

    The footnote zone must NOT be counted, and this is the correction that made
    the gate safe.  A consolidated Act's footnotes ARE its amendment history --
    every one of them says "substituted by the Finance Act, 2019" -- so including
    them inverts the test: measured over the corpus, footnote-zone density runs
    5.56 on Sales Tax, 7.07 on Customs 2012 and **270** on Finance Act 2013,
    against a body-zone density of 0.09-0.11 for the consolidated families.
    Counting both zones classified **Customs 2012 as an amendment instrument and
    the title gate cut it from 303 sections to 6** -- the exact catastrophe this
    corpus's doctrine warns about, caught by ``structure_diff``.

    The body zone alone separates the populations with a 20x margin:

    | population | body-zone density |
    |---|---|
    | amendment instruments | **4.05** (Income Tax 3rd Amdt 2016) to 34.49 |
    | consolidated Acts (Customs, Sales Tax, Federal Excise) | 0.09 - 0.11 |
    | substantive gazette Acts (PSW 2021, VDDA) | 0.00 |

    ``page_footnotes`` is accepted and ignored, so callers do not have to change
    and so this docstring sits where someone would otherwise re-add them.

    The known cost is Finance Act 2025 at **0.21**: ledger P14 zones its own
    amending clauses as footnotes, so it is not recognised as the amendment
    instrument it plainly is and keeps its two tariff-row "sections".  That is
    already recorded as P06-for-FA2025 being blocked on P14, and it is the right
    trade: one edition unimproved against twenty consolidated editions intact.
    """
    text = "\n".join(r.line.text() for r in body_refs)
    if not text:
        return 0.0
    return 10000.0 * len(_AMENDING_RE.findall(text)) / len(text)


def _is_own_clause_title(heading: str) -> bool:
    """Whether a clause title reads as an amendment instrument's OWN clause.

    Inside a classified amendment instrument only: a clause either says what it
    does ("Amendments of the Customs Act, 1969", "Short title and commencement")
    or names the instrument it amends.  A section REPRODUCED from the amended Act
    ("Tax credit for specified industrial undertakings", "Prosecution for
    enabling offshore tax evasion") and a tariff row ("Solar Desalination System
    8421.2100") do neither.

    This gate is applied ONLY where the classifier fired, because 357 accepted
    codes across the flat acts match neither pattern and most of them are real
    statutory sections -- applying it to substantive Acts would shred five of
    them to tidy the Finance Acts (measured 2026-08-07).

    Naming an instrument is the weaker half, because a SCHEDULE entry of the
    amended instrument can name one in passing.  Ledger P33: Finance Act 2019's
    page 12 prints the Stamp Act's Schedule I entry ``30. ENTRY AS AN ADVOCATE,
    OR ATTORNEY ON THE ROLL OF ANY HIGH COURT--under the Legal Practitioners and
    Bar Councils Act, 1973``, whose trailing "Act, 1973" satisfied that half.
    Accepting code 30 on page 12 advanced the monotonic cursor past every one of
    the Act's REAL clauses 3-19 on pages 30-130 -- one false accept cost
    seventeen clauses, the A12/NEW-5 cascade again -- and the edition shipped
    with three "sections", one of them holding 219 KB.

    The Stamp Act sets its schedule entries in full capitals and a Finance Act
    never sets a clause title that way.  Measured over every clause title
    accepted in the corpus's flat acts (130 of them, across 24 editions): two
    leading ALL-CAPS words occur on **exactly one**, the FA2019 entry above.  A
    position cap on the instrument match was measured first and rejected --
    FA2019's entry matches at character 111 and Finance Act 2025's real clause 12
    at 116, so magnitude cannot separate them.  The veto is scoped to titles that
    qualify on the instrument half ALONE, so a gazette that really did set
    "AMENDMENT OF ..." in capitals still passes on the verb.
    """
    h = (heading or "").strip()
    if _AMEND_TITLE_RE.search(h):
        return True
    return bool(_INSTRUMENT_TITLE_RE.search(h)) and not _CAPS_SCHEDULE_ENTRY_RE.match(h)


def _alt_code(code: str, words, last_key) -> str:
    """The section code, arbitrated by the OCR engines where they disagreed.

    Ledger **P42**.  The Finance (Supplementary) Act, 2022 opens with `1. Short
    title and commencement`, and its scan is read `4.` -- Tesseract says `4.` at
    77.0 confidence, RapidOCR says `1.` at 65.5, and the pipeline keeps the
    higher-confidence reading and flags the token ``needs_review``.  One misread
    digit then cost the document its structure: the monotonic cursor started at
    4, so the Act's real clauses **2 and 3 were both rejected as out of sequence**
    and their 17 KB merged into clause "4".  `clause_codes_plausible` reported
    "first clause code is 4, not 1".

    A ``needs_review`` flag says the token is uncertain; it cannot say which
    reading is right.  The document's own numbering can, and only in the one
    place where the flag and the numbering disagree: **the FIRST clause**, where
    no cursor value exists yet to check the code against and where a single wrong
    digit cascades over everything after it.  So: if no clause has been accepted
    yet, the code token was disagreed, and the rejected reading is a SMALLER
    valid code, take the rejected reading.

    Deliberately narrow.  It fires only on an OCR'd document (``alt`` is empty
    on a text layer and on every agreed token), only for the opening clause, and
    only downward -- an engine disagreement can never push the cursor forward,
    which is the direction that skips statute.
    """
    if last_key is not None:
        return code
    for w in words:
        t = (w.text or "").strip()
        if not t or w.is_marker or set(t) <= set("[]* "):
            continue
        alt = (getattr(w, "alt", "") or "").strip().strip(".[]")
        if not alt or not _DOTFORM_RE.match(t[:40]):
            return code
        m = _DOTFORM_RE.match(alt + ".")
        if not m:
            return code
        return m.group(1) if code_sort_key(m.group(1)) < code_sort_key(code) else code
    return code


def _quoted_container(is_amendment: bool, last_key) -> bool:
    """Whether a structural heading here is material the instrument QUOTES.

    An amendment instrument is a flat list of numbered clauses -- it declares no
    chapters of its own, and the only container it prints is the gazette's own
    part label in the front matter ("PART I / Acts, Ordinances, President's
    Orders and Regulations", page 2, ahead of clause 1).  Anything structural
    printed AFTER its first clause is a heading of the instrument it amends,
    reproduced inside a quotation.

    Ledger P32.  Measured on the two editions this was found on: Finance Act
    2013 prints ``DIVISION XII`` .. ``Division XVll`` on pages 38-39, inside
    clause 7's reproduction of the Income Tax Ordinance's First Schedule, and
    the LAST of them adopted clause **8** ("Amendments of the Federal Excise
    Act, 2005"); Finance Act 2014 does the same on pages 56-61 with ``Division
    IA``/``XIX``/``XX``, which took clauses 8 and 15.  Both editions then
    reported ``section '1' out of order after '8'`` because the leaf iterator
    walks containers before their siblings' sections.

    Scoped to a CLASSIFIED amendment instrument and to headings after the first
    accepted clause, so it cannot reach a document that really does declare
    chapters -- Public Finance Management Act 2019 is the case to protect: it is
    a gazette reproducing an Act WITH ten chapters, it classifies below
    ``AMENDING_DENSITY_MIN``, and its reproduced chapters legitimately parent
    the reproduced Act's sections.

    Rejecting a heading here does not drop it: the line falls through to the
    body and the enclosing clause claims it, which is the handover rule
    P19/P21/P22 established -- the component that says "not mine" hands the
    lines over, it never discards them.
    """
    return is_amendment and last_key is not None


def discover_structure(body_refs, printed_by_page, page_footnotes,
                       _gate: bool = True):
    """Reconstruct ``(chapters, ordered_sections)`` from the body stream.

    Same contract as :func:`toc.parse_toc` (schedules stay on their existing
    body-driven path), except every real section entry also carries
    ``anchor`` -- the LineRef of its heading line.
    """

    # Does this document use a bold face AT ALL?  ``_bold_title`` gates every
    # section start below, and a document typeset wholly in one plain face (the
    # Finance (Supplementary) Acts, all Helvetica) would otherwise have every
    # candidate vetoed and yield zero sections.
    doc_has_bold = any("bold" in (w.fontname or "").lower()
                       for r in body_refs
                       for w in (getattr(r.line, "words", []) or []))
    # Is this document an amendment instrument at all?  The clause-title gate
    # below is only safe inside one -- see ``_is_own_clause_title``.
    density = amending_density(body_refs, page_footnotes)
    is_amendment = _gate and density >= AMENDING_DENSITY_MIN
    rejected: list[str] = []

    chapters: list[Node] = []
    reals: list[tuple[int, SectionEntry]] = []      # (body index, entry)
    container_at: list = [None] * len(body_refs)    # container per body index
    cur_chapter = cur_part = cur_division = None
    pending: Node | None = None      # structural node awaiting heading line(s)
    pending_left = 0
    last_key = None                  # code_sort_key of the last REAL section

    # Where this act's OWN numbering begins.  A gazette Act reproduced inside a
    # Finance Act is preceded by the host instrument's enacting clause, which
    # carries the HOST's number: page 1 of the Voluntary Declaration of Domestic
    # Assets Act, 2018 prints "12. Voluntary Declaration of Domestic Assets Act,
    # 2018.-There is hereby enacted ...", clause 12 of the Finance Act 2018.
    # Accepted greedily, that code-12 candidate advances the monotonic cursor and
    # every one of the reproduced act's own sections 1-11 is then rejected as out
    # of sequence -- 12 sections became 3.  So if a bare section "1" appears
    # LATER in the body, nothing before it belongs to this act's numbering.
    # A bare "N." with no title is not a section start -- page 1 of that Act is a
    # declaration FORM whose numbered blanks print as "3.", "4.", "1.", "2." with
    # nothing after them, so the first "1." in the body is a form field, not
    # section 1.  Require real title text after the code.
    #
    # ...and require the HEADING TERMINATOR too, because "real title text" is not
    # enough.  A SCHEDULE that lists numbered entities looks exactly like a run of
    # section starts: the Pakistan Single Window Act 2021 ends with a schedule of
    # ministries beginning "1. Alternate Energy Development Board", 31 alphabetic
    # characters, at body line 580 of 702.  Anchoring there discarded the Act's 20
    # real sections on pages 4-15 and shipped a document with **8.127% of its body
    # text** -- three "sections" whose codes were table rows.  Ledger P15.
    #
    # A real section start runs its title straight into the provision text and so
    # prints ".—", ".-", ".--" or ".―" (``_HEADING_DASH_RE``, the same idiom
    # ``_find_heading_split`` already relies on); a schedule list entry is a bare
    # noun phrase with nothing after it.  Measured over every document that
    # reaches this code path -- the three TOC-less Phase-1 editions plus six
    # gazette Acts -- this moves the anchor on PSW 2021 alone and leaves all eight
    # others byte-identical, each of them anchoring 0.1%-9.1% into the body.
    #
    # Accepting the dash-less form `commencement. (1) This Act shall` as well was
    # TRIED and REVERTED, and the measurement is worth keeping so it is not
    # retried: it gains a section boundary on Finance Supplementary Act 2023 --
    # which already conserved 100.000% of its body without it -- and costs
    # Finance Act 2025 **9 points of conservation, 115 missing words to 3,007**,
    # because the levy Act reproduced inside it opens `1. Short title, extent and
    # commencement. (1)` and the anchor jumps there, discarding everything before.
    # Trading ~2,900 words of statute for one section node is the wrong direction.
    # Telling those two cases apart needs to know which instrument the document
    # IS, which is the P06 question, not something this pre-scan can decide.
    #
    # Finding NO anchor is the safe outcome, not a failure: ``section_start``
    # stays 0, nothing is discarded, and a host clause can only ADD a spurious
    # section. Dropping real statute is the worse error, so the fallback must
    # never be "skip ahead".
    section_start = 0
    for _i, _r in enumerate(body_refs):
        _t = _r.line.text().strip()
        _m = _DOTFORM_RE.match(_t[:40])
        if not _m or code_sort_key(_m.group(1)) != (1, ""):
            continue
        if (len(re.findall(r"[A-Za-z]", _t[_m.end():])) >= 8
                and _HEADING_DASH_RE.search(_t)):
            section_start = _i
            break

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
        if is_structural_boundary(text) and not _quoted_container(is_amendment,
                                                                  last_key):
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
                else:
                    # A PART with no enclosing CHAPTER is a ROOT container, not a
                    # floating node.  The gazette Finance Acts open with a bare
                    # "PART I" (their own division label, no chapters anywhere in
                    # the document), and every clause was parented to it -- but it
                    # was attached to nothing and `chapters` came back empty, so
                    # all 11 sections of Finance Act 2024 were unreachable and the
                    # file converted to 91 characters from 89 pages while
                    # reporting success.  A node that parents sections MUST be
                    # reachable from the returned roots.
                    chapters.append(node)
                cur_part, cur_division = node, None
            else:  # Division
                node = Node(kind="division", code="Division " + numeral)
                parent = cur_part if cur_part is not None else cur_chapter
                if parent is not None:
                    parent.divisions.append(node)
                else:
                    chapters.append(node)   # same rule as PART above
                cur_division = node
            pending, pending_left = node, 2
            container_at[idx] = container()
            continue

        words = sorted(ref.line.words, key=lambda w: w.x0)

        # ---- real section start --------------------------------------------
        entry = None
        m = _DOTFORM_RE.match(text[:40]) if idx >= section_start else None
        if m:
            # ``printed`` is what the page shows, ``code`` what the document
            # means -- they differ only where the OCR engines disagreed on the
            # opening clause's digit (P42).  The heading stripper must be given
            # the PRINTED code, or it leaves "4." at the head of the title and
            # the P25 clause-title gate then rejects the clause it just rescued.
            printed_code = m.group(1)
            code = _alt_code(printed_code, words, last_key)
            key = code_sort_key(code)
            # Gazette Finance Acts set their OWN clause titles in regular
            # ArialMT (FA2022 ``1. Short title...``, ``2. Amendments of Customs``);
            # only reproduced sections of the amended Act are bold (FA2022
            # ``38. Alternative Dispute Resolution``).  Requiring bold here
            # dropped every real clause into the preamble (104 uncovered pages)
            # and kept the one bold foreign section.  Amendment instruments
            # already have ``_is_own_clause_title`` (P06) as the gate; skip bold.
            title_ok = (
                is_amendment
                or _bold_title(words, _code_token_index(words), doc_has_bold)
            )
            if (last_key is None or key > last_key) and title_ok:
                split = _find_heading_split(body_refs[idx:idx + 4],
                                            min(4, len(body_refs) - idx))
                if split is not None:
                    li, before, _after = split
                    entry = SectionEntry(
                        code=code,
                        heading=_multiline_heading(body_refs, idx, li,
                                                   before, printed_code),
                        printed_page=printed(ref.page), parent=container(),
                        anchor=ref)
                else:
                    # colon-dash terminator ("99B. Special procedure for
                    # small traders and shopkeepers:-Notwithstanding ...")
                    # -- a shape _find_heading_split's period-dash rule
                    # can't see; same-line only, still behind the bold gate
                    cm = re.match(
                        r"^\s*(?:[\d*]{1,3}\s+)?\[?\s*" + re.escape(printed_code)
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
        if entry is None and is_amendment:
            # A gazette sets some clause numbers with NO dot after the code:
            # Finance Act 2025 prints `2 Amendment in the Stamp Act, 1899 (ll of
            # 1899).- In the Stamp Act ...`, so `_DOTFORM_RE` never sees it and its
            # clauses 1-3 ended up inside the preamble.  `_dotless_candidate_code`
            # cannot help -- it requires a LETTER-suffixed code, because dot-less
            # is the shape of an *inserted* section.
            #
            # Accepted only where all of this holds at once: the document is a
            # classified amendment instrument, the code still advances the
            # monotonic cursor, the heading terminator is on the same line, and the
            # title passes the P06 gate below.  A bare number opening a line is far
            # too common to accept on any weaker evidence -- every tariff row is
            # one -- and the title gate is what makes this specific.
            m2 = _DOTLESS_NUMERIC_RE.match(text[:40])
            if m2 and _HEADING_DASH_RE.search(text):
                code = m2.group(1)
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
            # P06: inside an AMENDMENT INSTRUMENT, a clause title that neither
            # says what it amends nor names an instrument is not a clause of this
            # Act -- it is a section of the Act being amended, printed verbatim
            # inside a quotation, or a tariff row.  Rejecting it here only means
            # its lines stay with the previous clause, which is where the printed
            # quotation actually sits; the regions that used to be ORPHANED by a
            # rejection are now guaranteed a leaf (ledger P19/P21/P22), which is
            # what made the 2026-08-07 attempt lose 13,000 words.
            if is_amendment and not _is_own_clause_title(entry.heading):
                rejected.append(entry.code)
                continue
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

    # The gate must never be able to empty a document.  If every candidate was
    # rejected, this is not an amendment instrument the gate understands -- redo
    # the scan ungated and keep today's behaviour.  A document with no sections
    # has nowhere to put its body at all, which is how the 2026-08-07 attempt took
    # Finance Act 2022 to 0 sections and lost 4,563 words.
    if is_amendment and not reals and rejected:
        return discover_structure(body_refs, printed_by_page, page_footnotes,
                                  _gate=False)

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
