"""Assemble sections from cleaned body lines and render html / plain_text.

Given the ordered list of body :class:`~legal_ingest.pagemodel.Line` objects
(each tagged with its PDF page) and the ordered section list from the TOC, this
module:

  1. Splits the running body text into sections at each section-heading line
     (QA fix: sections that continue onto the next page are merged, because we
     cut on headings, not on page boundaries).
  2. Converts inline superscript markers into ``<sup class="cite">`` citations
     linked to the correct footnote text (QA fix: right asterisk + right refs).
  3. Emits ``html``, ``plain_text`` and the ``footnotes`` list per section, in
     the exact shape of the target JSON.
"""

from __future__ import annotations

import functools
import html as _html
import re
from dataclasses import dataclass, field
from statistics import median as _median

from .footnotes import BRACKETS_ONLY_RE, all_markers_anonymous, ref_sort_key
from .grammar import CODE, CODE_SUFFIXED, MARKER_PREFIX, is_code_like, norm_code

# em dash / en dash that separates a heading from its text
DASHES = "—–-"
# The terminator is a period OR A COMMA followed by a dash.  The Customs Act
# prints both ("...to pass certain orders,-(1) The Board..."), and a
# period-only pattern left that heading unsplit, so its last word reappeared
# at the head of the body text (section 195).
HEAD_SPLIT_RE = re.compile(r"[.,]\s*[" + DASHES + r"]")

SUBSEC_RE = re.compile(r"^\((\d+[A-Z]{0,3})\)")          # (1) (1A) (12) (1AAA)
CLAUSE_RE = re.compile(r"^\(([a-z]{1,3})\)")             # (a) (aa) (bb)
# Roman-numeral sub-clause markers 1-99.  Romans in this range use only i/v/x/l,
# so lettered clauses (c)/(d)/(m) never collide; the one genuine ambiguity is a
# BARE "(l)" (roman 50 vs the 12th lettered clause), excluded by the lookahead so
# it stays a lettered clause -- every multi-character 40-99 roman ("(xl)", "(xli)",
# "(xliii)", "(li)", "(lvii)", "(lx)", "(xcv)") is unambiguous and matched, fixing
# the >39 clauses that otherwise fell through to text and merged into one <li>.
ROMAN_RE = re.compile(r"^\((?!l\))((?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3}))\)$")


@dataclass
class LineRef:
    page: int
    line: object   # pagemodel.Line


@dataclass
class BuiltSection:
    code: str
    heading: str
    page_number: int
    html: str
    plain_text: str
    start_page: int | None
    end_page: int | None
    footnotes: list = field(default_factory=list)
    # the TOC's own wording, kept beside the (authoritative) body heading, and
    # which of the two ``heading`` came from -- see ``_build_one``
    toc_heading: str = ""
    heading_source: str = "toc"
    # Tokens in this section that the two OCR engines read differently, in
    # document order.  Empty for every text-layer document; non-empty only where
    # the text came from a scan, and then it is the record of exactly which
    # words a reader must not rely on.
    ocr_review: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# line -> (plain string, html string) with inline markers resolved
# ---------------------------------------------------------------------------

def _cite_entry(footnote_map, page, marker):
    """``(title, note_page)`` for a marker cited on ``page``.

    Tolerates a bare-string map as well as the ``(title, page)`` form so callers
    that legitimately have no page context still work.
    """
    v = (footnote_map or {}).get(page, {}).get(marker)
    if v is None:
        return "", None
    if isinstance(v, tuple):
        return v[0], v[1]
    return v, None


def _cite_has_text(title) -> bool:
    """True when a lookup found note BODY, not merely a blank extracted note."""
    return bool((title or "").strip())


def _marker_or_cite_sup(ref: str, marker: str, title: str) -> str:
    """``<sup class="cite">`` only when the note has text; else ``class="marker"``.

    An empty title with ``class="cite"`` is what the review popover prints as a
    card that says only ``Footnote {ref}`` (Customs 25B / 37.42).  A marker that
    resolved to no body is not a citation.
    """
    if not _cite_has_text(title):
        return (f'<sup class="marker" data-ref="{_html.escape(ref, quote=True)}">'
                f'{_html.escape(marker)}</sup>')
    return (f'<sup class="cite" '
            f'title="{_html.escape(title, quote=True)}">{ref}</sup>')


def _ocr_marker_fn(words):
    """Marker predicate for a line, tightened for OCR'd words.

    An inline marker is a SUPERSCRIPT -- visibly smaller than the text it sits
    in -- and on a text-layer page ``Word.is_marker``'s absolute size cutoff
    expresses that well enough.  On a scan it does not: hOCR reports one size per
    recognised token and they come out within a fraction of a point of each other,
    so a section code at the head of a line (``14.``) is indistinguishable from a
    superscript by size alone.

    Measured on the Benami Transactions Act 2017 (26 scanned pages): the output
    rendered 56 citations, of which every single one pointed at no footnote --
    ``5.3.``, ``8.14.``, ``12.23.`` are its own section numbers, and ``19.1860``,
    ``23.1898``, ``24.1882`` are the years of the statutes it cites.  A citation
    that resolves to nothing is worse than no superscript at all in legally
    binding text, and the note itself still reaches the leaf through the
    orphan-adoption net.

    So for an OCR'd word (``conf`` is set only by ``ocr.align``) require the
    RELATIVE test that ``_true_table_marker`` already uses for dense tables: at
    least 0.8 pt below the line's dominant size.
    """
    sizes = [w.size for w in words if w.size]
    dominant = max(set(sizes), key=sizes.count) if sizes else 0.0

    def is_marker(w):
        if not w.is_marker:
            return False
        if getattr(w, "conf", None) is None:
            # TEXT LAYER: keep the absolute cutoff.  Applying the relative test
            # here was TRIED and REVERTED -- it took `citation_refs_resolve` from
            # 9 failures to 12 and `footnote_on_citing_leaf` from 2 to 15, i.e. it
            # stopped rendering REAL citations whose note was still attached, and
            # dropped the corpus from 64 editions at 53/53 to 51.  A text-layer
            # marker is reliably raised and reliably smaller than body text; the
            # relative test only adds value where hOCR has flattened the sizes.
            return True
        return w.size <= dominant - 0.8

    return is_marker


def _render_line(line, page: int, footnote_map: dict, page_offset: int = 0,
                 cited=None) -> tuple[str, str]:
    """Return (plain_text, html) for one body line."""
    words = sorted(line.words, key=lambda w: w.x0)
    return _render_words(words, page, footnote_map, page_offset, cited,
                         is_marker_fn=_ocr_marker_fn(words))


def _render_words(words, page: int, footnote_map: dict,
                  page_offset: int = 0, cited=None,
                  is_marker_fn=None) -> tuple[str, str]:
    """Render a list of Word objects to (plain_text, html), resolving markers.

    ``footnote_map`` maps ``page -> {marker: text}`` for citation titles.
    Citation refs use the *printed* page number (``page - page_offset``).
    When ``cited`` is a list, every referenced ``(page, marker)`` is appended to
    it so the caller can attach exactly the footnotes this section cites.
    ``is_marker_fn`` overrides marker detection (defaults to ``w.is_marker``);
    heading rendering passes a predicate that also accepts large-type heading
    markers so a title citation is never rendered as a bare digit.
    """
    plain_parts: list[str] = []
    html_parts: list[str] = []   # (sep, fragment, bold)
    prev_x1 = None
    prev_text = ""
    for w in words:
        # glue only fragments with NO real space character between them --
        # fully-justified lines compress genuine word gaps below 2pt
        glue = (prev_x1 is not None and (w.x0 - prev_x1) < 2.0
                and not getattr(w, "space_before", False))
        # RC-7 (stray-space hyphen): a compound wrapped mid-word is extracted as
        # two tokens ("sub-" + "section") separated by a justification gap.  Re-
        # join them with NO space so both html and plain read "sub-section", never
        # "sub- section".  Only when the left token ends "<letter>-" and the right
        # starts lowercase -- never a spaced dash (" - ") or a range ("1948- 49").
        if (not glue and len(prev_text) >= 2 and prev_text[-1] == "-"
                and prev_text[-2].isalpha() and w.text[:1].islower()):
            glue = True
        sep = "" if glue else " "
        if is_marker_fn(w) if is_marker_fn else w.is_marker:
            marker = w.text.strip()
            title, note_pg = _cite_entry(footnote_map, page, marker)
            # ref names the page the NOTE is printed on, not the citing page --
            # identical in a bottom-of-page layout, different where notes are
            # collected onto their own pages (Customs).  Keeping them in step is
            # what lets a reader match the superscript to the note.
            ref = f"{(note_pg if note_pg is not None else page) - page_offset}.{marker}"
            if cited is not None:
                cited.append((page, marker))
            # Missing OR blank title: not a citation.  A note extracted as
            # marker-only (Customs zone-split left 42's body in the quote under
            # 41) used to emit ``<sup class="cite" title="">37.42</sup>`` because
            # this branch required ``note_pg is None`` as well as empty text.
            # The marker is still real printed text; ``data-ref`` keeps the
            # reference it WOULD have made so ``inv_citation_refs_resolve`` can
            # tell a binding break from a source defect (ledger O04).
            frag = _marker_or_cite_sup(ref, marker, title)
            bold = False
            # RC-5: a superscript marker must never fuse into the preceding word or
            # number ("2005"+"4" -> "2005 4[", not "20054["), but must stay glued to
            # opening punctuation ("—1[") and at line start.  So force a separating
            # space ONLY when the marker is glued to a preceding alphanumeric char;
            # every other case keeps the original glue behaviour verbatim.
            prev_plain = "".join(plain_parts)
            marker_sep = " " if (glue and prev_plain[-1:].isalnum()) \
                else ("" if glue else " ")
            plain_parts.append(marker_sep + marker)
        else:
            frag = _html.escape(w.text)
            bold = "Bold" in (w.fontname or "")
            plain_parts.append(sep + w.text)
        html_parts.append((sep, frag, bold))
        prev_x1 = w.x1
        prev_text = w.text

    # assemble html, wrapping maximal runs of bold words in <strong> (the target
    # keeps bold rule/heading text, e.g. "1. Application.-")
    out = []
    in_bold = False
    for sep, frag, bold in html_parts:
        if bold and not in_bold:
            out.append(sep + "<strong>" + frag)
            in_bold = True
        elif bold and in_bold:
            out.append(sep + frag)
        elif not bold and in_bold:
            out.append("</strong>" + sep + frag)
            in_bold = False
        else:
            out.append(sep + frag)
    if in_bold:
        out.append("</strong>")

    plain = "".join(plain_parts).strip()
    html = "".join(out).strip()
    # glue a following bracket onto a citation / marker: "</sup> [" -> "</sup>["
    html = re.sub(r"(</sup>)\s+\[", r"\1[", html)
    plain = re.sub(r"(\d|\*)\s+\[", r"\1[", plain)
    return plain, html


def _render_heading_words(words, page: int, footnote_map: dict,
                          page_offset: int = 0, cited=None) -> tuple[str, str]:
    """Render heading words, treating large-type title citations as markers.

    A section heading may carry a superscript that is bigger than the body
    ``MARKER_MAX_SIZE`` cutoff (it scales with the heading type size), so
    ``Word.is_marker`` misses it.  ``_is_heading_marker`` catches those too --
    render them as ``<sup class="cite">`` so a heading citation is never a bare
    digit (guarded by the ``leading_marker_cited`` invariant).
    """
    ctx = list(words)
    return _render_words(words, page, footnote_map, page_offset, cited,
                         is_marker_fn=lambda w: _is_heading_marker(w, ctx))


# ---------------------------------------------------------------------------
# html document assembly from rendered content lines
# ---------------------------------------------------------------------------

_RULE_RE = re.compile(r"^\d{1,3}\.\s+[A-Z]")   # "1. Application.- ..." (schedule rule)


