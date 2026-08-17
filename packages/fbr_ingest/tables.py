"""Detect and render tables that appear in section / schedule *body* text.

Unlike footnote tables (rendered as ``fn-table`` flex grids), body tables use
the reference's ``<table class="fbr-table">`` markup with a ``<thead>`` (the
column-title row plus the ``(1) (2) ...`` numbering row) and a ``<tbody>``.

A table is recognised by a header line beginning with ``S. No.`` / ``S.No.`` or
by a literal ``TABLE`` keyword, anchored on a ``(1) (2) ...`` numbering row that
also fixes the column edges.  Wrapped cell text (a line indented past the first
column) is merged into the row it continues.
"""

from __future__ import annotations

import html as _html
import re

_COL_TOL = 14.0

_NUM_CELL = re.compile(r"^\(\d+\)$")


def _clean_cell(c) -> str:
    return "" if c is None else str(c).strip()


def _pad_rows(cells):
    rows = [[None if c is None else str(c).strip() for c in row]
            for row in cells]
    rows = [r for r in rows if any(c is not None for c in r)]
    if not rows:
        return []
    ncol = max(len(r) for r in rows)
    return [r + [None] * (ncol - len(r)) for r in rows]


def _span_len(row, ci: int) -> int:
    """Number of raw columns covered by ``row[ci]``.

    pdfplumber/PyMuPDF represent a horizontal span as a real cell followed by
    ``None`` placeholders.  Blank strings are real empty cells and do not count
    as covered slots.
    """
    j = ci + 1
    while j < len(row) and row[j] is None:
        j += 1
    return j - ci


def _uniform_group_size(rows) -> int | None:
    """Return the repeated phantom-column group size, if a table has one.

    Some ruled FBR tables are visually 3 or 6 columns wide, but the extractor
    sees each visual column as a fixed group of tiny subcolumns.  A separator
    row exposes that pattern as e.g. cells at 0,3,6 or 0,3,6,9,12,15, each
    followed by ``None`` placeholders.  Collapsing by the smallest such group
    removes the empty gutter columns while preserving later area/rate pairs.
    """
    candidates = []
    for row in rows:
        spans = []
        ci = 0
        while ci < len(row):
            if row[ci] is None:
                spans = []
                break
            span = _span_len(row, ci)
            spans.append(span)
            ci += span
        if (ci == len(row) and len(spans) >= 3 and len(set(spans)) == 1
                and spans[0] > 1):
            candidates.append(spans[0])
    return min(candidates) if candidates else None


def _cell(text="", colspan=1, rowspan=1):
    return {"text": text, "colspan": max(1, int(colspan)),
            "rowspan": max(1, int(rowspan))}


# ---------------------------------------------------------------------------
# geometric normalisation -- colspan AND rowspan from the extractor's cell
# bboxes.  The text matrix alone cannot tell a horizontal merge from a
# vertical one (both appear as ``None`` placeholders), which mis-rendered the
# Division VIII / IIB tall rate cells as colspans and dropped the s.182
# fragment's empty "section" column.  Bboxes are unambiguous.
# ---------------------------------------------------------------------------

_EDGE_TOL = 3.0


def _cluster_edges(vals):
    out: list[list[float]] = []
    for v in sorted(vals):
        if out and v - out[-1][-1] <= _EDGE_TOL:
            out[-1].append(v)
        else:
            out.append([v])
    return [sum(g) / len(g) for g in out]


def _edge_index(edges, x):
    for i, e in enumerate(edges):
        if abs(x - e) <= _EDGE_TOL:
            return i
    return None


