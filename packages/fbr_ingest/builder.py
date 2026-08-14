"""Assemble sections from cleaned body lines and render html / plain_text.

Given the ordered list of body :class:`~fbr_ingest.pagemodel.Line` objects
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

import html as _html
import re
from dataclasses import dataclass, field

from .footnotes import BRACKETS_ONLY_RE, all_markers_anonymous, ref_sort_key

# em dash / en dash that separates a heading from its text
DASHES = "—–-"
HEAD_SPLIT_RE = re.compile(r"\.\s*[" + DASHES + r"]")

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


# ---------------------------------------------------------------------------
# line -> (plain string, html string) with inline markers resolved
# ---------------------------------------------------------------------------

def _render_line(line, page: int, footnote_map: dict, page_offset: int = 0,
                 cited=None) -> tuple[str, str]:
    """Return (plain_text, html) for one body line."""
    return _render_words(sorted(line.words, key=lambda w: w.x0), page,
                         footnote_map, page_offset, cited)


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
    printed = page - page_offset
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
            title = footnote_map.get(page, {}).get(marker, "")
            ref = f"{printed}.{marker}"
            if cited is not None:
                cited.append((page, marker))
            frag = f'<sup class="cite" title="{_html.escape(title, quote=True)}">{ref}</sup>'
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
    return "\n".join(out)


def _line_is_bold_title(line) -> bool:
    """A preamble line whose every alphabetic word is bold -- a centred
    long-title line such as ``AN`` / ``ORDINANCE`` / ``To consolidate ...``."""
    ws = [w for w in getattr(line, "words", [])
          if any(c.isalpha() for c in w.text)]
    return bool(ws) and all("Bold" in (w.fontname or "") for w in ws)


def _build_preamble_html(pre_refs, footnote_map, off_fn):
    """Assemble the enacting preamble into ``(html, plain_text)``.

    Unlike the document-wide ``_build_html``, a fully-bold line (the centred
    long-title lines ``AN`` / ``ORDINANCE`` / ``To consolidate and amend ...``)
    is emitted as its OWN standalone ``<p>``: it never glues onto the preceding
    publication note and never absorbs the following ``WHEREAS ...`` recitals.
    Consecutive regular-weight lines merge into prose paragraphs, as before.
    Kept preamble-local so the shared ``_classify`` / ``_build_html`` /
    ``_is_allcaps`` heuristics (used by every section and schedule) stay
    untouched.
    """
    out: list[str] = []
    plains: list[str] = []
    buf: list[str] = []          # pending regular-weight prose fragments

    def flush():
        if buf:
            para = " ".join(x for x in buf if x)
            if para.strip():
                out.append(f"<p>{para}</p>")
            buf.clear()

    for r in pre_refs:
        line = r.line
        if getattr(line, "is_table", False):
            flush()
            out.append(line.html)
            plains.append(line.text())
            continue
        plain, html = _render_line(line, r.page, footnote_map, off_fn(r.page))
        if not html.strip():
            continue
        plains.append(plain)
        if _line_is_bold_title(line):
            flush()
            out.append(f"<p>{html}</p>")
        else:
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
        title = footnote_map.get(pg, {}).get(marker)
        if title is None:
            return marker
        ref = f"{pg - off_fn(pg)}.{marker}"
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
    ax0 = min(w.x0 for w in la.words); ax1 = max(w.x1 for w in la.words)
    bx0 = min(w.x0 for w in lb.words); bx1 = max(w.x1 for w in lb.words)
    return 0 < (lb.top - la.top) < 20 and bx0 >= ax0 - 6 and bx1 <= ax1 + 6


#   "namely: —", "equal to-", "namely:—", "namely:–" (the corpus mixes hyphen,
#   en dash, em dash and the two box-drawing look-alikes in this position)
_FORMULA_INTRO_END = (":",) + tuple(DASHES)

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
    lines = [l for (l, _) in geoms if l is not None and getattr(l, "words", None)]
    if not lines:
        return rows
    left = min(min(w.x0 for w in l.words) for l in lines)
    right = max(max(w.x1 for w in l.words) for l in lines)

    def is_formula(idx: int, after_formula: bool) -> bool:
        kind, plain, _ = rows[idx]
        if kind != "text":
            return False
        prev = rows[idx - 1][1].rstrip() if idx else ""
        intro = prev.endswith(_FORMULA_INTRO_END)
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
            if mre is not None and _looks_like_wrapped_reference(plain, prev_plain, mre):
                kind = "text"
            # schedule leaves: a standalone bold rule-heading / sub-heading line
            # becomes its own block instead of merging into a neighbour
            if subheads and kind in ("text", "htext") and _is_subheading(r.line, plain):
                kind = "subhead"
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
_HEAD = r"^\s*(?:[\d*]{1,3}\s+)?"           # optional leading superscript marker
_DOTFORM_RE = re.compile(_HEAD + r"\[?\s*(\d{1,3}[A-Z]{0,3})\s*\.")
_BRACKETPAREN_RE = re.compile(_HEAD + r"\[\s*\(?(\d{1,3}[A-Z]{0,3})\)")


def _candidate_code(line) -> str | None:
    head = line.text()[:40]
    m = _DOTFORM_RE.match(head)
    if m:
        return m.group(1)
    m = _BRACKETPAREN_RE.match(head)
    if m:
        return m.group(1)
    return None


# A DOT-LESS inserted section start: "1 [230E Directorate General of ...".
# 230E's body line carries no dot after the code, so _DOTFORM_RE never sees
# it and the section used to survive as a heading-only placeholder.
_DOTLESS_RE = re.compile(r"^\s*(?:[\d*]{1,3}\s+)?\[?\s*(\d{1,3}[A-Z]{1,3})\s+[A-Z]")
# the ".—" family of heading terminators, tolerating space before the dash
_HEADING_DASH_RE = re.compile(r"\.\s*[—–―─-]")


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


def _bold_title(words, code_i: int) -> bool:
    """True when the code token or either of the first two alphabetic words
    at/after it prints in the heading's bold face.

    Genuine section titles are set in the bold heading face; definition
    clauses and cross-references that mimic a section start are regular.
    Checking two words (not one) covers starts whose code token kept the
    regular face ("3[6A." / "2 [158.Time").
    """
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


def build_sections(body_refs: list[LineRef], ordered_sections,
                   footnote_map: dict, page_footnotes: dict,
                   page_offset: int = 19) -> dict:
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
    code_positions: dict[str, list[int]] = defaultdict(list)
    for idx, ref in enumerate(body_refs):
        cc = _candidate_code(ref.line) or _dotless_candidate_code(ref.line)
        if cc:
            code_positions[cc].append(idx)
    # body-driven entries (TOC-less editions) carry their heading LineRef;
    # resolve those by IDENTITY -- exact, and it survives the second
    # build_sections pass after claim_placeholder_lines filters body_refs,
    # because heading lines are never claimed
    pos_of_ref = {id(r): i for i, r in enumerate(body_refs)}

    starts: list[tuple[int, object]] = []
    last = -1
    for k, entry in enumerate(ordered):
        a = getattr(entry, "anchor", None)
        if a is not None:
            pos = pos_of_ref.get(id(a))
            if pos is not None and pos > last:
                starts.append((pos, entry))
                last = pos
            continue
        expected = entry.printed_page + page_offset
        positions = [p for p in code_positions.get(entry.code, []) if p > last]
        pos = None
        for tol in (2, 4, 8):
            near = [p for p in positions
                    if abs(body_refs[p].page - expected) <= tol]
            if near:
                # closest to the expected page, breaking ties by document order
                pos = min(near, key=lambda p: (abs(body_refs[p].page - expected), p))
                break
        if pos is not None:
            # The TOC can list the SAME code twice (a section omitted and later
            # re-inserted under its old number, e.g. 236Y).  The single body
            # heading must go to whichever TOC row expects it closest; the
            # other row stays unmatched and becomes a placeholder.
            dist = abs(body_refs[pos].page - expected)
            if any(e2.code == entry.code
                   and abs(body_refs[pos].page - (e2.printed_page + page_offset)) < dist
                   for e2 in ordered[k + 1:]):
                continue
            starts.append((pos, entry))
            last = pos

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
            expected = entry.printed_page + page_offset
            p = min(gap, key=lambda p: (abs(body_refs[p].page - expected), p))
            matched_pos[id(entry)] = p
            claimed.add(p)
            added.append((p, entry))
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

    # keyed by the TOC entry's identity, NOT its code: duplicate-code rows must
    # not share one body
    built: dict[int, BuiltSection] = {}
    for k, (start_idx, entry) in enumerate(starts):
        end_idx = starts[k + 1][0] if k + 1 < len(starts) else len(body_refs)
        seg = body_refs[start_idx:end_idx]
        if seg:
            try:
                built[id(entry)] = _build_one(entry, seg, footnote_map,
                                              page_footnotes, page_offset)
            except Exception as exc:  # never let one bad section kill the run
                import sys
                print(f"[fbr] warning: section {entry.code} failed: {exc}",
                      file=sys.stderr)
    return built


def preamble_refs(body_refs, ordered_sections, page_offset=0):
    """The body lines before the first section (the enacting preamble).

    The preamble ends at the EARLIER of the opening section code or the first
    structural heading (CHAPTER/PART/Division).  The enacting preamble sits
    ahead of both; the chapter heading that follows it ("CHAPTER I" +
    "PRELIMINARY") is consumed separately by ``discover`` for the chapter
    code/heading, so including it here would emit that heading twice -- once as
    trailing bold text in the preamble and once as the chapter title.
    """
    first_code = ordered_sections[0].code if ordered_sections else None
    for idx, ref in enumerate(body_refs):
        if _candidate_code(ref.line) == first_code:
            return body_refs[:idx]
        if is_structural_boundary(ref.line.text()):
            return body_refs[:idx]
    return []


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
        hit = ("—" in t or "–" in t or "―" in t or "─" in t
               or t.endswith(".-") or ".-" in t
               or (t == "-" and prev.rstrip().endswith(".")))
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
            for pat in (".—", ".–", ".―", ".─", ".-", "—", "–", "―", "─"):
                p = t.rfind(pat)
                if p != -1:
                    head_suffix = t[: p + len(pat)]
                    oper_suffix = t[p + len(pat):]
                    break
            before = list(words[:i])
            if head_suffix:
                before.append(replace(w, text=head_suffix))
            rest = list(words[i + 1:])
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
    """
    for li in range(min(4, cutoff)):
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
    return None


