"""Invariants shared by every lane -- one copy, the lane only where it differs.

These three files were near-forks. Measured at AST level before splitting: 56 functions
and 47 module constants were **byte-identical** between the Acts and the Rules lanes (zero
comment drift), 71 of those 103 blocks were identical in the Ordinance lane too, and only
7 functions plus `_SPLIT_ORDINAL` genuinely differed. Everything identical lives here.

Exactly two shared invariants read a value that varies by lane, so each takes it as a
keyword-only argument defaulting to the form **two of the three** lanes use -- and only the
outlier lane binds anything:

* `inv_no_split_ordinals` -> `_SPLIT_ORDINAL`, where the Rules regex carries an extra
  negative lookahead. Acts and Ordinance take the default; `rules.py` binds a partial.
* `inv_footnotes_in_numeric_order` -> `_ref_key`. Acts and Rules take the default;
  `ordinance.py` binds a partial.

That is the whole injection mechanism. Phase 3 deferred this split expecting to need the
`legal_ingest` profile as an injection point; the measurement showed two keyword defaults
cover it, which is why nothing here imports from `packages/` -- the `tools/` import chain
stays stdlib-only, as CI's pipeline job requires.

A lane defining its own `inv_<name>` wins automatically via `all_invariants()` below, so an
override never has to be registered in a second place.
"""

from __future__ import annotations

import re

from ..loader import (
    html_fragments,
    iter_all_leaves,
    iter_schedule_leaves,
    iter_section_leaves,
)

# a private-use glyph leaking through (e.g. the U+F0D8 asterisk)
_PUA = re.compile(r"[-]")


# a bare number at the end of a line, after sentence punctuation
_TRAILING_NUM = re.compile(r"[.\]\;”]\s+(\d{2,4})\s*$")


#: a money amount ending the line.  ``_TRAILING_NUM`` anchors on the punctuation
#: before the number, and the dot in "Rs. 250" is an ABBREVIATION dot, not
#: sentence punctuation -- the Sales Tax Ninth Schedule's rate column ("Rs. 250"
#: for a SIM card) was read as printed page 250 of its own 255-258 span.  The
#: docstring above always claimed rate amounts were excluded; nothing implemented it.
_MONEY_TAIL = re.compile(r"(?:Rs|Rupees|US\$|\$)\.?\s*[\d,]+\s*$", re.IGNORECASE)


def inv_no_pua_glyphs(doc):
    bad = []
    for leaf in iter_all_leaves(doc):
        if _PUA.search(leaf.get("html", "")) or _PUA.search(leaf.get("plain_text", "")):
            bad.append(f"section {leaf.get('code')}: private-use glyph present")
    return bad


def inv_no_page_number_bleed(doc):
    """A running-footer page number must never bleed into the text.

    The footer number equals one of the leaf's own pages -- either the physical
    PDF page or its printed equivalent.  We only flag a trailing number that
    matches one of those, so legitimate trailing numbers (rate amounts like
    "Rs. 800", cross-refs like "section 113") are not false positives.

    The printed-page offset is read from ``metadata.calibration``, not hardcoded:
    it is 19 for the Ordinance but 22 for the Customs Act and 0 for Sales Tax and
    Federal Excise, so a fixed 19 both misses real bleeds and invents plausible
    pages that do not exist in the document.
    """
    offset = ((doc.get("metadata") or {}).get("calibration") or {}).get(
        "page_offset", 19)
    bad = []
    for leaf in iter_all_leaves(doc):
        sp, ep = leaf.get("start_page"), leaf.get("end_page")
        if sp is None or ep is None:
            continue
        # A leaf spanning many pages makes the plausible-page set so wide that it
        # overlaps the ordinary range of statutory cross-references, and the test
        # stops discriminating.  Customs s.156 is a 60-page penalty table whose
        # columns literally list the section numbers contravened, so a row ending
        # "...30[***] 131" matched its own printed page range -- "section 131",
        # not a bled folio.  Sections this long are the exception (median span
        # here is 0 pages); skipping them keeps the guard meaningful for the other
        # 320-odd.
        if ep - sp > 10:
            continue
        plausible = set()
        for p in range(sp, ep + 1):
            plausible.add(p)          # physical PDF page
            plausible.add(p - offset)  # printed page (calibrated offset)
        text = leaf.get("plain_text", "") or ""
        for line in text.split("\n"):
            line = line.strip()
            m = _TRAILING_NUM.search(line)
            if not (m and int(m.group(1)) in plausible):
                continue
            if _MONEY_TAIL.search(line):
                continue
            # A number this leaf CITES as a section is a cross-reference, not a
            # folio.  Sales Tax section 33 is the penalty table, and its third
            # column is "section of this Act to which the offence has reference":
            # row 16 reads "fails to make payment in the manner prescribed under
            # section 73 of this Act" and its reference cell is the bare "73",
            # which happens to fall inside the leaf's own 72-82 page span.  This
            # is the D02 class the docstring above already exempts for Customs
            # s.156 -- there by page span (>10), which this table misses by one
            # page.  Evidence beats a span threshold: require that the same leaf
            # does NOT name the number as a section before calling it a folio.
            if re.search(rf"\bsections?\s+{m.group(1)}\b", text):
                continue
            bad.append(f"section {leaf.get('code')}: footer page {m.group(1)} "
                       f"bled into text")
            break
    return bad


_STRAY_DOTNUM = re.compile(r"^\.\d{2,}$")


def inv_no_stray_dotnumber(doc):
    """A standalone leading-dot-number line ('.9230') must never appear in text.

    Such a line is a PDF extraction artifact (no legal text, no citation/value/
    code form) and is stripped in ``pagemodel`` before zoning.  This guards the
    strip document-wide so the artifact can never re-leak into a section.
    """
    bad = []
    for leaf in iter_all_leaves(doc):
        for line in (leaf.get("plain_text", "") or "").split("\n"):
            if _STRAY_DOTNUM.match(line.strip()):
                bad.append(f"section {leaf.get('code')}: stray dot-number line {line.strip()!r}")
                break
    return bad


_ORPHAN_MARKER_LI = re.compile(r"^\(\d{1,3}[A-Za-z]{0,2}\)\s*\.?\s*\]?$")


def inv_no_orphan_marker_li(doc):
    """A list item must not be a bare wrapped-marker fragment ("(1).]").

    A cross-reference whose "(N)" wraps onto a new line ("...in sub-section\n
    (1).]") must stay in its owning list item, not become a phantom subsection
    <li> holding only the marker + a closing bracket.  Guards the
    _looks_like_wrapped_reference cross-reference-noun signal document-wide.
    """
    bad = []
    for leaf in iter_all_leaves(doc):
        for li in re.findall(r"<li>(.*?)</li>", leaf.get("html", ""), re.S):
            txt = re.sub(r"<[^>]+>", "", li).strip()
            if _ORPHAN_MARKER_LI.match(txt):
                bad.append(f"section {leaf.get('code')}: orphan marker <li> {txt!r}")
    return bad


_OMITTED_H4 = re.compile(r"^\s*[0-9A-Z]+\.\s+[Oo]mitted\b", re.I)


def inv_no_omitted_heading_emdash(doc):
    """A synthetic omitted/repealed placeholder heading ("N. Omitted by the
    Finance Act, ...") must not carry a fabricated trailing em-dash.

    The PDF prints an omitted section only as an empty "[ ]" bracket -- there is
    no operative title dash, so appending ".—" invents punctuation the source
    never had.  Guards the omitted-placeholder rendering document-wide.
    """
    bad = []
    for leaf in iter_all_leaves(doc):
        m = re.search(r"<h4[^>]*>(.*?)</h4>", leaf.get("html", ""), re.S)
        if not m:
            continue
        vis = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if _OMITTED_H4.match(vis) and re.search(r"[—–―]\s*$", vis):
            bad.append(f"section {leaf.get('code')}: omitted heading ends with a dash: {vis!r}")
    return bad


def inv_footnote_schema(doc):
    bad = []
    need = {"ref", "marker", "text", "html"}
    for leaf in iter_all_leaves(doc):
        for fn in leaf.get("footnotes", []):
            missing = need - set(fn)
            if missing:
                bad.append(f"section {leaf.get('code')} footnote {fn.get('ref')}: missing {missing}")
    return bad


def inv_footnote_refs_printed_page(doc):
    """Footnote refs must be '<printed-page>.<marker>' with a plausible page."""
    bad = []
    for leaf in iter_all_leaves(doc):
        for fn in leaf.get("footnotes", []):
            ref = str(fn.get("ref", ""))
            m = re.match(r"^(\d+)\.", ref)
            if not m:
                bad.append(f"footnote ref not printed-page form: {ref!r}")
            elif int(m.group(1)) > 900:
                bad.append(f"footnote ref page implausibly large: {ref!r}")
    return bad


def _ref_key(ref: str):
    """Numeric order for a '<printed-page>.<marker>' ref.

    Delegates to the pipeline's own ordering so the check cannot disagree with
    the code it guards.  A local digits-only key called ['7.1', '7.1a', '7.2']
    unsorted, because it has no place for the letter suffix the Customs Act
    prints (33a, 36b, 36c) -- the ordering was right and the invariant wrong.
    """
    from legal_ingest.footnotes import ref_sort_key
    return ref_sort_key(ref)


def inv_footnotes_in_numeric_order(doc, *, ref_key=_ref_key):
    """A leaf's footnotes must be sorted numerically by (printed page, marker).

    Refs are strings, so a lexical sort renders 10.1, 10.10, 10.11, 10.2 --
    the reader sees the notes out of order.  Guards the ref_sort_key ordering
    applied at every footnote sort site in both pipelines."""
    bad = []
    for leaf in iter_all_leaves(doc):
        refs = [str(fn.get("ref", "")) for fn in leaf.get("footnotes", [])]
        keys = [ref_key(r) for r in refs]
        if keys != sorted(keys):
            bad.append(f"section {leaf.get('code')}: footnotes out of "
                       f"numeric order: {refs}")
    return bad


def inv_no_year_marker_refs(doc):
    """A ref like '19.2020' means a year inside quoted footnote text was misread
    as a marker, splitting the footnote -- the parser must fold those lines.

    Only the four-digit YEAR band counts as year-like.  The Ordinance could treat
    any marker >= 100 as a misread year because its notes never reach three
    digits; the Customs Act runs past 130 and Sales Tax into the 800s, so that
    rule flagged 57 perfectly good markers here (and, in the parser, would have
    discarded them).  See grammar.is_year_like."""
    from legal_ingest.grammar import is_year_like
    bad = []
    for leaf in iter_all_leaves(doc):
        for fn in leaf.get("footnotes", []):
            marker = str(fn.get("ref", "")).partition(".")[2]
            if is_year_like(marker):
                bad.append(f"section {leaf.get('code')}: year-like footnote ref {fn.get('ref')!r}")
    return bad


# a split ordinal ("30 th June", "1 st day") or a stray leading suffix line --
# both mean the superscript ordinal was not re-attached to its number
_SPLIT_ORDINAL = re.compile(r"\b\d+ (st|nd|rd|th)\b")


_LEAD_ORDINAL = re.compile(r"^(st|nd|rd|th)\b")


