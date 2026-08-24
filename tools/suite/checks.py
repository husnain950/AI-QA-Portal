"""Check-type registry for data-driven regression cases (tests/cases.json).

Each case names a ``check`` and a ``target`` (a section, schedule or footnote).
A check returns ``None`` on pass or a failure message string.  Adding a new
kind of assertion = adding one function here and referencing it from a case.
"""

from __future__ import annotations

import re

from .loader import find_footnote, find_leaf, find_section


def _leaf(doc, case):
    t = case.get("target", {})
    return find_leaf(doc, t.get("kind", "section"), t.get("code", ""))


def _text(doc, case, field):
    leaf = _leaf(doc, case)
    if leaf is None:
        return None, f"target not found: {case.get('target')}"
    return leaf.get(field, ""), None


# ---- string / regex checks over a leaf's plain_text or html ---------------

def chk_plain_contains(doc, case):
    txt, err = _text(doc, case, "plain_text")
    if err:
        return err
    return None if case["arg"] in txt else f"plain_text missing {case['arg']!r}"


def chk_plain_not_contains(doc, case):
    txt, err = _text(doc, case, "plain_text")
    if err:
        return err
    return f"plain_text unexpectedly contains {case['arg']!r}" if case["arg"] in txt else None


def chk_plain_not_matches(doc, case):
    txt, err = _text(doc, case, "plain_text")
    if err:
        return err
    m = re.search(case["arg"], txt, re.MULTILINE)
    return f"plain_text matches forbidden /{case['arg']}/ -> {m.group(0)!r}" if m else None


def chk_html_contains(doc, case):
    txt, err = _text(doc, case, "html")
    if err:
        return err
    return None if case["arg"] in txt else f"html missing {case['arg']!r}"


def chk_html_not_contains(doc, case):
    txt, err = _text(doc, case, "html")
    if err:
        return err
    return f"html unexpectedly contains {case['arg']!r}" if case["arg"] in txt else None


def chk_html_matches(doc, case):
    txt, err = _text(doc, case, "html")
    if err:
        return err
    return None if re.search(case["arg"], txt) else f"html does not match /{case['arg']}/"


def chk_html_not_matches(doc, case):
    txt, err = _text(doc, case, "html")
    if err:
        return err
    m = re.search(case["arg"], txt)
    return f"html matches forbidden /{case['arg']}/ -> {m.group(0)!r}" if m else None


def chk_plain_matches(doc, case):
    txt, err = _text(doc, case, "plain_text")
    if err:
        return err
    return None if re.search(case["arg"], txt, re.MULTILINE) else f"plain_text does not match /{case['arg']}/"


# ---- structural checks ----------------------------------------------------

def chk_has_fbr_table(doc, case):
    txt, err = _text(doc, case, "html")
    if err:
        return err
    return None if '<table class="fbr-table">' in txt else "no <table class='fbr-table'> present"


def chk_has_subsection_li(doc, case):
    """The subsection (arg) must exist as its OWN <li> (not merged)."""
    txt, err = _text(doc, case, "html")
    if err:
        return err
    n = case["arg"]
    # an <li> that opens with "(n)" possibly after a citation sup/bracket
    pat = re.compile(r"<li>(?:<sup[^>]*>[^<]*</sup>)?\[?\(" + re.escape(n) + r"\)")
    return None if pat.search(txt) else f"subsection ({n}) is not its own <li>"


def chk_footnote_text_nonempty(doc, case):
    fn = find_footnote(doc, case["arg"])
    if fn is None:
        return f"footnote {case['arg']} not found"
    return None if fn.get("text", "").strip() else f"footnote {case['arg']} has empty text"


def chk_footnote_any_contains(doc, case):
    """Any footnote of the target contains the substring (e.g. omitted text)."""
    leaf = _leaf(doc, case)
    if leaf is None:
        return f"target not found: {case.get('target')}"
    for fn in leaf.get("footnotes", []):
        if case["arg"] in fn.get("text", ""):
            return None
    return f"no footnote contains {case['arg']!r}"


def chk_footnote_html_has_table(doc, case):
    fn = find_footnote(doc, case["arg"])
    if fn is None:
        return f"footnote {case['arg']} not found"
    return None if "fn-table" in fn.get("html", "") else f"footnote {case['arg']} not rendered as fn-table"


