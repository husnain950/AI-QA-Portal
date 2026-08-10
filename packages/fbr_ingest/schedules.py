"""Schedule content extraction.

The Schedules (First .. Fourteenth) sit after the main body (PDF pages ~507+)
and carry the rate tables and exemption lists.  Unlike sections they have no
numbered codes, so we segment them by their *structural* headings instead:

    SCHEDULE TITLE  ->  PART  ->  Division

Each terminal node (a Part with no Divisions, or a Division) becomes a content
leaf carrying ``html`` / ``plain_text`` / ``footnotes`` for the text between its
heading and the next heading -- mirroring the target JSON, where a terminal
Part/Division holds the content directly.

Footnote refs use each page's *printed* page number (read from the footer by
:mod:`fbr_ingest.pagemodel`), because the printed-to-PDF page offset is not
constant across the schedules.
"""

from __future__ import annotations

import re

from .builder import (LineRef, _build_html, _classify, _render_line,
                      content_rows_with_tables)
from .footnotes import ref_sort_key

_ORD_LIST = ["FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH",
             "EIGHTH", "NINTH", "TENTH", "ELEVENTH", "TWELFTH", "THIRTEENTH",
             "FOURTEENTH", "FIFTEENTH"]
_ORD = "|".join(_ORD_LIST)
# Leading amendment decoration on a structural title: marker digit(s)/asterisk(s),
# bracket(s), and the OPENING QUOTE that wraps a freshly-INSERTED title printed as
# quoted amendment text.  The 30.06.2020 edition prints its brand-new Eleventh
# Schedule as ``1[“ELEVENTH SCHEDULE`` (added by the Finance Act, 2020); without
# tolerating the “ the title went unrecognised and its Builders & Developers
# rules folded into the Tenth Schedule.  Mirror this class wherever leading
# decoration is stripped (_norm_code) or matched (_LEAD).
_DECOR = r'(?:[\d*]{1,3}\s*|[\[\]“”"]+\s*)*'
# whole-line schedule title, e.g. "THE FIRST SCHEDULE", "ELEVENTH SCHEDULE",
# or an amendment-inserted one like "1 [ THE SEVENTH SCHEDULE ]" / "1[“ELEVENTH".
_SCH_RE = re.compile(
    r'^' + _DECOR + r'(THE\s+)?(%s)\s+SCHEDULE\s*[\]”"]?$' % _ORD,
    re.IGNORECASE)


def _sched_ordinal(text: str):
    """Return the 0-based ordinal index of a schedule title, or None."""
    m = _SCH_RE.match(text.strip())
    return _ORD_LIST.index(m.group(2).upper()) if m else None
# optional amendment decoration: marker(s) and/or bracket(s), possibly CHAINED
# when a division was inserted and later substituted ("1[ 2[Division IIA" --
# First Schedule's super-tax division wears both citations).  Mirrors
# builder._STRUCT_DECOR_RE; leading decoration only, a trailing "]" alone
# never qualifies a line.
_LEAD = r'^' + _DECOR
# allow "PART I", "PART-I", "PART - I" (the Schedules use a hyphen in places)
# suffix up to TWO letters: "Division IIIAA" (inserted by the Finance Act,
# 2025) must split like any other division -- [A-Z]? left it fused to the
# previous division's body
_PART_RE = re.compile(_LEAD + r"PART[\s\-]+[IVXL]+[A-Z]{0,2}\s*\]?$", re.IGNORECASE)
_DIV_RE = re.compile(_LEAD + r"Division[\s\-]+[IVXL]+[A-Z]{0,2}\s*\]?$", re.IGNORECASE)
_SEE_RE = re.compile(r"^[\[(]?\s*See\b", re.IGNORECASE)

# A repealed Part/Division quoted inside a "substituted/omitted ... read as
# follows:" footnote is set ~1-2pt SMALLER than body text and, when the quoted
# block spills into the body zone, its "PART I"/"Division X" lines would be
# mis-read as active headings (the Third Schedule's duplicate PART I, the
# Seventh Schedule's PART I/II, the triplicated First-Schedule "Division I",
# and the "Division III"-coded quotes of Division III A/B).  Measured across all
# three editions the split is clean: quoted headings render at <=8.0pt while
# every genuine active heading is >=9.0pt (the smallest, the Twelfth Schedule's
# "Part III", is 9.0pt), so a threshold in the gap keeps the real ones and drops
# the quotes.  This is deliberately BELOW pagemodel.BODY_MIN_SIZE (9.6): the
# 9.0pt "Part III" is a real heading that must survive.
_HEADING_MIN_SIZE = 8.5