def inv_no_split_ordinals(doc, *, split_ordinal=_SPLIT_ORDINAL):
    """Ordinal superscripts must be merged into their number ('30th', not
    '30 th' / a stray 'th' line).  Guards the word-fragment merge in
    pagemodel._merge_split_words."""
    bad = []
    for leaf in iter_all_leaves(doc):
        if split_ordinal.search(leaf.get("plain_text", "")):
            bad.append(f"section {leaf.get('code')}: split ordinal in body")
        for fn in leaf.get("footnotes", []):
            t = fn.get("text", "")
            if split_ordinal.search(t):
                bad.append(f"footnote {fn.get('ref')}: split ordinal")
            elif _LEAD_ORDINAL.match(t):
                bad.append(f"footnote {fn.get('ref')}: stray leading ordinal suffix")
    return bad


# a leaf whose text opens with an amendment marker ("1[236Y. ..." or a bare
# bracket line "3[ ]") cites a footnote -- the rendered html must carry a
# visible <sup class="cite"> for it (in the h4 prefix or the body)
_LEADING_AMEND_MARKER = re.compile(r"^\d{1,3}\[")


def inv_leading_marker_cited(doc):
    """Every leaf that opens with an amendment marker must render a citation.

    Guards the classes fixed on 2026-07-04: heading-region markers dropped
    from html (236Y/236Z/4AB), and omitted-section bracket lines rendered
    without their <sup> citations (236T's '4[5[ ]]').

    Either superscript class satisfies it.  What this guards is the marker being
    DROPPED from the html; whether it also resolves to a note is
    ``inv_citation_refs_resolve``'s question, and since 2026-08-08 a marker with no
    note renders as ``<sup class="marker">`` rather than as a citation to nothing
    (Customs 2025 sections 155Q, 211A and 223 print exactly that shape)."""
    bad = []
    for leaf in iter_all_leaves(doc):
        first = (leaf.get("plain_text") or "").lstrip().split("\n", 1)[0]
        html = leaf.get("html") or ""
        if _LEADING_AMEND_MARKER.match(first.replace(" ", "")) \
                and '<sup class="cite"' not in html \
                and '<sup class="marker"' not in html:
            bad.append(f"section {leaf.get('code')}: leading amendment marker "
                       f"with no <sup> citation in html")
    return bad


# the longest genuine word in this corpus is ~20 letters; a 25+ run of letters
# means whole words were glued together ("toasuspenseaccountinaccordancewith")
_JAMMED_RUN = re.compile(r"[A-Za-z]{25,}")


#: Function words that appear in glued ENGLISH PROSE and not inside a chemical
#: name.  Chosen against the corpus's actual long tokens: "or" and "for" are
#: excluded because "chloro" and "chloroform" contain them, and a match needs TWO
#: distinct words so one accident cannot fire the check.
_JAM_WORDS = ("the", "and", "not", "shall", "may", "with", "which", "that",
              "this", "from", "been", "any", "tax", "per", "cent", "rupees",
              "year", "person", "fine", "extend", "purpose", "who", "fails",
              "means", "under", "said", "such")


def _is_jam(run: str) -> bool:
    """Whether a 25+ letter run is glued PROSE rather than one long word.

    A length threshold alone cannot tell them apart, and in this corpus the long
    tokens are overwhelmingly legitimate: the tariff schedules are full of
    ``bromochlorodifluoromethane`` (26), ``Dichloropentafluoropropanes`` (27) and
    ``Aminohydroxynaphthalenesulphonic`` (32), while the two real jams measured
    are ``roundnutsshelledweatherornotbroken`` (34, "ground nuts shelled whether
    or not broken") and ``maliciousmayextendtofouryearsandfine`` (36).  Verified
    over both sets: 0 of 11 chemical names contain two of the function words
    below, and every glued sentence contains at least two.
    """
    low = run.lower()
    return sum(1 for w in _JAM_WORDS if w in low) >= 2


def inv_no_jammed_words(doc):
    """No leaf or footnote text may contain a jammed run of glued words.

    Guards the word-glue rule: fully-justified lines compress real word gaps
    below the glue threshold; the space characters in the PDF are the ground
    truth for word boundaries (pagemodel._mark_space_before, and on a scan the
    recogniser's own tokenisation -- ledger P23)."""
    bad = []

    def first_jam(text):
        for m in _JAMMED_RUN.finditer(text or ""):
            if _is_jam(m.group(0)):
                return m.group(0)
        return None

    for leaf in iter_all_leaves(doc):
        run = first_jam(leaf.get("plain_text", ""))
        if run:
            bad.append(f"section {leaf.get('code')}: jammed words {run[:40]!r}")
        for fn in leaf.get("footnotes", []):
            run = first_jam(fn.get("text", ""))
            if run:
                bad.append(f"footnote {fn.get('ref')}: jammed words {run[:40]!r}")
    return bad


def inv_html_well_formed(doc):
    try:
        from lxml import etree
    except Exception:
        import xml.etree.ElementTree as etree  # fallback (less strict)
    bad = []
    for label, html in html_fragments(doc):
        if not html:
            continue
        try:
            root = etree.fromstring("<root>" + html + "</root>")
        except Exception as exc:
            bad.append(f"{label}: malformed html ({str(exc)[:50]})")
            continue
        # balanced tags are not enough: "<p><p>x</p></p>" parses as XML but is
        # invalid html (a browser closes the outer <p> and re-parents), and a
        # stray <li> outside a list renders unnumbered.  Both come from a
        # renderer wrapping a fragment that already carried its own block tag.
        if any(p.find(".//p") is not None for p in root.iter("p")):
            bad.append(f"{label}: nested <p> inside <p>")
        for parent in root.iter():
            if parent.tag in ("ol", "ul"):
                continue
            if any(child.tag == "li" for child in parent):
                bad.append(f"{label}: <li> outside a list (in <{parent.tag}>)")
                break
    return bad


def inv_strong_balanced(doc):
    bad = []
    for label, html in html_fragments(doc):
        if html.count("<strong>") != html.count("</strong>"):
            bad.append(f"{label}: unbalanced <strong>")
    return bad


def inv_no_heading_word_duplication(doc):
    """A section body must not restart with the last word of its heading.

    Exception: an ALL-CAPS acronym that ends the heading and legitimately opens
    the operative sentence as its grammatical subject -- e.g. section 233AA
    "Collection of tax by NCCPL.— NCCPL shall collect ..." (pre-2024 editions,
    before the operative text was substituted).  That is faithful legal text,
    not a heading-into-body mis-split, so a fully-uppercase leading word is not
    treated as a duplication.
    """
    bad = []
    for leaf in iter_section_leaves(doc):
        html = leaf.get("html", "")
        if "</h4>" not in html:
            continue
        m = re.search(r"([A-Za-z]{4,})\.—</h4>", html)
        if not m or m.group(1).isupper():
            continue
        body = re.sub(r"<[^>]+>", "", html.split("</h4>", 1)[1]).strip()
        fw = re.match(r"([A-Za-z]+)", body)
        if fw and fw.group(1) == m.group(1):
            bad.append(f"section {leaf.get('code')}: heading word '{m.group(1)}' duplicated at body start")
    return bad


def inv_schedules_have_content(doc):
    """Every schedule must contain at least one content leaf (not an empty shell)."""
    bad = []
    for sc in doc.get("schedules", []):
        leaves = [lf for lf in iter_schedule_leaves({"schedules": [sc]}) if lf.get("html")]
        if not leaves:
            bad.append(f"schedule {sc.get('code')}: no content leaves (empty shell)")
    return bad


# A structural heading (CHAPTER/PART/Division) belongs to the TOC tree, never
# inside a leaf's body.  An inserted part wears an amendment marker on its
# heading ("1[PART VA") which defeated exact-line matching and leaked the
# heading (plus its title line) into the previous section (98/180/230, and
# "Division IIIAA"'s two-letter suffix in the First Schedule).  Only LEADING
# decoration is stripped before matching: a line with a trailing "]" alone is
# a wrapped table cell ("... of Chapter X or\nChapter XII]" in section 182's
# penalty table) and is legitimate body content.
_STRUCT_LINE = re.compile(
    r"^(CHAPTER\s+[IVXLC0-9]+|PART\s+[IVXLC0-9]+[A-Z]{0,2}|"
    r"DIVISION\s+[IVXLC0-9]+[A-Z]{0,2})$", re.IGNORECASE)


_STRUCT_DECOR = re.compile(r"^(?:[\d*]{1,3}\s*|\[+\s*)+")


# A repealed Part/Division heading QUOTED below an amendment note is legitimate
# history, not a boundary.  Schedule pages print the whole substituted/omitted
# block (its own PART/Division headings included) below such a note; once a
# leaf's body reaches it the remaining lines are quoted.  The cue is either the
# classic "... read as follows:" or a footnote-citation amendment note -- the
# pre-2021 editions introduce a quoted repealed block with one (e.g. the Seventh
# Schedule's "A Earlier inserted by the Finance Act, 2003." above its quoted
# "PART III"), so those markers open quote territory too.  Broadening the cue
# can only skip MORE lines, never fewer, so it cannot turn a passing edition red.
_QUOTE_CUE = re.compile(
    r"read as follows"
    r"|\b(?:inserted|substituted|added|omitted|re-?numbered|re-?lettered|deleted)"
    r"\b.{0,60}?\bby\s+(?:the\s+)?(?:Finance|President|Ordinance|Act\b)",
    re.IGNORECASE)


def _table_cell_lines(html: str) -> set:
    """Every physical line of text that sits inside a table CELL.

    ``plain_text`` is flat, so a narrow cell's wrapped content becomes ordinary
    lines and a cross-reference can land on a line of its own.  The Sales Tax
    Eleventh Schedule prints "any kind of gypsum under chapter 25 (PCT headings
    2520.1010, ...)" in a ~12-character column, so "chapter 25" -- a CUSTOMS
    TARIFF chapter, not a structural boundary -- wraps onto its own line.  The
    html still knows it is cell content, which is the only reliable signal.
    """
    import html as _h
    out = set()
    for cell in _CELL_TEXT.findall(html or ""):
        for ln in _h.unescape(cell).split("\n"):
            if ln.strip():
                out.add(ln.strip())
    return out


def _is_amendment_instrument(doc) -> bool:
    """Whether this document is an amending instrument, by the same measured
    classifier the parser uses (``discover.amending_density``, threshold 2.0).

    Computed from the emitted leaf text rather than the page model, which is all
    an invariant is handed.  Amendment instruments score 4.05 (Income Tax 3rd
    Amdt 2016) to 34.49; the consolidated families score 0.09-0.11.
    """
    from legal_ingest.discover import _AMENDING_RE, AMENDING_DENSITY_MIN
    # The CLAUSE side only.  A Finance Act's amending language lives in its
    # clauses; its schedules are tariff data and carry none, so including them
    # measures how big the tariff annex is rather than what the instrument does.
    # Finance Act, 2022 scores **1.50 over everything and 26.38 over its clauses**
    # -- 1.26 MB of schedule against 120 KB of clause -- and at 1.50 it fell below
    # the threshold, so none of the amendment-instrument scoping reached it while
    # the PARSER's own classifier (``discover.amending_density``, which sees only
    # ``body_refs``) had already classified it as one.  The two must not disagree.
    # Measured on the clause side: amendment instruments 22.01-30.57, the
    # consolidated families 0.05-0.11, Pakistan Single Window 0.00.
    parts = [(leaf.get("plain_text") or "") for leaf in iter_section_leaves(doc)]
    parts.append(((doc.get("preamble") or {}).get("plain_text")) or "")
    text = "\n".join(parts)
    if not text:
        return False
    return 10000.0 * len(_AMENDING_RE.findall(text)) / len(text) >= AMENDING_DENSITY_MIN