def _is_allcaps(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    return len(letters) >= 8 and sum(c.isupper() for c in letters) / len(letters) > 0.7


# words that, right after a "(x)" marker, mean it's a mid-sentence cross-
# reference ("clause (c) or (d) of sub-section (2)"), NOT a new list item.
_CONT_AFTER_MARKER = {"of", "and", "or", "to", "in", "for", "read", "as",
                      "thereof", "above", "below"}


def _is_reference_not_item(probe: str, marker_re) -> bool:
    m = marker_re.match(probe)
    if not m:
        return False
    rest = probe[m.end():].lstrip()
    nxt = re.match(r"([A-Za-z]+)", rest)
    return bool(nxt and nxt.group(1).lower() in _CONT_AFTER_MARKER)


def _classify(line_plain: str) -> str:
    s = line_plain.lstrip()
    # An amendment-inserted subsection opens with a citation marker + bracket
    # before the "(N)", e.g. "33.1[(6) Where..." (rendered plain: "1[(6)...").
    # Strip a leading marker/bracket so the "(6)" is still recognised as its own
    # subsection rather than being merged into the previous one.
    s2 = re.sub(r"^\d+\.\S*", "", s).lstrip()             # citation ref "20.1["
    # A re-numbered clause carries TWO fused markers -- the insertion bracket and
    # the renumbering note -- before the "(N)": "4[5(1B) “amalgamation” ...",
    # "6[6[(13AB)]", "3[4[(59AB)]".  Strip every "marker[" group plus a trailing
    # bare marker (the 2nd note has no bracket of its own).  A "[" is still
    # required, so a line opening on a bare number ("233 (2A) ...") is untouched.
    s3 = re.sub(r"^(?:[\d*]+\s*\[+\s*)+(?:[\d*]+\s*)?", "", s).lstrip()
    for probe in (s, s2, s3):
        if SUBSEC_RE.match(probe):
            return "subsec"
        if ROMAN_RE.match(probe.split()[0] if probe.split() else ""):
            return "roman"
        if CLAUSE_RE.match(probe):
            return "clause"
    if _RULE_RE.match(s):
        return "rule"        # numbered rule/paragraph -> starts its own <p>
    if _is_allcaps(s):
        return "htext"       # an all-caps title line -> its own <p>
    return "text"


_SUBHEAD_SEE = re.compile(r"(?i)^\[?\(?\s*See\b")


def _is_subheading(line, plain: str) -> bool:
    """A standalone SCHEDULE sub-heading: a fully-bold line that is ALL-CAPS or
    short title-case, is not a list marker / numbered rule / "[See ...]" ref,
    and does not read as a running sentence (no terminal .:;,).

    Distinguished from in-sentence bold emphasis by requiring the WHOLE line
    bold.  Used only for schedule leaves (see ``_render_line_run(subheads=)``)
    so a mid-body rule-heading ("RULES FOR THE COMPUTATION ...") or sub-heading
    ("Computation of Profits") renders as its own block instead of being merged
    into a neighbouring paragraph."""
    t = plain.strip()
    if not t or _SUBHEAD_SEE.match(t) or re.match(r"^[\d(\[]", t):
        return False
    ws = [w for w in getattr(line, "words", [])
          if any(c.isalpha() for c in w.text)]
    if not ws or not all("bold" in (w.fontname or "").lower() for w in ws):
        return False
    if t[-1] in ".:;,":
        return False
    letters = [c for c in t if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        return True                                    # ALL-CAPS heading (any length)
    if len(ws) > 12:                                   # title-case must be short
        return False
    cap = sum(1 for w in ws if w.text.lstrip("[(“\"'")[:1].isupper())
    return cap / len(ws) >= 0.6                        # title-cased sub-heading


OL_STYLE = {
    "subsec": ('<ol class="subsection" style="list-style-type: none; '
               'padding-left: 0; margin-left: 1.5em;">'),
    "clause": ('<ol class="subsection" type="a" style="list-style-type: none; '
               'padding-left: 0; margin-left: 3.5em;">'),
    "roman": ('<ol class="subsection" type="i" style="list-style-type: none; '
              'padding-left: 0; margin-left: 5.5em;">'),
}

# Gazette / nested-Act preamble lines that must not merge into a neighbour.
# Finance Act host clauses reprint a whole Act after "There is hereby enacted
# ... in the manner as follows:-", so the centred "AN" / "ACT" / long title and
# the WHEREAS recitals sit in the preamble (or in that host section).  Merging
# them produced one run-on <p> — Foreign Assets (Declaration and Repatriation)
# Act, 2018, the leaf that opens "11. Foreign Assets ...".
_GAZETTE_TITLE_RE = re.compile(
    r"^(?:THE\s+)?(?:AN|ACT|ORDINANCE|A\s+BILL)$", re.I)
_GAZETTE_LONG_TITLE_RE = re.compile(
    r"^to\s+(?:provide|amend|consolidate|levy|give|make|further|enact)\b", re.I)
_GAZETTE_RECITAL_RE = re.compile(r"^(?:AND\s+)?WHEREAS\b", re.I)
_GAZETTE_ENACTING_IT_RE = re.compile(r"^It\s+is\s+hereby\s+enacted\b", re.I)
_GAZETTE_ENACTING_THERE_RE = re.compile(
    r"^There\s+is\s+hereby\s+enacted\b", re.I)
_GAZETTE_TABLE_CAPTION_RE = re.compile(r"^TABLES?$", re.I)
_HOST_CLAUSE_HEAD_RE = re.compile(r"^\d+[A-Z]{0,3}\.")
GAZETTE_KINDS = (
    "act-title", "act-long-title", "recital",
    "enacting-formula", "enacting-clause",
)


def _gazette_block_class(plain: str) -> str | None:
    """CSS class for a gazette title / recital / enacting line, else None."""
    s = (plain or "").strip()
    if not s:
        return None
    if _GAZETTE_TITLE_RE.match(s) or _GAZETTE_TABLE_CAPTION_RE.match(s):
        return "act-title"
    if _GAZETTE_LONG_TITLE_RE.match(s):
        return "act-long-title"
    if _GAZETTE_RECITAL_RE.match(s):
        return "recital"
    if _GAZETTE_ENACTING_IT_RE.match(s):
        return "enacting-formula"
    if _GAZETTE_ENACTING_THERE_RE.match(s):
        return "enacting-clause"
    return None


def _p(html: str, cls: str | None = None) -> str:
    if not (html or "").strip():
        return ""
    if cls:
        return f'<p class="{cls}">{html}</p>'
    return f"<p>{html}</p>"


def _build_html(heading_html: str, content: list[tuple[str, str, str]]) -> str:
    """content = list of (kind, plain, html) rows already rendered."""
    out = [heading_html]
    i = 0
    n = len(content)
    while i < n:
        kind, plain, htm = content[i]
        if kind == "table":
            out.append(htm)
            i += 1
            continue
        if kind in GAZETTE_KINDS:
            buf = [htm]
            i += 1
            # Short centred titles stay one line; recitals / long titles / the
            # enacting formula wrap, so absorb following plain text until the
            # next structural line.
            if kind != "act-title":
                while (i < n and content[i][0] == "text"
                       and _gazette_block_class(content[i][1]) is None):
                    buf.append(content[i][2])
                    i += 1
            para = " ".join(x for x in buf if x)
            if para.strip():
                out.append(_p(para, kind))
            continue
        if kind == "subhead":
            # a standalone bold rule-heading / sub-heading: its own <p> block.
            # 'subhead' is in no 'mergeable' set, so it neither absorbs the
            # following rule/text nor is absorbed by a preceding paragraph; a
            # heading wrapped over consecutive lines merges together.
            buf = [htm]
            i += 1
            while i < n and content[i][0] == "subhead":
                buf.append(content[i][2])
                i += 1
            para = " ".join(x for x in buf if x)
            if para.strip():
                out.append(f"<p>{para}</p>")
            continue
        if kind in ("text", "rule", "htext"):
            # a paragraph.  'rule' / 'htext' start fresh; following plain 'text'
            # lines merge in; consecutive 'htext' title lines merge together.
            buf = [htm]
            mergeable = ("text", "htext") if kind == "htext" else ("text",)
            i += 1
            while i < n and content[i][0] in mergeable:
                buf.append(content[i][2])
                i += 1
            para = " ".join(x for x in buf if x)
            if para.strip():
                out.append(f"<p>{para}</p>")
        else:
            style = OL_STYLE[kind]
            items = []
            # group consecutive items of the same list kind; continuation
            # 'text' lines are appended to the current <li>
            while i < n and content[i][0] in (kind, "text"):
                if content[i][0] == kind:
                    items.append(content[i][2])
                else:
                    if items:
                        items[-1] += " " + content[i][2]
                    else:
                        items.append(content[i][2])
                i += 1
            lis = "\n".join(f"<li>{it}</li>" for it in items)
            out.append(f"{style}\n{lis}\n</ol>")
    return _strip_first_li_heading_bold("\n".join(out))


#: First ``<li>`` must not open with ``<strong>(marker)`` — that is heading-bold
#: leaking onto the first body marker (Customs "...Customs,.- (1) The..."), which
#: ``inv_no_bold_body_subsection_marker`` scopes to the first list item only.
#: Mid-body genuine bold markers (Customs s.54 (c) etc.) are left alone.
_FIRST_LI_BOLD_MARKER = re.compile(
    r"(<li>(?:<sup[^>]*>[^<]*</sup>)?\[*\s*)<strong>"
    r"(\((?:\d+[A-Za-z]{0,2}|[a-z]{1,3})\))\s*"
)


def _strip_first_li_heading_bold(html: str) -> str:
    """Move ``<strong>`` past a leading subsection marker on the first ``<li>``."""
    first_li = html.find("<li>")
    if first_li == -1:
        return html
    m = _FIRST_LI_BOLD_MARKER.match(html, first_li)
    if not m:
        return html
    return html[:m.start()] + m.group(1) + m.group(2) + " <strong>" + html[m.end():]


def _line_is_bold_title(line) -> bool:
    """A preamble line whose every alphabetic word is bold -- a centred
    long-title line such as ``AN`` / ``ORDINANCE`` / ``To consolidate ...``."""
    ws = [w for w in getattr(line, "words", [])
          if any(c.isalpha() for c in w.text)]
    return bool(ws) and all("Bold" in (w.fontname or "") for w in ws)


def _preamble_heading_split(pre_refs):
    """Heading dash on a host-clause opener (``11. Foreign Assets ...—``).

    Only when the preamble itself starts with a numbered clause; otherwise a
    later ``It is hereby enacted as follows:—`` dash would swallow AN/ACT/WHEREAS
    into the <h4>.
    """
    if not pre_refs:
        return None
    first = pre_refs[0].line.text().strip()
    if not _HOST_CLAUSE_HEAD_RE.match(first):
        return None
    return _find_heading_split(pre_refs, min(4, len(pre_refs)))


def _build_preamble_html(pre_refs, footnote_map, off_fn):
    """Assemble the enacting preamble into ``(html, plain_text)``.

    Gazette structure is preserved as separate blocks rather than one run-on
    paragraph:

      * a host-clause heading (``11. Foreign Assets ... Act, 2018.—``) as
        ``<h4 class="section-heading">`` when a heading dash is present
      * centred short titles (``AN`` / ``ACT`` / ``ORDINANCE``)
      * the long title (``to provide for ...``)
      * each WHEREAS recital
      * the enacting formula (``It is hereby enacted as follows:—``)

    Fully-bold title lines still never glue onto neighbouring prose.  Wrapped
    recitals / long titles / enacting clauses fold their continuation lines.
    """
    out: list[str] = []
    plains: list[str] = []
    buf: list[str] = []          # pending regular-weight prose fragments
    block_cls: str | None = None
    block_html: list[str] = []

    def flush_block():
        nonlocal block_cls
        if block_html:
            para = " ".join(x for x in block_html if x)
            tag = _p(para, block_cls)
            if tag:
                out.append(tag)
            block_html.clear()
        block_cls = None

    def flush():
        flush_block()
        if buf:
            para = " ".join(x for x in buf if x)
            if para.strip():
                out.append(f"<p>{para}</p>")
            buf.clear()

    def start_block(html: str, cls: str):
        nonlocal block_cls
        flush()
        if cls == "act-title":
            tag = _p(html, cls)
            if tag:
                out.append(tag)
            return
        block_cls = cls
        block_html.append(html)

    start = 0
    split = _preamble_heading_split(pre_refs)
    if split is not None:
        d, before_words, after_words = split
        page = pre_refs[d].page
        off = off_fn(page)
        head_parts = []
        for li in range(d):
            _, hh = _render_heading_words(
                sorted(pre_refs[li].line.words, key=lambda w: w.x0),
                pre_refs[li].page, footnote_map, off_fn(pre_refs[li].page))
            if hh.strip():
                head_parts.append(hh)
        _, hh = _render_heading_words(before_words, page, footnote_map, off)
        if hh.strip():
            head_parts.append(hh)
        heading = re.sub(r"</?strong>", "", " ".join(head_parts))
        heading = re.sub(r"\s{2,}", " ", heading).strip()
        if heading:
            out.append(f'<h4 class="section-heading">{heading}</h4>')
        rp, rh = _render_words(after_words, page, footnote_map, off)
        if rh.strip():
            cls = _gazette_block_class(rp)
            # The dash often splits mid-sentence ("—There is" / "hereby enacted"),
            # so the first fragment never matches the full enacting-clause regex.
            if cls is None and re.match(r"^There\s+is\b", rp.strip(), re.I):
                cls = "enacting-clause"
            if cls:
                start_block(rh, cls)
            else:
                buf.append(rh)
        start = d + 1

    for r in pre_refs:
        line = r.line
        if getattr(line, "is_table", False):
            plains.append(line.text())
        else:
            plain, _html_line = _render_line(line, r.page, footnote_map,
                                             off_fn(r.page))
            if plain.strip():
                plains.append(plain)

    for r in pre_refs[start:]:
        line = r.line
        if getattr(line, "is_table", False):
            flush()
            out.append(line.html)
            continue
        plain, html = _render_line(line, r.page, footnote_map, off_fn(r.page))
        if not html.strip():
            continue
        cls = _gazette_block_class(plain)
        if cls is None and _line_is_bold_title(line):
            cls = "act-title"
        if cls:
            start_block(html, cls)
            continue
        if block_cls:
            block_html.append(html)
            continue
        buf.append(html)
    flush()
    return "\n".join(out), "\n".join(p for p in plains if p.strip()).strip()


def content_rows_with_tables(content_refs, footnote_map, off_fn, cited,
                             subheads=False):
    """Render content refs into (kind, plain, html) rows.

    Refs may carry a Line or a pre-extracted ``Table`` block (from gridlines).
    Table blocks are emitted directly; runs of Lines go through the text-based
    fallback detector (for the rare gridless table) and per-line rendering.

    ``subheads=True`` (schedule leaves only) lifts a standalone bold
    rule-heading / sub-heading line to a ``"subhead"`` row so it renders as its
    own block instead of merging into a neighbouring paragraph.
    """
    rows = []
    run = []

    def flush():
        if run:
            rows.extend(_render_line_run(run, footnote_map, off_fn, cited,
                                         subheads=subheads))
            run.clear()

    for r in content_refs:
        if getattr(r.line, "is_table", False):
            flush()
            _cite_table_markers(r, cited)
            rows.append(("table", r.line.text(), r.line.html))
        else:
            run.append(r)
    flush()
    rows = _merge_continuation_tables(rows)
    # citation markers inside table cells travel as sentinels (they survive
    # escaping and the continuation merge above); expand them into visible
    # <sup class="cite"> citations now that the footnote map is at hand
    return [(k, p, _expand_table_cites(h, footnote_map, off_fn))
            if k == "table" else (k, p, h) for (k, p, h) in rows]


_CITE_SENT_RE = re.compile(r"\x01(\d+)\.([0-9*]{1,3})\x02")


def _expand_table_cites(html_text: str, footnote_map, off_fn) -> str:
    """Expand cell-citation sentinels to ``<sup class="cite">`` markup.

    A sentinel whose (page, marker) matches a parsed footnote becomes the
    same citation the body renders (printed-page ref + footnote text title);
    one that matches nothing (a superscript digit that anchors no footnote)
    is restored to its literal text, so no content is ever altered.
    """
    def sub(m):
        pg, marker = int(m.group(1)), m.group(2)
        title, note_pg = _cite_entry(footnote_map, pg, marker)
        if not _cite_has_text(title):
            return marker
        # ref names the note's page -- same rule as _render_words -- and it is
        # converted with the offset of THAT page, not of the citing one.  Mixing
        # the two is invisible while a document has a single folio series and
        # wrong the moment it does not: Finance Act, 2022 restarts its numbering
        # at the Schedules, so a note in the first series converted with the
        # second series' offset came out as printed page -4.
        src = note_pg if note_pg is not None else pg
        ref = f"{src - off_fn(src)}.{marker}"
        return (f'<sup class="cite" '
                f'title="{_html.escape(title, quote=True)}">{ref}</sup>')
    return _CITE_SENT_RE.sub(sub, html_text)


def _cite_table_markers(ref, cited):
    """Record the citations anchored INSIDE a table block.

    Grid-extracted tables keep only cell text, so their superscript markers
    never pass through :func:`_render_words`; the markers are preserved on the
    block (``pagemodel.Table.marker_words``) and registered here, so the
    footnotes they anchor bind to the section/division that owns the table.
    """
    if cited is None:
        return
    for w in getattr(ref.line, "marker_words", []):
        cited.append((ref.page, w.text.strip()))


_TR = re.compile(r"<tr>(.*?)</tr>", re.S)
_CELL = re.compile(r"<(t[dh])([^>]*)>(.*?)</\1>", re.S)
_COLSPAN = re.compile(r'\bcolspan="(\d+)"')
_ROWSPAN = re.compile(r'\browspan="(\d+)"')


def _table_struct(html):
    """Parse an fbr-table back into cell-structure rows (text + spans).

    Continuation merging must not re-infer spans from text (that is exactly
    what mis-rendered the Division VIII/IIB tall cells) -- the rendered
    colspan/rowspan attributes are authoritative and travel through the merge
    unchanged.
    """
    import html as _h
    rows = []
    for tr in _TR.findall(html):
        row = []
        for _tag, attrs, body in _CELL.findall(tr):
            mc = _COLSPAN.search(attrs)
            mr = _ROWSPAN.search(attrs)
            row.append({"text": _h.unescape(body),
                        "colspan": int(mc.group(1)) if mc else 1,
                        "rowspan": int(mr.group(1)) if mr else 1})
        rows.append(row)
    return rows


def _struct_width(rows) -> int:
    return sum(c["colspan"] for c in rows[0]) if rows and rows[0] else 0


def _struct_owners(rows):
    """Per-position owning cell, resolving colspans and rowspan carries.

    Returns (width, owners) where owners[r][w] is the dict cell that covers
    position (r, w) -- the cell itself for anchors and for every position its
    colspan/rowspan extends over.
    """
    width = _struct_width(rows)
    owners = []
    pending: dict[int, tuple[int, dict]] = {}   # col -> (rows left, cell)
    for row in rows:
        slots: list = [None] * width
        it = iter(row)
        w = 0
        while w < width:
            left = pending.get(w)
            if left and left[0] > 0:
                pending[w] = (left[0] - 1, left[1])
                slots[w] = left[1]
                w += 1
                continue
            c = next(it, None)
            if c is None:
                w += 1
                continue
            for k in range(w, min(width, w + c["colspan"])):
                slots[k] = c
                if c["rowspan"] > 1:
                    pending[k] = (c["rowspan"] - 1, c)
            w += c["colspan"]
        owners.append(slots)
    return width, owners


def _row_texts(row) -> list:
    """Cell texts expanded over colspans (None for continuation slots)."""
    out = []
    for c in row:
        out.append(_CITE_SENTINELS.sub("", c["text"]))
        out.extend([None] * (c["colspan"] - 1))
    return out


# a table-cell citation sentinel (pagemodel.cite_sentinel) -- stripped before
# header-pattern matching so "\x01554.4\x02[S. No." still reads as a header
_CITE_SENTINELS = re.compile("\x01[^\x02]*\x02")


def _slotted(rows):
    """Insert colspan continuation slots so ``render_structure`` can emit.

    ``_table_struct`` parses rows as DENSE cell lists; the structure renderer
    walks rows as slotted arrays (advancing by colspan).  Emitting a dense
    row directly would skip every cell that follows a spanning one -- the
    Division VIII merge silently dropped its column-6 header that way.
    """
    out = []
    for row in rows:
        slots = []
        for c in row:
            slots.append(c)
            slots.extend([None] * (c["colspan"] - 1))
        out.append(slots)
    return out


def _row_is_header(cells):
    joined = " ".join((c or "").strip() for c in cells).strip()
    # tolerate a printed amendment-marker / bracket / quote prefix on the
    # header cell ("4[S. No.", "“S. No") -- part of the header as printed
    if re.match(r"^[\d\s\[\]“”\"']*S(r)?\.?\s*(#|No)", joined, re.I):
        return True
    nonempty = [(c or "").strip() for c in cells if (c or "").strip()]
    return bool(nonempty) and all(re.match(r"^\(\d+\)$", c) for c in nonempty)


def _expand_lead_rowspans(body):
    """Flatten rowspans anchored on a fragment's LEAD row before fusion.

    Fusing (dropping) the lead row would orphan the rows its rowspan cells
    covered -- their cell lists would come up short and every later cell
    would shift left a column.  The coverage is materialised as explicit
    empty cells instead.
    """
    lead = body[0]
    pos = 0
    inserts = []                        # (row_offset, col_start, colspan)
    for c in lead:
        if c["rowspan"] > 1:
            for k in range(1, c["rowspan"]):
                inserts.append((k, pos, c["colspan"]))
            c["rowspan"] = 1
        pos += c["colspan"]
    for k, col, cs in inserts:
        if k >= len(body):
            continue
        row = body[k]
        run, idx = 0, 0
        for i2, c2 in enumerate(row):
            if run >= col:
                break
            run += c2["colspan"]
            idx = i2 + 1
        row.insert(idx, {"text": "", "colspan": cs, "rowspan": 1})


def _try_merge_structs(a, b):
    """Merge continuation-fragment ``b`` into table ``a`` (both structures).

    Returns the merged structure, or None when b is not a continuation.
    Handles: repeated header rows (skipped), a header-only fragment followed
    by its data grid (pdf p554/555), a wrapped last row split by the page
    break (Division IIB row 7's "million but does not exceed ..." tail --
    fused into the owning cells of a's last anchor rows), and a leading
    fragment row that continues a tall rowspan cell (Division VII's col-4
    rate cell) -- fused into that column's last anchor.
    """
    if not a or not b or _struct_width(a) != _struct_width(b):
        return None
    a_header_only = all(_row_is_header(_row_texts(r)) for r in a)
    # drop only b rows that literally REPEAT a's leading header rows
    skip = 0
    while (skip < min(len(a), len(b))
           and _row_is_header(_row_texts(b[skip]))
           and _row_texts(a[skip]) == _row_texts(b[skip])):
        skip += 1
    rest = b[skip:]
    if rest and not a_header_only:
        t0 = [c for c in _row_texts(rest[0]) if c and c.strip()]
        if t0 and _row_is_header([*t0]):
            # b opens its OWN different header: a numbering row continuing a
            # table that has none yet is a continuation (the p554 ruled
            # header box + p555 data grid); any other header is a new table
            is_numrow = all(re.match(r"^\(\d+\)$", c.strip()) for c in t0)
            a_has_numrow = any(
                (lambda ts: ts and all(re.match(r"^\(\d+\)$", c.strip())
                                       for c in ts))
                ([c for c in _row_texts(r) if c and c.strip()]) for r in a)
            if not is_numrow or a_has_numrow:
                return None
    body = rest
    merged = [list(r) for r in a]
    # a leading row whose serial column is EMPTY is the wrapped tail of a's
    # last row (or of a tall rowspan cell) split by the page break -- fuse
    # each of its cells into the column's last text-bearing cell in a
    if body and not a_header_only:
        _expand_lead_rowspans(body)
        lead = body[0]
        texts = _row_texts(lead)
        if (texts and not (texts[0] or "").strip()
                and any((t or "").strip() for t in texts[1:])):
            width, owners = _struct_owners(merged)
            plan = []
            ok = True
            w = 0
            for cell in lead:
                if cell["text"].strip():
                    target = next((owners[r][w]
                                   for r in range(len(merged) - 1, -1, -1)
                                   if w < width and owners[r][w] is not None
                                   and owners[r][w]["text"].strip()), None)
                    if target is None:
                        ok = False
                        break
                    plan.append((target, cell["text"]))
                w += cell["colspan"]
            if ok:
                for target, text in plan:
                    target["text"] = target["text"] + "\n" + text
                body = body[1:]
    merged.extend(list(r) for r in body)
    return merged


def _merge_continuation_tables(rows):
    """Join a table split across a page break into one table.

    A later table is a continuation of the previous one when it has the same
    effective column count and its leading row is a data row (or repeats the
    same header), e.g. Division VII's securities rate table or the s.182
    penalties table (rows 25-28 on a later page).  A genuinely different
    table (different columns / its own header) is left separate; a one-row
    fragment that merges with nothing is demoted back to a text paragraph so
    its words never masquerade as a header.
    """
    import html as _h

    from .tables import render_structure
    out = []
    for kind, plain, html in rows:
        if kind == "table" and out and out[-1][0] == "table":
            a = _table_struct(out[-1][2])
            b = _table_struct(html)
            merged = _try_merge_structs(a, b)
            if merged is not None:
                out[-1] = ("table", out[-1][1] + "\n" + plain,
                           render_structure(_slotted(merged)))
                continue
        if kind == "table":
            struct = _table_struct(html)
            if len(struct) == 1 and not _row_is_header(_row_texts(struct[0])):
                # an unmerged single ruled row is not a table -- keep its
                # words as a plain paragraph (pdf p413's s.182 row would
                # otherwise render as a bogus one-row header table).  Emit the
                # bare text: _build_html wraps every "text" row in its own <p>,
                # so wrapping here produced invalid "<p><p>...</p></p>".
                out.append(("text", plain, _h.escape(plain)))
                continue
        out.append((kind, plain, html))
    return out


# Distinguish a wrapped cross-reference from a real list item, both of which can
# look like a line-initial "(x)":
#
#   reference (downgrade to text):  "...clause (c) or\n(d) of sub-section (2)"
#   list item  (keep as <li>):      "...receivable; or\n(b) in the case of ..."
#
# Two signals separate them:
#   * the word right after "(x)": a reference continues with "of" ("(d) of
#     sub-section"); a real item opens with prose ("(b) in the case"), so we
#     only downgrade when that word is a reference connector ("of").
#   * the previous line's ending: a real list separates items with ";"/":" before
#     the connective ("receivable; or"); a reference enumerates inline after a
#     ")"/word ("clause (c) or"), with no such terminator.
_REF_CONT = {"of"}
# previous line ends mid-sentence on a bare connective/comma (reference)...
_PREV_MIDSENTENCE = re.compile(r"(?:\b(?:or|and)\b|,)\s*$", re.I)
# ...but NOT if a list-item terminator precedes that connective (real list).
_PREV_LIST_SEP = re.compile(r"[;:–—]\s*(?:or|and)?\s*$", re.I)
# The previous line ends ON a cross-reference NOUN, so a following "(x)" is that
# noun's number, not a new item: "...mentioned in sub-section\n(1).]" (s.6A),
# "...under clause\n(19) of section 2]" (s.5).  A real new list item instead
# separates on a terminator ("...receivable;\n(b) in the case ...") -- the noun
# is never the last token, so this never fires there.
_PREV_XREF_NOUN = re.compile(
    r"\b(?:clauses?|sub-?clauses?|sub-?sections?|sections?|paras?|paragraphs?|"
    r"divisions?|parts?|rules?|tables?|items?|sub-?rules?)\s*$", re.I)

_MARKER_RE_FOR = {"clause": CLAUSE_RE, "subsec": SUBSEC_RE, "roman": ROMAN_RE}

#: A line that is nothing but a marker.  A list ITEM carries the provision it
#: numbers; a marker standing alone with no words after it is something else, and
#: the corpus shows three somethings (ledger P38, all four occurrences of
#: ``inv_no_orphan_marker_li``):
#:
#:   * a tariff table's COLUMN-NUMBERING row wrapped across two lines -- Finance
#:     Act 2013 clause 7 prints ``(1) (2)`` then ``(3)`` under "S.No. | Gross
#:     amount of rent | Rate of tax";
#:   * a cross-reference whose number wrapped -- Finance Act 2014 clause 7,
#:     ``... taxable income under sub-section |`` / ``(3).``, where the trailing
#:     table pipe is why ``_looks_like_wrapped_reference`` could not see it;
#:   * a subsection the SOURCE prints empty -- Sales Tax 01-07-2014 page 96 sets
#:     a bare ``(3)`` between section 72C's sub-section (2) and section 73.
#:
#: None of the three is a list item, and rendering them as running text keeps
#: every word (only the <li> wrapper changes) while the shape stops asserting a
#: subsection that has no provision in it.
_MARKER_ONLY_LINE = re.compile(r"^\(\s*[\dA-Za-z]{1,4}\s*\)\s*[.\]]?\s*$")


def _looks_like_wrapped_reference(plain: str, prev_plain: str, mre) -> bool:
    """True when a line-initial "(x)" is a wrapped cross-reference, not a list item."""
    m = mre.match(plain.lstrip())
    if not m:
        return False
    prev = prev_plain.rstrip()
    # (a) the previous line ends on a cross-reference noun ("...sub-section" /
    #     "...clause") -> the "(x)" is that reference's number, a continuation.
    if _PREV_XREF_NOUN.search(prev):
        return True
    # (b) "(x) of ..." after a mid-sentence connective, with no list terminator.
    nxt = re.match(r"([A-Za-z]+)", plain.lstrip()[m.end():].lstrip())
    if not (nxt and nxt.group(1).lower() in _REF_CONT):
        return False
    return bool(_PREV_MIDSENTENCE.search(prev)) and not _PREV_LIST_SEP.search(prev)


# ---------------------------------------------------------------------------
# PDF-faithful block layout inside a paragraph / list item
#
# The PDF sets several kinds of line apart from the running paragraph text:
#   * formulas    -- short symbol-only lines centred between the margins
#                    ("A x B/C", "(A + B) – C"), including the stacked
#                    fraction "A x 15" printed over "85" with a bar (sec 233);
#   * provisos    -- "Provided that ..." always opens its own indented line;
#   * explanations-- "Explanation. – ..." likewise;
#   * definitions -- "“term” means ..." lines in an unnumbered definition run;
#   * omitted brackets -- an empty amendment bracket ("5[ ]") on its own line.
# plain_text (line-based) already preserves these breaks; the html renderer
# used to glue them into the surrounding paragraph.  Each such line is wrapped
# in a display:block span so the html shows the same break without changing
# the list/paragraph structure (or plain_text) at all.
# ---------------------------------------------------------------------------

_FORMULA_CHARS_RE = re.compile(r"^[\s()\[\]A-Z0-9x×+/=%.,*–—¼½¾⅓⅔⅛“”\"-]+$")
_BRACKET_ROW_RE = re.compile(r"^\s*(?:[\d*]{1,3}\s*\[\s*\]\s*)+$")
# optional citation-marker prefix on a block-opening line: "8[Provided",
# "9[: Provided further", "1[“scientific ..."
_BLOCK_PREFIX_RE = re.compile(r"^\s*[\d*]{0,3}\s*\[?\s*:?\s*")
_DEFN_RE = re.compile(r"^[“\"][^”\"]{1,60}[”\"]\s*(?:means|includes|,\s*in relation to)")


def _is_formula_line(plain: str, line, page_left: float, page_right: float,
                     require_centre: bool = True) -> bool:
    """A centred, symbol-only standalone line ("A x B/C", "(A + B) – C", "85").

    ``require_centre=False`` accepts the same shape indented at the paragraph
    margin instead of centred -- the caller only does that when the line is
    sandwiched between its intro and its legend, which is proof enough.
    """
    s = plain.strip()
    if not (1 <= len(s) <= 40) or not _FORMULA_CHARS_RE.match(s):
        return False
    if re.search(r"[A-Z]{2,}", s) or not re.search(r"[A-Z0-9]", s):
        return False
    if line is None or not getattr(line, "words", None) or page_right - page_left < 200:
        return False
    if not require_centre:
        return True
    x0 = min(w.x0 for w in line.words)
    x1 = max(w.x1 for w in line.words)
    centre = (page_left + page_right) / 2.0
    return (x0 > page_left + 50 and x1 < page_right - 50
            and abs((x0 + x1) / 2.0 - centre) < 40)


def _block_class(plain: str) -> str | None:
    """CSS class when this line opens its own block in the PDF, else None."""
    s = _BLOCK_PREFIX_RE.sub("", plain.strip(), count=1)
    if s.startswith("Provided"):
        return "proviso"
    if s.startswith("Explanation"):
        return "explanation"
    if _DEFN_RE.match(s) or _DEFN_RE.match(plain.strip()):
        return "defn"
    return None


def _stacked_fraction(a, b) -> bool:
    """True when line *b* sits directly under *a*, horizontally inside it."""
    la, pa = a
    lb, pb = b
    if la is None or lb is None or pa != pb:
        return False
    ax0 = min(w.x0 for w in la.words)
    ax1 = max(w.x1 for w in la.words)
    bx0 = min(w.x0 for w in lb.words)
    bx1 = max(w.x1 for w in lb.words)
    return 0 < (lb.top - la.top) < 20 and bx0 >= ax0 - 6 and bx1 <= ax1 + 6


#   "namely: —", "equal to-", "namely:—", "namely:–" (the corpus mixes hyphen,
#   en dash, em dash and the two box-drawing look-alikes in this position)
_FORMULA_INTRO_END = (":",) + tuple(DASHES)
#: ...and the intro must NAME the formula.  Every real formula in this corpus is
#: introduced by "computed according to the following formula" / "calculated by
#: the following formula"; see ``_layout_blocks.is_formula`` (ledger P44).
_FORMULA_INTRO_WORD = re.compile(r"\bformula\b", re.IGNORECASE)

# A formula's legend: the PDF prints "where —" and one line per symbol under the
# centred formula ("A is the total tax paid ...", "B is-", "C means ...").  Only
# ever consulted on the lines directly following a formula block, so ordinary
# prose that happens to open with "A is" is never affected.
_LEGEND_WHERE_RE = re.compile(
    r"^\s*[Ww]here\s*[,;:.—–-]*\s*$"          # "where —" on its own line
    r"|^\s*[Ww]here\s+[A-Z]\s+(?:is|means)\b")  # one-symbol legend: "where A is ..."
_LEGEND_SYMBOL_RE = re.compile(r"^\s*[A-Z]\s*(?:is|means)\b")


def _is_legend_line(plain: str) -> bool:
    return bool(_LEGEND_WHERE_RE.match(plain) or _LEGEND_SYMBOL_RE.match(plain))


def _layout_blocks(rows, geoms):
    """Wrap formula / proviso / definition / empty-bracket rows in block spans.

    rows  = [(kind, plain, html)];  geoms = matching [(Line|None, page)].
    Only plain "text" rows are touched; kinds, order and plain stay intact
    (a folded block keeps its lines newline-joined in the plain slot).
    """
    lines = [ln for (ln, _) in geoms if ln is not None and getattr(ln, "words", None)]
    if not lines:
        return rows
    left = min(min(w.x0 for w in ln.words) for ln in lines)
    right = max(max(w.x1 for w in ln.words) for ln in lines)

    def is_formula(idx: int, after_formula: bool) -> bool:
        kind, plain, _ = rows[idx]
        if kind != "text":
            return False
        prev = rows[idx - 1][1].rstrip() if idx else ""
        # An intro line ends on ":" or a dash AND says what it is introducing.
        # Ledger P44: ending on a colon is what thousands of amending clauses do
        # ("...the following shall be substituted, namely:—"), so the punctuation
        # alone made a formula out of any short numeric line that followed one.
        # Measured over every ``<span class="formula">`` in the corpus -- 20 of
        # them -- **6 are real and all 6 are introduced by the words "the
        # following formula"**; the other 14 are a serial number (`5`, `7`, `29`,
        # `32`, `38`, `56`, `236`), a rate (`"0.75%`), and the four wrapped cells
        # of Finance Act 2025's income-tax rate table (`1,200, 000/-`, ...), whose
        # next column then read as a legend and produced the whole of that
        # edition's `no_inline_formula_legend` failure.
        #
        # The word is looked for across the last few rows, not just the one
        # immediately above: the introducing sentence wraps, and its LAST line is
        # often only "namely: —" ("...shall be computed according to the\n
        # following formula, namely: —"), which is how requiring it on ``prev``
        # alone dropped Finance Act 2025's own genuine "(A/B) x C".
        lead = " ".join(rows[j][1] for j in range(max(0, idx - 3), idx))
        intro = bool(prev.endswith(_FORMULA_INTRO_END)
                     and _FORMULA_INTRO_WORD.search(lead))
        # some prints indent the formula at the paragraph margin instead of
        # centring it (s.168 "(A/B) x C").  Sandwiched between its intro
        # ("namely:—") and its legend ("Where —"), it is unmistakably a formula,
        # so the centring test is dropped for that one shape.
        legend_next = (idx + 1 < len(rows) and rows[idx + 1][0] == "text"
                       and _is_legend_line(rows[idx + 1][1]))
        if not _is_formula_line(plain, geoms[idx][0], left, right,
                                require_centre=not (intro and legend_next)):
            return False
        if after_formula:      # fraction denominator under a formula line
            return True
        return intro

    out = []
    i, n = 0, len(rows)

    def fold(i: int, cls: str, stop_legend: bool) -> int:
        """Emit rows[i] as a ``cls`` block, folding its wrapped tail into it."""
        buf, plains = [rows[i][2]], [rows[i][1]]
        j = i + 1
        # a block runs until the next list marker / table / block opener
        while (j < n and rows[j][0] == "text" and not is_formula(j, False)
               and not _BRACKET_ROW_RE.match(rows[j][1])
               and _block_class(rows[j][1]) is None
               and not (stop_legend and _is_legend_line(rows[j][1]))):
            buf.append(rows[j][2])
            plains.append(rows[j][1])
            j += 1
        out.append(("text", "\n".join(plains),
                    f'<span class="{cls}" style="display:block; '
                    f'margin:0.5em 0 0 1.5em;">{" ".join(x for x in buf if x)}</span>'))
        return j

    def emit_legend(i: int) -> int:
        """Give each legend line under a formula its own block, as the PDF sets
        them ("where —" / "A is ..." / "B is-"), instead of folding the whole
        legend back into the paragraph that introduced the formula."""
        while i < n and rows[i][0] == "text" and _is_legend_line(rows[i][1]):
            i = fold(i, "legend", True)
        return i

    while i < n:
        kind, plain, html = rows[i]
        if kind != "text":
            out.append(rows[i])
            i += 1
            continue
        if is_formula(i, False):
            if i + 1 < n and is_formula(i + 1, True) and \
                    _stacked_fraction(geoms[i], geoms[i + 1]):
                den_plain, den_html = rows[i + 1][1], rows[i + 1][2]
                frac = ('<span class="formula" style="display:block; '
                        'text-align:center; margin:0.5em 0;">'
                        '<span class="frac" style="display:inline-block; '
                        'text-align:center; vertical-align:middle;">'
                        f'<span style="display:block;">{html}</span>'
                        '<span style="display:block; border-top:1px solid '
                        f'currentColor;">{den_html}</span></span></span>')
                # RC-7: html keeps the real stacked numerator-over-bar-over-
                # denominator; plain_text must carry a division indicator, so emit
                # the fraction as "(<numerator>) / <denominator>" -- e.g. the
                # s.233(2A) formula "A x 15" over "85" -> "(A x 15) / 85".
                out.append(("text",
                            f"({plain.strip()}) / {den_plain.strip()}", frac))
                i = emit_legend(i + 2)
                continue
            out.append(("text", plain,
                        '<span class="formula" style="display:block; '
                        f'text-align:center; margin:0.5em 0;">{html}</span>'))
            i = emit_legend(i + 1)
            continue
        if _BRACKET_ROW_RE.match(plain):
            out.append(("text", plain,
                        f'<span class="omitted-bracket" style="display:block;">{html}</span>'))
            i += 1
            continue
        cls = _block_class(plain)
        if cls:
            i = fold(i, cls, False)
            continue
        out.append(rows[i])
        i += 1
    return out


def _render_line_run(line_refs, footnote_map, off_fn, cited, subheads=False):
    """Render a run of Line refs: gridless-table fallback + per-line rendering."""
    from .tables import find_table_spans, render_table

    spans = find_table_spans(line_refs)
    span_start = {s: e for (s, e) in spans}
    rows = []
    geoms = []   # (Line|None, page) matching rows -- for _layout_blocks
    i = 0
    n = len(line_refs)
    prev_plain = ""
    while i < n:
        if i in span_start:
            end = span_start[i]
            region = line_refs[i:end]
            html = render_table(region)
            if html:
                # markers on the table's own lines never reach _render_line --
                # register their citations so the footnotes stay on this leaf
                if cited is not None:
                    for r in region:
                        for w in sorted(r.line.words, key=lambda w: (w.top, w.x0)):
                            if w.is_marker:
                                cited.append((r.page, w.text.strip()))
                plain = "\n".join(r.line.text() for r in region)
                rows.append(("table", plain, html))
                geoms.append((None, region[0].page))
                prev_plain = plain
                i = end
                continue
        r = line_refs[i]
        plain, html = _render_line(r.line, r.page, footnote_map, off_fn(r.page), cited)
        if plain.strip():
            kind = _classify(plain)
            # Context-aware guard: only downgrade a "(x)" list marker to running
            # text when it is genuinely a wrapped cross-reference (see
            # _looks_like_wrapped_reference).  A real list item is left as <li>.
            mre = _MARKER_RE_FOR.get(kind)
            if mre is not None and (_looks_like_wrapped_reference(plain, prev_plain, mre)
                                    or _MARKER_ONLY_LINE.match(plain.strip())):
                kind = "text"
            # schedule leaves: a standalone bold rule-heading / sub-heading line
            # becomes its own block instead of merging into a neighbour
            if subheads and kind in ("text", "htext") and _is_subheading(r.line, plain):
                kind = "subhead"
            gcls = _gazette_block_class(plain)
            if gcls and kind in ("text", "htext", "subhead"):
                kind = gcls
            rows.append((kind, plain, html))
            geoms.append((r.line, r.page))
            prev_plain = plain
        i += 1
    return _layout_blocks(rows, geoms)


# ---------------------------------------------------------------------------
# public entry: split body into sections and build them
# ---------------------------------------------------------------------------

# A section heading at the start of a body line.  Real layouts seen:
#   * clean:      "4. Tax on ..."        -> code 4
#   * inserted:   "6 [4B. Super tax ..."  -> code 4B   (leading marker + bracket)
#   * inserted:   "1 [7A . Tax on ..."    -> code 7A   (space before the dot)
#   * inserted:   "4 [ (4AB) Subject ..." -> code 4AB  (parenthesised in bracket)
#   * inserted:   "2 [ 158.Time of ..."   -> code 158
#
# Dot-form is accepted with an optional leading marker (a superscript digit/`*`)
# and optional "[".  Parenthesised codes are only accepted *inside* a bracket,
# so ordinary subsection markers like "(2)" are never mistaken for a heading.
# A heading may carry a RUN of markers ("6,71,76,81[194.") -- see
# grammar.MARKER_PREFIX.  Code grammar is shared too, so 3AAA / 221-A parse.
_HEAD = r"^\s*" + MARKER_PREFIX
#: The decoration between the marker run and the code.  An inserted section is
#: sometimes wrapped in BOTH the amendment bracket and an opening paren that is
#: never closed -- the Customs Act prints s.14A as ``5[(14-A. Provision of
#: accommodation at Customs-ports, etc.-`` and s.21A as ``24[(21A. Power to defer
#: collection of customs-duty.-``.  ``\[?\s*`` cannot step over the ``(`` and
#: ``_BRACKETPAREN_RE`` below needs a closing ``)`` that never comes, so neither
#: section bound and both texts stayed with ss.14/21 in every edition.
#:
#: The paren is admitted ONLY inside the bracket, which is the rule
#: ``_BRACKETPAREN_RE`` already states and this pattern had drifted from.  A BARE
#: ``(`` reads Finance Act 2014's PCT tariff heading ``(90.22).`` as section 90.
#: The mandatory ``\.`` below is what keeps this off an inserted SUBSECTION
#: (``2 [ (5) The Federal Government may ...``, the false accept the comment on
#: ``_BRACKETPAREN_RE`` records as costing thirty sections) -- a subsection
#: marker carries no dot after its code.
#: A SUBSTITUTED section is printed inside its amendment bracket AND inside the
#: quotation marks of the substituting instrument: Sales Tax 15.01.2022 prints
#: s.47A as ``602[“47A. Alternative dispute resolution.—``.  Like the paren, the
#: quote is admitted only INSIDE the bracket -- a quote at the head of a line is
#: otherwise the opening of quoted repealed text, which must never start a
#: section.  ``_BRACKETED_DOTLESS_RE`` already allowed a quote AFTER the code for
#: the same reason; this is the other side of it.
_OPEN = r"(?:\[\s*[“”\"'‘]?\s*\(?\s*|\[?\s*)"
_DOTFORM_RE = re.compile(_HEAD + rf"{_OPEN}({CODE})\s*\.")
# A parenthesised code is only a SECTION when it carries a letter suffix.
# ``CODE`` alone matched an inserted SUBSECTION -- "2 [ (5) The Federal
# Government may, by notification..." on page 40 of the 2007 edition read as
# section 5, and because it sat 8 pages past section 5's real page the tol-8
# fallback took it, advanced the monotonic cursor past pages 32-38 and blocked
# THIRTY later sections into heading-only stubs.  discover.py already required
# a suffix here; the two had drifted.
_BRACKETPAREN_RE = re.compile(_HEAD + rf"\[\s*\(?({CODE_SUFFIXED})\)")
# Bare ``(10) Refund of input tax. —`` (Sales Tax 2009 body): TOC lists it as
# section 10 but the PDF drops the ``10.`` form.  Require a Capitalised title
# so amendment bullets ``(19) in section 120...`` and subsections stay clauses.
_PAREN_SECTION_RE = re.compile(_HEAD + rf"\(({CODE})\)\s+(?=[A-Z\"“\[])")
# A substituted section is wrapped in its amendment bracket and may print no dot
# after the code, with the title opening on a curly quote:
#
#     4 [5 “Delegation of powers.- 5 (1)] The Board may, by notification ...
#
# Requiring the BRACKET keeps this bounded -- a bare "5 The" in running prose
# cannot match, so this cannot manufacture section starts out of body text.
_BRACKETED_DOTLESS_RE = re.compile(
    _HEAD + rf"\[\s*({CODE})\s*[“\"'‘]?\s*[A-Z]")
# The suffix separator may be a DOT or a bare SPACE, not just the hyphen ``CODE``
# allows.  Measured in the shipped corpus:
#
#     3[18.A Special customs duty on imported goods.-      (Customs, 18A)
#     4[83. A Omitted]                                      (Customs, 83A)
#     2[25 AA. Transactions between associates. - -         (Sales Tax, 25AA)
#     2[37 D. Cognizance of offences by Special Judges.-    (Sales Tax, 37D)
#
# ``CODE`` must NOT be widened to ``[-.]?`` to cover this: its separator is
# optional and its letter run may be EMPTY, so ``\d{1,4}[-.]?[A-Z]{0,4}`` matches
# "194." with zero letters and ``_BRACKETED_DOTLESS_RE``'s ``[A-Z]`` then eats the
# title's first letter -- "6[194. Appellate Tribunal.-" becomes code "194.".
# Here both the separator and 1-4 letters are MANDATORY, which is what makes the
# dot safe where widening CODE is not.
#
# Tried BEFORE ``_DOTFORM_RE``, because match ORDER is the actual defect: that
# pattern's mandatory ``\.`` is satisfied by the SEPARATOR dot with the letters
# backtracked away, so it returned "18" and offered 18A's body line to section
# 18 -- 3,201 chars on s.18 against a 43-char 18A stub in the 2007 edition.
#
# The BRACKET is required, and it is the whole guard: a dot- or space-separated
# suffix only ever prints on an INSERTED section, which always carries its
# amendment bracket, while the same shape unbracketed is a tariff or schedule row
# ("9.PDA Closure Devices", "12. ICIC Foundation").
#
# A SPACE separator needs one discriminator more than a dot or hyphen does,
# because a schedule rate row has the same shape ("72[44 Steel billets M. Tons").
# Two suffix letters are enough on their own ("25 AA"); a LONE capital must carry
# its own dot ("37 D." is section 37D, "44 Steel" is not section 44S).
#
# That guard was re-measured over 186,984 distinct body lines and it HAS changed:
# unbracketed instances are no longer all tariff rows.  Two real families print
# the shape with no amendment bracket at all --
#
#     150 ZQR. Application.-The provisions of this Chapter shall apply ...
#     196-A. Statement of case to Supreme Court in certain cases.- If, on an ...
#
# -- an 18-section run of Sales Tax Rules 2006 whose codes the text layer splits
# ("150 ZQR" for 150ZQR), and 32 hyphenated Customs Act sections.  So a SECOND,
# unbracketed alternative is added rather than the bracket gate being dropped.
#
# It is narrower than the bracketed one in three ways, each measured:
#
#   * the dot after the letter run is MANDATORY.  Dropping the bracket with the
#     existing lookahead gains 392 lines, the tariff rows the old note describes
#     ("1 ITEM NAME 7.5 1 9.23 132.23", "10. PDA Delivery System").
#   * the separator may be a HYPHEN or a SPACE but never a DOT.  A dot separator
#     unbracketed is "2. A. Low Priced Cellular Mobile Phones", a rate row, and
#     it is also the TOC's own "150. ZQR. Application [150ZQS. Definitions 110".
#   * a space separator needs 2-4 letters, never a lone capital.  The lone
#     capital unbracketed is "20 T. V. Sets Nos." and "42 G. I. Pipes and MS
#     Pipes", where the letters are an abbreviation, not a suffix.
#
# Together: 48 lines gained, 0 lost.  47 are the two families above; the 48th is
# a TOC leader row ("325 AA. Transactions between associates _____") that mints
# the code 325AA, which no TOC entry carries, so it is indexed and never read.
_DOTSUFFIX_RE = re.compile(
    _HEAD + r"(?:\[\s*\(?\s*(\d{1,4}(?:\s*[-.]\s*[A-Z]{1,4}"
    r"|\s+[A-Z]{2,4}|\s+[A-Z](?=\s*\.)))"
    r"(?=\s*\.\s+[A-Z]|\s+[A-Z])"
    r"|(\d{1,4}(?:\s*-\s*[A-Z]{1,4}|\s+[A-Z]{2,4}))"
    r"(?=\s*\.\s+[A-Z]))")


def _candidate_code(line) -> str | None:
    """The rule code a body line opens with, or None.

    Wrapped so every caller gets the year filter: `CODE` allows four digits (Customs
    Rules runs to 1110), which also admits a YEAR, and these documents print their own
    year on the title line -- "SALES TAX SPECIAL PROCEDURE (WITHHOLDING) RULES, 2007"
    produced a leaf coded 2007 sitting ahead of rule 1.

    The code is FOLDED to its canonical spelling (``grammar.norm_code``) before
    it is returned.  The body and the TOC print the same section differently and
    ``build_sections`` keys ``code_positions`` on this value while looking it up
    by the TOC's ``entry.code``, so the two sides must agree or the section never
    binds at all.  Measured in the shipped corpus: the body prints ``155-I.``,
    ``221-A.``, ``194-A.``, ``18.A``, ``83. A`` and ``38-`` for what the TOC
    lists as ``155I``, ``221A``, ``194A``, ``18A``, ``83A`` and ``38``.  Every
    one of those was a heading-only stub whose text stayed with the preceding
    section -- Federal Excise s.38's alternative-dispute-resolution provision
    sat inside s.37, 3,500-4,500 characters of it, in five editions.  The TOC
    side has always folded (``toc.norm_code``); this side never did.

    Folding here rather than at the ``code_positions`` key so that every caller
    agrees on one spelling -- ``tools/acts/why_unbuilt.py`` reported "code never
    opens a body line" for codes the builder did find, and ``discover.py`` minted
    ``155-I`` as a leaf code where every other edition says ``155I``.
    """
    code = norm_code(_candidate_code_raw(line))
    return code if code and is_code_like(code) else None


#: Marker run plus opening bracket(s) as their own line, the code on the next.
#: Customs 2025 prints s.14A as ``5&7[`` over ``(14A. Provision of security…``;
#: neither line matches ``_DOTFORM_RE`` on its own (the paren is only legal
#: inside ``[`` on the SAME line).
_SPLIT_BRACKET_PREFIX_RE = re.compile(rf"^\s*{MARKER_PREFIX}\[+\s*$")
_BARE_PAREN_SUFFIXED_DOT_RE = re.compile(
    rf"^\s*\(({CODE_SUFFIXED})\s*\.")


def _split_bracket_candidate_code(prev_line, line) -> str | None:
    """Code when the amendment bracket closed on the previous line.

    The paren is still only admitted after a bracket -- just split across the
    line break.  ``CODE_SUFFIXED`` keeps this off ``(90.22).`` and ``(5) The``.
    """
    if prev_line is None or line is None:
        return None
    if not _SPLIT_BRACKET_PREFIX_RE.match((prev_line.text() or "").strip()):
        return None
    m = _BARE_PAREN_SUFFIXED_DOT_RE.match((line.text() or "")[:40])
    if not m:
        return None
    code = norm_code(m.group(1))
    return code if code and is_code_like(code) else None


def _candidate_code_raw(line) -> str | None:
    head = line.text()[:40]
    # FIRST -- before _DOTFORM_RE, whose mandatory dot would otherwise be
    # satisfied by this code's own separator.  See _DOTSUFFIX_RE.
    m = _DOTSUFFIX_RE.match(head)
    if m:
        # two alternatives, two groups: bracketed is 1, unbracketed is 2
        return m.group(1) or m.group(2)
    m = _DOTFORM_RE.match(head)
    if m:
        return m.group(1)
    m = _BRACKETPAREN_RE.match(head)
    if m:
        return m.group(1)
    m = _BRACKETED_DOTLESS_RE.match(head)
    if m:
        return m.group(1)
    # Parenthetical section heading (not a subsection): require ``Title.—``
    # right after the code.  Definition clauses print ``means,–``; amendment
    # bullets open lowercase (``(19) in section``); subsections have no dash.
    m = _PAREN_SECTION_RE.match(head)
    if m:
        rest = line.text()[m.end():].lstrip()
        if rest[:1] not in "\"“'‘" and re.match(
            r"[A-Z][^.]{1,80}\.\s*[—–―─-]", rest
        ):
            return m.group(1)
    return None


# A DOT-LESS inserted section start: "1 [230E Directorate General of ...".
# 230E's body line carries no dot after the code, so _DOTFORM_RE never sees
# it and the section used to survive as a heading-only placeholder.
_DOTLESS_RE = re.compile(_HEAD + rf"\[?\s*({CODE_SUFFIXED})\s+[A-Z]")
# the ".—" family of heading terminators, tolerating space before the dash
_HEADING_DASH_RE = re.compile(r"[.,]\s*[—–―─-]")


def _code_token_index(words) -> int:
    """Index of the token carrying the section code (skips marker/bracket)."""
    for i, w in enumerate(words):
        t = w.text.strip()
        if not t:
            continue
        if w.is_marker or set(t) <= set("[]* "):
            continue
        return i
    return 0


def _bold_title(words, code_i: int, doc_has_bold: bool = True) -> bool:
    """True when the code token or either of the first two alphabetic words
    at/after it prints in the heading's bold face.

    Genuine section titles are set in the bold heading face; definition
    clauses and cross-references that mimic a section start are regular.
    Checking two words (not one) covers starts whose code token kept the
    regular face ("3[6A." / "2 [158.Time").

    On an OCR'd page there is NO font information at all (hOCR carries neither a
    font name nor a bold flag), so the gate cannot be evaluated -- and since it
    gates every section start in ``discover.py``, a scanned act would convert to
    zero sections.  Where no word carries a font name, defer to the caller's
    shape tests (the dot form plus the heading dash) instead of failing closed.
    """
    if not any(w.fontname for w in words[code_i:code_i + 3]):
        return True
    if not doc_has_bold:
        # The document sets NO text in a bold face anywhere, so the gate cannot
        # discriminate and must not veto.  The Finance (Supplementary) Acts are
        # typeset entirely in plain Helvetica -- headings included -- so every
        # candidate was rejected and the whole statute came out with zero
        # sections.  Distinct from the no-fontname case above (an OCR'd page):
        # here a font name IS present, it is simply never bold.
        return True
    checked = 0
    for w in words[code_i:]:
        if "Bold" in (w.fontname or ""):
            return True
        if any(ch.isalpha() for ch in w.text):
            checked += 1
            if checked >= 2:
                break
    return False


def _dotless_candidate_code(line) -> str | None:
    """Same as :func:`_candidate_code` for the dot-less shapes, and folded the
    same way and for the same reason -- see that docstring."""
    code = norm_code(_dotless_candidate_code_raw(line))
    return code if code and is_code_like(code) else None


def _dotless_candidate_code_raw(line) -> str | None:
    """Code of a dot-less section start, or None.

    Without the dot the shape is much weaker, so acceptance is gated three
    ways: the code must be letter-suffixed (only inserted sections print
    dot-less), the title must be in the bold heading face, and the heading
    dash must sit on the same line.  In TOC mode the caller's expected-page
    anchor and monotonic-order rules constrain it further.
    """
    text = line.text()
    m = _DOTLESS_RE.match(text[:40])
    if not m or not _HEADING_DASH_RE.search(text):
        return None
    words = sorted(getattr(line, "words", []), key=lambda w: w.x0)
    if not words or not _bold_title(words, _code_token_index(words)):
        return None
    return m.group(1)


def own_heading_prefix_start(body_refs, pos: int, floor: int,
                             page_footnotes) -> int:
    """Pull a section's start index back over its own split-bracket prefix.

    A live section that was inserted and later substituted/re-enacted opens
    with a NESTED bracket pair that can span two physical lines: an empty
    bracket for the anonymous insertion note directly above the heading line
    (printed page 175 renders 100C as "1[  ]" above "2[100C. ...", footnote 1
    being "Inserted by the Finance Act, 2014.").  Those bracket lines are part
    of THIS section's heading region -- left in place they become the previous
    section's tail and carry the insertion footnote to the wrong leaf.  Walks
    upward from ``pos`` over same-page bracket-only lines whose markers all
    anchor anonymous history notes; never crosses ``floor`` (the previous
    section's start).  The omitted-section variant of the same layout is
    handled by ``pipeline.claim_placeholder_lines``.
    """
    new_pos = pos
    i = pos - 1
    while i > floor:
        r = body_refs[i]
        t = r.line.text().strip()
        if not t:
            i -= 1
            continue
        if (r.page == body_refs[pos].page and "[" in t
                and BRACKETS_ONLY_RE.match(t)
                and all_markers_anonymous(r, page_footnotes)):
            new_pos = i
            i -= 1
            continue
        break
    return new_pos


def _container_heading_pieces(containers) -> set:
    """The text pieces a CHAPTER/PART/Division node already holds as its own code
    or title, so the same line is never emitted twice as leaf/preamble text.

    ``discover`` builds a container's heading by joining up to two body lines after
    the structural heading, so match either the whole piece or a line contained in
    it (the join is lossy about the original line breaks).
    """
    out = set()
    for node in containers or ():
        for part in (getattr(node, "code", ""), getattr(node, "heading", "")):
            for piece in re.split(r"\s{2,}|\n", part or ""):
                piece = re.sub(r"\s+", " ", piece).strip()
                if len(piece) > 2:
                    out.add(piece)
    return out


def _title_stems(text: str) -> list:
    """A heading as comparable 5-character token stems.

    Truncated because the TOC and the body disagree on inflection and
    punctuation for the same title -- the 2007 Customs TOC says "duplicates of
    customs' document" where the body prints "duplicate of customs document".
    Everything after a heading terminator is dropped: the body runs its title
    straight into the provision text on the same line.
    """
    head = re.split(r"[.,]\s*[-—–―─]|\.\s", text, maxsplit=1)[0]
    from .toc import strip_foreign_caption_tail
    head = strip_foreign_caption_tail(head)
    out = []
    for tok in re.findall(r"[A-Za-z]+", head):
        out.append(tok.lower()[:5])
    return out


def _title_prefix_matches(want: list, got: list) -> bool:
    """Whether ``got`` opens with ``want``'s title, allowing one stem to differ.

    Compares the first six stems (or the whole title if shorter) and needs at
    least four of them, with at most one mismatch, so a heading that merely
    shares an opening word cannot qualify.
    """
    n = min(len(want), len(got), 6)
    if n < 4:
        return False
    return sum(1 for a, b in zip(want[:n], got[:n]) if a != b) <= 1


def build_sections(body_refs: list[LineRef], ordered_sections,
                   footnote_map: dict, page_footnotes: dict,
                   page_offset: int = 19, printed_by_page: dict | None = None,
                   containers=(), cited_footnotes: dict | None = None) -> dict:
    """Split ``body_refs`` into sections keyed by section code.

    Boundary detection is code-driven, page-anchored and non-stalling:

      * We index every body line that opens with a section code.
      * Each section's heading must appear on/near its expected PDF page
        (``printed_page + page_offset``).  This page anchor is what keeps a
        stray ``8.`` deep in the body from being mistaken for the section-8
        heading -- without it, one false match poisons every later section.
      * Matches must stay monotonic (after the previous section's start).

    Sections whose code never appears in the body near its page (e.g. fully
    omitted ones that live only in a footnote) are skipped and later emitted as
    empty placeholders, exactly as the reference format does.
    """
    from collections import defaultdict

    ordered = list(ordered_sections)

    # Where a TOC printed page maps to in the PDF, measured from the folios the
    # pages actually print rather than computed as printed + constant offset.
    # A single global offset assumes the two run in lockstep for the whole
    # document; they do not.  The 11.03.2019 Customs edition drifts from 9 to 14
    # pages, so 247 of its 312 sections fell outside the +/-8 page anchor and
    # collapsed to placeholders -- including s.156, whose 1,391-word penalty
    # table was the entire body-conservation shortfall.  Schedules already used a
    # per-page offset for exactly this reason.
    page_of_printed: dict[int, int] = {}
    for pdf_pg, printed in sorted((printed_by_page or {}).items()):
        page_of_printed.setdefault(printed, pdf_pg)

    def expected_page(entry) -> int:
        got = page_of_printed.get(entry.printed_page)
        return got if got is not None else entry.printed_page + page_offset

    code_positions: dict[str, list[int]] = defaultdict(list)
    for idx, ref in enumerate(body_refs):
        cc = _candidate_code(ref.line) or _dotless_candidate_code(ref.line)
        start_idx = idx
        if not cc and idx > 0:
            prev = body_refs[idx - 1]
            if prev.page == ref.page:
                cc = _split_bracket_candidate_code(prev.line, ref.line)
                if cc:
                    start_idx = idx - 1
        if cc:
            code_positions[cc].append(start_idx)
    # body-driven entries (TOC-less editions) carry their heading LineRef;
    # resolve those by IDENTITY -- exact, and it survives the second
    # build_sections pass after claim_placeholder_lines filters body_refs,
    # because heading lines are never claimed
    pos_of_ref = {id(r): i for i, r in enumerate(body_refs)}

    starts: list[tuple[int, object]] = []
    last = -1
    # Rolling drift of the TOC's page column against the pages the body really
    # uses, measured on the sections already placed.  A constant offset assumes
    # the two paginations advance in lockstep; the 11.03.2019 edition proves they
    # need not -- its TOC page column runs progressively AHEAD of its own body
    # (0 pages at s.1, +8 by s.32, +13 from s.79 on, and the folios its pages
    # print agree with the body, not the TOC).  Past +/-8 the page anchor then
    # missed every candidate: 105 of 312 sections collapsed to heading-only
    # stubs (incl. s.156 and its 1,391-word penalty table, the whole
    # conservation shortfall), and the gap-fill bound ss.78/80/81 to penalty-
    # TABLE ROW SERIALS ("78. If any person on board ...") 57 pages away.
    # The median over a short window is robust to one bad match, and where the
    # two paginations do agree (the other 19 editions) it stays 0.
    drift_window: list[int] = []
    for k, entry in enumerate(ordered):
        a = getattr(entry, "anchor", None)
        if a is not None:
            pos = pos_of_ref.get(id(a))
            if pos is not None and pos > last:
                starts.append((pos, entry))
                last = pos
            continue
        drift = (int(_median(drift_window)) if len(drift_window) >= 3 else 0)
        expected = expected_page(entry) + drift
        positions = [p for p in code_positions.get(entry.code, []) if p > last]
        nxt = next((e for e in ordered[k + 1:] if e.printed_page), None)
        # Look ahead ONE entry before choosing, not after.  The ordering guard
        # below rejects a match that sits past where the next entry is expected;
        # it cannot see a match that sits past where the next entry actually
        # PRINTS, and the tolerance ladder walks outward from the expected page,
        # so a nearby wrong candidate is reached before a distant right one.
        # Sales Tax 15.9.2021: s.3 is expected on page 34 and its code opens a
        # body line on 28 and on 37.  The whole block runs about six pages ahead
        # of its own TOC, so 28 is the real heading -- but tol=4 reaches 37
        # first, the cursor jumps to it, and ss.3A/3AA/3B/4/5/6/7 all print
        # BEFORE it and are blocked.  Seven entries starved by one choice, five
        # of them register hits.
        # Only ever a tie-break BETWEEN candidates: with one candidate, or where
        # every candidate starves the next entry (its code may not open a body
        # line at all), the filter is skipped and the ladder decides as before.
        if nxt is not None and len(positions) > 1:
            nxt_positions = code_positions.get(nxt.code, ())
            viable = [p for p in positions if any(q > p for q in nxt_positions)]
            if viable:
                positions = viable
        pos = None
        for tol in (2, 4, 8):
            near = [p for p in positions
                    if abs(body_refs[p].page - expected) <= tol]
            if near:
                # closest to the expected page, breaking ties by document order
                pos = min(near, key=lambda p: (abs(body_refs[p].page - expected), p))
                break
        if pos is not None:
            # Ordering guard: sections are printed in order, so a match cannot
            # sit past the page where the NEXT entry is expected.  Without this a
            # single false match anywhere poisons the monotonic cursor and every
            # subsequent section collapses to a placeholder -- the failure mode
            # that cost the 2007 edition 30 sections.  Rejecting the match leaves
            # this one entry as a placeholder instead of thirty.
            if nxt is not None and body_refs[pos].page > expected_page(nxt) + drift + 8:
                continue
            # The TOC can list the SAME code twice (a section omitted and later
            # re-inserted under its old number, e.g. 236Y).  The single body
            # heading must go to whichever TOC row expects it closest; the
            # other row stays unmatched and becomes a placeholder.
            dist = abs(body_refs[pos].page - expected)
            if any(e2.code == entry.code
                   and abs(body_refs[pos].page - expected_page(e2) - drift) < dist
                   for e2 in ordered[k + 1:]):
                continue
            starts.append((pos, entry))
            last = pos
            drift_window.append(body_refs[pos].page - expected_page(entry))
            del drift_window[:-5]

    # Second pass -- gap fill for a stale/typo'd TOC page.  The primary match
    # anchors each entry within +/-8 pages of its printed TOC page; a single
    # outlier page number defeats it (the 31.07.2025 TOC lists s.207 on page 404
    # though it prints on 417 -- 15 pages before s.208's own 419 -- so s.207
    # collapsed to a heading-only placeholder and its body folded into s.206).
    # An entry the primary pass skipped can still be placed when its code has an
    # unclaimed body heading BETWEEN its already-matched ordered neighbours.
    # Bounding the search to that gap (never an arbitrary far candidate) keeps a
    # spurious same-code hit elsewhere from stealing the slot and cannot advance
    # the monotonic cursor of the primary pass.  Placeholders remain reserved for
    # truly omitted sections, whose code has no body heading at all.
    matched_pos = {id(e): p for p, e in starts}
    if len(matched_pos) < len(ordered):
        claimed = set(matched_pos.values())
        added = []
        for k, entry in enumerate(ordered):
            if id(entry) in matched_pos:
                continue
            cands = code_positions.get(entry.code) or []
            if not cands:
                continue
            lo = -1
            for e2 in reversed(ordered[:k]):
                if id(e2) in matched_pos:
                    lo = matched_pos[id(e2)]
                    break
            hi = len(body_refs)
            for e2 in ordered[k + 1:]:
                if id(e2) in matched_pos:
                    hi = matched_pos[id(e2)]
                    break
            gap = [p for p in cands if lo < p < hi and p not in claimed]
            if not gap:
                continue
            expected = expected_page(entry)
            p = min(gap, key=lambda p: (abs(body_refs[p].page - expected), p))
            matched_pos[id(entry)] = p
            claimed.add(p)
            added.append((p, entry))
        if added:
            starts.extend(added)
            starts.sort(key=lambda t: t[0])

    # Third pass -- the section whose code the PRINTER omitted.  Some editions
    # simply do not set the number: page 227 of the 2007 Customs edition opens
    # s.204 as "Issue of certificate and duplicate of customs document.- A
    # certificate or a", with the title's first word at x0=94.1 (exactly
    # body_left) and the only "204" on the page being the 9.5pt folio in the
    # bottom margin.  No grammar change can reach that -- there is no code to
    # match -- so the entry stayed a placeholder and its text folded into s.203A.
    #
    # The TOC still knows the title, so match on THAT, under every constraint the
    # code-anchored passes use plus two more: the entry must have no code-anchored
    # candidate ANYWHERE (so this can never outbid a real code match), and the
    # body line must not itself open with any section code (so it cannot steal a
    # line the earlier passes deliberately rejected).  Titles are compared on
    # 5-character token stems because the TOC and the body disagree on inflection
    # and punctuation ("duplicates of customs' document" vs "duplicate of customs
    # document").
    if len(matched_pos) < len(ordered):
        claimed = set(matched_pos.values())
        added = []
        # ``body_refs`` is in page order, so the +/-2 page window this pass allows
        # is a contiguous index range.  Resolving it by bisect keeps the scan to
        # the ~5 candidate pages: walking the whole (lo, hi) gap and filtering by
        # page inside the loop is O(unmatched entries x body_refs), which is fine
        # on a document where the first two passes place nearly everything and
        # quadratic on one where they do not.  Measured output-identical.
        import bisect as _bisect
        _pages = [r.page for r in body_refs]

        def _page_window(centre: int, tol: int = 2) -> tuple:
            return (_bisect.bisect_left(_pages, centre - tol),
                    _bisect.bisect_right(_pages, centre + tol))

        for k, entry in enumerate(ordered):
            if id(entry) in matched_pos or code_positions.get(entry.code):
                continue
            want = _title_stems(getattr(entry, "heading", "") or "")
            if len(want) < 3:
                continue
            lo = -1
            for e2 in reversed(ordered[:k]):
                if id(e2) in matched_pos:
                    lo = matched_pos[id(e2)]
                    break
            hi = len(body_refs)
            for e2 in ordered[k + 1:]:
                if id(e2) in matched_pos:
                    hi = matched_pos[id(e2)]
                    break
            expected = expected_page(entry)
            wlo, whi = _page_window(expected)
            best = None
            for pos in range(max(lo + 1, wlo, 0), min(hi, whi, len(body_refs))):
                if pos in claimed:
                    continue
                ref = body_refs[pos]
                if getattr(ref.line, "is_table", False):
                    continue
                text = ref.line.text()
                if not _HEADING_DASH_RE.search(text):
                    continue
                if _candidate_code(ref.line) or _dotless_candidate_code(ref.line):
                    continue
                words = sorted(ref.line.words, key=lambda w: w.x0)
                if not _bold_title(words, 0, True):
                    continue
                if not _title_prefix_matches(want, _title_stems(text)):
                    continue
                d = (abs(ref.page - expected), pos)
                if best is None or d < best[0]:
                    best = (d, pos)
            if best is not None:
                matched_pos[id(entry)] = best[1]
                claimed.add(best[1])
                added.append((best[1], entry))
        if added:
            starts.extend(added)
            starts.sort(key=lambda t: t[0])

    # pull each start back over the section's own split-bracket prefix (see
    # own_heading_prefix_start) -- AFTER all starts are known, so the walk can
    # never cross into the previous section's heading
    for k in range(len(starts)):
        pos, entry = starts[k]
        floor = starts[k - 1][0] if k else -1
        starts[k] = (own_heading_prefix_start(body_refs, pos, floor,
                                              page_footnotes), entry)

    # A segment ends at the next structural heading (``_build_one``'s cut), so the
    # text between that heading and the NEXT section belonged to nothing and was
    # dropped.  Hand it to that next section instead: it sits inside the container
    # the heading opens, which is the container that section belongs to.
    #
    # Measured on Income Tax (Third Amendment) 2016, 346 missing words of 1,938
    # (82.147%): it reproduces a Schedule whose PART headings run to three lines,
    # so ``FALLING UNDER SUB-SECTION (1) OF SECTION 99A`` plus rules 1-3 -- rejected
    # by the monotonic cursor because the host's clause numbering had already passed
    # them -- sat between ``PART I`` and the first accepted rule and reached no leaf.
    #
    # Only lines the tree does not already hold are moved: the boundary line itself
    # and the (up to two) lines ``discover`` consumed as the container's title, or
    # the change would print "CHAPTER II"/"PRELIMINARY" at the head of every
    # chapter-opening section in the corpus.
    consumed = _container_heading_pieces(containers)
    for k in range(len(starts) - 1):
        lo, hi = starts[k][0], starts[k + 1][0]
        b = next((i for i in range(lo + 1, hi)
                  if is_structural_boundary(body_refs[i].line.text())), None)
        if b is None:
            continue
        j, pending = b + 1, 2
        while j < hi and pending:
            t = re.sub(r"\s+", " ", body_refs[j].line.text()).strip()
            if not t:
                j += 1
                continue
            if is_structural_boundary(body_refs[j].line.text()):
                j, pending = j + 1, 2
                continue
            if any(t == c or (len(t) > 8 and t in c) for c in consumed):
                j, pending = j + 1, pending - 1
                continue
            break
        if j < starts[k + 1][0]:
            starts[k + 1] = (j, starts[k + 1][1])

    # keyed by the TOC entry's identity, NOT its code: duplicate-code rows must
    # not share one body
    built: dict[int, BuiltSection] = {}
    for k, (start_idx, entry) in enumerate(starts):
        end_idx = starts[k + 1][0] if k + 1 < len(starts) else len(body_refs)
        seg = body_refs[start_idx:end_idx]
        if seg:
            try:
                built[id(entry)] = _build_one(entry, seg, footnote_map,
                                              page_footnotes, page_offset,
                                              is_last=(k + 1 == len(starts)),
                                              printed_by_page=printed_by_page,
                                              cited_footnotes=cited_footnotes)
            except Exception as exc:  # never let one bad section kill the run
                import sys
                print(f"[fbr] warning: section {entry.code} failed: {exc}",
                      file=sys.stderr)
    return built


def preamble_refs(body_refs, ordered_sections, containers=()):
    """The body lines before the first section (the enacting preamble).

    The preamble ends at the first section's own anchor line, and every line
    before it that is not already held elsewhere in the tree belongs here.  It
    must NOT end at the first structural heading, and it must NOT end at the
    first line that merely *matches* the opening section's code:

    * A gazette Finance Act prints ``PART I`` (its own division label) on page 1,
      ahead of the notification, the ``A CT NO. X OF 2024`` title, the long
      title, ``WHEREAS ...`` and ``It is hereby enacted as follows:—``.  Cutting
      at that structural heading left the whole enacting preamble held by
      nothing: after it, before section 1, no leaf claims those lines.  Measured
      on the gazette family -- Finance Act 2024 lost 23 body words this way,
      Finance Act 2011-12 lost 55 and the Voluntary Declaration of Domestic
      Assets Act 2018 lost 23, each of them page 1 and 2 in full.
    * The Voluntary Declaration Act's page 1 is a declaration FORM whose numbered
      blanks print as bare ``3.``, ``4.``, ``1.``, ``2.``; ``_candidate_code``
      answers ``1`` on a form field, so the old scan cut there and the preamble
      came out as ``3. 4. 5. 6. B. IMMOVABLE PROPERTY``.  ``discover`` already
      decided where section 1 really starts (its ``anchor``), so use that
      decision rather than making the same guess a second time and differently.

    ``containers`` are the structural nodes whose code/heading text was consumed
    from these very lines (``discover`` takes up to two lines after a
    CHAPTER/PART/Division heading as its title).  Those lines are dropped, which
    is what the structural cut was really protecting: without it "CHAPTER I" and
    "PRELIMINARY" would appear both as the chapter title and as trailing text in
    the preamble.
    """
    end = None
    first = ordered_sections[0] if ordered_sections else None
    anchor = getattr(first, "anchor", None) if first is not None else None
    if anchor is not None:
        for idx, ref in enumerate(body_refs):
            if ref is anchor:
                end = idx
                break
    if end is None:
        # TOC-driven edition: no anchor, so fall back to the opening code -- but
        # still take the LAST such line before any structural heading, since the
        # TOC path has no form-field problem and its preamble precedes CHAPTER I.
        first_code = first.code if first is not None else None
        for idx, ref in enumerate(body_refs):
            if _candidate_code(ref.line) == first_code:
                end = idx
                break
            if is_structural_boundary(ref.line.text()):
                end = idx
                break
    if not end:
        return []

    consumed = _container_heading_pieces(containers)

    # Drop a consumed heading line only where ``discover`` consumed it: in the two
    # lines FOLLOWING the structural heading (its own ``pending_left = 2``).  A
    # gazette Act reprints its masthead on the next page too -- Finance Act 2014
    # prints "NATIONAL ASSEMBLY" / "SECRETARIAT" on page 1 and "NATIONAL ASSEMBLY
    # SECRETARIAT" again on page 2 -- and dropping every line that matches the
    # container's title threw the SECOND copy away as well, losing three words.
    out, pending = [], 0
    for ref in body_refs[:end]:
        text = ref.line.text()
        t = re.sub(r"\s+", " ", text).strip()
        if not t:
            continue
        if is_structural_boundary(text):
            pending = 2
            continue
        if pending and any(t == c or (len(t) > 8 and t in c) for c in consumed):
            pending -= 1
            continue
        pending = 0
        out.append(ref)
    return out


# structural headings that sit *between* sections and must not be swallowed
# into the preceding section's body (e.g. "CHAPTER II", "PART III", "Division IV").
# Matched only when the WHOLE line is the structural code -- otherwise ordinary
# cross-references in body text ("...specified in Division V of Part I...") would
# wrongly truncate a section.
_STRUCTURAL_RE = re.compile(
    r"^(CHAPTER\s+[IVXLC0-9]+|PART\s+[IVXLC0-9]+[A-Z]{0,2}|Division\s+[IVXLC0-9]+[A-Z]{0,2})$",
    re.IGNORECASE)

# leading amendment decoration on a structural heading: superscript marker(s)
# and/or opening bracket(s), e.g. "1[PART VA", "[PART III" (the marker can land
# on its own line, leaving just the bracket)
_STRUCT_DECOR_RE = re.compile(r"^(?:[\d*]{1,3}\s*|\[+\s*)+")


def is_structural_boundary(text: str) -> bool:
    """True when a body line is a CHAPTER/PART/Division heading, tolerating a
    LEADING amendment marker + bracket ("1[PART VA" -- Part VA was inserted by
    the Finance Act, 2003, so its heading wears a citation).  Only leading
    decoration is stripped: a trailing "]" alone must NOT qualify, because a
    wrapped table cell can end "... of Chapter X or\nChapter XII]" and that
    line is body content, not a boundary (section 182's penalty table).
    """
    return bool(_STRUCTURAL_RE.match(_STRUCT_DECOR_RE.sub("", text.strip())))


#: an em/en dash sitting BETWEEN two word characters ("customs–ports") -- a
#: compound separator, not a heading terminator (see _words_after_heading_dash)
_INTERIOR_DASH_RE = re.compile(r"[A-Za-z0-9][—–―─][A-Za-z0-9]")
#: A run of 1-3 ASCII hyphens, and the same run closing a title ("period. --").
#: The heading terminator is not always a single hyphen: Federal Excise Rules
#: prints "78. Extension of time and period. -- Where any rule ..." with a
#: DOUBLE hyphen, as the three tokens `period.` `--` `Where`.
_DASH_RUN_RE = re.compile(r"-{1,3}")
_DOT_DASH_RUN_RE = re.compile(r"[.,]-{1,3}")

# A token that is only the section code plus a trailing dash ("227D.-", "[236C.-"),
# i.e. inserted-code decoration -- NOT the "<title>.-" heading terminator.
_CODE_DASH_RE = re.compile(r"^\[*\(?\d{1,3}[A-Z]{0,3}\)?\.?[-—–―─]$")


def _words_after_heading_dash(words, allow_first=False):
    """Return the content words that follow the heading separator dash.

    The separator is a period followed by an em/en dash (or a hyphen), e.g.
    ``commencement.—`` or ``companies.-``.  Requiring the preceding period keeps
    hyphenated heading words such as ``Cash-basis`` from splitting early.
    Returns ``None`` when the line carries no heading dash.

    The dash can be FUSED with the first operative word into one token
    (``—Any``, ``enterprise.-(1)``) -- the pagemodel re-joins touching glyph
    runs -- so the token is split after its last dash and the remainder is
    kept as the first content word.

    ``allow_first`` permits the dash to be the first token -- used on wrapped
    heading lines whose second line opens with e.g. ``servant.—``.
    """
    from dataclasses import replace
    prev = ""
    for i, w in enumerate(words):
        t = w.text
        em = ("—" in t or "–" in t or "―" in t or "─" in t)
        run = _DASH_RUN_RE.match(t)
        run_len = len(run.group(0)) if run else 0
        # Every hyphen test below reads a RUN, not a single "-".  With a
        # single-hyphen test, Federal Excise Rules 78 ("...and period. -- Where
        # any rule specifies any time or") matched nothing on the line: the
        # heading fell back to the TOC title and the prefix-consumption then
        # dropped the whole first body line, so "Where any rule specifies any
        # time or" was missing from the html while staying in plain_text.
        hit = (em
               or bool(_DOT_DASH_RUN_RE.search(t))
               or (run_len == len(t) > 0 and prev.rstrip().endswith((".", ",")))
               # ...and the hyphen fused to the first operative word, which a
               # scan sets without the space: PSW 2021 prints `20. Delegation.
               # -The Federal may, ...` as the two tokens `Delegation.` `-The`.
               # Ledger P43.  Kept as tight as the bare-hyphen rule above -- the
               # previous token must close the title with "." or "," and what
               # follows the hyphen must open a word, so a wrapped compound
               # ("sub-" / "-section") cannot match.
               or (run_len and len(t) > run_len and t[run_len].isalpha()
                   and prev.rstrip().endswith((".", ","))))
        # An en/em dash INSIDE a word is a compound separator, never the heading
        # terminator: the pre-2012 editions print s.9 as "Declaration of
        # customs–ports, customs airports, etc.-" with an EN DASH where the TOC
        # prints a hyphen, and splitting there cut the <h4> down to
        # "9. Declaration of customs–" and pushed "ports, customs airports,
        # etc.-" into the body as a stray <p>.  A genuine terminator is preceded
        # by "." or "," (kept via _HEADING_DASH_RE) or stands as its own token.
        if hit and em and _INTERIOR_DASH_RE.search(t) \
                and not _HEADING_DASH_RE.search(t):
            prev = t
            continue
        if hit and (i >= 1 or allow_first):
            # A dash that is merely the section-code decoration ("227D.-", the
            # inserted-code marker) is NOT the title terminator -- skip it so the
            # real "<title>.-" dash further along the line ("...regime.-") is the
            # split point and the operative title stays in the heading.
            if _CODE_DASH_RE.match(t):
                prev = t
                continue
            # split the dash token into its heading side (through the dash) and
            # its operative side (anything fused after it), so the caller can
            # render the <h4> from the real heading words and keep the dash.
            head_suffix = oper_suffix = ""
            for pat in (".—", ".–", ".―", ".─", ".-", ",—", ",–", ",-",
                        "—", "–", "―", "─"):
                p = t.rfind(pat)
                if p != -1:
                    head_suffix = t[: p + len(pat)]
                    oper_suffix = t[p + len(pat):]
                    break
            else:
                # A hyphen RUN carries no pattern above ("--", "--Where").  The
                # caller only accepts a heading whose rendered text ENDS in a
                # dash, so the run has to reach the heading side or the split is
                # discarded and the section falls back to its TOC title.
                if run_len:
                    head_suffix, oper_suffix = t[:run_len], t[run_len:]
            before = list(words[:i])
            if head_suffix:
                before.append(replace(w, text=head_suffix))
            # EVERY word after the heading dash on this line is operative body
            # text and must shed the heading's bold, not just a token fused to
            # the dash.  The Customs Act sets the whole heading line bold and
            # opens the body on that same line ("...Customs,.- (1) The
            # Directorate ..."), so the subsection marker arrives as its own
            # token and kept <strong> in six sections.
            rest = [replace(x, fontname=(x.fontname or "").replace("Bold", ""))
                    for x in words[i + 1:]]
            if oper_suffix:
                # the operative text after the heading dash is body text, never
                # the heading's bold -- when the bold dash token fused with the
                # first token ("—The", "accounting.—A", "enterprise.-(1)"), that
                # token inherits the dash's bold font, so drop it whether the
                # token is a WORD ("The") or a subsection MARKER ("(1)").  In the
                # PDF the markers are regular ArialMT (verified for s.1, 106A and
                # 48 more); genuinely-bold schedule paragraph markers come from
                # the real-font path, not this split, so are unaffected.
                fn = (w.fontname or "").replace("Bold", "")
                rest.insert(0, replace(w, text=oper_suffix, fontname=fn))
            return before, rest
        prev = t
    return None


def _find_heading_split(seg, cutoff):
    """Find where a (possibly multi-line) section heading ends.

    Section headings run ``<code>. <title>.—`` and can wrap across up to a few
    lines before the operative text begins.  We scan the first lines for the
    heading-ending dash, stopping as soon as a subsection ``(1)`` / clause
    ``(a)`` begins (which means the heading had no dash form).  Returns
    ``(line_index, heading_words, words_after)`` -- ``heading_words`` are the
    words that make up the heading (up to and including the dash, on line
    ``line_index``) so the caller can render the <h4> from the real body
    heading; ``words_after`` are the operative words that follow.  ``None`` when
    no heading terminator is found.

    The scan stops at a grid-extracted TABLE, which can never be part of a
    heading -- ``discover`` already refuses to let one open a section or carry a
    structural heading, and this is the same rule on the build side.  Ledger
    **P39**: page 30 of Federal Excise 11-03-2019 is read as a grid, so section
    26's whole first block ("26. Power to seize.– (1) The counterfeited
    cigarettes 1[or beverages] ...") arrived as ONE table line; the scan walked
    past it, found the split on the NEXT line's "(2)", and the caller then
    dropped everything up to and including the table as heading region.  The
    section shipped with subsection (2) alone, its six lines of subsection (1)
    present in ``plain_text`` and absent from the ``html`` -- which the
    conservation audit cannot see, because it reads ``plain_text``.
    """
    for li in range(min(4, cutoff)):
        if getattr(seg[li].line, "is_table", False):
            return None
        words = sorted(seg[li].line.words, key=lambda w: w.x0)
        # 1) preferred: the "<title>.—" heading dash
        res = _words_after_heading_dash(words, allow_first=(li > 0))
        if res is not None:
            before, after = res
            return li, before, after
        # 2) inserted sections often have no dash and run straight into "(1)"
        #    (e.g. "99A. ...electricity\nconnections. (1) Notwithstanding...").
        #    Split just before the first subsection marker on the line.  The
        #    marker can be fused with its amendment bracket into one token
        #    ("[(4AB)") -- match through the leading "[".
        from dataclasses import replace
        for i, w in enumerate(words):
            if li == 0 and i == 0:
                continue  # skip the section-code token itself
            t = w.text.strip()
            core = t.lstrip("[")
            if _SUBSEC_TOKEN.match(core):
                before = list(words[:i])
                out = list(words[i:])
                if core != t:
                    out[0] = replace(out[0], text=core)
                return li, before, out
            # ...and the marker can be FUSED to the last word of the title, which
            # is how a scan usually renders it: the Pakistan Single Window Act
            # 2021 prints `3. Establishment of the Pakistan single window.(1) The
            # Federal`, one token `window.(1)`.  Ledger P43 -- sections 3, 10 and
            # 20 of that Act were rejected for want of a terminator this rule
            # could see, and it is the same shape ``_words_after_heading_dash``
            # already splits for a fused dash.  The title side must END on a
            # period, so an ordinary cross-reference ("under clause (b)") is
            # untouched.
            fm = _FUSED_SUBSEC_RE.match(core)
            if fm:
                before = list(words[:i]) + [replace(w, text=fm.group(1))]
                out = [replace(w, text=fm.group(2))] + list(words[i + 1:])
                return li, before, out
    return None


_SUBSEC_TOKEN = re.compile(r"^\((\d{1,3}[A-Z]{0,2}|[a-z]{1,3})\)$")
#: "window.(1)" -- a title whose terminating period is glued to the first
#: subsection marker.  Group 1 is the heading side (through the period), group 2
#: the operative marker.
_FUSED_SUBSEC_RE = re.compile(r"^(.*[A-Za-z]\.)(\((?:\d{1,3}[A-Z]{0,2}|[a-z]{1,3})\))$")


def _is_heading_marker(w, words) -> bool:
    """A superscript citation marker on a heading line.

    ``Word.is_marker``'s absolute size cutoff is tuned against 10pt body
    text; large-type headings scale their superscripts up with them (the
    16pt ``1 [ELEVENTH SCHEDULE`` title carries a 10.6pt marker), so a
    digit/``*`` visibly SMALLER than the heading's own dominant size is also
    a marker.  Small serials only -- a quoted year is never a marker.
    """
    if w.is_marker:
        return True
    t = w.text.strip()
    if not (t == "*" or (t.isdigit() and int(t) < 100)):
        return False
    sizes = [x.size for x in words if any(c.isalpha() for c in x.text)]
    dominant = max(set(sizes), key=sizes.count) if sizes else 10.0
    return w.size <= dominant - 2.0


def _heading_marker_prefix(head_refs, after_ids, footnote_map, off_fn,
                           cited=None) -> str:
    """Render the citation markers found in a dropped heading region.

    Returns html like ``<sup class="cite" title="...">478.1</sup>[`` for the
    ``1[`` that opens ``1[236Y. ...`` -- so a footnote anchored on the heading
    keeps a visible citation even though the heading text itself is replaced
    by the canonical <h4>.  Words whose id is in ``after_ids`` already render
    in the body and are skipped.  When ``cited`` is a list, each rendered
    ``(page, marker)`` is appended so the anchored footnote binds to this leaf.
    A heading marker that does not resolve to note text is ``class="marker"``,
    not an empty-title cite.
    """
    bits: list[str] = []
    for ref in head_refs:
        words = sorted(getattr(ref.line, "words", []), key=lambda w: w.x0)
        for j, w in enumerate(words):
            if id(w) in after_ids or not _is_heading_marker(w, words):
                continue
            marker = w.text.strip()
            title, note_pg = _cite_entry(footnote_map, ref.page, marker)
            # ref names the note's page, not the heading's.  Missing this made a
            # leading heading marker ("54[187A. Presumption of legal
            # character...") render 200.54 while the note it anchors is printed
            # on 208 and attached as 208.54 -- the citation pointed at nothing
            # and the note looked mis-attached.
            src = note_pg if note_pg is not None else ref.page
            cite = f"{src - off_fn(src)}.{marker}"
            if cited is not None:
                cited.append((ref.page, marker))
            frag = _marker_or_cite_sup(cite, marker, title)
            nxt = words[j + 1] if j + 1 < len(words) else None
            if (nxt is not None and id(nxt) not in after_ids
                    and nxt.text.lstrip().startswith("[")):
                frag += "["
            bits.append(frag)
    return "".join(bits)


def printed_page_for(pg: int, printed_by_page: dict, default_offset: int) -> int:
    """The printed folio for a PDF page: its own, else its NEAREST neighbour's.

    A document can carry more than one folio series, and then no single offset is
    right for all of it.  Finance Act, 2022 runs pdf 2 -> folio 1 for its first 255
    pages and then restarts, pdf 273 -> folio 18, so the calibrated modal offset is
    255 -- correct for the second series, and on a first-series page with no folio
    of its own it produced ``page - 255``, i.e. a NEGATIVE printed page minted into
    footnote refs (``-6.^cont``, ``-4.^cont``).

    Falling back to the nearest page that DID print a folio keeps the ref inside
    the series the page actually belongs to, which the global constant cannot do.
    The constant remains the last resort, for a document that prints no folios at
    all, and a result that is still not a plausible page falls back to the PDF
    index rather than emitting a negative one.
    """
    own = printed_by_page.get(pg)
    if own and own > 0:
        return own
    # Deliberately NO interpolation from a neighbouring page.  It was TRIED --
    # "use the nearest page that did print a folio" -- and it re-created the exact
    # defect ``sanitize_printed_pages`` already records: the 15.09.2021 Sales Tax
    # edition prints no footer on almost any page, so one surviving folio spoke
    # for the whole document and minted refs like `93.5` onto sections cited 90
    # pages away (21 ``footnote_on_citing_leaf`` failures, from 0).  Bounding it
    # to +/-10 pages cut that to 2 and still was not the prior behaviour.
    # ``sanitize_printed_pages`` is the component that owns filling in gaps by
    # local consensus, and it votes with its own window; this must not second-guess
    # it.  What is left here is only the guarantee the refs actually needed: never
    # a non-positive printed page.
    got = pg - default_offset
    return got if got > 0 else pg


def adopt_orphan_footnotes(leaves, page_footnotes, printed_by_page, default_offset=19,
                           note_body_pages=None):
    """Attach every parsed footnote that no leaf cited to the content leaf whose
    page range covers it, so no footnote (and its legal text) is ever dropped.

    Works document-wide on leaf dicts (chapters + schedules).  By-citation /
    page-span assignment stays primary; this is the completeness safety net for
    uncited notes -- each orphan is adopted once, by the first leaf spanning its
    PDF page.  The printed-page ref uses the footer number where known (schedules
    have a non-constant offset), else the body offset.
    """
    # Dedup by (ref, text): the PDF misprints duplicate marker numbers on some
    # pages (two "5" footnotes on printed page 92 etc.) -- both texts are real.
    # Counted, not a set, and capped by how many times the SOURCE prints the note:
    # this must collapse the same note read twice by two code paths, and must not
    # collapse one the document really repeats (Federal Excise 07-05-2024 prints
    # the same note three times on page 70 and three times on page 77).
    have: dict = {}
    for lf in leaves:
        for f in lf.get("footnotes", []):
            k = (f["ref"], f["text"])
            have[k] = have.get(k, 0) + 1
    src_mult: dict = {}
    for _pg, _fns in (page_footnotes or {}).items():
        for _fn in _fns:
            k = (_pg, _fn.marker, _fn.text)
            src_mult[k] = src_mult.get(k, 0) + 1
    covered = [lf for lf in leaves
               if lf.get("start_page") is not None and lf.get("end_page") is not None]
    covered.sort(key=lambda lf: (lf["start_page"], lf["end_page"]))
    adopted = 0
    for pg, fns in page_footnotes.items():
        cover = next((lf for lf in covered
                      if lf["start_page"] <= pg <= lf["end_page"]), None)
        if cover is None and note_body_pages:
            # A collector page (the Customs Act prints whole pages of notes after
            # each body run) lies OUTSIDE every leaf's page range, because a
            # leaf's range tracks its body.  Fall back to the body run those
            # notes annotate -- without this, 184 notes on this edition are
            # reachable by neither the citation path nor this net, and their
            # legal text is simply lost.
            for bp in note_body_pages.get(pg, ()):
                cover = next((lf for lf in covered
                              if lf["start_page"] <= bp <= lf["end_page"]), None)
                if cover is not None:
                    break
        if cover is None:
            continue
        printed = printed_page_for(pg, printed_by_page, default_offset)
        for fn in fns:
            ref = f"{printed}.{fn.marker}"
            key = (ref, fn.text)
            if have.get(key, 0) >= src_mult.get((pg, fn.marker, fn.text), 1):
                continue
            have[key] = have.get(key, 0) + 1
            cover.setdefault("footnotes", []).append(
                {"ref": ref, "marker": ref, "text": fn.text, "html": fn.html,
                 "page": pg})
            adopted += 1
    for lf in leaves:
        lf.get("footnotes", []).sort(key=lambda f: ref_sort_key(f["ref"]))
    return adopted


def all_leaves(node):
    """Yield every content-leaf dict (has plain_text) under a tree node."""
    if isinstance(node, dict):
        if "plain_text" in node:
            yield node
        for k in ("parts", "divisions", "sections"):
            for c in node.get(k, []):
                yield from all_leaves(c)


# --- document-level text normalization (RC-5 bare markers, RC-7 hyphen wraps) ---

# A compound split at a line wrap: "<word>-" then a real gap -- a newline (plain)
# OR one-or-more spaces (html joins wrapped lines with a space) -- then a
# lowercase continuation.  The gap is REQUIRED, so a zero-gap mid-line compound
# ("sub-section") is left untouched, and a spaced em-dash ("word - word", space
# BEFORE the hyphen) never matches.
_HYPHEN_WRAP_RE = re.compile(r"([A-Za-z]+)-(?:[ \t]*\n[ \t]*|[ \t]+)([a-z]{2,})")
_SOLID_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_MIDLINE_HYPHEN_RE = re.compile(r"([A-Za-z]{2,})-([a-z]{2,})")
_BARE_MARKER_LINE_RE = re.compile(r"^\s*\d{1,3}\*?\s*$")
# The stacked-fraction html span produced by _layout_blocks; used to repair the
# corresponding plain_text ("A x 15\n85" -> "(A x 15) / 85") on the section path,
# whose plain is assembled line-by-line and never sees _layout_blocks.
_FRAC_SPAN_RE = re.compile(
    r'<span class="frac"[^>]*>'
    r'<span style="display:block;">(.*?)</span>'
    r'<span style="display:block; border-top:[^"]*">(.*?)</span>'
    r"</span>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _hyphenation_vocab(leaves):
    """Corpus counts used to resolve a line-break hyphen (RC-7).

    Returns ``(solid, hyph)``: ``solid[w]`` = times ``w`` is written as one
    un-hyphenated token; ``hyph[a-b]`` = times ``a-b`` occurs hyphenated mid-line.
    A wrapped ``a-\\n b`` keeps its hyphen for a real compound (``sub-section`` --
    "subsection" is never written solid) but drops it for a word merely broken
    across lines (``which-\\n ever`` -> "whichever", written solid dozens of
    times).  Both signals are needed so a word that is *usually* hyphenated
    (``co-operative``) is never solidified by a stray solid occurrence.
    """
    solid: dict[str, int] = {}
    hyph: dict[str, int] = {}

    def scan(txt: str) -> None:
        for tok in _SOLID_WORD_RE.findall(txt):
            k = tok.lower()
            solid[k] = solid.get(k, 0) + 1
        for m in _MIDLINE_HYPHEN_RE.finditer(txt):
            k = (m.group(1) + "-" + m.group(2)).lower()
            hyph[k] = hyph.get(k, 0) + 1

    for lf in leaves:
        scan(lf.get("plain_text") or "")
        for fn in lf.get("footnotes") or []:
            scan(fn.get("text") or "")
    return solid, hyph


def _dehyphenate(text: str, solid: dict, hyph: dict, min_freq: int = 3) -> str:
    """Join a compound wrapped across a line break (RC-7), keeping the hyphen
    unless the joined form is predominantly a single solid word.

    Applied to a fixpoint: in a chain of adjacent wraps ("poly- alpha- olefin")
    one ``re.sub`` pass consumes the middle word, so the next wrap can't anchor
    until a following pass.  Each pass strictly removes the matched gap
    whitespace, so this always terminates (bounded by the longest hyphen chain).
    """
    def repl(m):
        a, b = m.group(1), m.group(2)
        joined = (a + b).lower()
        hyphenated = (a + "-" + b).lower()
        sf = solid.get(joined, 0)
        if sf >= min_freq and sf > hyph.get(hyphenated, 0):
            return a + b            # a real word split by a line break
        return a + "-" + b          # a genuine hyphenated compound -> keep hyphen
    for _ in range(8):              # fixpoint (hyphen chains are short)
        new = _HYPHEN_WRAP_RE.sub(repl, text)
        if new == text:
            break
        text = new
    return text


def _merge_bracket_markers(plain: str) -> str:
    """RC-5: an amendment marker sometimes lands alone on its own plain line, just
    above the ``[`` it opens (``shall be –\\n2\\n[Table``).  Glue the marker onto
    the bracket line (``2[Table``) so it never reads as a stray number.  Scoped to
    a bare-marker line immediately followed by a ``[``-line, so footnote-leak
    markers and fraction denominators (``A x 15`` / ``85``) are left untouched."""
    lines = plain.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if _BARE_MARKER_LINE_RE.match(lines[i]) and nxt.lstrip().startswith("["):
            out.append(lines[i].strip() + nxt.lstrip())
            i += 2
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def _fix_fraction_plain(plain: str, html: str) -> str:
    """RC-7: give plain_text a division indicator for a stacked fraction.  The
    html already renders the real numerator-over-bar-over-denominator; the section
    plain path builds text line-by-line, so the fraction lands as two lines
    ("A x 15\\n85").  Drive the repair off the authoritative html frac span:
    replace the "<num>\\n<den>" line pair with "(<num>) / <den>"."""
    for m in _FRAC_SPAN_RE.finditer(html):
        num = _TAG_RE.sub("", m.group(1)).strip()
        den = _TAG_RE.sub("", m.group(2)).strip()
        if num and den and f"{num}\n{den}" in plain:
            plain = plain.replace(f"{num}\n{den}", f"({num}) / {den}", 1)
    return plain


# RC-5: a marker digit fused by pdfplumber into the preceding word or year AS A
# SINGLE TOKEN ("Pakistan7[and", "20054[") -- _render_words never sees these as
# separate words, so they need a text-level split.  Mirrors the invariant
# signatures; the digit stays glued to the "[" it opens ("7[").
_FUSED_WORD_MARKER_RE = re.compile(r"([a-z])(\d)\[")
_FUSED_YEAR_MARKER_RE = re.compile(r"(\d{4})(\d)\[")

# RC-6d: a word whose glyphs pdfplumber spaced apart inside a table cell
# ("i n c o me" for "income").  The signature (>=3 single letters + a short tail)
# ALSO matches formulas ("A x B/C") and glyph-split phrases ("i s not" = "is
# not"), which must NEVER be mangled -- so a run is collapsed only when its
# space-removed form is a genuine, frequent word of the corpus (see _deglyph).
_GLYPH_RUN_RE = re.compile(r"(?:\b[A-Za-z] ){2,}[A-Za-z][a-z]{0,3}\b")


def _deglyph(text: str, solid: dict, min_freq: int = 5) -> str:
    """Collapse intra-word glyph spacing ("i n c o me" -> "income"), but ONLY when
    the collapsed form is a frequent solid word of the corpus.  This leaves
    formulas ("A x B/C" -> "AxB" is not a word) and glyph-split phrases ("i s
    not" -> "isnot" is not a word) untouched, so legal text is never corrupted."""
    def repl(m):
        collapsed = m.group(0).replace(" ", "")
        if solid.get(collapsed.lower(), 0) >= min_freq:
            return collapsed
        return m.group(0)
    return _GLYPH_RUN_RE.sub(repl, text)


def _space_fused_markers(text: str) -> str:
    """RC-5: separate a footnote/amendment marker that was glued into the
    preceding word or year as one token ("Pakistan7[" -> "Pakistan 7[",
    "20054[" -> "2005 4[")."""
    text = _FUSED_WORD_MARKER_RE.sub(r"\1 \2[", text)
    text = _FUSED_YEAR_MARKER_RE.sub(r"\1 \2[", text)
    return text


_FNTABLE_CELL_RE = re.compile(r'<div style="flex:0 0 ([\d.]+)%;[^"]*">(.*?)</div>', re.S)
# capture the whole cell run (each cell keeps its own </div>) up to the container
# close -- ".*?</div></div>" would eat the LAST cell's close and drop that cell.
_FNTABLE_RE = re.compile(r'<div class="fn-table"[^>]*>(.*?</div>)</div>', re.S)
_CITE_SUP_RE = re.compile(r'<sup class="cite"[^>]*>([^<]*)</sup>')


def _fntable_to_text(m):
    """Render one fn-table div to ROW-MAJOR plain text (cells left-to-right, then
    down), so a rate column never interleaves a wrapped condition."""
    cells = _FNTABLE_CELL_RE.findall(m.group(1))
    if not cells:
        return ""
    ncol = max(1, round(100 / float(cells[0][0])))
    texts = [_TAG_RE.sub("", c).strip() for _, c in cells]
    rows = [texts[i:i + ncol] for i in range(0, len(texts), ncol)]
    return "\n".join(" ".join(r) for r in rows)


def _footnote_text_from_html(html: str) -> str:
    """RC-6c: derive a footnote's plain text from its (correct) html, so a quoted
    rate table reads row-major instead of interleaving the rate cell mid-condition
    ("...but does not exceed Rs. 800,000 | Rs. 1,000", not "...but does not Rs.
    1,000 exceed Rs. 800,000").  A citation <sup> collapses back to its bare marker
    digit; block tags become line breaks."""
    s = _CITE_SUP_RE.sub(lambda m: m.group(1).split(".")[-1], html)
    s = _FNTABLE_RE.sub(_fntable_to_text, s)
    s = re.sub(r"</(?:p|div)>", "\n", s)
    s = _TAG_RE.sub("", s)
    s = _html.unescape(s)
    out, prev = [], None
    for ln in (x.strip() for x in s.split("\n")):
        if ln and ln != prev:           # drop blanks + consecutive duplicates
            out.append(ln)
        prev = ln
    return "\n".join(out)


def normalize_document_text(result):
    """Apply document-wide plain/html text repairs after the tree is built:
    RC-7 line-break de-hyphenation, RC-5 fused-marker spacing (leaf + footnote
    plain/html) and RC-5 bare-marker merging (leaf plain).  Runs once per
    document."""
    leaves = [lf for root in ("chapters", "schedules")
              for node in result.get(root, []) for lf in all_leaves(node)]
    solid, hyph = _hyphenation_vocab(leaves)
    for lf in leaves:
        if lf.get("plain_text"):
            p = _dehyphenate(lf["plain_text"], solid, hyph)
            p = _merge_bracket_markers(p)
            p = _space_fused_markers(p)
            p = _deglyph(p, solid)
            if lf.get("html"):
                p = _fix_fraction_plain(p, lf["html"])
            lf["plain_text"] = p
        if lf.get("html"):
            lf["html"] = _deglyph(_space_fused_markers(_dehyphenate(lf["html"], solid, hyph)), solid)
        for fn in lf.get("footnotes") or []:
            if fn.get("html"):
                fn["html"] = _deglyph(_space_fused_markers(_dehyphenate(fn["html"], solid, hyph)), solid)
            if fn.get("text"):
                if fn.get("html") and 'class="fn-table"' in fn["html"]:
                    # RC-6c: a footnote quoting a rate table -- rebuild its plain
                    # text row-major from the (correct) html so the rate column
                    # no longer interleaves the wrapped condition text.
                    fn["text"] = _footnote_text_from_html(fn["html"])
                else:
                    fn["text"] = _deglyph(_space_fused_markers(_dehyphenate(fn["text"], solid, hyph)), solid)
    pre = result.get("preamble")
    if pre:
        if pre.get("plain_text"):
            pre["plain_text"] = _deglyph(_space_fused_markers(_merge_bracket_markers(
                _dehyphenate(pre["plain_text"], solid, hyph))), solid)
        if pre.get("html"):
            pre["html"] = _deglyph(_space_fused_markers(_dehyphenate(pre["html"], solid, hyph)), solid)
    return result


# the decoration a body heading line carries BEFORE its title: stacked amendment
# markers, the insertion bracket, the section code, and the code's dot
# ("6,71,76,81[194. ", "[15. ", "2 [ 158.", "1[230E ").  Dot-less because
# inserted sections print none (s.230E), and the marker run is already bounded
# by MARKER_PREFIX so it cannot eat the code's first digit (grammar A08).
# ``_OPEN`` for the same reason ``_DOTFORM_RE`` uses it: without it the
# insertion pair in "5[(14-A. Provision of ..." is not stripped, so
# ``_body_heading_title`` returns "" and a section recovered by RC-A keeps
# its TOC heading instead of being upgraded to the body one.
_HEAD_CODE_PREFIX_RE = re.compile(_HEAD + rf"{_OPEN}{CODE}\s*[.\]]?\s*")


@functools.lru_cache(maxsize=None)
def _head_code_prefix_re(code: str):
    """``_HEAD_CODE_PREFIX_RE`` for ONE known code, tolerating how it is printed.

    ``CODE`` is positional and allows a hyphen but never a space, so on the
    18-section run whose text layer splits the code -- ``150 ZQR.`` for 150ZQR,
    the family ``_DOTSUFFIX_RE`` above exists to catch -- it matches ``150`` and
    stops, and the title keeps the tail: ``heading`` came out as "ZQR.
    Application".  Measured over the shipped corpus: 31 leaves in 15 documents
    across two lanes -- the 16-rule ``150ZQ*`` run plus 14A in rules, and
    156A x7 / 18A x5 / 25AA / 37D in acts -- every one of them
    ``heading_source="body"``; a leaf whose heading came from the TOC is clean,
    which is why the shape only appears once a section has a body to be read
    from.  The dot is not always printed: Customs 18A reads "A Special customs
    duty on imported goods".

    So the strip is driven by the code the caller ALREADY passes and never used.
    ``discover._heading_from_words`` solves the same disagreement the same way
    and says why: the code arrives FOLDED (``norm_code``) while the words carry
    the PRINTED spelling.  Anchored, and bounded to len(code)-1 separator runs.

    The separator run is why the code token must be required to END on a
    boundary.  Without the lookahead the run between the last two characters
    can swallow the code's OWN terminator: Customs 193A prints ``193. Appeals
    to Collector``, and ``3`` + ``. `` + ``A`` matches, taking the title's first
    letter with it ("ppeals to Collector").  ``discover._heading_from_words``
    carries the same construction and a comment claiming the len(code)-1 bound
    makes that impossible; the bound limits how MANY separator runs there are,
    not how far one reaches, so the claim does not hold for a code whose letter
    suffix also begins the title word.
    """
    return re.compile(_HEAD + _OPEN + r"[\s.\-]*".join(map(re.escape, code))
                      + r"(?=[\s.\]]|$)" + r"\s*[.\]]?\s*")


def _body_heading_title(h4_inner: str, code: str) -> str:
    """The section title as PRINTED IN THE BODY, in the shape of a TOC heading.

    The body heading is the authoritative one for a legal document: it carries
    the *amended* wording, and it carries the source's own spelling, which the
    stale TOC row does not (the 2008 Customs body prints ``AFFFECTING`` /
    ``CAERGO`` / ``SHCEUDLE`` where its TOC prints the corrected words).  This
    reduces the rendered <h4> inner html ("1[15. Prohibitions.-") to the bare
    title ("Prohibitions") so the ``heading`` field keeps exactly the shape of
    the TOC heading it replaces: no amendment-marker/bracket decoration, no
    code, no ".—" terminator.  Citation ``<sup>`` refs are dropped -- they are
    page/marker pointers, not title words, and they stay visible in the html.

    Returns "" when the line does not reduce to a recognisable title, in which
    case the caller keeps the TOC heading.
    """
    s = re.sub(r"<sup\b[^>]*>.*?</sup>", "", h4_inner)
    s = _html.unescape(re.sub(r"<[^>]+>", "", s))
    # LONGEST match wins, and neither pattern can be dropped.
    #
    # The positional one alone is the bug this fixes: it cannot span "150 ZQT".
    # But the code-driven one alone is a bug in the other direction -- where the
    # body prints a code carrying a suffix the TOC's does not (TOC "15", body
    # "15A. Title"), it matches only the "15" and leaves "A." in the title,
    # which is the very shape being removed here.  It also cannot match at all
    # where the body prints a different code than the TOC lists (Sales Tax Rules
    # lists 39E for a body printing 39K with the same title).
    #
    # Each covers the other's blind spot and both are anchored, so taking the
    # longer span is strictly better than either and can never strip less than
    # today does.
    cands = [m for m in (_head_code_prefix_re(code).match(s) if code else None,
                         _HEAD_CODE_PREFIX_RE.match(s)) if m]
    if not cands:
        return ""
    m = max(cands, key=lambda c: c.end())
    s = s[m.end():]
    # drop the heading terminator (".—" / ",-" / a bare dash) and any bracket
    s = re.sub(r"[\s\]\[]*[.,]?\s*[—–―─-]+\s*$", "", s).strip()
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s if any(c.isalpha() for c in s) else ""


def _squash(text: str) -> str:
    """Case- and whitespace-free form, for comparing a wrapped heading."""
    return re.sub(r"\s+", "", text or "").lower()


def _wrapped_heading_lines(seg, code: str, heading: str) -> int:
    """Index of the LAST body line the section's title occupies (0 if one line).

    Used only where ``_find_heading_split`` found no terminator, so the title's
    extent has to come from the TOC entry rather than from the printed dash.
    Bounded by 4 lines, the same window ``_find_heading_split`` scans, so a bad
    TOC row can never swallow a paragraph.
    """
    want = _squash(f"{code}.{heading}")
    if not heading or len(want) < 8:
        return 0
    acc, d = "", 0
    for li in range(min(4, len(seg) - 1)):
        acc += _squash(seg[li].line.text())
        # a strict prefix means the title is not finished on this line
        if not (want.startswith(acc.rstrip(".")) and len(acc.rstrip(".")) < len(want)):
            break
        d = li + 1
    return d


def _build_one(entry, seg: list[LineRef], footnote_map, page_footnotes,
               page_offset: int = 0, is_last: bool = False,
               printed_by_page: dict | None = None,
               cited_footnotes: dict | None = None) -> BuiltSection:
    # A section ends when a new structural heading begins -- even though the
    # next *section* heading may be a page or two further on.
    #
    # ...but NOT for the last section in the body, where the cut has nothing to
    # hand the remaining text to and simply drops it.  A structural heading that
    # opens no section is not structuring anything.  Finance Act 2013 quotes
    # Divisions XII-XVII of the Income Tax Ordinance's First Schedule inside its
    # own clauses; each is recognised as a structural boundary, each ends up
    # holding **zero** sections, and the first of them cut the last section at
    # page 38 of 59 -- so pages 39-59, the whole tariff tail, reached no leaf at
    # all and were counted as 1,395 missing body words.
    cut = len(seg)
    if not is_last:
        for i in range(1, len(seg)):
            if is_structural_boundary(seg[i].line.text()):
                cut = i
                break
    seg = seg[:cut]

    cited: list[tuple[int, str]] = []  # (pdf_page, marker) referenced in body

    # Per-page folio where the page printed one, the calibrated constant only as a
    # fallback.  A single global offset assumes one pagination for the whole
    # document, and Finance Act, 2022 has TWO: its own pages run pdf 2 -> folio 1
    # (offset 1) for 255 pages, then the Schedules restart their numbering and pdf
    # 273 prints folio 18 (offset 255).  ``_modal`` picks whichever series is
    # longer -- 255, on 22 of 36 sampled pages -- so every ref minted in the FIRST
    # series came out as `page - 255`, i.e. NEGATIVE: `-6.^cont`, `-4.^cont`.
    # This is the same lesson as the TOC-to-body drift already fixed in
    # ``build_sections`` ("a single global offset assumes the two run in lockstep;
    # they do not"), applied to the side that mints footnote refs.
    # The CONSTANT offset for body refs.  Deriving it per page from
    # ``printed_by_page`` was TRIED and REVERTED: on an edition whose folios are
    # sparse or noisy it makes every ref follow the noise instead of a single
    # document-wide measurement, and the 15.09.2021 Sales Tax edition (almost no
    # printed footers) went 53/53 -> 52/53 with a note bound across 90 pages.
    # ``adopt_orphan_footnotes`` reads the per-page map because it always did and
    # its refs are for notes whose own page is known; this path is different.
    def off_fn(p, _off=page_offset):
        return _off

    pages = [r.page for r in seg]
    page_number = seg[0].page
    start_page, end_page = min(pages), max(pages)

    # Fallback heading: TOC-derived (canonical casing).  This is overridden
    # below by the actual PDF body heading line whenever a heading split is
    # found -- for a legal document the *operative* (possibly amended) heading
    # wording is authoritative, and it may diverge from the stale TOC entry
    # (title substitutions "Disposal"->"Decision", "of"->"to"; TOC typos like
    # "Tan"/"temporary"; inserted amendment brackets "[or digital means]"; the
    # real dash char/spacing as printed).  Matches the reference JSON.
    heading_display = f"{entry.code}. {entry.heading}"
    heading = entry.heading
    heading_source = "toc"
    # An omitted/repealed section is a synthetic placeholder ("N. Omitted by the
    # Finance Act, ...") with no operative title dash in the PDF -- don't append a
    # fabricated em-dash to it.  Real titles keep the ".—".
    head_tail = "" if re.search(r"\b[Oo]mitted\b|\b[Rr]epealed\b",
                                entry.heading or "") else ".—"
    heading_html = (f'<h4 class="section-heading">'
                    f'{_html.escape(heading_display)}{head_tail}</h4>')

    # plain_text keeps every line as extracted (heading lines + operative text);
    # rendering each line here also collects the section's citations exactly once.
    plain_lines = []
    for r in seg:
        if getattr(r.line, "is_table", False):
            _cite_table_markers(r, cited)
            p = r.line.text()
        else:
            p, _ = _render_line(r.line, r.page, footnote_map, page_offset, cited)
        if p.strip():
            plain_lines.append(p)
    plain_text = "\n".join(plain_lines).strip()

    # For the HTML body we drop the heading region: everything up to and
    # including the "<title>.—" dash, which may fall on a wrapped 2nd/3rd line
    # (e.g. "...by a public\nservant.— A person ...").  Only the operative text
    # after the dash becomes body content -- so the heading is never duplicated.
    split = _find_heading_split(seg, len(seg))
    remainder_rows = []
    body_rendered = False
    if split is not None:
        d, before_words, after_words = split
        content_seg = seg[d + 1:]
        head_region = seg[:d + 1]
        after_ids = {id(w) for w in after_words}
        has_title = any(c.isalpha() for w in before_words for c in w.text)
        after_alpha = any(c.isalpha() for w in after_words for c in w.text)

        if d == 0 and not has_title and after_alpha:
            # Title-less inserted subsection ("4[(4AB) Subject to this
            # Ordinance, a surcharge shall be payable ...") -- there is no
            # heading before the operative "(N)", so (as the reference does)
            # render the whole FIRST body line as the <h4> and continue the body
            # from line 2.  The TOC entry here would fabricate a bogus
            # "<code>. ...payable.—" with an em-dash the PDF never prints.
            first = sorted(seg[0].line.words, key=lambda w: w.x0)
            _, hh = _render_heading_words(first, seg[0].page, footnote_map,
                                          page_offset)
            bh = re.sub(r"</?strong>", "", hh.strip())
            bh = re.sub(r"(</sup>)\s+\[", r"\1[", bh)
            bh = re.sub(r"\s{2,}", " ", bh).strip()
            if bh:
                heading_html = f'<h4 class="section-heading">{bh}</h4>'
                body_rendered = True
                content_seg = seg[1:]   # first line is wholly in the <h4>
        else:
            rp, rh = _render_words(after_words, seg[d].page, footnote_map, page_offset)
            if rp.strip():
                remainder_rows.append((
                    _gazette_block_class(rp) or _classify(rp), rp, rh))

            # Render the <h4> from the real PDF body heading: the full head lines
            # 0..d-1 plus the pre-dash words on line d.  This surfaces
            # heading-region citation markers as inline <sup> naturally, keeps
            # inserted amendment brackets, and preserves the operative wording +
            # dash exactly as printed (fixing stale TOC casing/typos, amended
            # titles "Disposal"->"Decision", a hardcoded em-dash, and -- for a
            # heading that WRAPS onto a 2nd/3rd line -- the operative wording the
            # stale TOC gets wrong, e.g. s.49 "Government," not "Governments").
            # `_find_heading_split` only scans the first 4 lines, so d <= 3 and a
            # false dash can never swallow a whole paragraph; the dash-terminated
            # guard below is the final safety.
            if before_words:
                head_parts = []
                for li in range(d):
                    _, hh = _render_heading_words(
                        sorted(seg[li].line.words, key=lambda w: w.x0),
                        seg[li].page, footnote_map, page_offset)
                    if hh.strip():
                        head_parts.append(hh)
                _, hh = _render_heading_words(before_words, seg[d].page,
                                              footnote_map, page_offset)
                if hh.strip():
                    head_parts.append(hh)
                # the <h4> is already a styled heading; the reference never bolds
                # it (section headings are wholly Arial-BoldMT) -- drop <strong>.
                bh = re.sub(r"</?strong>", "", " ".join(head_parts).strip())
                bh = re.sub(r"(</sup>)\s+\[", r"\1[", bh)
                bh = re.sub(r"\s{2,}", " ", bh).strip()
                # require a real heading terminator (a dash) so a bare-marker
                # fragment never becomes the heading.
                if re.search(r"[—–―─\-]$", re.sub(r"<[^>]+>", "", bh).rstrip()):
                    heading_html = f'<h4 class="section-heading">{bh}</h4>'
                    body_rendered = True
                    # ... and the same body wording becomes the ``heading``
                    # field, the TOC's going to ``toc_heading``: the printed
                    # heading is the operative one (2008 s.9 "customs–ports"
                    # with an EN DASH, chapter-caption typos, amended titles),
                    # and it is what a reader of the PDF sees.
                    t = _body_heading_title(bh, entry.code)
                    if t:
                        heading, heading_source = t, "body"
    else:
        # No heading terminator anywhere in the first four lines, so the <h4>
        # stays TOC-derived -- but the heading region is still however many body
        # lines the title actually occupies, not one.  Ledger P36: Sales Tax 2009
        # page 67 sets section 63's title across two lines, breaking the compound
        # word,
        #
        #     63. Drawback on goods taken into use between importation and re-
        #     exportation.
        #     Notwithstanding anything contained in section 62, ...
        #
        # and prints no ".—" at all, so `exportation.` opened the body and the
        # section read "...re-exportation.— exportation. Notwithstanding ...".
        # That is what `inv_no_heading_word_duplication` reports.
        #
        # The TOC heading says how far the title runs, so consume leading lines
        # while their joined text is still a strict PREFIX of "<code>. <title>".
        # Whitespace is ignored on both sides -- the wrap glues `re-` to
        # `exportation` with no space -- and a trailing period is not part of the
        # title.  Nothing is dropped: `plain_text` is built from the whole
        # segment above, and the words removed here are the ones the <h4> is
        # already printing.
        if seg and getattr(seg[0].line, "is_table", False):
            # ...and where the section OPENS on a grid-extracted table there is
            # no heading line to consume at all.  Consuming one drops the whole
            # table (P39).  The <h4> stays TOC-derived and the table renders in
            # full; the heading words it repeats are a duplication, which is the
            # right side of that trade -- losing six lines of statute is not.
            d = -1
        else:
            d = _wrapped_heading_lines(seg, entry.code, entry.heading)
        content_seg = seg[d + 1:]
        head_region = seg[:d + 1]
        after_ids = set()

    if not body_rendered:
        # Keep the TOC-derived heading (an omitted-section placeholder whose
        # body is just an empty amendment bracket, a wrapped/title-less heading,
        # etc.), but surface any dropped heading-region citation markers as
        # <sup> prefixes inside the <h4>, mirroring the PDF where the marker
        # precedes the heading ("1[236Y. ...").
        prefix = _heading_marker_prefix(head_region, after_ids, footnote_map,
                                        lambda p: page_offset, cited)
        if prefix:
            heading_html = (f'<h4 class="section-heading">{prefix}'
                            f'{_html.escape(heading_display)}{head_tail}</h4>')

    seg_rows = content_rows_with_tables(content_seg, footnote_map, off_fn, None)
    html_doc = _build_html(heading_html, remainder_rows + seg_rows)

    # footnotes: exactly those cited in this section's body, keyed by the
    # (pdf_page, marker) of each citation.  refs use the *printed* page number
    # (pdf page - offset), e.g. "1.*".  Deduped by (ref, text) -- the PDF
    # misprints duplicate marker numbers on some pages and both notes are real
    # legal text -- and sorted numerically by ref (printed page, then
    # marker), matching the printed footer order.
    # A citation is attached from the page that PRINTS the note, which for every
    # bottom-of-page layout is the citing page itself.  Resolving it through
    # ``footnote_map`` instead -- the citation view, which lets a Customs body
    # page bind to the collector page that follows it -- was TRIED and REVERTED,
    # and the measurement is kept so it is not retried.  It fixes one row on
    # Federal Excise 01-07-2014 (section 24 prints its marker on page 27 and its
    # note on page 28) and **destroys all twenty Customs editions**: a collector
    # page carries a whole run of notes, so every body page in the run attached
    # every note in it, `footnote_on_citing_leaf` went from 0 to 486-769 failures
    # per edition and `citation_refs_resolve` from green to 30-43%.
    #
    # ``adopt_orphan_footnotes`` already owns the collector-page case and owns it
    # correctly; this loop's business is the notes a leaf's own page prints.  Same
    # lesson as the P30 note: a component must not second-guess one that already
    # owns the decision.
    by_marker: dict = {}
    cite_pages = {p for (p, _) in cited}
    # Also index the immediately following page: Federal Excise 01-07-2014 s.24
    # prints its marker on page 27 and the note on page 28 (ledger A20).  Full
    # ``footnote_map`` attach was measured and destroyed Customs (P41); looking
    # ONLY at citing_page+1, and ONLY when the citing page has no such marker,
    # covers A20 without opening collector pages (Customs gaps are 7–30+ pages).
    for pg in cite_pages | {p + 1 for p in cite_pages}:
        d: dict = {}
        for fn in page_footnotes.get(pg, []):
            d.setdefault(fn.marker, []).append(fn)
        by_marker[pg] = d
    # How many times the SOURCE prints each (page, marker, text).  The dedup below
    # must collapse the same note read twice by two code paths, and must NOT
    # collapse a note the document really prints more than once: page 70 of the
    # Federal Excise 07-05-2024 edition prints `8 The figure "thirteen" substituted
    # through Finance (Supplementary) Act, 2023.` **three times** (verified in the
    # raw PDF: three distinct word instances), and page 77 prints its note three
    # times too.  Collapsing them to one cost 14 footnote words and kept the
    # edition out of the conservation gate, which the user's standing decision is
    # to chase rather than legislate away.
    src_mult: dict = {}
    for _pg, _fns in (page_footnotes or {}).items():
        for _fn in _fns:
            k = (_pg, _fn.marker, _fn.text)
            src_mult[k] = src_mult.get(k, 0) + 1

    fns = []
    seen: dict = {}
    for (pg, marker) in cited:
        local = by_marker.get(pg, {}).get(marker, [])
        # The citing_page+1 lookup (A20) must agree with what the leaf DISPLAYS.
        # ``_render_words`` resolves a marker through ``footnote_map`` -- the
        # run-merged view, one note per marker (``_citation_scope`` builds it
        # with ``merged.setdefault``, so the run's FIRST note wins) -- while this
        # branch reads the raw page index, which keeps them all.  Where the next
        # page prints a marker the run has already bound elsewhere the two
        # disagree and the leaf holds a note it never cited: Federal Excise
        # 11-03-2019 s.43A cites marker ``5`` on page 45, page 45 prints no note
        # ``5``, and this branch took page 46's -- ``46.5``, s.45A's note, which
        # s.45A also renders.  Matching the note TEXT to the displayed title
        # keeps A20 (there both views name the same note) and drops the rest.
        # The test is whether the resolved note is AMONG the next page's
        # candidates, not which of them it is: page 97 of Customs 30-06-2014
        # prints marker ``4`` twice and s.83A cites it once, so both notes are
        # s.83A's -- keeping only the one equal to the title orphaned the other
        # and ``adopt_orphan_footnotes`` gave it to s.83, which does not cite it.
        # NOT applied to the collector branch below: that one reads
        # ``cited_footnotes``, the run-scoped view the render path is built from,
        # and a Customs collector page legitimately carries several notes under
        # one marker -- filtering it detached 18 notes across 15 Customs editions
        # and ``adopt_orphan_footnotes`` then put them on the wrong leaf.
        nxt = by_marker.get(pg + 1, {}).get(marker, []) if not local else []
        if nxt:
            title, _ = _cite_entry(footnote_map, pg, marker)
            if not any(fn.text == title for fn in nxt):
                nxt = []
        # Customs collector: same-page lookup in the CITATION view (notes the
        # run already scoped to THIS citing page).  Never look up citing_page+1
        # in that view -- cited_footnotes[pg+1] holds the NEXT body page's
        # whole collector block, which is how 155Q's heading ``4`` grabbed
        # note ``4`` printed on pdf 161 (``139.4``).
        collector = []
        if not local and not nxt and cited_footnotes:
            collector = [fn for fn in (cited_footnotes.get(pg) or [])
                         if fn.marker == marker]
        for fn in local or nxt or collector:
            # The ref names the page the NOTE is printed on, not the page that
            # cites it.  Those coincide in a bottom-of-page layout, but the
            # Customs Act collects its notes onto separate pages after each body
            # run -- keying the ref off the citing page there would both mint a
            # printed page the note does not appear on and break the (ref, text)
            # dedup against the orphan-adoption path, duplicating the note.
            if local:
                src_pg = getattr(fn, "pdf_page", None) or pg
            elif nxt:
                src_pg = getattr(fn, "pdf_page", None) or (pg + 1)
            else:
                src_pg = getattr(fn, "pdf_page", None) or pg
            # ``off_fn`` (per-page folio, constant only as a fallback) rather than
            # the raw constant: on a document with two folio series the constant
            # is right for only one of them, and it minted negative printed pages
            # into these refs -- see ``printed_page_for``.
            ref = f"{src_pg - off_fn(src_pg)}.{marker}"
            # emit up to as many copies as the source prints, no more: the outer
            # loop runs once per CITATION, so without a cap three citations of a
            # thrice-printed note would yield nine.
            key = (ref, fn.text)
            cap = src_mult.get((src_pg, marker, fn.text), 1)
            if seen.get(key, 0) >= cap:
                continue
            seen[key] = seen.get(key, 0) + 1
            fns.append({"ref": ref, "marker": ref, "text": fn.text, "html": fn.html,
                        "page": src_pg})
            # A footnote whose text continues onto the NEXT page extends the
            # section's physical reach -- but only that far.  Where notes are
            # collected onto their own pages, a cited note can sit 30+ pages
            # past the section's text, and letting it set end_page gave a
            # one-page section a 34-page range.  That range is what
            # adopt_orphan_footnotes uses to decide which leaf covers a note, so
            # an inflated span silently adopts other sections' notes (and makes
            # the page-bleed plausibility set match ordinary cross-references).
            # Collector-page coverage for by-page queries is handled later by
            # ``cover_footnote_collector_pages`` (last leaf of the body run only).
            fe = getattr(fn, "end_pdf_page", None)
            if fe is not None and end_page < fe <= end_page + 2:
                end_page = fe
    fns.sort(key=lambda x: ref_sort_key(x["ref"]))


    # Which of this section's words the OCR engines disagreed on.  Taken from
    # the section's own lines, so it is exact rather than a page-level
    # approximation, and empty for every text-layer document.
    ocr_review = [
        {"text": w.text, "page": r.page, "conf": w.conf}
        for r in seg for w in r.line.words if getattr(w, "needs_review", False)
    ]

    return BuiltSection(
        code=entry.code,
        heading=heading,
        toc_heading=entry.heading or "",
        heading_source=heading_source,
        page_number=page_number,
        html=html_doc,
        plain_text=plain_text,
        start_page=start_page,
        end_page=end_page,
        footnotes=fns,
        ocr_review=ocr_review,
    )


def _demo() -> None:
    """Pure-function pin: gazette preamble HTML must not glue titles into recitals."""
    # A section code the text layer SPLIT still has to bind.  The unbracketed
    # branch of _DOTSUFFIX_RE exists for two measured families and is narrow in
    # three ways; each case below fails if one of those narrowings is removed.
    class _L:
        def __init__(self, t):
            self._t = t

        def text(self):
            return self._t

    # the two families the unbracketed branch is FOR
    assert _candidate_code(_L(
        "150 ZQR. Application.-The provisions of this Chapter shall apply"
    )) == "150ZQR"
    assert _candidate_code(_L(
        "196-A. Statement of case to Supreme Court in certain cases.- If, on an"
    )) == "196A"
    # the bracketed branch is untouched
    assert _candidate_code(_L("3[18.A Special customs duty on imported goods.-")) == "18A"
    assert _candidate_code(_L("2[25 AA. Transactions between associates. - -")) == "25AA"
    # ... and the three narrowings, each with the row it keeps out.  A lone
    # capital is an abbreviation ("T.V.", "G.I."), a dot separator unbracketed is
    # a rate row, and without the mandatory trailing dot the tariff tables flood
    # in (392 lines, measured).
    assert _candidate_code(_L("20 T. V. Sets Nos.")) is None
    assert _candidate_code(_L("42 G. I. Pipes and MS Pipes '000' Meters")) is None
    assert _candidate_code(_L("1 ITEM NAME 7.5 1 9.23 132.23")) is None

    # A marker RUN separated by nothing but whitespace.  Customs 2022-2025 print
    # s.202B as "42 53[202B. ..." -- two markers, one space, no comma -- so the
    # run never closed and the section was a heading-only stub in four editions,
    # its body left inside s.202A.  The branch is admitted only behind a lookahead
    # for "[CODE. Capital", which over 153,736 corpus lines matches exactly this
    # one line; allowing whitespace generally gains 17 penalty- and
    # statistics-table rows with it.
    # BOTH spellings: the parser's own line text carries a space before the
    # bracket, while the rendered plain_text collapses it.  A lookahead anchored
    # hard on "[" matched the JSON and missed the document.
    assert _candidate_code(_L(
        "42 53 [202B. Reward to officers and officials of Customs and law"
    )) == "202B"
    assert _candidate_code(_L(
        "42 53[202B. Reward to officers and officials of Customs and law"
    )) == "202B"
    assert _candidate_code(_L("25, 38 1[38A or 40B].")) is None
    assert _candidate_code(_L("1,314,273 1,482,319 12.8")) is None
    # and the separators that already worked still do
    assert _candidate_code(_L("6,71,76,[194. Appellate Tribunal.-")) == "194"
    assert _candidate_code(_L("2 [99. Compost(non-commercial fertilizer)")) == "99"

    assert _gazette_block_class("AN") == "act-title"
    assert _gazette_block_class("ACT") == "act-title"
    assert _gazette_block_class("ORDINANCE") == "act-title"
    assert _gazette_block_class("to provide for declaration") == "act-long-title"
    assert _gazette_block_class("WHEREAS there is") == "recital"
    assert _gazette_block_class("AND WHEREAS it is expedient") == "recital"
    assert _gazette_block_class("It is hereby enacted as follows:—") == "enacting-formula"
    assert _gazette_block_class(
        "There is hereby enacted Foreign Assets") == "enacting-clause"
    assert _gazette_block_class("TABLE") == "act-title"
    assert _gazette_block_class("(1) This Act") is None

    html = _build_html(
        '<h4 class="section-heading">11. Foreign Assets (Declaration and '
        'Repatriation) Act, 2018.—</h4>',
        [
            ("enacting-clause",
             "There is hereby enacted ... as follows:-",
             "There is hereby enacted Foreign Assets (Declaration and "
             "Repatriation) Act, 2018, in the manner as follows:-"),
            ("act-title", "AN", "AN"),
            ("act-title", "ACT", "ACT"),
            ("act-long-title", "to provide for declaration",
             "to provide for declaration and repatriation of assets and "
             "income held outside Pakistan"),
            ("recital", "WHEREAS there is a large scale",
             "WHEREAS there is a large scale non-reporting and under-reporting "
             "of assets"),
            ("text", "and income held outside Pakistan;",
             "and income held outside Pakistan;"),
            ("recital", "AND WHEREAS it is expedient",
             "AND WHEREAS it is expedient to provide for declaration and "
             "repatriation of assets and income held outside Pakistan for the "
             "purposes hereinafter appearing;"),
            ("enacting-formula", "It is hereby enacted as follows:—",
             "It is hereby enacted as follows:—"),
        ],
    )
    assert '<p class="act-title">AN</p>' in html, html
    assert '<p class="act-title">ACT</p>' in html, html
    assert 'class="act-long-title"' in html, html
    assert html.count('class="recital"') == 2, html
    assert "and income held outside Pakistan;" in html
    assert "Pakistan WHEREAS" not in html, html
    assert "appearing; It is hereby" not in html, html

    from .pagemodel import Line, Word

    def _mw(text, size=6.5, x0=72.0, top=100.0):
        return Word(text=text, x0=x0, x1=x0 + 10, top=top, size=size, fontname="Arial")

    head_line = Line(top=100.0, words=[
        _mw("42"),
        Word(text="[25B.", x0=84, x1=120, top=100, size=12.0, fontname="Arial"),
        Word(text="[Omitted.]]", x0=122, x1=180, top=100, size=12.0, fontname="Arial"),
    ])
    head_refs = [LineRef(page=75, line=head_line)]
    empty = _heading_marker_prefix(head_refs, set(), {}, lambda _p: 38)
    assert 'class="marker"' in empty, empty
    assert 'class="cite"' not in empty, empty
    assert 'title=""' not in empty, empty
    resolved = _heading_marker_prefix(
        head_refs, set(),
        {75: {"42": ("Inserted by Finance Act, 1988 and Omitted by Finance Act, 2004.", 75)}},
        lambda _p: 38)
    assert 'class="cite"' in resolved, resolved
    assert "Inserted by Finance Act, 1988" in resolved, resolved
    assert ">37.42</sup>" in resolved, resolved
    blank_note = _heading_marker_prefix(
        head_refs, set(), {75: {"42": ("", 75)}}, lambda _p: 38)
    assert 'class="marker"' in blank_note, blank_note
    assert 'class="cite"' not in blank_note, blank_note
    _, html_words = _render_words([_mw("42")], 75, {75: {"42": ("", 75)}}, 38)
    assert 'class="marker"' in html_words, html_words
    assert 'class="cite"' not in html_words, html_words

    # ---- section-start recognition (RC-A / RC-B / RC-C) --------------------
    # These pin the SHAPES the shipped corpus prints and, just as importantly,
    # the ORDER the patterns are tried in: _DOTSUFFIX_RE must stay ahead of
    # _DOTFORM_RE, or the separator dot satisfies the latter and a body line is
    # offered to the PARENT section (18A's text to s.18, 25AA's to s.25).
    # Exercised through the real wrappers, so a reordering is caught here.
    def _codeline(text):
        return Line(top=0.0, words=[Word(text=text, x0=72.0, x1=400.0, top=0.0,
                                         size=12.0, fontname="Arial-BoldMT")])

    for text, want in [
        # RC-A: the "[(" insertion pair, and "&" between stacked markers
        ("5[(14-A. Provision of accommodation at Customs-ports, etc.- Any", "14A"),
        ("5&7[(14A. Provision of security and accommodation", "14A"),
        ("24[(21A. Power to defer collection of customs-duty.- 25[(1)]", "21A"),
        # a dangling marker separator, and a SUBSTITUTED section quoted inside
        # its amendment bracket
        ("6,71,76,[194. Appellate Tribunal.- (1) There shall be established", "194"),
        ("602[\u201c47A. Alternative dispute resolution.- (1) Notwithstanding", "47A"),
        # RC-B: the printed spelling folds to the one the TOC lists
        ("46[221-A. Validation.- (1) All notifications and orders", "221A"),
        ("3[38- Alternative dispute resolution.- (1) Notwithstanding", "38"),
        ("155-I. Unauthorized access to or improper use of the Customs", "155I"),
        # RC-C: dot- and space-separated suffixes
        ("3[18.A Special customs duty on imported goods.- The Federal", "18A"),
        ("4[83. A Omitted]", "83A"),
        ("2[25 AA. Transactions between associates. - -", "25AA"),
        ("2[37 D. Cognizance of offences by Special Judges.- (1)", "37D"),
        ("86[156 A. Proceedings against authority and persons.- (1)", "156A"),
        # shapes that must be unchanged by all of the above
        ("6,71,76,81[194. Appellate Tribunal.- (1) There shall be", "194"),
        ("1[15. Prohibitions.- The Federal Government may", "15"),
        ("10. Power to approve landing places", "10"),
        ("2 [ 158.Time of filing of goods declaration.- (1) The", "158"),
    ]:
        line = _codeline(text)
        got = _candidate_code(line) or _dotless_candidate_code(line)
        assert got == want, (text[:46], got, want)

    # Marker/bracket on the previous line, code on this one.  Without the
    # prefix, a bare ``(14A.`` is not a section (the paren is only legal
    # inside ``[``).
    prefix = _codeline("5&7[")
    split = _codeline("(14A. Provision of security and accommodation at Customs-ports")
    assert _candidate_code(split) is None
    assert _split_bracket_candidate_code(prefix, split) == "14A"
    assert _split_bracket_candidate_code(_codeline("["), split) == "14A"
    assert _split_bracket_candidate_code(prefix, _codeline("(90.22).")) is None
    assert _split_bracket_candidate_code(prefix, _codeline("(5) The Federal Government")) is None
    glued = ("Provision of accommodation at customs ports, etc "
             "PROHIBITION AND RESTRICTION OF IMPORTATION AND EXPORTATION")
    stems = _title_stems(glued)
    assert "prohib" not in stems and stems[:3] == ["provi", "of", "accom"], stems

    # The guards.  A bare "(" outside the amendment bracket reads Finance Act
    # 2014's PCT tariff heading as a section; an inserted SUBSECTION has no dot
    # after its code and must never open a section (the false accept the
    # _BRACKETPAREN_RE comment records as costing thirty sections); a schedule
    # rate row whose title opens on a lone capital is not a suffixed code.
    for text in ("(90.22).",
                 "2 [ (5) The Federal Government may, by notification",
                 "16&39[(1) Subject to sub-section (2), in cases",
                 "9.PDA Closure Devices",
                 "12. ICIC Foundation",
                 # a quote at the head of a LINE opens quoted repealed text; only
                 # a quote INSIDE the amendment bracket introduces a section
                 "\u201cProvided that the Board may, by notification",
                 "\u201c(c) \u201cbill of entry\u201d means a bill of entry"):
        got = _candidate_code(_codeline(text))
        assert got is None or got.isdigit(), (text[:46], got)
    for text in ("72[44 Steel billets M. Tons", "75[53 Cane Molasses M. Tons"):
        got = _candidate_code(_codeline(text))
        assert got is None or got.isdigit(), (text[:46], got)

    print("builder self-check passed")


if __name__ == "__main__":
    _demo()
