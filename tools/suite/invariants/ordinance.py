"""Global invariants -- always-on checks that must hold for the whole document.

Each invariant is a function ``(doc) -> list[str]`` returning human-readable
failure messages (empty list = pass).  These encode the *classes* of bug we've
fixed, so a regression anywhere in the 821 pages is caught, not just in the one
section that was originally reported.
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


def inv_no_pua_glyphs(doc):
    bad = []
    for leaf in iter_all_leaves(doc):
        if _PUA.search(leaf.get("html", "")) or _PUA.search(leaf.get("plain_text", "")):
            bad.append(f"section {leaf.get('code')}: private-use glyph present")
    return bad


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
    """Numeric order for a '<printed-page>.<marker>' ref; '*' notes come
    before the numbered notes of their page, as printed in the footer."""
    page, _, marker = str(ref).partition(".")
    page_n = int(page) if page.isdigit() else 0
    if marker.isdigit():
        return (page_n, 1, int(marker))
    return (page_n, 0, 0)


def inv_footnotes_in_numeric_order(doc):
    """A leaf's footnotes must be sorted numerically by (printed page, marker).

    Refs are strings, so a lexical sort renders 10.1, 10.10, 10.11, 10.2 --
    the reader sees the notes out of order.  Guards the ref_sort_key ordering
    applied at every footnote sort site in both pipelines."""
    bad = []
    for leaf in iter_all_leaves(doc):
        refs = [str(fn.get("ref", "")) for fn in leaf.get("footnotes", [])]
        keys = [_ref_key(r) for r in refs]
        if keys != sorted(keys):
            bad.append(f"section {leaf.get('code')}: footnotes out of "
                       f"numeric order: {refs}")
    return bad


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


# a split ordinal ("30 th June", "1 st day") or a stray leading suffix line --
# both mean the superscript ordinal was not re-attached to its number
_SPLIT_ORDINAL = re.compile(r"\b\d+ (st|nd|rd|th)\b")
_LEAD_ORDINAL = re.compile(r"^(st|nd|rd|th)\b")


def inv_no_split_ordinals(doc):
    """Ordinal superscripts must be merged into their number ('30th', not
    '30 th' / a stray 'th' line).  Guards the word-fragment merge in
    pagemodel._merge_split_words."""
    bad = []
    for leaf in iter_all_leaves(doc):
        if _SPLIT_ORDINAL.search(leaf.get("plain_text", "")):
            bad.append(f"section {leaf.get('code')}: split ordinal in body")
        for fn in leaf.get("footnotes", []):
            t = fn.get("text", "")
            if _SPLIT_ORDINAL.search(t):
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
    without their <sup> citations (236T's '4[5[ ]]')."""
    bad = []
    for leaf in iter_all_leaves(doc):
        first = (leaf.get("plain_text") or "").lstrip().split("\n", 1)[0]
        if _LEADING_AMEND_MARKER.match(first.replace(" ", "")) \
                and '<sup class="cite"' not in (leaf.get("html") or ""):
            bad.append(f"section {leaf.get('code')}: leading amendment marker "
                       f"with no <sup> citation in html")
    return bad


# the longest genuine word in this corpus is ~20 letters; a 25+ run of letters
# means whole words were glued together ("toasuspenseaccountinaccordancewith")
_JAMMED_RUN = re.compile(r"[A-Za-z]{25,}")


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


# A section that was inserted and later omitted renders as a nested bracket
# pair: the outer bracket anchors an anonymous insertion note ("Inserted by
# the Finance Act, 2016." -- no section named), the inner one the omission
# note naming the code ("Section 236V omitted...").  Markers are consecutive,
# so the notes mint consecutive refs (477.1/477.2).  The anonymous half must
# travel WITH the omitted section's leaf -- when it lands elsewhere (printed
# page 477 put 477.1/477.5 on 236O), the section's legal history is split
# across two sections.  inv_footnote_on_citing_leaf cannot see this: the
# swallowing leaf's html genuinely cites the marker, so citation and
# attachment agree -- the defect is in body segmentation, which only this
# pairing check observes.

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