def _is_heading_size(line) -> bool:
    """True if the line is set large enough to be a genuine structural heading
    (not a footnote-quoted, repealed one that leaked into the body zone)."""
    sizes = [w.size for w in getattr(line, "words", []) if getattr(w, "size", None)]
    return bool(sizes) and max(sizes) >= _HEADING_MIN_SIZE


def _kind(text: str):
    t = text.strip()
    if _SCH_RE.match(t):
        return "schedule"
    if _PART_RE.match(t):
        return "part"
    if _DIV_RE.match(t):
        return "division"
    return None


def _clean_code(code: str) -> str:
    """Drop a trailing TOC page number, e.g. 'THE FIFTH SCHEDULE 706'."""
    return re.sub(r"\s+\d+\s*$", "", (code or "")).strip()


def _norm(code: str) -> str:
    """Normalise a code for matching TOC <-> body ('THE FIRST'=='FIRST',
    'PART-I'=='PART I')."""
    c = re.sub(r"\s+", " ", _clean_code(code)).strip().upper()
    c = re.sub(r"\b(PART|DIVISION)[\s\-]+", r"\1 ", c)
    return c.replace("THE ", "").strip()


def _any_page(node: dict):
    """First page_number found anywhere in a schedule subtree (fallback page for
    a placeholder that has no body line of its own)."""
    if node.get("page_number") is not None:
        return node["page_number"]
    for k in ("parts", "divisions", "sections"):
        for c in node.get(k, []) or []:
            p = _any_page(c)
            if p is not None:
                return p
    return None


def _heading_sibling(t, prev: dict) -> dict:
    """A same-code heading-only sibling: the TOC lists several sub-headings under
    one division code (Division I -> 'Rates of Tax for Individuals' AND '... for
    Association of Persons').  The first keeps the body content; each extra TOC
    heading becomes this heading-only entry sharing the code and page."""
    import html as _h
    h = t.heading or ""
    return {
        "code": _clean_code(t.code), "heading": h,
        "page_number": prev.get("page_number"),
        "html": f'<h4 class="section-heading">{_h.escape(h)}</h4>',
        "plain_text": h, "start_page": prev.get("start_page"),
        "end_page": prev.get("end_page"), "footnotes": [],
    }


def _omitted_placeholder(t, page) -> dict:
    """A heading-only placeholder for a Part/Division the TOC lists but the body
    carries only as repealed text inside a footnote (e.g. Division IA '(Omitted
    by the Finance Act, 2013)', PART IIA).  Mirrors an omitted *section*
    placeholder: it exists structurally, carries the canonical TOC code+heading,
    and holds no body content of its own (the repealed text stays in the
    footnote where the body prints it, so nothing is duplicated or dropped)."""
    import html as _h
    h = t.heading or ""
    return {
        "code": _clean_code(t.code), "heading": h,
        "page_number": page,
        "html": f'<h4 class="section-heading">{_h.escape(h)}</h4>',
        "plain_text": h,
        "start_page": page, "end_page": page, "footnotes": [],
    }