def _code_eq(a, b) -> bool:
    """Compare structural codes case- and whitespace-insensitively.

    Division codes are canonicalised to the TOC's mixed case ("Division VII"),
    while the PDF body and older test cases carry all-caps ("DIVISION VII");
    both name the same node.  Consistent with ``find_schedule``'s folded match.
    """
    return " ".join(str(a or "").upper().split()) == " ".join(str(b or "").upper().split())


def _all_divisions(node):
    for p in node.get("parts", []):
        for d in p.get("divisions", []):
            yield d
        yield from _all_divisions(p)
    for d in node.get("divisions", []):
        yield d
        yield from _all_divisions(d)


def chk_division_code_count(doc, case):
    """Number of divisions coded case['div'] equals arg, optionally scoped to a
    part (case['part']) so 'Division I' in other parts isn't counted."""
    from .loader import find_schedule
    sc = find_schedule(doc, case["target"]["code"])
    if sc is None:
        return f"schedule {case['target']['code']!r} not found"
    scope = sc
    if case.get("part"):
        scope = next((p for p in sc.get("parts", []) if _code_eq(p.get("code"), case["part"])), None)
        if scope is None:
            return f"part {case['part']!r} not found"
    divs = scope.get("divisions", []) if case.get("part") else list(_all_divisions(sc))
    n = sum(1 for d in divs if _code_eq(d.get("code"), case.get("div")))
    return None if n == int(case["arg"]) else \
        f"{n} '{case.get('div')}' divisions, expected {case['arg']}"


def chk_schedule_max_table_rows(doc, case):
    """The largest fbr-table anywhere in the schedule has >= arg rows (proves a
    page-spanning table was merged rather than left fragmented)."""
    import re

    from .loader import _iter_leaves, find_schedule
    sc = find_schedule(doc, case["target"]["code"])
    if sc is None:
        return f"schedule {case['target']['code']!r} not found"
    best = 0
    for leaf in _iter_leaves(sc):
        for t in re.findall(r'<table class="fbr-table">.*?</table>', leaf.get("html", ""), re.S):
            best = max(best, len(re.findall(r"<tr>", t)))
    return None if best >= int(case["arg"]) else \
        f"largest table has {best} rows, expected >= {case['arg']}"


def chk_division_table_count(doc, case):
    """A division (code + heading) has exactly ``arg`` fbr-tables in its body."""
    from .loader import find_schedule
    sc = find_schedule(doc, case["target"]["code"])
    if sc is None:
        return f"schedule {case['target']['code']!r} not found"
    for d in _all_divisions(sc):
        if _code_eq(d.get("code"), case.get("div")) and \
                case.get("div_heading", "") in (d.get("heading") or ""):
            n = d.get("html", "").count('<table class="fbr-table">')
            return None if n == int(case["arg"]) else \
                f"division has {n} tables, expected {case['arg']}"
    return f"division {case.get('div')!r} not found"


def chk_schedule_has_table(doc, case):
    """Any leaf anywhere in the target schedule renders an fbr-table."""
    from .loader import _iter_leaves, find_schedule
    sc = find_schedule(doc, case["target"]["code"])
    if sc is None:
        return f"schedule {case['target']['code']!r} not found"
    for leaf in _iter_leaves(sc):
        if '<table class="fbr-table">' in leaf.get("html", ""):
            return None
    return "no fbr-table anywhere in schedule"


def chk_schedule_code_equals(doc, case):
    from .loader import find_schedule
    sc = find_schedule(doc, case["target"]["code"])
    if sc is None:
        return f"schedule {case['target']['code']!r} not found"
    return None if sc.get("code") == case["arg"] else \
        f"schedule code is {sc.get('code')!r}, expected {case['arg']!r}"


def chk_division_body_excludes(doc, case):
    """A division (matched by code + heading substring) must not contain arg in
    its body plain_text -- guards against footnote tables leaking into the body."""
    from .loader import find_schedule
    sc = find_schedule(doc, case["target"]["code"])
    if sc is None:
        return f"schedule {case['target']['code']!r} not found"
    for d in _all_divisions(sc):
        if _code_eq(d.get("code"), case.get("div")) and \
                case.get("div_heading", "") in (d.get("heading") or ""):
            return f"division body contains {case['arg']!r}" \
                if case["arg"] in d.get("plain_text", "") else None
    return f"division {case.get('div')!r}/{case.get('div_heading')!r} not found"