def _normalise_geometric(cells, rows):
    """Normalise via cell bboxes; returns None when geometry is unusable.

    ``rows`` is the extractor's per-row list of cell bboxes (None where a
    position is covered by a merged cell), parallel to ``cells``.  A raw grid
    column is *witnessed* when at least one cell occupies exactly that column
    -- unwitnessed slivers (the Eleventh Schedule's phantom column between
    header and data rules) are absorbed into the spans that cross them, while
    genuinely empty columns (the s.182 "section" column on a continuation
    page) survive because their empty cells witness them.
    """
    n = min(len(cells), len(rows))
    keep = [r for r in range(n)
            if any(_clean_cell(c) for c in cells[r])
            and any(bb is not None for bb in rows[r])]
    if len(keep) < 1:
        return None
    boxes = []                       # (kept_row_idx, raw_col, bbox)
    for ki, r in enumerate(keep):
        for c, bb in enumerate(rows[r]):
            if bb is not None:
                boxes.append((ki, c, bb))
    edges = _cluster_edges([bb[0] for *_, bb in boxes]
                           + [bb[2] for *_, bb in boxes])
    if len(edges) < 3:
        return None
    witnessed: set[int] = set()
    spans_x = {}
    for ki, c, bb in boxes:
        i0, i1 = _edge_index(edges, bb[0]), _edge_index(edges, bb[2])
        if i0 is None or i1 is None or i1 <= i0:
            return None              # jittered grid -> let the text paths try
        spans_x[(ki, c)] = (i0, i1)
        if i1 - i0 == 1:
            witnessed.add(i0)
    if len(witnessed) < 2:
        return None
    wit = sorted(witnessed)
    windex = {rawcol: i for i, rawcol in enumerate(wit)}
    width = len(wit)
    # vertical bands of the kept rows (midpoints decide rowspan membership)
    mids = []
    for r in keep:
        tops = [bb[1] for bb in rows[r] if bb is not None]
        bots = [bb[3] for bb in rows[r] if bb is not None]
        mids.append((min(tops) + max(bots)) / 2)
    out = [[None] * width for _ in keep]
    covered = [[False] * width for _ in keep]
    for ki, c, bb in boxes:
        i0, i1 = spans_x[(ki, c)]
        cover_w = [windex[k] for k in wit if i0 <= k < i1]
        if not cover_w:
            # cell entirely inside an unwitnessed sliver: fold right/leftward
            near = min(wit, key=lambda k: abs(edges[k] - bb[0]))
            cover_w = [windex[near]]
        start, colspan = cover_w[0], len(cover_w)
        rowspan = 1
        for k2 in range(ki + 1, len(keep)):
            if bb[1] < mids[k2] < bb[3]:
                rowspan += 1
            else:
                break
        if covered[ki][start]:
            continue                 # defensive: overlapping geometry
        out[ki][start] = _cell(_clean_cell(cells[keep[ki]][c]),
                               colspan, rowspan)
        for k2 in range(ki, ki + rowspan):
            for w in cover_w:
                if k2 < len(keep) and not (k2 == ki and w == start):
                    covered[k2][w] = True
    # fill genuine holes (witnessed column, no cell, not span-covered) so
    # every row's emitted colspans + covered slots sum to the table width
    for ki in range(len(keep)):
        for w in range(width):
            if out[ki][w] is None and not covered[ki][w]:
                out[ki][w] = _cell("")
    return out