def _reconcile(body_nodes: list[dict], toc_nodes: list, default_page,
               overwrite_heading: bool) -> list[dict]:
    """Order-preserving merge of body child nodes against the canonical TOC list.

    The TOC is the authoritative spine.  Walking the TOC in order:
      * a TOC node matched by the next body node of the same code keeps the body
        content and takes the TOC's canonical code (+ heading);
      * a repeated TOC code the body has only once becomes a heading-only sibling
        (Division I -> Individuals + Association of Persons);
      * a TOC node with no body match becomes an omitted/repealed placeholder;
      * a body node whose code the TOC never lists (a real heading the TOC omits,
        e.g. the Twelfth Schedule's Parts) is kept in its original position.
    When the TOC lists no children at all, the body structure is returned as-is.
    """
    from collections import deque
    if not toc_nodes:
        return body_nodes
    toc_codes = {_norm(t.code) for t in toc_nodes}
    body = deque(body_nodes)
    out: list[dict] = []
    prev_code = None
    last_page = default_page
    for t in toc_nodes:
        tn = _norm(t.code)
        # emit any leading body-only real nodes (codes the TOC never lists) here,
        # in place, so a heading the TOC omits is neither dropped nor reordered
        while body and _norm(body[0].get("code", "")) not in toc_codes:
            nd = body.popleft()
            last_page = nd.get("page_number", last_page)
            out.append(nd)
        if body and _norm(body[0].get("code", "")) == tn:
            nd = body.popleft()
            nd["code"] = _clean_code(t.code)
            if t.heading and (overwrite_heading or not nd.get("heading")):
                nd["heading"] = t.heading
            last_page = nd.get("page_number", last_page)
            out.append(nd)
            prev_code = tn
        elif tn == prev_code and t.heading:
            out.append(_heading_sibling(t, out[-1]))
        else:
            out.append(_omitted_placeholder(t, last_page))
    out.extend(body)                          # trailing body-only real nodes
    return out


def apply_toc_headings(schedules_out: list[dict], toc_schedules: list) -> None:
    """Reconcile each schedule's Part/Division tree to the TOC (the canonical
    spine) and fill canonical codes + headings.

    The body reconstructs structure only from *active* headings, so it misses
    Parts/Divisions the ordinance repealed (they survive in the body only as a
    footnote-quoted block) and, before this, mis-split a few.  The TOC lists the
    full hierarchy with clean names, so we treat it as authoritative: matched
    nodes keep their body content, omitted nodes are inserted as placeholders,
    and real headings the TOC happens not to enumerate (the Twelfth Schedule's
    Parts) are preserved.  Matching is by normalised code.
    """
    tmap = {_norm(t.code): t for t in (toc_schedules or [])}
    for sc in schedules_out:
        tsc = tmap.get(_norm(sc.get("code", "")))
        if tsc is None:
            # no TOC match: keep the body title as-is, just tidy any page number
            sc["code"] = _clean_code(sc.get("code", ""))
            continue
        sc["code"] = _clean_code(tsc.code)
        if tsc.heading and not sc.get("heading"):
            sc["heading"] = tsc.heading
        sc_page = _any_page(sc)
        if tsc.parts:
            # overwrite=True: the leaf peel now populates a part's body heading
            # (the operative rule-title, removed from the body to kill the
            # duplicate echo), so the canonical TOC heading must win over it.
            # For every TOC-listed part this yields the SAME h4 as before (it
            # was TOC-sourced then too); TOC-omitted parts (Twelfth Schedule)
            # are unmatched and keep their body heading, unaffected by this flag.
            sc["parts"] = _reconcile(sc.get("parts", []), tsc.parts, sc_page,
                                     overwrite_heading=True)
            # within each part, reconcile its divisions against the TOC part's
            tpart = {_norm(p.code): p for p in tsc.parts}
            for bp in sc.get("parts", []):
                tp = tpart.get(_norm(bp.get("code", "")))
                if tp is not None and tp.divisions:
                    bp["divisions"] = _reconcile(
                        bp.get("divisions", []) or [], tp.divisions,
                        _any_page(bp) or sc_page, overwrite_heading=True)
                    if bp.get("divisions"):
                        _strip_content(bp)     # a Part with Divisions is a container
        if tsc.divisions:
            sc["divisions"] = _reconcile(sc.get("divisions", []) or [],
                                         tsc.divisions, sc_page,
                                         overwrite_heading=True)