def chk_division_heading_contains(doc, case):
    """A named division under the target schedule has a heading containing arg."""
    from .loader import find_schedule
    sc = find_schedule(doc, case["target"]["code"])
    if sc is None:
        return f"schedule {case['target']['code']!r} not found"
    want = case.get("div")
    for d in _all_divisions(sc):
        if _code_eq(d.get("code"), want):
            return None if case["arg"] in (d.get("heading") or "") else \
                f"division {want} heading is {d.get('heading')!r}"
    return f"division {want!r} not found in schedule"


def _codes_norm(seq):
    return [" ".join(str(x or "").upper().split()) for x in (seq or [])]


def chk_schedule_part_codes(doc, case):
    """The target schedule's top-level Part codes equal arg (an ordered list),
    matched case/space-insensitively.  Pins Part-level reconciliation to the
    TOC: the First Schedule regains PART IIA/IIB, the Third Schedule keeps a
    single (un-duplicated) PART I, and the Seventh Schedule has no Parts."""
    from .loader import find_schedule
    sc = find_schedule(doc, case["target"]["code"])
    if sc is None:
        return f"schedule {case['target']['code']!r} not found"
    got = [p.get("code") for p in sc.get("parts", []) or []]
    return None if _codes_norm(got) == _codes_norm(case["arg"]) else \
        f"part codes {got}, expected {case['arg']}"


def chk_part_division_codes(doc, case):
    """The ordered Division codes of part case['part'] equal arg (a list),
    matched case/space-insensitively.  Pins omitted-division insertion and the
    spaced-suffix codes -- First Schedule PART III carries 'Division III A' and
    'Division III B' (not a 'Division III' repeated three times)."""
    p, err = _find_part(doc, case)
    if err:
        return err
    got = [d.get("code") for d in p.get("divisions", []) or []]
    return None if _codes_norm(got) == _codes_norm(case["arg"]) else \
        f"division codes {got}, expected {case['arg']}"


def _find_part(doc, case):
    from .loader import find_schedule
    sc = find_schedule(doc, case["target"]["code"])
    if sc is None:
        return None, f"schedule {case['target']['code']!r} not found"
    p = next((p for p in sc.get("parts", [])
              if _code_eq(p.get("code"), case.get("part"))), None)
    if p is None:
        return None, f"part {case.get('part')!r} not found"
    return p, None


def chk_part_heading_equals(doc, case):
    """A part (case['part']) of the target schedule has exactly this heading --
    pins that a TOC row glued into the heading (e.g. 'Division I 533 ...')
    can never come back."""
    p, err = _find_part(doc, case)
    if err:
        return err
    return None if p.get("heading") == case["arg"] else \
        f"part heading is {p.get('heading')!r}, expected {case['arg']!r}"


def chk_part_division_heading_contains(doc, case):
    """Some division coded case['div'] inside part case['part'] of the target
    schedule has a heading containing arg.  Part-scoped, unlike
    division_heading_contains, because the First Schedule reuses division
    codes across parts (Part I and Part IV both have a 'Division II')."""
    p, err = _find_part(doc, case)
    if err:
        return err
    divs = [d for d in p.get("divisions", []) if _code_eq(d.get("code"), case.get("div"))]
    if not divs:
        return f"division {case.get('div')!r} not found in {case.get('part')}"
    return None if any(case["arg"] in (d.get("heading") or "") for d in divs) else \
        f"division {case.get('div')} headings are " \
        f"{[d.get('heading') for d in divs]!r}, none contain {case['arg']!r}"


def _find_division(doc, case):
    """Locate a division -- or a content-bearing PART -- by code (+ heading).

    ``div_probe`` (optional) disambiguates same-code divisions whose heading
    field is empty (e.g. the First Schedule has six "Division III" nodes and
    Part IV's motor-vehicle one carries no heading): the division's html must
    contain the probe string.
    """
    from .loader import find_schedule
    sc = find_schedule(doc, case["target"]["code"])
    if sc is None:
        return None, f"schedule {case['target']['code']!r} not found"
    parts = [p for p in sc.get("parts", []) if "plain_text" in p]
    for d in list(_all_divisions(sc)) + parts:
        if _code_eq(d.get("code"), case.get("div")) and \
                case.get("div_heading", "") in (d.get("heading") or "") and \
                case.get("div_probe", "") in (d.get("html") or ""):
            return d, None
    return None, f"division {case.get('div')!r}/{case.get('div_heading')!r} not found"