def inv_no_structural_heading_in_body(doc):
    """No leaf body line may be a (possibly marker-decorated) structural
    heading -- those lines are boundaries and live in the tree, not in text.

    Exception: a structural heading QUOTED inside a "... read as follows:"
    amendment note is repealed history, not a live boundary, so lines after
    that cue in the same leaf are skipped.  This is safe because a genuine
    active heading always starts a NEW leaf and so can never appear after the
    cue within one leaf's body.

    Exception: a line that is TABLE CELL content (see ``_table_cell_lines``) is
    never a boundary -- a boundary line ends the table.

    Exception: a CHAPTER whose keyword is not ALL-CAPS is a Pakistan Customs
    Tariff chapter cited in a rate table, not a boundary -- "any kind of gypsum
    under\\nchapter 25\\n(PCT headings 2520.1010, ...)" wraps inside a
    twelve-character column, so the cross-reference lands on a line of its own.
    Measured over all 46 converted editions there are exactly 11 non-all-caps
    hits and every one is a tariff reference (``chapter 25``, ``chapter 78``,
    ``Chapter 84``), while every genuine chapter boundary prints ``CHAPTER``.
    PART and Division stay case-blind: the Twelfth Schedule really does print
    "Part III" in title case.

    Exception: an AMENDMENT INSTRUMENT reproduces the structure of the instrument
    it amends.  Finance Act 2013 quotes Divisions XII-XVII of the Income Tax
    Ordinance's First Schedule inside its clauses, Finance Act 2019 quotes the
    Stamp Act's ``CHAPTER I``, and Income Tax (3rd Amdt) 2016 quotes ``PART I`` of
    the Schedule it inserts -- all live text of the amending Act, none of them a
    boundary of it.  ``_QUOTE_CUE`` cannot see them because the quotation opens
    pages earlier (the same reason P06's opening-quote test does not transfer).
    Scoped by the measured classifier (``discover.amending_density`` over the
    document's own text, threshold 2.0; amendment instruments score 4.05-34.49,
    consolidated Acts 0.09-0.11), and recorded as ``deliberate`` in the ledger:
    the residual risk is that a Finance Act's own swallowed boundary goes
    unreported here, which conservation and ``structure_counts`` still cover.
    """
    bad = []
    if _is_amendment_instrument(doc):
        return []
    for leaf in iter_all_leaves(doc):
        in_quote = False
        cell_lines = _table_cell_lines(leaf.get("html") or "")
        for ln in (leaf.get("plain_text") or "").split("\n"):
            if ln.strip() in cell_lines:
                continue
            kw = _STRUCT_DECOR.sub("", ln.strip()).split(" ")[0]
            if kw.upper() == "CHAPTER" and kw != "CHAPTER":
                continue
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


def inv_no_footnote_text_in_body(doc):
    """A footnote's tell-tale intro ('Table substituted by the Finance Act', 'read
    as follows') must never appear in a section/division BODY -- it belongs below
    the footnote separator.  Guards the substituted-table-spilling-into-body bug.

    TRACKED KNOWN GAP (deferred fix): the 11.03.2019 edition prints Division XXI's
    (Advance Tax on Banking Transactions, s.236P -- since omitted) substituted
    rate table as a deeply-nested footnote-quoted block that renders inside the
    division body.  Content is fully conserved (99.997% body / 100% footnotes) --
    this is a placement issue whose fix needs fn-table zoning surgery
    (_extract_body_tables / footnotes.py), too risky to attempt for one
    since-omitted division without regressing the eleven green editions.  Only
    this ONE (edition, leaf) pair is exempted; the guard stays fully live for
    every other leaf and every other edition.  Remove the entry once the zoning
    fix lands.
    """
    bad = []
    markers = ("Table substituted by the Finance Act",)
    filename = (doc.get("metadata") or {}).get("filename", "")
    known_gaps = (("11th March, 2019", "Division XXI"),)  # see docstring
    for leaf in iter_all_leaves(doc):
        if any(ed in filename and str(leaf.get("code")) == code
               for ed, code in known_gaps):
            continue
        body = leaf.get("plain_text", "")
        for mk in markers:
            if mk in body:
                bad.append(f"section {leaf.get('code')}: footnote text in body ({mk!r})")
                break
    return bad


_ANON_INSERTION = re.compile(r"^\s*(?:Inserted|Added)\s+by\b", re.IGNORECASE)


_NAMES_ELEMENT = re.compile(
    r"\b(?:sections?|sub-?sections?|clauses?|paras?|paragraphs?|divisions?|"
    r"parts?|provisos?|explanations?|schedules?|tables?)\b", re.IGNORECASE)


_SECTION_OMISSION = re.compile(
    r"^\s*Section\b[^0-9A-Za-z]{0,10}\S+.{0,40}?\b(?:omitted|substituted|"
    r"repealed)\b", re.IGNORECASE | re.DOTALL)


def _cited_on_empty_bracket(html: str, ref: str) -> bool:
    """True when the ref's <sup> citation sits on an EMPTY amendment bracket
    paragraph ("1[ ]") -- i.e. the note describes removed text.  A citation
    inside a real-text paragraph anchors an insertion the leaf still contains
    (e.g. 51's added sub-section "5[(2) Where ...]") and belongs there."""
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", html or "", re.S):
        frag = m.group(1)
        if f">{ref}</sup>" not in frag:
            continue
        rest = re.sub(r"<sup class=\"cite\"[^>]*>[^<]*</sup>", "", frag)
        rest = re.sub(r"<[^>]+>", "", rest)
        if re.fullmatch(r"[\[\]\s]*", rest):
            return True
    return False


def inv_insertion_note_paired_with_omission(doc):
    """An anonymous 'Inserted by ...' footnote anchored on an EMPTY amendment
    bracket, whose successor ref (same page, marker + 1) is a 'Section X
    omitted/substituted' note, must be attached to the same leaf as that
    successor -- both notes describe section X's history."""
    leaves = list(iter_all_leaves(doc))
    owners: dict = {}
    text_by_ref: dict = {}
    for i, lf in enumerate(leaves):
        for fn in lf.get("footnotes", []):
            r = str(fn.get("ref", ""))
            owners.setdefault(r, set()).add(i)
            text_by_ref.setdefault(r, fn.get("text") or "")
    bad = []
    for i, lf in enumerate(leaves):
        for fn in lf.get("footnotes", []):
            t = fn.get("text") or ""
            if not _ANON_INSERTION.match(t) or _NAMES_ELEMENT.search(t):
                continue
            m = re.match(r"^(\d+)\.(\d+)$", str(fn.get("ref", "")))
            if not m:
                continue
            nxt = f"{m.group(1)}.{int(m.group(2)) + 1}"
            if not _SECTION_OMISSION.match(text_by_ref.get(nxt, "")):
                continue
            if not _cited_on_empty_bracket(lf.get("html") or "", str(fn.get("ref"))):
                continue
            if i not in owners.get(nxt, set()):
                where = [leaves[j].get("code") for j in sorted(owners.get(nxt, set()))]
                bad.append(f"section {lf.get('code')}: insertion note "
                           f"{fn.get('ref')} split from its omission note "
                           f"{nxt} (attached to {where})")
    return bad


# A quoted table's numbering row can WRAP ("(1) (2)" with "(3)" on the next
# physical line -- footnote 494.2's company-rate table).  Mis-parsed, the grid
# breaks BEFORE its data row and the row's cells ("50% 35% 45%") fall out of
# the flex table as a bare paragraph -- legally binding rates rendered as
# stray text.  A <p> of pure rate tokens directly after an fn-table close is
# that exact signature; prose legitimately following a table always starts
# with words ("Provided that ...").
_RATE_TOKEN = re.compile(r"^[\d.,]+%[\]”;.)]*$")


# A formula legend ("where A is the amount of the gain determined under
# sub-section (2).") sits BELOW its rate table.  Absorbed as a row wrap, it
# fuses into the last row's cell and the row reads "...exceeds eight years
# where A is the amount..." -- legally wrong row text (footnotes 89.1-89.3).
# Lowercase "where" + single-capital variable is the legend signature; row
# descriptions start with capital "Where".
_LEGEND_IN_CELL = re.compile(r"\bwhere\s+[A-Z]\s+is\s+the\b")


_ANY_CELL = re.compile(r'box-sizing:border-box;">([^<]*)</div>')


def inv_no_formula_legend_inside_cell(doc):
    """No table cell (footnote fn-table or body table) may contain a fused
    formula legend -- the legend belongs below the table as its own line."""
    bad = []
    for leaf in iter_all_leaves(doc):
        sources = [("leaf", leaf.get("html") or "")]
        sources += [(f"footnote {fn.get('ref')}", fn.get("html") or "")
                    for fn in leaf.get("footnotes", [])]
        for label, html in sources:
            for cell in _ANY_CELL.findall(html):
                if _LEGEND_IN_CELL.search(cell):
                    bad.append(f"section {leaf.get('code')} {label}: formula "
                               f"legend fused into a table cell: {cell[:70]!r}")
    return bad


# a formula span, then whatever follows it in the same block
_AFTER_FORMULA = re.compile(r'<span class="formula".*?</span>\s*(.{0,90})', re.S)


# how a legend line opens: "where —" / "Where," / "A is ..." / "B means ..."
_LEGEND_OPEN = re.compile(r'^(?:<strong>)?[Ww]here\b|^(?:<strong>)?[A-Z](?:</strong>)?\s+(?:is|means)\b')


def inv_no_inline_formula_legend(doc):
    """A formula's legend must open its own block, never run on inline.

    The PDF sets "where —" and each "A is ..." line under the centred formula;
    gluing them back into the sentence that introduced the formula loses that
    structure (and reads as one run-on paragraph).  Keyed on a rendered formula
    span so a legend the print genuinely sets inline is not flagged.
    """
    bad = []
    for label, html in html_fragments(doc):
        for tail in _AFTER_FORMULA.findall(html):
            if tail.lstrip().startswith('<span class="legend"'):
                continue
            if _LEGEND_OPEN.match(tail.lstrip()):
                bad.append(f"{label}: formula legend inline after the formula "
                           f"span: {tail.strip()[:60]!r}")
    return bad


def inv_no_dropped_table_row_paragraph(doc):
    """No footnote may render a paragraph of pure rate tokens immediately
    after an fn-table -- that is a table row that fell out of the grid."""
    bad = []
    for leaf in iter_all_leaves(doc):
        for fn in leaf.get("footnotes", []):
            html = fn.get("html") or ""
            if "fn-table" not in html:
                continue
            for m in re.finditer(r"</div>\s*<p>([^<]+)</p>", html):
                toks = m.group(1).split()
                if len(toks) >= 2 and all(_RATE_TOKEN.match(t) for t in toks):
                    bad.append(f"footnote {fn.get('ref')}: table row dropped "
                               f"out of the grid: {m.group(1)!r}")
    return bad


_CITE_SUP = re.compile(r'<sup class="cite"[^>]*>([^<]+)</sup>')