def build_schedules(sched_refs: list[LineRef], page_footnotes: dict,
                    footnote_map: dict, printed_by_page: dict,
                    toc_schedules: list | None = None) -> list[dict]:
    """Return the list of schedule dicts (nested parts/divisions with content)."""
    # 1) split the schedule line stream into heading-delimited segments.
    #    Schedule titles must arrive in ordinal order (First, Second, ...), so a
    #    stray "Twelfth Schedule" cross-reference in body text is ignored unless
    #    it is the next expected schedule.
    segments: list[dict] = []
    cur: dict | None = None
    expected_ord = 0
    for ref in sched_refs:
        text = ref.line.text().strip()
        k = _kind(text)
        # A footnote-quoted PART/Division (a repealed block that spilled into the
        # body zone) is set below heading size -- do not let it start a new
        # structural node; keep its text as content of the current leaf so no
        # legal text is lost.  Schedule titles are left to the ordinal-order
        # guard below (a quoted, already-seen title is never "the next" one).
        if k in ("part", "division") and not _is_heading_size(ref.line):
            k = None
        if k == "schedule":
            o = _sched_ordinal(text)
            if o is None or not (expected_ord <= o <= expected_ord + 2):
                # not the next schedule -> treat as ordinary content
                if cur is not None:
                    cur["lines"].append(ref)
                continue
            expected_ord = o + 1
        if k is not None:
            # keep the heading ref: its page can carry footnotes that belong
            # to no other line (e.g. the "1[DIVISION VII" substitution marker
            # alone on printed page 506, whose footnote quotes the pre-2024
            # Division VII) -- without it those pages fall into a span gap.
            cur = {"kind": k, "code": _norm_code(text, k), "lines": [],
                   "head": ref}
            segments.append(cur)
        elif cur is not None:
            cur["lines"].append(ref)
        # lines before the first schedule title are ignored

    # 2) nest segments: schedule -> part -> division
    schedules: list[dict] = []
    sch_segs: list[tuple[dict, dict]] = []   # (node, its own segment)
    sch = part = div = None
    for seg in segments:
        if seg["kind"] == "schedule":
            sch = _new_node(seg)
            schedules.append(sch)
            sch_segs.append((sch, seg))
            part = div = None
        elif seg["kind"] == "part":
            part = _new_node(seg)
            (sch or _fallback(schedules)).setdefault("parts", []).append(part)
            div = None
            _finish_leaf(part, seg, page_footnotes, footnote_map, printed_by_page)
        elif seg["kind"] == "division":
            div = _new_node(seg)
            parent = part or sch or _fallback(schedules)
            parent.setdefault("divisions", []).append(div)
            _finish_leaf(div, seg, page_footnotes, footnote_map, printed_by_page)

    # 3) a Part that gained Divisions is a container -> strip its own content
    for sch in schedules:
        for p in sch.get("parts", []):
            if p.get("divisions"):
                _strip_content(p)

    # 4) a Schedule with no Parts/Divisions carries content directly, in a
    #    single "sections" leaf (matching the reference's Fourth/Seventh/... shape)
    for sch, seg in sch_segs:
        if not sch.get("parts") and not sch.get("divisions") and seg["lines"]:
            leaf = {"code": sch["code"], "heading": ""}
            _finish_leaf(leaf, seg, page_footnotes, footnote_map, printed_by_page)
            if "html" in leaf:
                sch.setdefault("sections", []).append(_clean_node(leaf))

    # 4b) a Schedule WITH Parts/Divisions is a container with no leaf of its
    #    own, so a citation marker on its TITLE line ("1 [THE NINTH SCHEDULE")
    #    would render nowhere: surface it (and its footnote) on the schedule's
    #    first content leaf, mirroring what _finish_leaf does for the
    #    sections-leaf schedules.
    for sch, seg in sch_segs:
        if sch.get("parts") or sch.get("divisions"):
            _attach_sched_head_citations(sch, seg, page_footnotes,
                                         footnote_map, printed_by_page)

    out = [_clean_node(s) for s in schedules]
    apply_toc_headings(out, toc_schedules)
    _sync_h4_to_heading(out)
    _apply_h4_prefixes(out)
    return out


def _apply_h4_prefixes(nodes) -> None:
    """Insert each leaf's pending heading-marker citations into its <h4>.

    Runs after the canonical TOC headings are applied, so the prefix survives
    the h4 rewrite (e.g. DIVISION VII renders as
    ``<h4 ...><sup class="cite" ...>506.1</sup>[Capital Gains ...</h4>``).
    """
    tag = '<h4 class="section-heading">'

    def visit(o):
        if not isinstance(o, dict):
            return
        pre = o.pop("_h4_prefix", "")
        html = o.get("html") or ""
        if pre and html:
            if html.startswith(tag):
                o["html"] = tag + pre + html[len(tag):]
            else:
                o["html"] = pre + html
        for k in ("parts", "divisions", "sections"):
            for c in o.get(k, []):
                visit(c)

    for n in nodes:
        visit(n)