def chk_division_html_contains(doc, case):
    """A named division's html must contain arg (e.g. a specific <li>/<sup>)."""
    d, err = _find_division(doc, case)
    if err:
        return err
    return None if case["arg"] in (d.get("html") or "") else \
        f"division html lacks {case['arg']!r}"


def chk_division_html_not_contains(doc, case):
    """A named division's html must NOT contain arg."""
    d, err = _find_division(doc, case)
    if err:
        return err
    return f"division html contains {case['arg']!r}" \
        if case["arg"] in (d.get("html") or "") else None


def chk_footnote_contains(doc, case):
    """The footnote named by case['ref'] must contain arg in its text."""
    fn = find_footnote(doc, case["ref"])
    if fn is None:
        return f"footnote {case['ref']} not found"
    return None if case["arg"] in fn.get("text", "") else \
        f"footnote {case['ref']} text lacks {case['arg']!r}"


def chk_footnote_html_contains(doc, case):
    """The footnote named by case['ref'] must contain arg in its html."""
    fn = find_footnote(doc, case["ref"])
    if fn is None:
        return f"footnote {case['ref']} not found"
    return None if case["arg"] in fn.get("html", "") else \
        f"footnote {case['ref']} html lacks {case['arg']!r}"


def chk_footnote_html_not_contains(doc, case):
    """No footnote with ref case['ref'] may contain arg in its HTML (e.g. a
    quoted prose clause must not render as an fn-table)."""
    from .loader import all_footnotes
    found = False
    for _l, fn in all_footnotes(doc):
        if fn.get("ref") == case["ref"]:
            found = True
            if case["arg"] in fn.get("html", ""):
                return f"footnote {case['ref']} html contains {case['arg']!r}"
    return None if found else f"footnote {case['ref']} not found"


def chk_footnote_not_contains(doc, case):
    """No footnote with ref case['ref'] may contain arg in its text (guards
    body text leaking into a footnote)."""
    from .loader import all_footnotes
    found = False
    for _l, fn in all_footnotes(doc):
        if fn.get("ref") == case["ref"]:
            found = True
            if case["arg"] in fn.get("text", ""):
                return f"footnote {case['ref']} text contains {case['arg']!r}"
    return None if found else f"footnote {case['ref']} not found"


def chk_footnote_ref_distinct_texts(doc, case):
    """The ref (case['ref']) resolves to >= arg footnotes with distinct texts.

    Guards duplicate-marker preservation: the PDF misprints the same marker
    twice on some pages (e.g. two '5' footnotes on printed page 92) and both
    legal texts must survive dedup."""
    from .loader import all_footnotes
    texts = {fn.get("text") for _l, fn in all_footnotes(doc)
             if fn.get("ref") == case["ref"]}
    n = len(texts)
    return None if n >= int(case["arg"]) else \
        f"ref {case['ref']} has {n} distinct texts, expected >= {case['arg']}"


def chk_division_page_range(doc, case):
    """A named schedule division has exactly the 'start-end' PDF page range."""
    d, err = _find_division(doc, case)
    if err:
        return err
    want = case["arg"]
    got = f"{d.get('start_page')}-{d.get('end_page')}"
    return None if got == want else f"page range {got}, expected {want}"


def chk_division_footnote_contains(doc, case):
    """A named schedule division has a footnote ref (case['ref']) whose text
    contains arg."""
    d, err = _find_division(doc, case)
    if err:
        return err
    for fn in d.get("footnotes", []):
        if fn.get("ref") == case["ref"] and case["arg"] in fn.get("text", ""):
            return None
    return f"division has no footnote {case['ref']} containing {case['arg']!r}"


def chk_footnote_refs_exact(doc, case):
    """The target leaf's footnote refs equal arg exactly (as multisets).

    Pins the footnote-to-leaf mapping: a leaf must carry the footnotes its
    text cites -- no neighbours' notes leaking in from a shared page, no
    phantom duplicates under a misprinted footer's ref.  Targets a schedule
    division when 'div' is given, else the leaf named by 'target'.
    """
    if case.get("div"):
        d, err = _find_division(doc, case)
        if err:
            return err
    else:
        d = _leaf(doc, case)
        if d is None:
            return f"target not found: {case.get('target')}"
    got = sorted(fn.get("ref", "") for fn in d.get("footnotes", []))
    want = sorted(case["arg"])
    return None if got == want else f"footnote refs {got}, expected {want}"


