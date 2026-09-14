# Phase 3 — a flattened table row is table content (register 13 → 12)

Written 2026-09-14. Branch `fix/suite-table-row-join`.

**An invariant bug, not a parser defect.** No parser code was touched and no PDF was
converted. The distinction is the whole reason this repo insists on measuring the invariant
half and the parser half separately: a class that is "part wrong-invariant, part real
defect" hides both behind one total.

---

## What was measured

| lane | before | after |
|---|---|---|
| acts | 6 | 6 |
| rules | 2 | **1** |
| ordinance | 5 | 5 |
| **register** | **13** | **12** |

Per-invariant `FAIL` lines were diffed against a baseline captured from `main`, across all
103 documents. **Exactly one line differs**: the rules lane's
`no_foreign_section_start_in_body`. acts and ordinance are byte-identical.

`tools/tests`: **234 passed, 1 skipped** (231 baseline + 3 new). `ruff check` (bare): clean.
`data/ocr_cache`: 0 B.

## The bug

`_table_cell_lines` (`tools/suite/invariants/_common.py`) collected the text of each `<td>`
separately. But the renderer flattens a table **two** ways, and only one of them produces
lines that equal a cell:

- a cell whose content **wraps** contributes its own physical lines — the case the function
  was written for, the Eleventh Schedule's `chapter 25` tariff reference;
- a **short row** is emitted as ONE line with its cells joined by a single space.

A row-joined line equals no individual cell, so it was never excluded.

Sales Tax Rules 2006 (01-01-2025) rule 13 carries the Schedule row

```html
<tr><td>44A</td><td>Steel ingots / bala</td><td>M. Tons</td></tr>
```

which flattens to `44A Steel ingots / bala M. Tons`. `no_foreign_section_start_in_body`
read that **serial-number cell** as the start of rule 44A.

## Why the hit was convincing

Every other guard on that invariant agreed, which is what made it look genuine rather than
like a false positive:

- the code folds to a real leaf in the document;
- `44A` sorts after `13`, so a body could legitimately have swallowed it;
- **the victim really is starved** — rule 44A *is* heading-only, because the source prints
  `“44A.` with a left double quotation mark before the code (PDF page 66), a printing error
  `exemptions/rules.json` already covers from round 19.

Only the table exclusion could refuse this line, and it was looking at cells.

## The reach is large and the effect is one hit — both are reported

The widened set excludes **46,228** more lines than the per-cell shape alone. Of those,
6,404 *look* like a section start or a structural boundary — penalty-table rows
(`1. Where any person Such person shall pay a penalty of five 26`) and schedule rate rows
(`32. Fertilizers Respective heading`). They are all genuinely table content and all
genuinely should be excluded.

**Exactly one reported hit changes.** The other 46,227 were already refused by the callers'
own guards — the code must resolve to a real leaf, it must sort after this one, the victim
must be starved. Both numbers are in the docstring on purpose: a future reader who
discovers the reach without the effect would reasonably conclude the fix was reckless.

Of 49,739 `<tr>` row-joins across the corpus, **20,671** appear verbatim as a `plain_text`
line. The rest are rows whose cells wrap, already covered by the per-cell shape.

## What was rejected

**Stripping tags from cell text before joining.** Measured across all 103 documents: it
moves neither number — 20,671 live row-joins either way. A row carrying a `<sup>` citation
does not match its `plain_text` line with the tags stripped either, because the renderer
flattens the marker to a bare digit. It is code that changes nothing, so it is not there.

## The tests, and one that was wrong first

Three cases in `tools/tests/test_table_row_join_is_cell_content.py`. Two fail without the
fix; the third must pass **both** ways.

- `test_a_flattened_row_counts_as_table_content` — the row-join is excluded. RED without.
- `test_the_serial_cell_is_not_reported_as_a_foreign_section_start` — end to end through the
  invariant. RED without.
- `test_wrapped_cell_lines_are_still_collected` — the shape that already worked. Green
  either way, on purpose: a fix that *replaced* the per-cell collection instead of adding
  to it would pass the first two and silently drop the Eleventh Schedule's wrapped
  `chapter 25` back into the invariant's path.

**The end-to-end case passed without the fix on its first draft**, i.e. it was not a gate at
all. The fixture nested its leaves under `children`; `loader._iter_leaves` walks
`parts`/`divisions`/`sections` and nothing else, so it yielded **no leaves** and the
invariant returned `[]` trivially. Corrected to `sections`, it goes red as it should. A
test that has not been watched to fail is not evidence — this one proves the point twice.