_OMISSION_WORDS = re.compile(r"omitted|substituted|read as follows", re.IGNORECASE)


def _leaf_own_history_note(leaf, text: str) -> bool:
    code = str(leaf.get("code") or "")
    if not code or not _OMISSION_WORDS.search(text or ""):
        return False
    return bool(re.search(r"\b" + re.escape(code) + r"\b", text or ""))


def inv_footnote_on_citing_leaf(doc):
    """Every attached footnote must sit on the leaf that cites it (see above)."""
    leaves = list(iter_all_leaves(doc))
    cited = [set(_CITE_SUP.findall(lf.get("html") or "")) for lf in leaves]
    citing = {}
    for i, refs in enumerate(cited):
        for r in refs:
            citing.setdefault(r, []).append(i)
    attached = {}
    for i, lf in enumerate(leaves):
        for fn in lf.get("footnotes", []):
            attached.setdefault((fn.get("ref"), fn.get("text")), []).append(i)

    def label(i):
        return f"{leaves[i].get('code')} ({(leaves[i].get('heading') or '')[:28]})"

    bad = []
    for i, lf in enumerate(leaves):
        own_refs = {fn.get("ref") for fn in lf.get("footnotes", [])}
        for fn in lf.get("footnotes", []):
            ref, text = fn.get("ref"), fn.get("text")
            if ref in cited[i] or _leaf_own_history_note(lf, text):
                continue
            owners = [j for j in citing.get(ref, []) if j != i]
            if owners:
                bad.append(f"footnote {ref} attached to {label(i)} "
                           f"but cited by {label(owners[0])}")
            else:
                dup = [j for j in attached[(ref, text)] if j != i]
                if dup:
                    bad.append(f"uncited footnote {ref} duplicated on "
                               f"{label(i)} and {label(dup[0])}")
        # the converse: a citation rendered in this leaf whose footnote exists
        # in the document must be attached to THIS leaf
        have = {r for (r, _t) in attached}
        for r in cited[i]:
            if r in have and r not in own_refs:
                bad.append(f"{label(i)} cites {r} but the footnote is "
                           f"attached elsewhere only")
    return bad


_CTRL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def inv_no_control_chars(doc):
    """No control characters anywhere in html / plain_text / footnotes.

    Table-cell citations travel through rendering as \\x01...\\x02 sentinels
    (pagemodel.cite_sentinel) that builder._expand_table_cites must expand to
    <sup class="cite"> markup; a leaked sentinel means a render path skipped
    the expansion."""
    bad = []
    for leaf in iter_all_leaves(doc):
        for field in ("html", "plain_text"):
            if _CTRL_CHARS.search(leaf.get(field) or ""):
                bad.append(f"section {leaf.get('code')}: control char in {field}")
        for fn in leaf.get("footnotes", []):
            if _CTRL_CHARS.search(fn.get("text") or "") \
                    or _CTRL_CHARS.search(fn.get("html") or ""):
                bad.append(f"footnote {fn.get('ref')}: control char")
    pre = doc.get("preamble") or {}
    if _CTRL_CHARS.search(pre.get("html", "") + pre.get("plain_text", "")):
        bad.append("preamble: control char")
    return bad


# Text that is provably NOT front matter and so must never end up in the
# preamble.  Two measured shapes, both meaning the body page range was computed
# wrong (see reports/m3-handoff.md H5):
#
#   * a TABLE OF CONTENTS row -- the "Contents" caption, the Federal Excise
#     column header, or a dot-leader run ending in a folio (Sales Tax): the scan
#     started INSIDE the front matter (STA 15.01.2022, FEA 30-06-2020/21);
#   * an OPERATIVE definitions clause -- '(13) "goods" means ...': the scan
#     started PAST section 1, so section 2's definitions became the preamble and
#     the pages before it were never read at all (FEA 30th June 2019 and 31st
#     December 2019 lose 41 body + 42 footnote words this way).
#
# A genuine cover page matches neither: "(As amended up to 1st July 2015)\n(The
# amendments made through Finance Act 2015, have been shown in blue)".
_NOT_A_PREAMBLE = re.compile(
    r"^\s*Contents\s*$"
    r"|^\s*Section\s+Description\s+Page\s*$"
    r"|[.…]{5,}\s*\d{1,4}\s*$"
    r"|^\s*\(\d{1,2}[a-z]?\)\s*[“\"]",
    re.MULTILINE)


def inv_preamble_present(doc):
    r"""The enacting preamble (text before section 1) must be captured.

    Recognised by the enacting formula rather than the literal word ORDINANCE:
    every statute in this corpus opens with a long title ("An Act to consolidate
    and amend the law relating to Customs") followed by a recital ("Whereas it is
    expedient ..."), but only the Income Tax Ordinance calls itself an Ordinance.
    Matching on that one word reported a missing preamble for every Act here,
    while the preamble was in fact captured correctly.

    Not every document HAS one.  All seventeen Federal Excise Act editions open
    directly on ``CHAPTER I / PRELIMINARY / 1. Short title, extent and
    commencement`` -- verified by scanning the first eight pages of each: not one
    prints "An Act to", "WHEREAS" or "It is hereby enacted" (ledger F01).  So an
    absent preamble is only a defect if the pipeline SWALLOWED it, which shows up
    as the recital appearing inside the first section's body instead.  That is
    what is checked when there is no preamble node -- asserting mere presence
    would demand the pipeline fabricate text the PDF does not print.
    """
    pre = (doc.get("preamble") or {}).get("plain_text", "")
    if not pre.strip():
        first = next(iter_all_leaves(doc), None)
        body = ((first or {}).get("plain_text") or "").upper()
        if "WHEREAS" in body or "IT IS HEREBY ENACTED" in body:
            return [f"preamble swallowed into section {(first or {}).get('code')}"]
        return []
    up = pre.upper()
    enacting = any(w in up for w in ("ACT", "ORDINANCE"))
    recital = "WHEREAS" in up or "IT IS HEREBY ENACTED" in up
    if enacting and recital:
        return []
    # No recital, so this is not an enacting preamble -- it is the COVER PAGE.
    # The three TOC-less Federal Excise editions (July 01 2014, 30th June 2015,
    # 1st July 2016) print no contents at all, so their cover ("(As amended up to
    # 1st July 2015)\n(The amendments made through Finance Act 2015, have been
    # shown in blue).\nThe Federal Excise\nAct, 1990") is genuinely the only text
    # before section 1 and lands here.  That is printed front matter, correctly
    # conserved; demanding a recital of it would demand the pipeline invent one.
    # What must NEVER land here is the CONTENTS or operative section text -- both
    # mean the body scan began inside the front matter or past section 1
    # (m3-handoff.md H5), so those two shapes stay red.
    if _NOT_A_PREAMBLE.search(pre):
        return [f"not front matter -- body page range is wrong "
                f"(m3-handoff H5): {pre[:90]!r}"]
    return []


_TABLE_BLOCK = re.compile(r'<table class="fbr-table">.*?</table>', re.S)


_TR_BLOCK = re.compile(r"<tr>(.*?)</tr>", re.S)


_CELL_TEXT = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)


_NUM_ONLY = re.compile(r"^\(\d+\)$")


def inv_numbering_row_in_thead(doc):
    """A table's ``(1) (2) ...`` column-numbering row must sit inside <thead>.

    The QA screenshots of 2026-07-08 (First Schedule Division II super-tax
    table) showed the numbering row and the year sub-header rows rendered as
    DATA rows because thead was cut at the first physical row -- i.e. the table
    had NO numbering row in its thead at all.  That is what this checks.

    A table whose thead already carries the numbering row may still show one in
    the tbody, and legitimately: a table spanning several PDF pages has its
    header BOX reprinted at the top of every continuation page (Sales Tax s.33's
    penalty table reprints "Offences | Penalties | Section of the Act" plus
    "(1) (2) (3)" on each of its twelve pages; the Sixth Schedule's Table-1 does
    it 34 times over ~70 pages).  Those reprints are printed legal text sitting
    exactly where the page break falls -- dropping them would lose ~135 body
    words in s.33 alone and breach the conservation gate -- so they are kept as
    rows.  Rendering them as ``<th>`` cells inside the tbody would be nicer
    markup and is recorded in reports/m3-handoff.md; it is a markup nicety, not
    a content defect, so it is not gated here.
    """
    bad = []
    for leaf in iter_all_leaves(doc):
        for table in _TABLE_BLOCK.findall(leaf.get("html") or ""):
            head, sep, tbody = table.partition("</thead>")
            if not sep:
                continue                  # no thead -> nothing was cut

            def _numbering_rows(chunk):
                for tr in _TR_BLOCK.findall(chunk):
                    cells = [c.strip() for c in _CELL_TEXT.findall(tr)]
                    nonempty = [c for c in cells if c]
                    if len(nonempty) >= 2 and all(_NUM_ONLY.match(c)
                                                  for c in nonempty):
                        yield nonempty

            if next(_numbering_rows(head), None) is not None:
                continue                  # thead carries it -> not the defect
            for nonempty in _numbering_rows(tbody):
                bad.append(f"section {leaf.get('code')}: numbering row "
                           f"{nonempty} rendered in tbody, with none in thead")
    return bad


# a bare row-serial label -- roman ("I", "II."), arabic ("1", "12.") or a
# bracketed clause serial ("(a)", "(i)").  A "(1)"-style numbering-row token is
# deliberately NOT matched (it legitimately sits in <thead>).
_SERIAL_TH = re.compile(r"^(?:[IVXLCivxlc]+|\d{1,3})\.?$|^\([a-z]{1,3}\)$")


def inv_no_serial_first_row_in_thead(doc):
    """A serial-led row (roman/arabic/'(a)') is DATA and must never sit in
    <thead> (which renders it bold).

    A header-less table whose first row opens with a serial label must render
    with no thead (all <tbody>).  The Third Schedule PART I depreciation table
    (I./II./III. ...) regressed this way -- its first data row was promoted to
    a bold <th> header (QA screenshot img 69, 2026-07-21).  Tables with a real
    header row or a '(1)(2)' numbering row keep their thead untouched."""
    bad = []
    for leaf in iter_all_leaves(doc):
        for table in _TABLE_BLOCK.findall(leaf.get("html") or ""):
            head, sep, _ = table.partition("</thead>")
            if not sep:                       # no thead -> nothing to check
                continue
            trs = _TR_BLOCK.findall(head)
            if not trs:
                continue
            cells = [c.strip() for c in _CELL_TEXT.findall(trs[0]) if c.strip()]
            if len(cells) >= 2 and _SERIAL_TH.match(cells[0]):
                bad.append(f"section {leaf.get('code')}: serial-led row "
                           f"{cells} rendered in thead (should be tbody data)")
    return bad


# a swallowed TOC row inside a heading: a structural code immediately followed
# by a printed page number ("Division I 533", "PART IV 543")
_TOC_ROW_IN_HEADING = re.compile(
    r"\b(?:CHAPTER|PART|Division)[\s\-]+[IVXLC0-9]+[A-Z]{0,2}\s+\d{1,4}\b",
    re.IGNORECASE)