def chk_footnote_refs_ordered_subsequence(doc, case):
    """The refs in arg all exist on the target leaf AND appear in that relative
    order.  Pins numeric ref ordering (10.2 before 10.10): refs are strings, so
    a lexical sort would render 10.1, 10.10, 10.11, 10.2.  Robust to unrelated
    footnotes being added to the leaf later."""
    d = _leaf(doc, case)
    if d is None:
        return f"target not found: {case.get('target')}"
    got = [fn.get("ref", "") for fn in d.get("footnotes", [])]
    missing = [r for r in case["arg"] if r not in got]
    if missing:
        return f"footnote refs missing: {missing} (have {got})"
    positions = [got.index(r) for r in case["arg"]]
    return None if positions == sorted(positions) else \
        f"footnote refs out of order: expected {case['arg']} in order, got {got}"


def chk_section_code_count(doc, case):
    """Exactly arg chapter-section leaves carry the target code (duplicate TOC
    rows, e.g. 236Y omitted + re-inserted, must yield distinct leaves)."""
    from .loader import iter_section_leaves
    code = case["target"]["code"]
    n = sum(1 for lf in iter_section_leaves(doc) if str(lf.get("code")) == code)
    return None if n == int(case["arg"]) else \
        f"{n} leaves with code {code!r}, expected {case['arg']}"


def chk_any_section_html_contains(doc, case):
    """At least one section leaf with the target code has arg in its html
    (find_section only reaches the first of duplicate-code leaves)."""
    from .loader import iter_section_leaves
    code = case["target"]["code"]
    hits = [lf for lf in iter_section_leaves(doc) if str(lf.get("code")) == code]
    if not hits:
        return f"no leaf with code {code!r}"
    return None if any(case["arg"] in (lf.get("html") or "") for lf in hits) \
        else f"no {code!r} leaf html contains {case['arg']!r}"


def chk_body_not_starts_with(doc, case):
    """Section body (after </h4>) must not start with arg."""
    txt, err = _text(doc, case, "html")
    if err:
        return err
    body = re.sub(r"<[^>]+>", "", txt.split("</h4>", 1)[-1]).strip()
    return f"body starts with {case['arg']!r}" if body.startswith(case["arg"]) else None


def chk_tree_division_heading_contains(doc, case):
    """A division under any *chapter* (code == case['div']) must exist with a
    heading containing arg -- e.g. Chapter III / Division II 'Deductions ...'."""
    for ch in doc.get("chapters", []):
        for node in _all_divisions(ch):
            if _code_eq(node.get("code"), case.get("div")) and \
                    case["arg"] in (node.get("heading") or ""):
                return None
    return f"no chapter division {case.get('div')!r} with heading containing {case['arg']!r}"


def chk_chapter_heading_equals(doc, case):
    """The chapter whose code == target.code must exist with heading == arg.

    Guards the chapter tree itself (e.g. CHAPTER I present and its heading
    'PRELIMINARY' free of TOC column-header noise) -- section-targeted checks
    can't see a missing or mis-headed chapter node.
    """
    code = (case.get("target") or {}).get("code")
    for ch in doc.get("chapters", []):
        if ch.get("code") == code:
            got = ch.get("heading") or ""
            if got == case["arg"]:
                return None
            return f"chapter {code!r} heading {got!r} != {case['arg']!r}"
    return f"no chapter with code {code!r} " \
           f"(have: {[c.get('code') for c in doc.get('chapters', [])]})"


def chk_section_heading_equals(doc, case):
    """The section leaf's own heading field must equal arg exactly."""
    leaf = find_section(doc, (case.get("target") or {}).get("code"))
    if leaf is None:
        return f"section {(case.get('target') or {}).get('code')!r} not found"
    got = leaf.get("heading") or ""
    if got == case["arg"]:
        return None
    return f"heading {got!r} != {case['arg']!r}"


def chk_any_schedule_leaf_html_contains(doc, case):
    """Some leaf under the target schedule has arg in its html.

    ``find_leaf('schedule_leaf', ...)`` reaches only the FIRST leaf; content
    assertions on a specific part/division deep in a schedule need the whole
    subtree scanned.
    """
    from .loader import _iter_leaves, find_schedule
    sc = find_schedule(doc, case["target"]["code"])
    if sc is None:
        return f"schedule {case['target']['code']!r} not found"
    if any(case["arg"] in (lf.get("html") or "") for lf in _iter_leaves(sc)):
        return None
    return f"no leaf under {case['target']['code']!r} has {case['arg']!r} in html"