def _sync_h4_to_heading(nodes) -> None:
    """After TOC headings are applied (canonical casing), keep each leaf's plain
    <h4> text in sync with its heading field.  A "[See ...]" or amendment-cite
    h4 (contains tags) is left untouched; only a plain heading h4 is rewritten.
    """
    import html as _h

    def visit(o):
        if not isinstance(o, dict):
            return
        heading = o.get("heading") or ""
        html = o.get("html") or ""
        if heading and html.startswith('<h4 class="section-heading">'):
            end = html.find("</h4>")
            if end != -1:
                inner = html[len('<h4 class="section-heading">'):end]
                if "<" not in inner:              # plain text h4 only
                    o["html"] = (f'<h4 class="section-heading">{_h.escape(heading)}'
                                 f'</h4>' + html[end + len("</h4>"):])
        for k in ("parts", "divisions", "sections"):
            for c in o.get(k, []):
                visit(c)

    for n in nodes:
        visit(n)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _fallback(schedules):
    if not schedules:
        s = {"code": "SCHEDULE", "heading": "", "parts": [], "divisions": []}
        schedules.append(s)
    return schedules[-1]


def _norm_code(text, kind):
    t = re.sub(r"\s+", " ", text.strip())
    # strip leading amendment decoration -- marker(s)/bracket(s)/opening quote,
    # possibly CHAINED ("1[ 2[Division IIA", "1[“ELEVENTH SCHEDULE") -- and a
    # trailing "]" / closing quote
    t = re.sub(r'^(?:[\d*]{1,3}\s*|[\[\]“”"]+\s*)+', "", t)
    t = t.strip('[]“”" ').strip()
    t = re.sub(r"(?i)\b(PART|Division)[\s\-]+", lambda m: m.group(1) + " ", t)
    if kind == "part":
        return t.upper()
    return t  # schedule title / "Division X" kept as-is


def _strip_head_markers(text):
    """Strip a leading amendment marker / bracket / opening quote from a peeled
    heading line ("1[INITIAL ALLOWANCE" -> "INITIAL ALLOWANCE") so it never
    leaks into the h4.  Mirrors the leading strip in :func:`_norm_code`."""
    t = re.sub(r'^(?:[\d*]{1,3}\s*|[\[\]“”"]+\s*)+', "", text)
    return t.strip()


def _new_node(seg):
    return {"code": seg["code"], "heading": "", "parts": [], "divisions": []}