def inv_no_toc_row_in_heading(doc):
    """No heading anywhere in the tree may contain a swallowed TOC row.

    The TOC parser classifies each line; a row it fails to classify falls
    through to heading-continuation and gets glued into the enclosing node's
    heading.  That is how First Schedule Part IV's heading once absorbed its
    entire division listing ("... ADVANCE TAX Division I 533 Omitted by the
    Finance Act, 2002 Division II 533 Brokerage and Commission ...") because
    'Division I 533' carried its page number inline.  The code+page pair is
    the signature: legitimate headings never contain one.
    """
    bad = []

    def walk(node, trail):
        if not isinstance(node, dict):
            return
        here = trail + [str(node.get("code") or "?")]
        m = _TOC_ROW_IN_HEADING.search(node.get("heading") or "")
        if m:
            bad.append(f"{'/'.join(here)}: heading contains TOC row {m.group(0)!r}")
        for key in ("chapters", "schedules", "parts", "divisions", "sections"):
            for child in node.get(key) or []:
                walk(child, here)

    walk(doc, [])
    return bad


_SCHED_ORD_WORDS = ("FIRST SECOND THIRD FOURTH FIFTH SIXTH SEVENTH EIGHTH NINTH "
                    "TENTH ELEVENTH TWELFTH THIRTEENTH FOURTEENTH FIFTEENTH "
                    "SIXTEENTH SEVENTEENTH").split()


_SCHED_ORD_RE = re.compile(r"\b(%s)\s+SCHEDULE" % "|".join(_SCHED_ORD_WORDS),
                           re.IGNORECASE)


def _schedule_ordinal(code):
    """1-based ordinal of a schedule title code ("THE ELEVENTH SCHEDULE" -> 11)."""
    m = _SCHED_ORD_RE.search(code or "")
    return _SCHED_ORD_WORDS.index(m.group(1).upper()) + 1 if m else None


_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


_CHAPTER_NUM_RE = re.compile(r"^CHAPTER\s+([IVXLC]+)(?:[\s\-]*([A-Z]{1,3}))?$",
                             re.IGNORECASE)


def inv_no_orphan_sections(doc):
    """Section conservation: every TOC-promised section reaches the tree.

    ``metadata.sections_count`` counts the parsed TOC section rows; a chapter
    tree with fewer leaves means sections were silently dropped (the exact
    failure that lost CHAPTER I / sections 1-3 of the 30.06.2024 edition when
    the TOC's merged column header defeated chapter detection).
    """
    md = doc.get("metadata", {})
    expected = md.get("sections_count", 0)
    n_leaves = sum(1 for _ in iter_section_leaves(doc))
    if n_leaves != expected:
        return [f"chapter-side section leaves {n_leaves} != "
                f"metadata sections_count {expected}"]
    return []


# ---------------------------------------------------------------------------
# section body attribution
#
# A section listed in the TOC is bound to its body text by
# ``builder.build_sections``, which indexes body lines by the code they open
# with.  When that binding misses, the section is emitted as a heading-only
# stub and its statutory text stays with the PREVIOUS section -- the words are
# still in the document, so the conservation audit reports 100.000% and every
# other invariant passes.  Customs 2007 shipped 15 sections that way (s.14A's
# text inside s.14), and Federal Excise 2005 shipped s.38's alternative-dispute-
# resolution provision -- 3,500-4,500 characters -- inside s.37 across five
# editions.  These two invariants are the only checks that can see it.
#
# ``tools/`` stays stdlib-only (see the module docstring), so the code grammar
# is re-stated here rather than imported from ``packages/legal_ingest``.  Both
# helpers mirror ``grammar.norm_code`` and ``grammar.code_sort_key`` exactly;
# if those change, these must follow.

def _fold_code(code) -> str:
    """``14.A`` / ``14 A`` / ``221-A`` / ``38-`` -> ``14A`` / ``221A`` / ``38``.

    Mirrors ``grammar.norm_code``: the body and the TOC print the same section
    both ways across editions, so the separated and the fused spellings are ONE
    code.
    """
    return re.sub(r"[\s.\-]", "", str(code or "")).upper()


_CODE_PARTS = re.compile(r"^(\d{1,4})([A-Z]{0,4})$")


def _code_key(code):
    """Statutory order for a folded code: ``4 < 4A < 4AB < 4B < 5``, or None.

    Mirrors ``grammar.code_sort_key``.  None means "not a code", which the
    callers treat as "cannot compare" rather than as a position.
    """
    m = _CODE_PARTS.match(_fold_code(code))
    return (int(m.group(1)), m.group(2)) if m else None


#: A section whose body is legitimately empty.  A repealed section prints its
#: omission bracket and nothing else, so a heading-only leaf is CORRECT there --
#: it is the one case these two invariants must not report.  ``***`` is how
#: Federal Excise prints an omitted section (s.19A, ``2[19A. ***]``).
#:
#: The prefix must tolerate the code's own DOT and letter suffix, because the
#: body prints the whole decorated start before the verb: Customs s.20 is
#: ``15[20. 112[Omitted]`` and Sales Tax s.45 is ``1 45. Omitted.``.  Without the
#: dot in the class, 16 correctly-empty repealed sections across the acts lane
#: were reported as having lost their text -- the leaf's HEADING is the TOC's
#: pre-repeal title ("Board's power to grant exemption from duty in exceptional
#: circumstances"), which is what makes them look like live sections.
#: ``_CODE_DECOR`` is the printed decoration a code can carry before the verb:
#: whitespace, amendment brackets, marker digits, asterisks, and the code's own
#: dot or hyphen separator.  A single suffix LETTER is allowed once, for the
#: ``195-A`` / ``83. A`` spellings.
_CODE_DECOR = r"[\s\[\]\d*.\-]*(?:[A-Z][\s\[\]\d*.\-]*)?"
_LEGITIMATELY_EMPTY = re.compile(
    rf"^{_CODE_DECOR}(?:omitted|repealed|\*\*\*)", re.IGNORECASE)


def _is_omission(leaf) -> bool:
    return bool(_LEGITIMATELY_EMPTY.match(leaf.get("heading") or "")
                or _LEGITIMATELY_EMPTY.match(leaf.get("plain_text") or ""))


def _body_beyond_heading(leaf) -> str:
    """What a leaf's ``plain_text`` carries beyond its own code and heading.

    The stub form is exactly ``"<code>. <heading>"`` (the TOC fallback at
    ``builder._build_one``), so removing that prefix leaves nothing.  Compared
    on collapsed whitespace because the heading may have been re-wrapped.
    """
    body = re.sub(r"\s+", " ", (leaf.get("plain_text") or "")).strip()
    head = re.sub(r"\s+", " ",
                  f"{leaf.get('code')}. {leaf.get('heading') or ''}").strip()
    if body.startswith(head):
        return body[len(head):].strip(" .,;:-—–")
    # heading re-wrapped or re-cased: fall back to a length comparison, which is
    # what the census used
    return "" if len(body) <= len(head) + 3 else body


def inv_section_carries_its_body(doc):
    """A section leaf must carry operative text beyond its own heading.

    The schedule side has had ``schedules_have_content`` since the beginning;
    the section side never had an equivalent, which is why the binding failures
    above went unreported through 45 invariants and a 100%-conserving audit.

    Exempt: a repealed/omitted section, where an empty body is the correct
    output (``_is_omission``).  Nothing else is exempt -- a section the source
    genuinely prints without a code (Customs 2007 s.204, whose heading line
    carries no ``204.`` at all) is a source defect that still loses text to its
    neighbour, so it must be reported and carried as a ledger exemption rather
    than silently tolerated here.
    """
    bad = []
    for leaf in iter_section_leaves(doc):
        if _is_omission(leaf):
            continue
        if _body_beyond_heading(leaf):
            continue
        bad.append(f"section {leaf.get('code')}: heading-only leaf, no body "
                   f"text beyond {(leaf.get('heading') or '')[:60]!r} -- its "
                   f"text is probably inside the preceding section")
    return bad


#: A body line opening with a section code, read PERMISSIVELY -- this is a
#: detector, so it must see the shapes the parser's own patterns miss (the
#: ``5[(14-A.`` insertion pair, the ``&`` marker separator, the ``18.A`` dot
#: suffix, the bare ``38-``).  False positives are filtered by the checks in
#: ``inv_no_foreign_section_start_in_body``, not by this pattern.
_ANY_SECTION_START = re.compile(
    r"^\s*(?:[\d*]{1,4}[a-z]?(?:\s*[,&]\s*[\d*]{1,4}[a-z]?)*"
    r"(?:\s+|(?=[\[\(])))?[\[\(]{0,3}\s*(\d{1,4}\s*[-.]?\s*[A-Z]{0,4})\s*[.\s]")


def _demo_section_attribution() -> None:
    """Self-check for the two attribution invariants' helpers.

    The suite has no ``_demo`` convention of its own (``tools/tests`` covers it),
    but these two predicates decide whether a leaf is reported as having lost its
    text, so the shapes they must separate are pinned here and exercised by
    ``tools/tests/test_suite_invariants.py``.
    """
    stub = {"code": "14A", "heading": "Provision of accommodation at customs ports, etc",
            "plain_text": "14A. Provision of accommodation at customs ports, etc"}
    assert not _body_beyond_heading(stub)
    # the same leaf once bound: plain_text opens with the BODY heading form
    # ("5[(14-A. ...") which is not the cleaned heading, so the prefix test fails
    # and the length fallback must still see a real body
    bound = dict(stub, plain_text=(
        "5[(14-A. Provision of accommodation at Customs-ports, etc.- Any agency "
        "or person\nmanaging or owning a customs-port shall provide accommodation."))
    assert _body_beyond_heading(bound)
    # a genuinely SHORT body is a body
    assert _body_beyond_heading({"code": "196J", "heading": "Definitions",
                                 "plain_text": "196J. Definitions.- In this Chapter;"})
    # A heading-only leaf whose body is correctly empty.  The BODY carries the
    # verb; the leaf's HEADING is the TOC's PRE-REPEAL title, which is exactly
    # what makes a repealed section look like a live one that lost its text.
    for body in ("2[19A. ***]",                # Federal Excise omission form
                 "15[20. 112[Omitted]",        # Customs: marker, code, dot, marker
                 "33[195-A. Omitted].",        # hyphenated suffix
                 "4[83. A Omitted]",           # dot-and-space suffix
                 "1 45. Omitted.",             # bare marker, no bracket
                 "295 [11. ***]",
                 "18[179-A. OMITTED"):
        assert _is_omission({"heading": "Board's power to grant exemption",
                             "plain_text": body}), body
    assert _is_omission({"heading": "*** ]omitted", "plain_text": "x"})
    # ...and a LIVE section is never mistaken for a repealed one
    for body in ("196J. Definitions.- In this Chapter;",
                 "14A. Provision of accommodation at customs ports, etc",
                 "40C. Monitoring of Tracking by Electronic or other means",
                 "202B. Reward to Customs Officers and Officials"):
        assert not _is_omission({"heading": "Definitions", "plain_text": body}), body
    # folding must agree with grammar.norm_code, and must not merge real sections
    assert _fold_code("155-I") == _fold_code("155 I") == _fold_code("155.I") == "155I"
    assert _fold_code("38-") == "38"
    assert _fold_code("221") != _fold_code("221-A")
    assert _code_key("4A") < _code_key("4AB") < _code_key("4B") < _code_key("5")