_SUBSEC_TOKEN = re.compile(r"^\((\d{1,3}[A-Z]{0,2}|[a-z]{1,3})\)$")


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
    """
    bits: list[str] = []
    for ref in head_refs:
        words = sorted(getattr(ref.line, "words", []), key=lambda w: w.x0)
        for j, w in enumerate(words):
            if id(w) in after_ids or not _is_heading_marker(w, words):
                continue
            marker = w.text.strip()
            title = footnote_map.get(ref.page, {}).get(marker, "")
            cite = f"{ref.page - off_fn(ref.page)}.{marker}"
            if cited is not None:
                cited.append((ref.page, marker))
            frag = (f'<sup class="cite" '
                    f'title="{_html.escape(title, quote=True)}">{cite}</sup>')
            nxt = words[j + 1] if j + 1 < len(words) else None
            if (nxt is not None and id(nxt) not in after_ids
                    and nxt.text.lstrip().startswith("[")):
                frag += "["
            bits.append(frag)
    return "".join(bits)


def adopt_orphan_footnotes(leaves, page_footnotes, printed_by_page, default_offset=19):
    """Attach every parsed footnote that no leaf cited to the content leaf whose
    page range covers it, so no footnote (and its legal text) is ever dropped.

    Works document-wide on leaf dicts (chapters + schedules).  By-citation /
    page-span assignment stays primary; this is the completeness safety net for
    uncited notes -- each orphan is adopted once, by the first leaf spanning its
    PDF page.  The printed-page ref uses the footer number where known (schedules
    have a non-constant offset), else the body offset.
    """
    # dedup by (ref, text): the PDF misprints duplicate marker numbers on some
    # pages (two "5" footnotes on printed page 92 etc.) -- both texts are real.
    have = {(f["ref"], f["text"]) for lf in leaves for f in lf.get("footnotes", [])}
    covered = [lf for lf in leaves
               if lf.get("start_page") is not None and lf.get("end_page") is not None]
    covered.sort(key=lambda lf: (lf["start_page"], lf["end_page"]))
    adopted = 0
    for pg, fns in page_footnotes.items():
        cover = next((lf for lf in covered
                      if lf["start_page"] <= pg <= lf["end_page"]), None)
        if cover is None:
            continue
        printed = printed_by_page.get(pg, pg - default_offset)
        for fn in fns:
            ref = f"{printed}.{fn.marker}"
            if (ref, fn.text) in have:
                continue
            have.add((ref, fn.text))
            cover.setdefault("footnotes", []).append(
                {"ref": ref, "marker": ref, "text": fn.text, "html": fn.html})
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


def _build_one(entry, seg: list[LineRef], footnote_map, page_footnotes,
               page_offset: int = 0) -> BuiltSection:
    # A section ends when a new structural heading begins -- even though the
    # next *section* heading may be a page or two further on.
    cut = len(seg)
    for i in range(1, len(seg)):
        if is_structural_boundary(seg[i].line.text()):
            cut = i
            break
    seg = seg[:cut]

    cited: list[tuple[int, str]] = []  # (pdf_page, marker) referenced in body
    off_fn = lambda p: page_offset  # noqa: E731 (constant offset for the body)

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
                remainder_rows.append((_classify(rp), rp, rh))

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
    else:
        content_seg = seg[1:]
        head_region = seg[:1]
        after_ids = set()

    if not body_rendered:
        # Keep the TOC-derived heading (an omitted-section placeholder whose
        # body is just an empty amendment bracket, a wrapped/title-less heading,
        # etc.), but surface any dropped heading-region citation markers as
        # <sup> prefixes inside the <h4>, mirroring the PDF where the marker
        # precedes the heading ("1[236Y. ...").
        prefix = _heading_marker_prefix(head_region, after_ids, footnote_map,
                                        lambda p: page_offset)
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
    by_marker: dict = {}
    for pg in {p for (p, _) in cited}:
        d: dict = {}
        for fn in page_footnotes.get(pg, []):
            d.setdefault(fn.marker, []).append(fn)
        by_marker[pg] = d
    fns = []
    seen = set()
    for (pg, marker) in cited:
        ref = f"{pg - page_offset}.{marker}"
        for fn in by_marker.get(pg, {}).get(marker, []):
            if (ref, fn.text) in seen:
                continue
            seen.add((ref, fn.text))
            fns.append({"ref": ref, "marker": ref, "text": fn.text, "html": fn.html})
            # a footnote whose text continues onto the next page extends the
            # section's physical reach
            fe = getattr(fn, "end_pdf_page", None)
            if fe is not None and fe > end_page:
                end_page = fe
    fns.sort(key=lambda x: ref_sort_key(x["ref"]))

    return BuiltSection(
        code=entry.code,
        heading=entry.heading,
        page_number=page_number,
        html=html_doc,
        plain_text=plain_text,
        start_page=start_page,
        end_page=end_page,
        footnotes=fns,
    )