def _normalise_grouped(rows, group_size: int):
    width = (max(len(r) for r in rows) + group_size - 1) // group_size
    out = []
    for row in rows:
        slots = [None] * width
        non_none = sum(1 for value in row if value is not None)
        text_cells = sum(1 for value in row
                         if value is not None and _clean_cell(value))
        ci = 0
        while ci < len(row):
            if row[ci] is None:
                ci += 1
                continue
            text = _clean_cell(row[ci])
            span = _span_len(row, ci)
            if text:
                start = ci // group_size
                end = min(width - 1, (ci + span - 1) // group_size)
                # A word line inside a visual group may be followed by Nones
                # from row/column spans belonging to neighbouring groups.  If
                # there are no explicit blank edge cells on the row, keep that
                # text in its own group; explicit blanks indicate a section
                # band that really spans across groups.
                if end > start and ci % group_size and non_none == text_cells:
                    end = start
                if slots[start] is None:
                    slots[start] = _cell(text, end - start + 1)
                else:
                    slots[start]["text"] = " ".join(
                        p for p in (slots[start]["text"], text) if p)
                    slots[start]["colspan"] = max(
                        slots[start]["colspan"], end - start + 1)
            ci += span
        if any(s and s["text"] for s in slots):
            out.append(slots)
    return _fill_missing_cells(out, width)


def _numbering_ranges(rows):
    width = max(len(r) for r in rows)
    for row in rows:
        starts = [ci for ci, value in enumerate(row)
                  if value is not None and _NUM_CELL.match(_clean_cell(value))]
        if len(starts) >= 3 and len(starts) < width and width - len(starts) <= 3:
            return [(starts[i], starts[i + 1] if i + 1 < len(starts) else width)
                    for i in range(len(starts))]
    return None


def _range_index(ranges, col):
    for idx, (start, end) in enumerate(ranges):
        if start <= col < end:
            return idx
    return None


def _normalise_ranges(rows, ranges):
    width = len(ranges)
    out = []
    for row in rows:
        slots = [None] * width
        text_cells = sum(1 for value in row
                         if value is not None and _clean_cell(value))
        ci = 0
        while ci < len(row):
            if row[ci] is None:
                ci += 1
                continue
            text = _clean_cell(row[ci])
            span = _span_len(row, ci)
            if text:
                start = _range_index(ranges, ci)
                end = _range_index(ranges, min(len(row) - 1, ci + span - 1))
                if start is not None and end is not None:
                    if end > start and text_cells != 1:
                        end = start
                    if slots[start] is None:
                        slots[start] = _cell(text, end - start + 1)
                    else:
                        slots[start]["text"] = " ".join(
                            p for p in (slots[start]["text"], text) if p)
                        slots[start]["colspan"] = max(
                            slots[start]["colspan"], end - start + 1)
            ci += span
        if any(s and s["text"] for s in slots):
            out.append(slots)
    return _fill_missing_cells(out, width)


def _normalise_columns(rows):
    width = max(len(r) for r in rows)
    keep = {
        ci
        for row in rows
        for ci, value in enumerate(row)
        if value is not None and _clean_cell(value)
    }
    if len(keep) < 2:
        keep = set(range(width))
    keep_order = [ci for ci in range(width) if ci in keep]
    remap = {old: new for new, old in enumerate(keep_order)}
    out = []
    for row in rows:
        slots = [None] * len(keep_order)
        ci = 0
        while ci < len(row):
            if row[ci] is None:
                ci += 1
                continue
            text = _clean_cell(row[ci])
            span = _span_len(row, ci)
            covered = [remap[c] for c in range(ci, min(ci + span, width))
                       if c in remap]
            if covered:
                # Keep blank cells only when their column is a real kept
                # column; this preserves alignment under multi-row headers.
                if text or ci in keep:
                    slots[covered[0]] = _cell(text, len(covered))
            ci += span
        if any(s and s["text"] for s in slots):
            out.append(slots)
    return _fill_missing_cells(out, len(keep_order))


def _fill_missing_cells(rows, width):
    filled = []
    for row in rows:
        current = [None] * width
        ci = 0
        while ci < width:
            cell = row[ci] if ci < len(row) else None
            if cell is None:
                current[ci] = _cell("")
                ci += 1
                continue
            current[ci] = cell
            for covered in range(ci + 1, min(width, ci + cell["colspan"])):
                current[covered] = None
            ci += cell["colspan"]
        filled.append(current)
    return filled


def _expanded_texts(row):
    texts = [""] * len(row)
    ci = 0
    while ci < len(row):
        cell = row[ci]
        if cell is None:
            ci += 1
            continue
        for k in range(ci, min(len(row), ci + cell["colspan"])):
            texts[k] = cell["text"]
        ci += cell["colspan"]
    return texts


def _start_cell_covering(row, col):
    ci = 0
    while ci < len(row):
        cell = row[ci]
        if cell is None:
            ci += 1
            continue
        if ci <= col < ci + cell["colspan"]:
            return ci, cell
        ci += cell["colspan"]
    return None, None


def _looks_like_new_row(text: str) -> bool:
    t = text.strip()
    return bool(re.match(r"^\d{1,3}\.$", t) or _NUM_CELL.match(t))


def _merge_sparse_continuations(rows):
    """Fold wrapped visual-cell lines into the previous row.

    Extractors often turn a multi-line cell into several sparse rows (for
    example the city list in the builders tables or "751 to" / "1500" bands).
    When every non-empty cell in a sparse row sits under a non-empty cell from
    the previous row, append it to that previous cell instead of drawing a new
    grid row.
    """
    out = []
    for row in rows:
        nonempty = [(i, c) for i, c in enumerate(row)
                    if c is not None and c["text"].strip()]
        if out and nonempty and len(nonempty) < len(row) \
                and all(c["colspan"] == 1 for _, c in nonempty) \
                and not any(_looks_like_new_row(c["text"]) for _, c in nonempty):
            prev_texts = _expanded_texts(out[-1])
            if all(prev_texts[i].strip() for i, _ in nonempty):
                for i, cell in nonempty:
                    _start, prev = _start_cell_covering(out[-1], i)
                    if prev is not None:
                        prev["text"] = " ".join(
                            p for p in (prev["text"], cell["text"]) if p)
                continue
        out.append(row)
    return out


def _normalise_grid(cells, rows=None):
    padded = _pad_rows(cells)
    if not padded:
        return []
    # geometry first: cell bboxes are authoritative for spans and column
    # count (the healed 6-column developers grid must NOT be re-collapsed by
    # the phantom-group heuristic, which exists for bbox-less matrices)
    if rows is not None:
        geo = _normalise_geometric(cells, rows)
        if geo is not None:
            return geo
    group = _uniform_group_size(padded)
    if group:
        return _merge_sparse_continuations(_normalise_grouped(padded, group))
    ranges = _numbering_ranges(padded)
    if ranges:
        return _normalise_ranges(padded, ranges)
    return _normalise_columns(padded)


_HDR_SIGNATURE = re.compile(r"^[\d\s\[\]“”\"']*S(r)?\.?\s*(#|No)", re.IGNORECASE)


def is_header_signature(row) -> bool:
    """True when a raw extract() row is a classic FBR column-header row.

    Used to keep a single-row ruled box (the header of a table whose data
    rows continue on the next page) as a Table instead of dropping it back
    into the line stream.  Leading amendment markers / brackets / quotes
    ("4[S. No.", "“S. No") are part of the printed header and are skipped.
    """
    texts = [_clean_cell(c) for c in row]
    texts = [t for t in texts if t]
    return len(texts) >= 2 and bool(_HDR_SIGNATURE.match(texts[0]))


def _cell_texts(row):
    return [c["text"].strip() for c in row if c is not None and c["text"].strip()]


def _is_numbering_cells(row) -> bool:
    texts = _cell_texts(row)
    return len(texts) >= 2 and all(_NUM_CELL.match(t) for t in texts)


# A cell that is a bare row-serial label: roman ("I", "II.", "iv"), arabic
# ("1", "12."), or a bracketed clause serial ("(a)", "(aa)", "(i)", "(viii)").
# A real column header ("S. No.", "Category", "(A) Karachi ...") never matches.
_SERIAL_CELL = re.compile(
    r"^(?:[IVXLC]+|[ivxlc]+|\d{1,3})\.?$"            # I  II.  1  12.  iv
    r"|^\([a-z]{1,3}\)$"                             # (a) (aa) (bb)
    r"|^\((?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})\)$"   # (i) (ii) (viii)
)


def _first_row_is_data(row) -> bool:
    """A header-less table whose first row is clearly DATA, not a column header:
    its leftmost non-empty cell is a serial label.  Such a row must NOT be
    promoted into ``<thead>`` (which renders it bold) -- e.g. the Third
    Schedule PART I depreciation table's ``I. | Building (all types). | 10%``."""
    texts = _cell_texts(row)
    return len(texts) >= 2 and bool(_SERIAL_CELL.match(texts[0]))


def _tr(cells_, tag):
    parts = []
    ci = 0
    while ci < len(cells_):
        c = cells_[ci]
        if c is None:
            ci += 1
            continue
        attrs = f' colspan="{c["colspan"]}"' if c["colspan"] > 1 else ""
        if c.get("rowspan", 1) > 1:
            attrs += f' rowspan="{c["rowspan"]}"'
        parts.append(f"<{tag}{attrs}>{_html.escape(c['text'])}</{tag}>")
        ci += c["colspan"]
    return "<tr>\n" + "\n".join(parts) + "\n</tr>"


def render_structure(rows) -> str:
    """Emit normalised cell-structure rows as fbr-table markup.

    A ``(1)(2)(3)`` numbering row (searched in the first five rows) closes the
    header.  Without one: a serial-led first row is DATA and gets NO header
    (``<tbody>`` only, so it is not bold); otherwise the first row alone is the
    header.
    """
    if len(rows) < 1 or max(len(r) for r in rows) < 2:
        return ""
    num_row = next((i for i, row in enumerate(rows[:5])
                    if _is_numbering_cells(row)), None)
    if num_row is not None:
        n_head = num_row + 1
    elif _first_row_is_data(rows[0]):
        n_head = 0
    else:
        n_head = 1
    tbody = "\n".join(_tr(r, "td") for r in rows[n_head:])
    if n_head == 0:
        return (f'<table class="fbr-table">\n'
                f'<tbody>\n{tbody}\n</tbody>\n</table>')
    thead = "\n".join(_tr(r, "th") for r in rows[:n_head])
    return (f'<table class="fbr-table">\n<thead>\n{thead}\n</thead>\n'
            f'<tbody>\n{tbody}\n</tbody>\n</table>')


def render_grid(cells, rows=None) -> str:
    """Render ``find_tables()`` output to fbr-table markup.

    ``cells`` is the extract() text matrix; ``rows`` (optional) the parallel
    per-row cell-bbox lists, which enable exact colspan/rowspan recovery
    (:func:`_normalise_geometric`).  This is the primary body-table renderer
    -- it uses the PDF's real gridlines, so it needs no text heuristics.
    """
    return render_structure(_normalise_grid(cells, rows))

_NUM_TOKEN = re.compile(r"^\(\d+\)$")
_BARE_NUM_TOKEN = re.compile(r"^\d{1,2}$")
_ROWNUM = re.compile(r"^\d{1,3}\.$")


def _words(line):
    return sorted(line.words, key=lambda w: w.x0)


def _is_num_cell(t: str) -> bool:
    """A column-numbering token: parenthesised "(3)" or a bare digit "3"."""
    t = t.strip()
    return bool(_NUM_TOKEN.match(t) or _BARE_NUM_TOKEN.match(t))


# A horizontal rule drawn with dash/underscore CHARACTERS (not vector ink), used
# as a separator inside a text-ruled table -- it is not cell content and must not
# break the table span or leak into a cell.
_RULE_LINE = re.compile(r"^[\s_\-–—=]{5,}$")


def _is_rule_line(line) -> bool:
    return bool(_RULE_LINE.match(line.text().strip()))


def _is_numbering_row(words) -> bool:
    toks = [w.text.strip() for w in words]
    if len(toks) < 3:
        return False
    if all(_NUM_TOKEN.match(t) for t in toks):
        return True
    # a BARE consecutive-digit numbering row "1 2 3 ..." -- some FBR tables print
    # the column numbers without parentheses (e.g. s.147(5B)'s advance-tax TABLE).
    # Require the digits to run 1..N in order so a stray data row of small numbers
    # is never mistaken for the numbering row.
    if all(_BARE_NUM_TOKEN.match(t) for t in toks):
        nums = [int(t) for t in toks]
        return nums == list(range(1, len(nums) + 1))
    return False


def _is_header_start(line) -> bool:
    t = line.text().strip()
    if t.upper() == "TABLE":
        return True
    # "S. No.", "S.No.", "Sr. No.", "Sr.No." -- the classic FBR table header
    return bool(re.match(r"^S(r)?\.?\s*No\.?\b", t, re.IGNORECASE))


# ---------------------------------------------------------------------------
# span detection
# ---------------------------------------------------------------------------

def find_table_spans(refs) -> list[tuple[int, int]]:
    """Return [(start, end)] index spans in ``refs`` that form a table.

    A span must contain a numbering row to be accepted (that is what makes the
    column structure recoverable).  A span runs from its header-start line until
    body prose resumes at the left margin or the content ends.
    """
    spans = []
    n = len(refs)
    i = 0
    while i < n:
        if not _is_header_start(refs[i].line):
            i += 1
            continue
        start = i
        # column-1 edge, taken from the numbering row if we can find one soon
        j = i + 1
        num_idx = None
        while j < n and j - start < 8:
            if _is_numbering_row(_words(refs[j].line)):
                num_idx = j
                break
            j += 1
        if num_idx is None:
            i += 1
            continue
        num_left = _words(refs[num_idx].line)[0].x0
        # extend past the numbering row across data rows + wrapped lines; stop
        # when a line begins clearly to the LEFT of the table (body prose or a
        # numbered rule resuming at the margin, e.g. "4. Option ..." at x0~54
        # while table rows sit at x0~103).
        k = num_idx + 1
        seen_data = False
        while k < n:
            if _is_rule_line(refs[k].line):
                # a dash/underscore rule BEFORE any data row separates the
                # header/numbering rows (skip it); the first rule AFTER data is
                # the table's bottom border -> the table ends there (so body
                # prose below it, e.g. a proviso, is never absorbed as rows).
                if seen_data:
                    break
                k += 1
                continue
            w = _words(refs[k].line)
            if not w:
                k += 1
                continue
            if w[0].x0 < num_left - 12:
                break  # a line to the left of the table -> table ended
            # a "(N)" subsection resuming (not the numbering row) ends the table
            if _NUM_TOKEN.match(w[0].text.strip()) and not _is_numbering_row(w):
                break
            seen_data = True
            k += 1
        spans.append((start, k))
        i = k
    return spans


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _center(w):
    return (w.x0 + w.x1) / 2


def _white_gap_between(region_refs, lo, hi):
    """Midpoint of the widest vertical WHITE gap (no word in any row) strictly
    between x-centres ``lo`` and ``hi``, or None if the columns touch.

    A narrow first column (a serial "1." / "2.") beside a wide one throws the
    centre-midpoint boundary off (it lands inside the wide column, leaking its
    left words the wrong way and even splitting a wrapped row).  When a real
    white gutter exists between the two columns, its midpoint is a far better
    boundary; dense tables with no gutter fall back to the centre-midpoint.
    """
    if region_refs is None:
        return None
    ivals = []
    for ref in region_refs:
        if _is_rule_line(ref.line):
            continue
        for w in _words(ref.line):
            if w.x1 > lo and w.x0 < hi:
                ivals.append((max(w.x0, lo), min(w.x1, hi)))
    if not ivals:
        return None
    ivals.sort()
    best = None            # (width, midpoint)
    cursor = lo
    for a, b in ivals:
        if a > cursor:      # a gap [cursor, a]
            w = a - cursor
            if best is None or w > best[0]:
                best = (w, (cursor + a) / 2)
        cursor = max(cursor, b)
    if hi > cursor:
        w = hi - cursor
        if best is None or w > best[0]:
            best = (w, (cursor + hi) / 2)
    # require a real gutter (>= 4pt) so a hairline between dense columns doesn't
    # masquerade as a gap
    return best[1] if best and best[0] >= 4.0 else None


def _boundaries(num_words, region_refs=None):
    """Column boundaries between the ``(1) (2) ...`` / ``1 2 3`` token centres.

    The numbering tokens are centred in their columns, so midpoints between
    consecutive centres give the column count and a first approximation.  Where a
    real white gutter separates two columns (``_white_gap_between``), its midpoint
    replaces the centre-midpoint -- this keeps a narrow serial column from
    stealing its wide neighbour's left words.  Dense tables with no gutter keep
    the centre-midpoint unchanged.
    """
    centers = sorted(_center(w) for w in num_words)
    bounds = [float("-inf")]
    for i in range(len(centers) - 1):
        mid = (centers[i] + centers[i + 1]) / 2
        gap = _white_gap_between(region_refs, centers[i], centers[i + 1])
        bounds.append(gap if gap is not None else mid)
    bounds.append(float("inf"))
    return bounds


def _col_of(w, bounds):
    c = _center(w)
    for i in range(len(bounds) - 1):
        if bounds[i] <= c < bounds[i + 1]:
            return i
    return len(bounds) - 2


def _has_col0(words, bounds):
    return any(_col_of(w, bounds) == 0 for w in words)


def _group_logical_rows(region_refs, bounds):
    from collections import Counter
    from dataclasses import replace

    from .pagemodel import _true_table_marker, cite_sentinel

    # Same marker test as the grid-table path: relative to the table's own
    # dominant size and capped below 100.  Bare ``is_marker`` is absolute
    # (size <= 9.4) and wraps dense-table CONTENT digits -- a 4-digit year
    # ("1983", 30.06.2024 p737) exceeds the sentinel's {1,3} marker pattern,
    # so it could never be expanded or restored and leaked \x01..\x02 into
    # the output.
    sizes = Counter(round(x.size, 1) for ref in region_refs
                    for x in _words(ref.line))
    dominant = sizes.most_common(1)[0][0] if sizes else 10.0
    rows = []
    for ref in region_refs:
        if _is_rule_line(ref.line):
            continue  # dash/underscore separator -> not a row
        # a superscript citation marker inside the table is wrapped in a
        # sentinel (on a COPY -- the Line's words stay pristine for plain_text)
        # so builder._expand_table_cites can render it as <sup class="cite">
        w = [replace(x, text=cite_sentinel(ref.page, x.text.strip()))
             if _true_table_marker(x, dominant) else x for x in _words(ref.line)]
        if not w:
            continue
        if rows and not _has_col0(w, bounds):
            rows[-1].extend(w)          # wrapped continuation of previous row
        else:
            rows.append(list(w))
    return rows


def _assign(words, bounds):
    cols = [[] for _ in range(len(bounds) - 1)]
    for w in words:
        cols[_col_of(w, bounds)].append(w)
    # read top-to-bottom, then left-to-right within each column
    return [" ".join(x.text for x in sorted(c, key=lambda w: (round(w.top), w.x0))).strip()
            for c in cols]


def render_table(region_refs) -> str:
    """Render a detected table span to ``<table class="fbr-table">`` markup."""
    num_i = next((i for i, r in enumerate(region_refs)
                  if _is_numbering_row(_words(r.line))), None)
    if num_i is None:
        return ""
    # gutters are measured from DATA rows only (rows after the numbering row);
    # the numbering row's isolated centred digits and the left-aligned header
    # create spurious gaps that would misplace a boundary.
    bounds = _boundaries(_words(region_refs[num_i].line), region_refs[num_i + 1:])
    if len(bounds) < 3:
        return ""
    rows = _group_logical_rows(region_refs, bounds)
    grid = [_assign(r, bounds) for r in rows]
    # the numbering row marks the thead/tbody boundary
    num_row = next((idx for idx, cells in enumerate(grid)
                    if any(c.strip() for c in cells)
                    and all(_is_num_cell(c) for c in cells if c.strip())), 0)

    def tr(cells, tag):
        return "<tr>\n" + "\n".join(
            f"<{tag}>{_html.escape(c)}</{tag}>" for c in cells) + "\n</tr>"

    thead = "\n".join(tr(c, "th") for c in grid[:num_row + 1])
    tbody = "\n".join(tr(c, "td") for c in grid[num_row + 1:])
    return (f'<table class="fbr-table">\n<thead>\n{thead}\n</thead>\n'
            f'<tbody>\n{tbody}\n</tbody>\n</table>')