def inv_no_foreign_section_start_in_body(doc):
    """No leaf may contain the START of another section in its body.

    The companion to ``section_carries_its_body``: that one names the starved
    section, this one names the leaf that ate it, and the pair is what makes a
    misattribution diagnosable rather than merely visible.  Reported only where
    all of the following hold, so an ordinary cross-reference cannot trip it:

      * the line is not the leaf's own first line (that is its own heading);
      * the code folds to a DIFFERENT code that really exists as a leaf in this
        document -- a reference to a section of another Act cannot match;
      * that code sorts AFTER this leaf's own code, because a section's body can
        only ever swallow the sections that follow it;
      * the victim leaf carries no body of its own, which is the signature of
        the binding failure (a cross-reference leaves the target intact);
      * the line is not table-cell content and does not sit after a quotation
        cue -- the same two exclusions ``no_structural_heading_in_body`` uses,
        for the same reasons (a narrow rate column wraps, and a repealed section
        quoted under "read as follows:" is history, not a boundary).
    """
    bad = []
    leaves = list(iter_section_leaves(doc))
    by_code = {}
    for leaf in leaves:
        by_code.setdefault(_fold_code(leaf.get("code")), leaf)
    for leaf in leaves:
        own = _code_key(leaf.get("code"))
        if own is None:
            continue
        cells = _table_cell_lines(leaf.get("html") or "")
        in_quote = False
        for ln in (leaf.get("plain_text") or "").split("\n")[1:]:
            t = ln.strip()
            if not t or t in cells:
                continue
            if not in_quote and _QUOTE_CUE.search(ln):
                in_quote = True
            if in_quote:
                continue
            m = _ANY_SECTION_START.match(t)
            if not m:
                continue
            other = _fold_code(m.group(1))
            key = _code_key(other)
            if key is None or key <= own or other not in by_code:
                continue
            victim = by_code[other]
            if _body_beyond_heading(victim):
                continue          # the target kept its own text: a reference
            bad.append(f"section {leaf.get('code')}: body contains the start of "
                       f"section {victim.get('code')}, which is itself "
                       f"heading-only: {t[:78]!r}")
            break
    return bad


# a body subsection/clause marker must never be bold.  A section heading is
# Arial-BoldMT and its terminator dash can glue to a fused first marker
# ("commencement.—(1)"), which used to inherit the bold and render
# <li><strong>(1)</strong> while (2)/(3) stayed plain.  In the PDF the markers
# are regular ArialMT (verified s.1, 106A + 48 more).  Genuinely-bold PARAGRAPH
# markers live in SCHEDULE leaves (a separate real-font path), so scan chapter
# sections only.
_BOLD_BODY_MARKER = re.compile(
    r"<li>(?:<sup[^>]*>[^<]*</sup>)?\[*\s*<strong>\((?:\d+[A-Za-z]{0,2}|[a-z]{1,3})\)")


def inv_no_bold_body_subsection_marker(doc):
    """A subsection marker must not inherit the HEADING's bold.

    Scoped to the first list item, which is the only marker the pipeline can
    fabricate bold for: the Customs Act sets its whole heading line bold and
    opens the body on that same line ("...Customs,.- (1) The Directorate..."), so
    the first marker used to keep <strong> from the heading run.

    Deliberately NOT applied to the rest of the body.  The Ordinance's markers
    are regular ArialMT throughout, so a document-wide rule was right there; the
    Customs Act genuinely prints some mid-body markers in
    TimesNewRomanPS-BoldMT with regular text after them (verified in the source
    for s.54 (c), s.180 (c), s.189 (2), s.2 (aaa)).  Flagging those would be
    asserting that the pipeline should depart from the printed text.
    """
    bad = []
    for leaf in iter_section_leaves(doc):
        html = leaf.get("html") or ""
        first_li = html.find("<li>")
        if first_li == -1:
            continue
        m = _BOLD_BODY_MARKER.search(html[first_li:first_li + 40])
        if m:
            bad.append(f"section {leaf.get('code')}: bold subsection marker "
                       f"{m.group(0)!r} inherited from the heading")
    return bad


def inv_preamble_no_chapter_heading(doc):
    """The enacting preamble must not contain the first chapter's heading.

    "CHAPTER I" / "PRELIMINARY" sit between the recitals and section 1; they
    belong to the chapter node (its code/heading) and must not ALSO be emitted
    as trailing text in ``preamble.html`` (they used to appear twice -- once in
    the preamble body, once as the chapter title).

    Matched as a WHOLE LINE, not as a substring.  A gazette Act's running header
    prints the volume's part label inside an ordinary text line -- Pakistan Single
    Window 2021 carries ``142 THE GAZETTE OF PAKISTAN, EXTRA., APRIL 14,
    2021[PART1`` and ``PART 1] THE GAZETTE ... 143`` in its preamble region,
    while its first container is coded ``PART I`` -- and a substring test calls
    that a duplicated chapter heading.  It is page furniture that both sides of
    the conservation audit count, so removing it would drop conserved words; the
    duplication this guards against is the code standing ALONE on its own line.
    """
    pre = doc.get("preamble") or {}
    plain = pre.get("plain_text", "") or ""
    html = pre.get("html", "") or ""
    chapters = doc.get("chapters") or []
    code = str(chapters[0].get("code", "")).strip() if chapters else ""
    if not code:
        return []
    stripped = re.sub(r"<[^>]+>", "\n", html)
    for text in (plain, stripped):
        for line in text.split("\n"):
            if line.strip() == code:
                return [f"preamble repeats first chapter code {code!r} as its "
                        f"own line"]
    return []


# RC-5: a superscript footnote/amendment marker fused into the preceding word or
# year, e.g. "lottery6[", "Members3[", "20054[" (should read "lottery 6[",
# "Members 3[", "2005 4[").  The amendment marker legitimately stays glued to the
# bracket it opens ("4["), so we only flag the *left* fusion into an alnum char.
_GLUED_MARKER = re.compile(r"[a-z]\d\[|\d{4}\d\[")


# RC-5: a bare amendment marker stranded alone on its own line, directly above the
# "[" it opens ("shall be –\n2\n[Table").  Scoped to a "["-followed line so RC-1
# footnote-leak markers (followed by prose) and fraction denominators are ignored.
_BARE_MARKER_ONLY = re.compile(r"^\s*\d{1,3}\*?\s*$")


def inv_no_glued_marker_digit(doc):
    """RC-5: a superscript marker digit must never fuse into the preceding word
    or year, in plain_text OR html ("2005 4[" not "20054[", "lottery 6[" not
    "lottery6[", "Pakistan 7[" not "Pakistan7[")."""
    bad = []
    for leaf in iter_all_leaves(doc):
        for field in ("plain_text", "html"):
            t = leaf.get(field, "") or ""
            m = _GLUED_MARKER.search(t)
            if m:
                bad.append(f"section {leaf.get('code')} [{field}]: "
                           f"glued marker {t[max(0, m.start() - 6):m.start() + 4]!r}")
                break
    return bad


def inv_no_bare_footnote_marker_line(doc):
    """RC-5: an amendment marker must not be stranded alone on its own plain line
    immediately above the "[" it opens (it should read "2[Table", not a lone "2")."""
    bad = []
    for leaf in iter_all_leaves(doc):
        lines = (leaf.get("plain_text", "") or "").split("\n")
        for i, ln in enumerate(lines):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if _BARE_MARKER_ONLY.match(ln) and nxt.lstrip().startswith("["):
                bad.append(f"section {leaf.get('code')}: bare marker line {ln.strip()!r} above {nxt.lstrip()[:12]!r}")
                break
    return bad


# RC-7: a compound split across a line wrap ("sub-", "section") rejoined with a
# stray space in either representation ("sub- section").  A genuine spaced dash
# (" - ", space BEFORE the hyphen) never matches this.
_STRAY_SPACE_HYPHEN = re.compile(r"[a-z]- [a-z]")


_GLYPH_SPACED = re.compile(r"(?:\b[A-Za-z] ){2,}[A-Za-z][a-z]{0,3}\b")


_SOLID_WORD_RE_INV = re.compile(r"[A-Za-z]{3,}")


def inv_no_glyph_spaced_cell(doc):
    """RC-6d: a real word must not be left glyph-spaced ("i n c o me" for
    "income"), in plain_text or html.  Only flag a run whose space-removed form
    is a FREQUENT solid word of this document -- so a formula ("A x B/C") or a
    glyph-split phrase ("i s not") is never misreported as a glyph-spacing bug."""
    solid = {}
    for leaf in iter_all_leaves(doc):
        for tok in _SOLID_WORD_RE_INV.findall(leaf.get("plain_text", "") or ""):
            k = tok.lower()
            solid[k] = solid.get(k, 0) + 1
    bad = []
    for leaf in iter_all_leaves(doc):
        for field in ("plain_text", "html"):
            for m in _GLYPH_SPACED.finditer(leaf.get(field, "") or ""):
                if solid.get(m.group(0).replace(" ", "").lower(), 0) >= 5:
                    bad.append(f"section {leaf.get('code')} [{field}]: glyph-spaced {m.group(0)!r}")
                    break
            else:
                continue
            break
    return bad


def _division_containers(doc):
    """Yield (label, [division dicts]) for every part/schedule that owns divisions."""
    for sch in doc.get("schedules", []):
        code = sch.get("code", "?")
        if sch.get("divisions"):
            yield (f"{code}", sch["divisions"])
        for part in sch.get("parts", []):
            if part.get("divisions"):
                yield (f"{code}/{part.get('code','?')}", part["divisions"])


def inv_no_duplicate_division_code_within_part(doc):
    """RC-2: within one Part (or Schedule), no division code may appear twice.

    A repeated code is a phantom -- a footnote-quoted or TOC-mis-split heading
    promoted to a spurious heading-only leaf (e.g. a second "Division I ·
    Rates of Tax for Association of Persons", a tripled "Division XXVII").
    Codes legitimately repeat ACROSS parts (each Part has its own Division I),
    which this does not flag.
    """
    bad = []
    for label, divs in _division_containers(doc):
        seen = {}
        for dv in divs:
            c = str(dv.get("code") or "").strip().upper()
            seen[c] = seen.get(c, 0) + 1
        for c, n in seen.items():
            if n > 1:
                bad.append(f"{label}: division code {c!r} appears {n}x (phantom sibling)")
    return bad


_OMITTED_DIV_RE = re.compile(
    r"Division\s+([IVXLC]+(?:\s?[A-Z]{1,2})?)\b[^.]{0,40}?\bomitted\b", re.I)


def _omitted_division_codes(doc):
    """Codes of divisions the document itself declares OMITTED via a footnote
    ("Division VIA ... omitted by the Finance Act, 2021").  Such a division is a
    legitimate heading-only placeholder (its text lives in the footnote), NOT an
    active division with a lost body.  A merely SUBSTITUTED active division
    (Division IIA / Super Tax) is never matched here, so its lost-body bug is
    still caught."""
    codes = set()
    for leaf in iter_all_leaves(doc):
        for fn in leaf.get("footnotes") or []:
            for m in _OMITTED_DIV_RE.finditer(fn.get("text", "") or ""):
                codes.add(re.sub(r"\s+", "", m.group(1)).upper())
    return codes


_BODY_LEAK_MARKER = re.compile(r"^\s*\d{1,3}\*?\s*$")