# ---- preamble checks (the enacting preamble is a doc-level singleton) ------

def _preamble_text(doc, case):
    pre = doc.get("preamble")
    if not pre:
        return None, "no preamble present"
    field = case.get("field", "html")
    return pre.get(field, "") or "", None


def chk_preamble_contains(doc, case):
    txt, err = _preamble_text(doc, case)
    if err:
        return err
    return None if case["arg"] in txt else \
        f"preamble {case.get('field','html')} missing {case['arg']!r}"


def chk_preamble_not_contains(doc, case):
    txt, err = _preamble_text(doc, case)
    if err:
        return err
    return f"preamble {case.get('field','html')} unexpectedly contains {case['arg']!r}" \
        if case["arg"] in txt else None


def chk_preamble_matches(doc, case):
    txt, err = _preamble_text(doc, case)
    if err:
        return err
    return None if re.search(case["arg"], txt) else \
        f"preamble {case.get('field','html')} does not match /{case['arg']}/"


def chk_preamble_not_matches(doc, case):
    txt, err = _preamble_text(doc, case)
    if err:
        return err
    m = re.search(case["arg"], txt)
    return f"preamble matches forbidden /{case['arg']}/ -> {m.group(0)!r}" if m else None


REGISTRY = {
    "chapter_heading_equals": chk_chapter_heading_equals,
    "preamble_contains": chk_preamble_contains,
    "preamble_not_contains": chk_preamble_not_contains,
    "preamble_matches": chk_preamble_matches,
    "preamble_not_matches": chk_preamble_not_matches,
    "any_schedule_leaf_html_contains": chk_any_schedule_leaf_html_contains,
    "section_heading_equals": chk_section_heading_equals,
    "plain_contains": chk_plain_contains,
    "plain_not_contains": chk_plain_not_contains,
    "plain_not_matches": chk_plain_not_matches,
    "html_contains": chk_html_contains,
    "html_not_contains": chk_html_not_contains,
    "html_matches": chk_html_matches,
    "html_not_matches": chk_html_not_matches,
    "plain_matches": chk_plain_matches,
    "has_fbr_table": chk_has_fbr_table,
    "has_subsection_li": chk_has_subsection_li,
    "footnote_text_nonempty": chk_footnote_text_nonempty,
    "footnote_any_contains": chk_footnote_any_contains,
    "footnote_html_has_table": chk_footnote_html_has_table,
    "schedule_has_table": chk_schedule_has_table,
    "division_table_count": chk_division_table_count,
    "division_code_count": chk_division_code_count,
    "schedule_part_codes": chk_schedule_part_codes,
    "part_division_codes": chk_part_division_codes,
    "schedule_max_table_rows": chk_schedule_max_table_rows,
    "schedule_code_equals": chk_schedule_code_equals,
    "division_heading_contains": chk_division_heading_contains,
    "part_heading_equals": chk_part_heading_equals,
    "part_division_heading_contains": chk_part_division_heading_contains,
    "division_body_excludes": chk_division_body_excludes,
    "division_html_contains": chk_division_html_contains,
    "division_html_not_contains": chk_division_html_not_contains,
    "body_not_starts_with": chk_body_not_starts_with,
    "footnote_contains": chk_footnote_contains,
    "footnote_html_contains": chk_footnote_html_contains,
    "footnote_not_contains": chk_footnote_not_contains,
    "footnote_html_not_contains": chk_footnote_html_not_contains,
    "footnote_ref_distinct_texts": chk_footnote_ref_distinct_texts,
    "division_page_range": chk_division_page_range,
    "division_footnote_contains": chk_division_footnote_contains,
    "footnote_refs_exact": chk_footnote_refs_exact,
    "footnote_refs_ordered_subsequence": chk_footnote_refs_ordered_subsequence,
    "section_code_count": chk_section_code_count,
    "any_section_html_contains": chk_any_section_html_contains,
    "tree_division_heading_contains": chk_tree_division_heading_contains,
}


def run_case(doc, case):
    fn = REGISTRY.get(case.get("check"))
    if fn is None:
        return f"unknown check type {case.get('check')!r}"
    try:
        return fn(doc, case)
    except Exception as exc:  # a check crashing is itself a failure
        return f"check raised {type(exc).__name__}: {exc}"