def _finish_leaf(node, seg, page_footnotes, footnote_map, printed_by_page):
    """Attach rendered content to a (currently terminal) node."""
    refs = seg["lines"]
    if not refs:
        return
    # heading = the leading run of *heading* lines: either ALL-CAPS titles or
    # FULLY-BOLD title-case lines (e.g. Division V's two-line bold heading "Rate
    # of Tax on Shipping or Air Transport Income / of a Non-resident Person").
    # Stop at the first line that is body: a "[See ...]" ref, a list/rule item
    # ("(a)", "1.", "(2)"), or plain regular-weight prose.
    body_start = 0
    heading_lines: list[str] = []
    mode = None                       # "caps" once an ALL-CAPS title anchors the run
    for ref in refs:
        t = ref.line.text().strip()
        if not t:
            body_start += 1
            continue
        if _SEE_RE.match(t):
            break
        is_caps = _is_title_line(t)
        is_bold = _is_bold_line(ref.line)
        # a list/rule/subsec opener ("(a)", "1.", "(2)", "1[(6)") is body --
        # stop.  (This catches every rule/clause opener, so an ALL-CAPS heading,
        # classified "htext", is no longer wrongly rejected by a stale
        # `_classify(t) != "text"` guard.)  EXCEPTION: an ALL-CAPS multi-word
        # parenthetical that continues a title already being peeled ("... MINERAL
        # DEPOSITS" / "(OTHER THAN PETROLEUM)") is a heading tail, not a marker.
        caps_paren_tail = (mode == "caps" and t.startswith("(")
                           and is_caps and " " in t)
        if re.match(r"^[\d(\[]", t) and not caps_paren_tail:
            break
        if not (is_caps or is_bold):                    # regular-weight prose -> body
            break
        # once anchored on an ALL-CAPS rule-title, a following title-case bold
        # line is a mid-body SUB-heading (Fifth's "Exploration and Production
        # ... Separate Business"), NOT part of the title -- leave it in the body
        # (it renders as its own "subhead" block, see content_rows_with_tables)
        if mode == "caps" and not is_caps:
            break
        if is_caps:
            mode = "caps"
        heading_lines.append(_strip_head_markers(re.sub(r"\s+", " ", t)))
        body_start += 1
        if len(heading_lines) >= 4:
            break
    heading = " ".join(heading_lines)
    node["heading"] = heading

    content_refs = refs[body_start:]
    cited: list[tuple[int, str]] = []

    # a leading "[See ...]" reference line becomes the leaf's <h4> -- but ONLY
    # when no title heading was peeled above it.  A leaf laid out as
    # "RECOGNIZED PROVIDENT FUNDS / [See sections 2(48) ...]" keeps the title as
    # its <h4> and renders the "[See ...]" line in the body; promoting the See
    # ref would hide the title and drop the See text.
    h4 = None
    if not heading and content_refs \
            and _SEE_RE.match(content_refs[0].line.text().strip()):
        _, h4 = _render_line(content_refs[0].line, content_refs[0].page,
                             footnote_map,
                             _off(content_refs[0].page, printed_by_page), cited)
        content_refs = content_refs[1:]

    off_fn = lambda p: _off(p, printed_by_page)  # noqa: E731
    rows = content_rows_with_tables(content_refs, footnote_map, off_fn, cited,
                                    subheads=True)

    import html as _h
    # h4 preference: a "[See ...]" reference line, else the descriptive heading
    # (e.g. "Rate of Tax on Shipping ..."), else the structural code.
    if h4 is not None:
        head_html = h4
    elif heading:
        head_html = f'<h4 class="section-heading">{_h.escape(heading)}</h4>'
    else:
        head_html = f'<h4 class="section-heading">{_h.escape(node["code"])}</h4>'
    # citation markers on the heading line(s) themselves ("1[DIVISION VII")
    # must stay visible -- surfaced as <sup> citations inside the <h4> after
    # the canonical TOC heading is applied (see _apply_h4_prefixes)
    from .builder import _heading_marker_prefix
    head_refs = ([seg["head"]] if seg.get("head") is not None else []) \
        + refs[:body_start]
    prefix = _heading_marker_prefix(head_refs, set(), footnote_map, off_fn,
                                    cited)
    if prefix:
        node["_h4_prefix"] = prefix

    node["page_number"] = content_refs[0].page if content_refs else refs[0].page
    node["html"] = _build_html(head_html, rows)
    node["plain_text"] = "\n".join(p for (_, p, _) in rows).strip()
    pages = [r.page for r in content_refs] or [refs[0].page]
    node["start_page"] = min(pages)
    node["end_page"] = max(pages)
    # Footnotes: exactly those the leaf CITES -- in its body text, inside its
    # tables (Table.marker_words) or on its heading lines.  Divisions routinely
    # share a PDF page with their neighbours, so collecting by page span puts
    # the neighbours' footnotes on every leaf touching the page; by-citation is
    # the only assignment that keeps each footnote on the leaf whose text
    # anchors it.  Footnotes cited by NO leaf anywhere are attached afterwards
    # by builder.adopt_orphan_footnotes, so nothing is ever dropped.
    node["footnotes"], fn_end = _collect_footnotes(cited, page_footnotes,
                                                   printed_by_page)
    # a footnote that continues past the leaf's last content page (e.g.
    # 505.2's provisos filling printed page 506) extends the leaf's reach
    if fn_end is not None:
        node["end_page"] = max(node["end_page"], fn_end)