_BODY_LEAK_NOTE = re.compile(r"\b(?:substituted|inserted|omitted|added|deleted)\b", re.I)


def inv_division_iia_non_empty(doc):
    """RC-3: an ACTIVE First-Schedule Division (heading names a live provision,
    not "Omitted") must carry its body, not be a heading-only placeholder whose
    rate table was swallowed by the previous division.  Guards the Division IIA
    (Rates of Super Tax) class across every edition; omitted divisions (their text
    preserved in a footnote) are legitimate placeholders and are skipped."""
    omitted = _omitted_division_codes(doc)
    bad = []
    for label, divs in _division_containers(doc):
        if "FIRST" not in label.upper():
            continue
        for dv in divs:
            h = (dv.get("heading") or "").strip()
            pt = (dv.get("plain_text") or "").strip()
            if not h or re.search(r"omitted|repealed", h, re.I):
                continue
            code = re.sub(r"(?i)^division\s+", "", str(dv.get("code") or "")).replace(" ", "").upper()
            if code in omitted:
                continue  # the document's own footnote declares this division omitted
            # an active division that is merely its own heading text = placeholder
            if len(pt) <= len(h) + 4:
                bad.append(f"{label} / {dv.get('code')}: active division "
                           f"{h!r} is heading-only ({len(pt)} chars) -- body lost")
    return bad