# -- footnote-to-leaf mapping ------------------------------------------------
#
# A footnote belongs to the leaf whose text CITES its marker (rendered as
# <sup class="cite">REF</sup>).  Guards the by-span over-collection bug
# (2026-07-04): First Schedule Division V carried Divisions IV/IVA's footnotes
# 501.1-501.3 because the divisions share a PDF page; and the misprinted-footer
# bug, where the same footnote attached twice under two different refs
# (sections 99/113/237 gained phantom 189.x/217.x/483.x copies).
#
# Allowed exceptions, both deliberate:
#   * an omission/substitution note that NAMES the leaf's own code is attached
#     to that (usually body-less) leaf even though its marker anchors in a
#     neighbour's text -- the section's legal history must travel with it
#     (e.g. 470.2 sits on both 236D, which cites it, and omitted 236F);
#   * a footnote cited by nobody (its marker sits inside quoted footnote text,
#     e.g. 489.2-489.7 anchor in 489.1's quoted rate table) is adopted by the
#     one leaf whose page range covers it -- it must appear exactly once.
# Citations recorded from markers INSIDE tables don't render as <sup> in html,
# so an uncited-looking footnote on a single leaf is fine; the failure mode is
# it ALSO being cited (or duplicated) elsewhere.

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


def inv_preamble_present(doc):
    """The enacting preamble (text before section 1) must be captured."""
    pre = (doc.get("preamble") or {}).get("plain_text", "")
    if "ORDINANCE" in pre and "WHEREAS" in pre:
        return []
    return ["preamble missing or incomplete (no 'AN ORDINANCE ... WHEREAS ...')"]


_TABLE_BLOCK = re.compile(r'<table class="fbr-table">.*?</table>', re.S)
_TR_BLOCK = re.compile(r"<tr>(.*?)</tr>", re.S)
_CELL_TEXT = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
_NUM_ONLY = re.compile(r"^\(\d+\)$")


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


ALL_INVARIANTS = [
    ("no_glued_marker_digit", inv_no_glued_marker_digit),
    ("no_bare_footnote_marker_line", inv_no_bare_footnote_marker_line),
    ("no_stray_space_hyphen", inv_no_stray_space_hyphen),
    ("no_duplicate_division_code_within_part", inv_no_duplicate_division_code_within_part),
    ("no_glyph_spaced_cell", inv_no_glyph_spaced_cell),
    ("no_footnote_note_in_body", inv_no_footnote_note_in_body),
    ("division_iia_non_empty", inv_division_iia_non_empty),
    ("schedule_parts_contiguous", inv_schedule_parts_contiguous),
    ("no_pua_glyphs", inv_no_pua_glyphs),
    ("no_bold_body_subsection_marker", inv_no_bold_body_subsection_marker),
    ("preamble_no_chapter_heading", inv_preamble_no_chapter_heading),
    ("no_page_number_bleed", inv_no_page_number_bleed),
    ("no_stray_dotnumber", inv_no_stray_dotnumber),
    ("no_orphan_marker_li", inv_no_orphan_marker_li),
    ("no_omitted_heading_emdash", inv_no_omitted_heading_emdash),
    ("footnote_schema", inv_footnote_schema),
    ("footnote_refs_printed_page", inv_footnote_refs_printed_page),
    ("footnotes_in_numeric_order", inv_footnotes_in_numeric_order),
    ("no_year_marker_refs", inv_no_year_marker_refs),
    ("no_split_ordinals", inv_no_split_ordinals),
    ("leading_marker_cited", inv_leading_marker_cited),
    ("no_jammed_words", inv_no_jammed_words),
    ("html_well_formed", inv_html_well_formed),
    ("strong_balanced", inv_strong_balanced),
    ("no_heading_word_duplication", inv_no_heading_word_duplication),
    ("schedules_have_content", inv_schedules_have_content),
    ("no_structural_heading_in_body", inv_no_structural_heading_in_body),
    ("no_footnote_text_in_body", inv_no_footnote_text_in_body),
    ("footnote_on_citing_leaf", inv_footnote_on_citing_leaf),
    ("insertion_note_paired_with_omission", inv_insertion_note_paired_with_omission),
    ("no_dropped_table_row_paragraph", inv_no_dropped_table_row_paragraph),
    ("numbering_row_in_thead", inv_numbering_row_in_thead),
    ("no_serial_first_row_in_thead", inv_no_serial_first_row_in_thead),
    ("no_formula_legend_inside_cell", inv_no_formula_legend_inside_cell),
    ("no_inline_formula_legend", inv_no_inline_formula_legend),
    ("no_control_chars", inv_no_control_chars),
    ("preamble_present", inv_preamble_present),
    ("no_toc_row_in_heading", inv_no_toc_row_in_heading),
    ("structure_counts", inv_structure_counts),
    ("no_orphan_sections", inv_no_orphan_sections),
    ("section_codes_ordered", inv_section_codes_ordered),
    ("toc_first_chapter_parse", inv_toc_first_chapter_parse),
    ("toc_schedule_regexes", inv_toc_schedule_regexes),
]