def _is_title_line(text: str) -> bool:
    t = text.strip()
    if not t or _SEE_RE.match(t):
        return False
    letters = [c for c in t if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.7


def _is_bold_line(line) -> bool:
    """True if (almost) every alphabetic word on the line is bold.

    Title-case division headings (e.g. "Rate of Tax on Shipping or Air Transport
    Income") are set in Arial-Bold and so fail the ALL-CAPS ``_is_title_line``
    test; this recovers them from the font weight instead.
    """
    ws = [w for w in getattr(line, "words", [])
          if any(c.isalpha() for c in w.text)]
    if not ws:
        return False
    bold = sum(1 for w in ws if "bold" in (w.fontname or "").lower())
    return bold / len(ws) > 0.7


def _off(page, printed_by_page):
    printed = printed_by_page.get(page)
    return (page - printed) if printed else 0


def _content_leaves(node):
    """Yield content-bearing leaf dicts under a schedule node, in order."""
    if "plain_text" in node:
        yield node
    for k in ("parts", "divisions", "sections"):
        for c in node.get(k, []) or []:
            yield from _content_leaves(c)


def _attach_sched_head_citations(sch, seg, page_footnotes, footnote_map,
                                 printed_by_page):
    """Surface a container schedule's title-line citations on its first leaf.

    The title's marker anchors the footnote recording the whole schedule's
    insertion/substitution ("The Ninth Schedule added by ..."); with no leaf
    of its own, the container's citation is prepended to the first content
    leaf's <h4> and the footnote attached there by citation.
    """
    from .builder import _heading_marker_prefix
    head = seg.get("head")
    head_refs = ([head] if head is not None else []) + seg["lines"]
    if not head_refs:
        return
    leaf = next(_content_leaves(sch), None)
    if leaf is None:
        return
    cited: list = []
    off_fn = lambda p: _off(p, printed_by_page)  # noqa: E731
    prefix = _heading_marker_prefix(head_refs, set(), footnote_map, off_fn,
                                    cited)
    if not prefix:
        return
    leaf["_h4_prefix"] = prefix + leaf.get("_h4_prefix", "")
    fns, _end = _collect_footnotes(cited, page_footnotes, printed_by_page)
    have = {(f["ref"], f["text"]) for f in leaf.get("footnotes", [])}
    for f in fns:
        if (f["ref"], f["text"]) not in have:
            leaf.setdefault("footnotes", []).append(f)
    leaf.get("footnotes", []).sort(key=lambda x: ref_sort_key(x["ref"]))


def _collect_footnotes(cited, page_footnotes, printed_by_page):
    """Footnote dicts for the cited ``(pdf_page, marker)`` pairs, plus the
    furthest PDF page any of them reaches (their text can continue overleaf).

    A marker maps to ALL footnotes carrying it on that page and dedup is by
    (ref, text): the PDF misprints duplicate marker numbers on some pages
    (e.g. two "5" footnotes on printed page 92), and both notes are real
    legal text that must survive."""
    by_marker: dict = {}
    for pg in {p for (p, _) in cited}:
        d: dict = {}
        for fn in page_footnotes.get(pg, []):
            d.setdefault(fn.marker, []).append(fn)
        by_marker[pg] = d
    out, seen = [], set()
    fn_end = None
    for (pg, marker) in cited:
        printed = printed_by_page.get(pg, pg)
        ref = f"{printed}.{marker}"
        for fn in by_marker.get(pg, {}).get(marker, []):
            if (ref, fn.text) in seen:
                continue
            seen.add((ref, fn.text))
            out.append({"ref": ref, "marker": ref, "text": fn.text, "html": fn.html})
            end = getattr(fn, "end_pdf_page", None)
            if end is not None:
                fn_end = end if fn_end is None else max(fn_end, end)
    out.sort(key=lambda x: ref_sort_key(x["ref"]))
    return out, fn_end


def _strip_content(node):
    for k in ("page_number", "html", "plain_text", "start_page", "end_page",
              "footnotes", "_h4_prefix"):
        node.pop(k, None)


def _clean_node(node):
    """Drop empty child lists so the shape matches the reference."""
    if not node.get("parts"):
        node.pop("parts", None)
    else:
        node["parts"] = [_clean_node(p) for p in node["parts"]]
    if not node.get("divisions"):
        node.pop("divisions", None)
    else:
        node["divisions"] = [_clean_node(d) for d in node["divisions"]]
    return node