def inv_schedule_parts_contiguous(doc):
    """RC-3: a schedule's PART codes must be contiguous roman numerals (I, II,
    III, ...).  A gap (PART I + PART III, no PART II) means a mid-page PART
    heading was missed and its rules merged into a neighbour (Ninth Schedule
    PART II, 2020).

    Not applied to an AMENDMENT instrument, for the same reason as the schedule
    ordinals in ``inv_structure_counts``: a Finance Act reproduces only the PARTs
    it amends.  Finance Act 2019 carries the Fifth Schedule's PARTs I, V and VI,
    Finance Act 2022 the Fifth's I, III, IV and V -- printing exactly what it
    changes, not a run with holes in it.  The guard stays fully live for the
    consolidated families, which is where a missing PART really is a lost heading.
    """
    roman = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
             "VIII": 8, "IX": 9, "X": 10}
    bad = []
    if _is_amendment_instrument(doc):
        return []
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
    plain_text OR html ("sub-section", never "sub- section").

    Flagged only when the two halves JOIN INTO A REAL WORD of this document --
    the same guard ``inv_no_glyph_spaced_cell`` uses, and for the same reason.  A
    hyphen at the end of a token is not always a wrap: Finance Act, 2022's Second
    Schedule prints the units glossary ``kV - kilovolt(s) ... m - metre(s) m- -
    meta- m2 - square metre(s)``, where ``m-`` and ``meta-`` are SI and chemical
    PREFIXES that end in a hyphen by definition, and the next entry begins right
    after.  ``metam`` is not a word, so it is not a wrapped compound; ``subsection``
    is, so ``sub- section`` still fails.
    """
    solid = {}
    for leaf in iter_all_leaves(doc):
        for tok in _SOLID_WORD_RE_INV.findall(leaf.get("plain_text", "") or ""):
            k = tok.lower()
            solid[k] = solid.get(k, 0) + 1
    bad = []
    for leaf in iter_all_leaves(doc):
        for field in ("plain_text", "html"):
            t = leaf.get(field) or ""
            for m in _STRAY_SPACE_HYPHEN.finditer(t):
                # the compound as it would read rejoined: the word ending in "-"
                # plus the word starting after the space
                left = re.search(r"([A-Za-z]+)-$", t[:m.start() + 2])
                right = re.match(r"[A-Za-z]+", t[m.end() - 1:])
                if not (left and right):
                    continue
                joined = (left.group(1) + right.group(0)).lower()
                if solid.get(joined, 0) >= 1:
                    bad.append(f"section {leaf.get('code')} [{field}]: "
                               f"stray-space hyphen "
                               f"{t[max(0, m.start() - 6):m.start() + 6]!r}")
                    break
            else:
                continue
            break
    return bad


#: an unresolved marker: real printed text, kept as a superscript, but NOT a
#: citation (see builder._render_words).  Counted as a failure to resolve.
_MARKER_SUP = re.compile(r'<sup class="marker" data-ref="([^"]+)">')


_CITE_REF = re.compile(r'<sup class="cite" title="[^"]*">([^<]+)</sup>')


def inv_citation_refs_resolve(doc):
    """A rendered citation must name a footnote attached to the same leaf.

    The superscript and the note carry the same "<printed-page>.<marker>" ref, so
    a reader matches one to the other by eye; if they disagree the citation
    points at nothing.  They coincide trivially when notes sit at the foot of the
    citing page, but the Customs Act collects its notes onto separate pages after
    each body run, and minting the ref from the CITING page there produced refs
    that existed nowhere in the document.

    Reported as a ratio with a floor rather than zero-tolerance: some citations
    genuinely have no note (the source prints a marker whose note was dropped in
    an earlier consolidation), and that is a defect of the PDF, not of the parse.
    The floor exists to catch a systematic break -- it was 72% before the binding
    was fixed and must not slide back.

    Counted across BOTH superscript classes, because the renderer no longer
    dresses an unresolved marker as a citation: ``<sup class="cite">`` is one that
    found its note, ``<sup class="marker">`` one that did not.  Reading only the
    first would make this vacuous -- every cite binds by construction -- so the
    ratio is bound / (bound + unresolved), which is exactly the measurement this
    invariant made before, now taken from the two classes.

    Measured only over markers whose note EXISTS IN THE DOCUMENT, which is the
    difference between the defect this guards and a defect of the PDF:

    * the note exists and is attached to another leaf -> the BINDING broke, which
      is what took this from 72% to green when the Customs collector pages were
      fixed, and what must never slide back;
    * the note appears nowhere -> the source prints a marker and never prints its
      note.  That is ledger **O04**, measured long before today ("in 2014, 20 of
      216 had no note anywhere = genuine source defect"), and it is pervasive:
      markers-without-notes run 15-25% across the Customs and Federal Excise
      families, and five editions (Finance Act 2014, 2021, 2018-19, Pakistan
      Single Window 2021, Tax Laws (Amdt) 2020) print amendment markers with **zero
      footnotes anywhere in the document**.

    Counting the second kind made the ratio a smooth continuum -- 0.749, 0.759,
    0.778, 0.790, 0.806, 0.810, 0.814 ... -- with no gap anywhere near the floor,
    so a threshold on it separates nothing and merely re-reports how defective each
    PDF is.  The count of note-less markers is still reported in the message, so
    O04 stays visible rather than being silently forgiven.
    """
    everywhere = {str(fn.get("ref"))
                  for leaf in iter_all_leaves(doc)
                  for fn in (leaf.get("footnotes") or [])}
    bound = misbound = absent = 0
    for leaf in iter_all_leaves(doc):
        html = leaf.get("html") or ""
        have = {str(fn.get("ref")) for fn in leaf.get("footnotes", [])}
        for ref in set(_CITE_REF.findall(html)) | set(_MARKER_SUP.findall(html)):
            if ref in have:
                bound += 1
            elif ref in everywhere:
                misbound += 1      # the note IS in this document, on another leaf
            else:
                absent += 1        # the source prints the marker and no note
    total = bound + misbound
    if total == 0:
        return []
    ratio = bound / total
    if ratio < 0.80:
        return [f"only {ratio:.1%} of {total} markers whose note EXISTS resolve "
                f"to it ({misbound} attached to the wrong leaf; {absent} more "
                f"markers have no note anywhere -- ledger O04)"]
    return []


_TAGS = re.compile(r"<[^>]+>")


def inv_text_density_plausible(doc):
    """A converted statute must carry a plausible amount of text per page.

    The JSON has no per-page record, so this is the proxy for "a body page
    yielded nothing".  It exists because six Phase-2 files were written with
    essentially no text and reported success: Finance Act 2025 produced **0
    characters from 292 pages**, Finance Act 2024 **91 characters from 89**.  A
    real page of any statute in this corpus carries roughly 1,000-2,500
    characters, so a floor of 200 per body page is far below anything genuine
    while still catching a total failure.

    Counts html with tags stripped as well as plain_text, because a tariff
    schedule's content lives in table cells and would otherwise read as empty.
    """
    meta = doc.get("metadata") or {}
    pages = (meta.get("total_pages") or 0) - (meta.get("toc_pages_scanned") or 0)
    if pages <= 0:
        return []
    chars = 0
    for leaf in iter_all_leaves(doc):
        chars += len(leaf.get("plain_text") or "")
        chars += len(_TAGS.sub(" ", leaf.get("html") or ""))
    chars += len((doc.get("preamble") or {}).get("plain_text") or "")
    density = chars / pages
    if density < 200:
        return [f"implausible text density: {chars} chars over {pages} body "
                f"page(s) = {density:.0f}/page (floor 200) -- the document is "
                f"probably empty or its pages were not read"]
    return []


def inv_zone_mode_none_has_no_footnotes(doc):
    """A document zoned ``"none"`` must not have produced footnotes.

    ``"none"`` means calibration could not separate body from footnote text, so
    every page was read as body.  If footnotes nevertheless came out, the zoning
    decision and the parse disagree and one of them is wrong -- exactly the
    ambiguity that used to raise, now surfaced as a check instead of a refusal.
    Misplaced footnote text in the body is caught separately by
    ``no_footnote_text_in_body``.
    """
    cal = ((doc.get("metadata") or {}).get("calibration") or {})
    if cal.get("zone_mode") != "none":
        return []
    n = sum(len(leaf.get("footnotes") or []) for leaf in iter_all_leaves(doc))
    if n:
        return [f'zone_mode "none" but {n} footnote(s) were parsed -- the zoning '
                f'decision and the parse disagree']
    return []


def inv_clause_codes_plausible(doc):
    """A flat act's clause numbers must look like an act's, not like table rows.

    Text conservation and structural sanity are different properties, and until
    now only the first was measured -- so a document could pass every check while
    its structure was nonsense.  Finance Act 2025 is the case that motivated
    this: 292 pages, 238 KB of text, `text_density_plausible` green,
    `document_carries_its_text` green, all 51 other invariants green, and its
    entire "structure" is **three** sections -- one real clause (`13. Enactment
    of the New Energy Vehicles Adoption Levy Act, 2025`) plus two tariff table
    rows, `54. 05, twine, cordage, rope or cables` and `702. 3210 Synthetic turf
    for sports fields`, between them holding the whole document.

    The cause (ledger P06: the monotonic clause cursor accepts any dot-form code
    greater than the last, including quoted amendments and tariff rows) is not
    yet fixed.  This is the detector, and it is deliberately independent of
    whatever discriminator eventually fixes the cause.

    Thresholds are measured, not guessed.  Over the 26 single-chapter editions in
    `output/`, the legitimate ones start at code 1 with a maximum numeric gap of
    5 -- including the TOC-less Sales Tax editions at 122 and 123 sections. The
    broken ones start at 13, 27, 38 or 4, or jump by 21, 29, 30, 65, 138, 180,
    187 and 648.  So: first code at most 3, no gap above 8.

    Known miss: Finance Act 2019 sits at exactly 8 (it emits 35 codes for 16 real
    clauses), so it slips through. Tightening to 5 would sit on top of Sales
    Tax's real maximum, which is the wrong risk to take for a detector.
    """
    meta = doc.get("metadata") or {}
    # Only a FLAT act -- one container holding every section. A real chapter tree
    # (Customs 16, Sales Tax 10, Federal Excise 6) numbers sections per chapter
    # and legitimately restarts and jumps.
    if (meta.get("chapters_count") or 0) != 1:
        return []
    from legal_ingest.discover import code_sort_key

    # Sections under CHAPTERS only.  iter_all_leaves also walks ``schedules``,
    # whose codes ("SCHEDULE", "TABLE-1") are not clause numbers at all --
    # code_sort_key maps them to a large sentinel, which then reads as a giant
    # jump and false-fired on two perfectly good Sales Tax editions.
    def _sections(node):
        for s in node.get("sections") or []:
            yield s
        for key in ("parts", "divisions"):
            for child in node.get(key) or []:
                yield from _sections(child)

    nums = []
    for chapter in doc.get("chapters") or []:
        for leaf in _sections(chapter):
            code = leaf.get("code")
            if not code:
                continue
            try:
                k = code_sort_key(str(code))
            except Exception:
                continue
            n = k[0] if isinstance(k, tuple) else k
            # a real clause number, not a sentinel for something unparseable
            if isinstance(n, int) and 0 < n < 10000:
                nums.append(n)
    if len(nums) < 2:
        return []
    bad = []
    if nums[0] > 3:
        bad.append(f"first clause code is {nums[0]}, not 1 -- the opening "
                   f"clauses were not found (structure starts mid-document)")
    gaps = [(a, b) for a, b in zip(nums, nums[1:]) if b - a > 8]
    if gaps:
        shown = ", ".join(f"{a}->{b}" for a, b in gaps[:5])
        bad.append(f"{len(gaps)} implausible jump(s) in clause numbering "
                   f"({shown}) -- codes from quoted amendments or table rows "
                   f"are being accepted as this act's own clauses (ledger P06)")
    return bad


def inv_document_carries_its_text(doc):
    """A converted document must carry the statute somewhere.

    ``text_density_plausible`` measures how MUCH text arrived; this measures
    whether any structure arrived to hold it.  They fail apart: Finance Act 2022
    carries 1.29M characters at a healthy density and has **0 chapters and 0
    sections**, its entire body filed under a synthetic ``SCHEDULE`` whose
    "divisions" are the Income Tax Ordinance divisions it quotes.  A document
    with pages but no section and no schedule did not parse -- it was written
    because ``pipeline.run``'s parentless-section refusal is unreachable when
    the section count is zero (empty list, so no orphans), which is how six
    935-1,297 byte files were written reporting success.
    """
    meta = doc.get("metadata") or {}
    if (meta.get("total_pages") or 0) <= 0:
        return []
    if (meta.get("sections_count") or 0) or (meta.get("schedules_count") or 0):
        return []
    return [f"no sections and no schedules over {meta['total_pages']} page(s) "
            f"-- the document carries no statute at all"]


def inv_ocr_fidelity_floor(doc):
    """A scanned edition must record that it cleared the fidelity floor.

    The floor existed and was measured long before anything enforced it:
    ``ocr.Fidelity.admitted`` was read at exactly two lines in the repo, inside
    ``scripts/ocr_review.py``, to sort a markdown table.  So the Right of Access
    to Information Act 2017 was scored at 80.49% agreement, recorded as EXCLUDE,
    and then written to ``output/`` ~39 hours later by a code path with no way
    to learn the verdict existed -- shipping "Right to have access to
    information not to be denied.-(!)" as statutory text.

    ``pipeline.run`` now refuses below the floor, so a shipped scan carries a
    ``metadata.ocr`` block by construction.  This checks the JSON cannot claim
    otherwise: the numbers must be present and must actually clear the floor.
    Silent on text-layer documents, which have no ``metadata.ocr`` at all.
    """
    ocr = ((doc.get("metadata") or {}).get("ocr") or {})
    if not ocr:
        return []
    if ocr.get("provisional"):
        # A document that DECLARES itself below the floor is not lying about
        # clearing it, so this check has nothing to say -- but it must not become
        # a way to opt out of the floor either. `provisional_is_flagged` below
        # holds that side: the declaration has to be complete and consistent.
        return []
    bad = []
    agree = ocr.get("mean_agreement")
    low = ocr.get("low_conf_share")
    if agree is None or agree < 85.0:
        bad.append(f"OCR mean agreement {agree} below the 85% floor")
    if low is None or low > 15.0:
        bad.append(f"OCR low-confidence share {low} above the 15% ceiling")
    if not ocr.get("pages"):
        bad.append("metadata.ocr present but records 0 OCR'd pages")
    return bad


def inv_provisional_is_flagged(doc):
    """Sub-floor text must be labelled as such, completely and consistently.

    The user decided 2026-08-07 to ship the nine sub-floor documents rather than
    withhold them, so the floor became a LABEL instead of a wall.  A label is
    only worth the check behind it: this is what stops "provisional" from
    degenerating into a way to silence the fidelity floor.

    Both directions, because either one alone is escapable:
      * a document whose measured agreement is under the floor MUST carry
        ``provisional: true``, ``floor: "provisional"`` and a reason
      * a document that claims ``provisional`` must actually be under the floor,
        so the flag cannot be sprinkled on clean files to pre-empt future
        failures

    The location rule -- provisional documents live in ``output/_provisional/``
    and never in ``output/`` -- is enforced by the single writer in
    ``scripts/acts_pdf_to_json.py``, and audited over the whole corpus by
    ``scripts/audit_all.py``, because P08 is precisely the anomaly where
    "refusing to write" was mistaken for "ensuring absence" and a stale file
    stayed in the corpus for 39 hours.
    """
    ocr = ((doc.get("metadata") or {}).get("ocr") or {})
    if not ocr:
        return []
    agree, low = ocr.get("mean_agreement"), ocr.get("low_conf_share")
    under = ((agree is not None and agree < 85.0)
             or (low is not None and low > 15.0))
    claims = bool(ocr.get("provisional"))
    bad = []
    if under and not claims:
        bad.append(f"agreement {agree}% / low-conf {low}% is under the floor but "
                   f"metadata.ocr.provisional is not set -- sub-floor text must "
                   f"be labelled, not shipped silently")
    if claims and not under:
        bad.append(f"metadata.ocr.provisional is set but agreement {agree}% / "
                   f"low-conf {low}% clears the floor -- the flag must mean "
                   f"something measured, not be applied pre-emptively")
    if claims and ocr.get("floor") != "provisional":
        bad.append(f"provisional document records floor={ocr.get('floor')!r}, "
                   f"which contradicts its own flag")
    if claims and not ocr.get("provisional_reason"):
        bad.append("provisional document carries no provisional_reason -- a "
                   "reader of the JSON alone cannot learn why it is doubted")
    return bad


def inv_no_unreviewed_ocr_token(doc):
    """Every doubted OCR token must be declared on the leaf that carries it.

    A file can clear the floor and still contain uncertain words -- Benami 2017
    is admitted at 85.20%, two tenths of a point above the line, with ~1,300
    tokens the two engines read differently.  Shipping those unmarked is the
    quiet version of the RTI defect, so the per-token flags must survive the
    conversion instead of dying at the pagemodel boundary.

    The check is a reconciliation, not a taste test: if the file says N tokens
    need review, the leaves must actually declare them.  A count that vanishes
    means the provenance was dropped somewhere between ``ocr.align`` and the
    JSON.

    Scoped to OCR'd pages that a leaf actually covers.  A flagged token on a page
    no leaf spans cannot be declared by anything and its absence is not evidence
    of a defect -- Finance Act 2022 and 2023 each recognise exactly page 1, the
    gazette cover, while their earliest section begins on page 2 (FA2022's only
    section spans 105-118).  Comparing a bare count against the leaves called
    both of those broken when nothing was wrong, which is why ``pages_ocred`` is
    recorded and intersected here instead.
    """
    ocr = ((doc.get("metadata") or {}).get("ocr") or {})
    if not ocr:
        return []
    claimed = ocr.get("needs_review_tokens") or 0
    if not claimed:
        return []
    pages = set(ocr.get("pages_ocred") or [])
    leaves = list(iter_all_leaves(doc))
    if pages:
        covered = any(
            leaf.get("start_page") is not None
            and any(leaf["start_page"] <= p <= (leaf.get("end_page")
                                                or leaf["start_page"])
                    for p in pages)
            for leaf in leaves)
        if not covered:
            return []
    declared = sum(len(leaf.get("ocr_review") or []) for leaf in leaves)
    if not declared:
        return [f"metadata.ocr declares {claimed} token(s) needing review on "
                f"page(s) that leaves do cover, but no leaf carries an "
                f"ocr_review list -- the per-token OCR provenance was dropped "
                f"before it reached the JSON"]
    return []


def inv_bold_gate_unchanged_on_text_layer(doc):
    """A text-layer document must never carry OCR provenance.

    ``_bold_title`` gates every section start, hOCR carries no font, and the
    fallbacks that let a scan through (``fontname is None``, and ``doc_has_bold``
    for a document typeset wholly in one plain face) must not start firing on
    documents that do have real font information.  The observable consequence of
    that going wrong is an ``metadata.ocr`` block, or an ``ocr_review`` list, on
    a document whose words carry real fontnames -- i.e. OCR ran where the text
    layer was authoritative and REPLACED an exact reading with a guess.

    ``zone_mode`` is the proxy for "calibration saw real typeset text": it is
    derived from font sizes and rule geometry, and a wholly scanned document
    cannot reach ``"size"`` honestly with no font metrics to measure.
    """
    meta = doc.get("metadata") or {}
    ocr = meta.get("ocr") or {}
    if not ocr:
        return []
    leaves_with_review = sum(1 for leaf in iter_all_leaves(doc)
                             if leaf.get("ocr_review"))
    pages = (meta.get("total_pages") or 0) - (meta.get("toc_pages_scanned") or 0)
    if pages > 0 and ocr.get("pages", 0) < 0.5 * pages and leaves_with_review:
        return [f"OCR provenance on {leaves_with_review} leaf/leaves but only "
                f"{ocr.get('pages')} of {pages} body pages were scanned -- "
                f"check OCR did not run over a real text layer"]
    return []


#: Invariant *order* for the Acts and the Rules lanes, whose ALL_INVARIANTS lists were
#: byte-identical. The Ordinance lane runs a different set and passes its own order.
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
    "calibration_sane",
    "text_density_plausible",
    "zone_mode_none_has_no_footnotes",
    "citation_refs_resolve",
    "ocr_fidelity_floor",
    "provisional_is_flagged",
    "no_unreviewed_ocr_token",
    "bold_gate_unchanged_on_text_layer",
    "document_carries_its_text",
    "clause_codes_plausible",
]


def all_invariants(ns, order=None):
    """Bind each invariant by name from the lane module, falling back to this one.

    A lane that defines its own ``inv_<name>`` -- or binds a partial of the shared one --
    simply wins, which is why an override is never registered in a second place.
    """
    bound = []
    for name in (order or _ORDER):
        fn = ns.get(f"inv_{name}") or globals().get(f"inv_{name}")
        if fn is None:
            raise KeyError(f"no invariant named inv_{name} in the lane module or _common")
        bound.append((name, fn))
    return bound
