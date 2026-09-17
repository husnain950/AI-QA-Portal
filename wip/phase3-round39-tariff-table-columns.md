# Round 39 — the tariff tables, FS-02 and FS-07

Round 38 closed 16 of QA Cycle 1's 19 rows and held two: the FIRST and THIRD
SCHEDULE tariff tables of `Federal Excise Act, 2005 as amended upto 30-06-2025`,
which reached the review portal as `<p>` prose instead of a table. The ledger
carried them with a diagnosis and an open question:

> `tables.find_table_spans` needs a `(1) (2) (3)` numbering row within 8 lines of
> the header; the source prints `Col.(1) Col.(2) Col.(3) Col.(4)`, so no span is
> detected … **Widening `_NUM_TOKEN` is one line**; whether `render_table` then
> produces usable output across repeated page headers, six-line wrapped cells,
> cite markers inside cells and Table-II's nested 3(a)/(b)/(i) is the open
> question.

The diagnosis is right and was re-derived from the page before anything moved:
page 73 prints `Col.(1)` `Col.(2)` `Col.(3)` `Col.(4)` as four words on one line
at top 170.1, spanning 130.1–159.3, 226.4–255.6, 342.4–371.6 and 440.2–469.4.

**The answer to the open question is no.** The one-line widening detects the span
and then renders a table that is worse than the prose it replaced. It took
**four** changes, not one, and this round ships all four.

---

## Why the one-line fix is not a fix

With `_NUM_TOKEN` widened and nothing else, Table-I renders 125 `<tr>` for a
table with 69 rows. Serial 6 alone is shredded across five of them:

```
<tr><td>6 Aerated</td><td>waters manufactured wholly from</td>…
<tr><td>juices</td><td>or pulp of [ vegetables, food grains</td><td>] or</td>…
<tr><td>fruits</td><td>and which do</td><td>not</td><td></td></tr>
```

and the per-page header block reappears nine times as data:

```
<tr><td>S.No.</td><td>Description of Goods</td>…</tr>
<tr><td>Col.(1)</td><td>Col.(2) quantities prescribed under</td>…</tr>
```

Shipping the widening alone would have turned a readable paragraph into that.

---

## What was actually wrong — four defects, measured

### 1. `_NUM_TOKEN` matched only the bare `(N)` spelling

`^\(\d+\)$` against a source that prints `Col.(1)`. No span, so all eleven pages
fell through to `<p>`/`<li>`. Widened to `^(?:Col\.?\s*)?\(\d+\)$`.

The same constant also picks the thead/tbody split in `render_table`
(`_is_num_cell`), so one edit fixes both.

### 2. The column boundaries came from the labels' centres

`_boundaries` puts a boundary at the midpoint between two numbering labels'
centres, and refines it with `_white_gap_between` when a fully white gutter
exists. Neither works here:

- The centre rule assumes a label is centred over its own column. `Col.(1)` is a
  label **wider than the serial column it names** — centre 144.7 against a true
  boundary near 170 — so the midpoint lands 19pt **inside** a description column
  that starts at x0 174.1, and every short leading word of a wrapped line is
  stolen into the serial cell.
- The white-gutter refinement never fires on a table this long. Measured over
  Table-I's 221 data rows, the minimum occupancy in each gutter is **4, 4 and 5
  rows** — about 2%, never zero. All three gutters returned `None`.

Fixed with `_valley_gap_between`: the widest **low-occupancy** valley, tolerating
a bridge from under 5% of the rows (`len(rows) // 20`, so under 20 rows it is 0
and the behaviour is exactly the old exact-white test). It runs **only where the
white test already returned None**, so a table that renders correctly today keeps
the boundary it has.

Boundaries on the real document, before → after:

| table | before (label centres) | after (valley) | true column left edges |
|---|---|---|---|
| FIRST SCH. Table-I | 192.8 / 299.0 / 405.9 | **170.0 / 316.0 / 395.0** | 174.1 / 319 / 406 |
| FIRST SCH. Table-II | 189.4 / 292.3 / 394.3 | **164.5 / 311.5 / 386.0** | 174 / 319 / 406 |

### 3. The header block is reprinted on every printed page

Only the first is the thead. `_group_logical_rows` now drops each repeat whole —
from its `S.No.` line through its numbering row, bounded to 8 lines so a stray
`S. No.` in a cell cannot eat the table — which also lets the wrapped tail below
a page break continue the row it belongs to instead of being glued into the
reprinted `Col.(2)` cell.

### 4. `_assign` ordered a column's words by `top`

`top` restarts at the head of each page, so for a row that crosses a page break
the continuation sorted **before** the text it continues. Serial 6 read
`quantities prescribed under … Aerated waters if manufactured …`. The words are
already appended in reading order by `_group_logical_rows`, one line at a time,
each line sorted by `x0`; the re-sort is simply dropped.

---

## Serial 6, before and after

Before — one cell per printed line, out of order, across five rows:

```
<td>6 Aerated</td><td>waters manufactured wholly from</td><td>if Respective headings</td>
```

After — one cell, in reading order, across the page break, cite marker in place:

```
<td>6</td>
<td>Aerated waters if manufactured wholly from juices or pulp of
    <sup class="cite" title="Word omitted by Finance Act, 2008.">72.4</sup>
    [ ] vegetables, food grains or fruits and which do not contain any other
    ingredient, indigenous or imported, other than sugar, coloring materials,
    preservatives or additives in quantities prescribed under the West Pakistan
    Pure Food Rules, 1965.</td>
<td>Respective headings</td>
<td><sup class="cite" …>72.5</sup> [Twenty] per cent of retail price</td>
```

---

## The reviewer found one instance of a corpus-wide class, again

Measured over all 168 staged sources before any code was written:

| class | sites |
|---|---|
| `Col.(N)` numbering rows | **162 rows / 17 documents** |
| lanes affected | **acts only** — 0 in rules, 0 in ordinance |

All 17 are Federal Excise editions. This is why the `_NUM_TOKEN` widening is
**not** ported to the `fbr_ingest` fork: no document that fork parses prints the
spelling. Defects 2–4 are general and the port is logged as its own row.

---

## What this round does NOT close

**THIRD SCHEDULE Table-I is still prose**, and it is a different defect. Its
header (p.90) is `S.No. Description of Goods Heading/ sub-heading Number` with
**no numbering row at all** — the next line is data, `(1) Crude vegetable oil, …`,
where `(1)` is a serial, not a column label. `find_table_spans` requires a
numbering row because that is what makes the column count recoverable, so there
is nothing here to widen.

Rendering it needs column boundaries inferred with no numbering row — from the
header's own word positions, or from the data's left-edge clusters. That makes
`find_table_spans` accept spans it rejects everywhere in the corpus today, which
is a far wider blast radius than anything above. It is logged as its own row, not
bundled into this one.

So of the two held rows: **FS-02 closed**, **FS-07 half closed** (Third Schedule
Table-II renders; Table-I does not).
