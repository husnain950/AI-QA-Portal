# Round 17 — before / after

Companion to [`phase3-round17-container-code-guard.md`](phase3-round17-container-code-guard.md).
Every number measured on this machine at `e09d156`, the two runs differing only in
`_STRUCTURAL_RE`'s PART branch.

## The register

| lane | before | after |
|---|---|---|
| acts | 15 | **15** |
| rules | 5 | **5** |
| ordinance | 5 | **5** |
| **total** | **25** | **25** |

`tools/suite/register.json` unchanged. **That is the row's own prediction** — "0 hits, an
enabler". No invariant can see a swallowed `PART-N`: `_STRUCT_LINE` keeps the narrow
`PART\s+` spelling deliberately, because widening it would report nine annexure-FORM part
lines as defects.

## What actually moved — 14 gained, 0 lost

| document | candidates | cut | kept | why kept |
|---|---|---|---|---|
| Sales Tax Rules 2006 (01-01-2025) | 7 | **4** | 3 | 2 × form STR-11 · 1 × `PART – IV` en dash |
| Sales Tax Rules 2006 (30-06-2025) | 5 | **4** | 1 | `PART – IV` en dash |
| Customs Rules 2001 (30.06.2023) | 5 | **0** | 5 | rule 34's permission form; 0 parts in tree |
| STSP Rules 2007 (05.03.2015) | 3 | **3** | 0 | — |
| STSP Rules 2007 (30.06.2015) | 3 | **3** | 0 | — |
| | **23** | **14** | **9** | |

Round 13 predicted 14 gained : 6 lost for the bare widening. **The guard turns the 6 into
0 and the 14 holds.** All six are in the `kept` column.

## Before / after, one leaf

`Sales Tax Rules, 2006 (Updated upto 01-01-2025)`, CHAPTER XI · PART I · rule 87 — the
real case:

```diff
  87. ... shall be sold in the manner prescribed in this Part.
- PART-II
- ATTACHMENT AND SALE OFMOVABLE
- PROPERTY
```
The code line is dropped (the tree holds it as `PART II`); the two caption lines are
**re-homed to rule 88**, not discarded, because they do not match the node's one-line
heading. Net −1 word on the document.

And the form, same document, CHAPTER XVIII · rule 165 — unchanged, which is the point:

```
  165. ... FORM STR-11
  [See rule 18(2)]
  PART-I            <- still here
  376[PART-II       <- still here
```

## Conservation — unchanged everywhere

| document | before | after |
|---|---|---|
| STSP Rules 2007 (05.03.2015) | 100.000% | **100.000%** |
| STSP Rules 2007 (30.06.2015) | 100.000% | **100.000%** |
| Sales Tax Rules 2006 (01-01-2025) | 99.998% | **99.998%** |
| Sales Tax Rules 2006 (30-06-2025) | 100.000% | **100.000%** |
| Customs Rules 2001 (30.06.2023) | 74.087% | **74.087%** (output byte-identical) |

## The gate

`tools/tests/test_hyphenated_part_needs_a_container.py`, 3 cases, all through
`build_sections`. Each way to break the change fails a different case:

| removed | fails |
|---|---|
| the widening | `test_a_vouched_part_line_cuts_the_section` |
| the guard | `test_an_unvouched_part_line_does_not_cut_the_section` |
| the **wiring** (`container_codes=frozenset()`) | `test_a_vouched_part_line_cuts_the_section` |

## Rejected, measured

- **Guarding CHAPTER too.** 74.087% → 74.099% on Customs Rules 2001, and **all 28 tokens
  are a duplication** — the preamble swallows rule 1's opening text a second time because
  `preamble_refs` passes no codes. Not one leaf changed. Those four captions are Phase 5.
- **En/em dashes in the separator class.** Zero gain: neither Sales Tax Rules 2006 edition
  holds a `PART IV` node, so the guard refuses `PART – IV` regardless.
- **Widening the suite's `_STRUCT_LINE`.** Would report the nine FORM lines as defects.

## Verified

```
pytest tools/tests -q     95 passed, 1 skipped   (92 + 1 baseline, +3 new)
ruff check                All checks passed      (bare)
run_suite.py × 3          15 / 5 / 5 = 25        (unchanged)
discover_corpus --check   no drift
du -sh data/ocr_cache     0B
```
