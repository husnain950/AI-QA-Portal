# Phase 3 — a split code suffix that kept its dot (rules 2 → 1)

Written 2026-09-14. Branch `fix/phase3-split-suffix-multiletter`.

Removes a **phantom duplicate leaf** from Sales Tax Rules 2006 (30-06-2025). No other
document in the corpus is touched.

---

## What was measured

| | before | after |
|---|---|---|
| section leaves | 344 | **343** |
| duplicate codes | `{'150': 2}` | **`{}`** |
| codes gained / lost | — | **0 / 0** |
| rules lane `section_carries_its_body` | 1 | **0** |

`legal_ingest` had **zero** commits since the corpus revision `f3a37e0`, so the staged file
*was* the HEAD baseline and this diff isolates the fix exactly.

## The defect

Round 24 taught `toc._rejoin_split_suffix` to read `79` `A` — a code whose letter suffix the
text layer split off, losing the dot along with the space. Its discriminator is the
**duplicate**: a row repeating the code immediately above it.

Page xii of this edition prints a second shape that signal cannot see:

```
SUB-CHAPTER 1 ................................................  110
150 ZQR.           Application. ..........................  110
[150ZQS.           Definitions. ..........................  110
```

The suffix is **three letters** and it **kept its dot**, and only this one row of the whole
`150Z*` family carries the space — every sibling from `150ZA` to `150ZQQ` prints correctly.
Read as code `150`, the title runs on and swallows the rest of the contents page, so the
document shipped **two leaves coded 150**:

| | heading | body |
|---|---|---|
| real | `Form` | 349 chars |
| phantom | `ZQR. Application [150ZQS. Definitions 110 [150ZQT Goods to b…` | 95 chars |

`150ZQR` and `150ZQS` already existed with their own correct bodies (651 and 2,274 chars),
so nothing was lost to the phantom — it was pure contents-page furniture wearing a code.

## The fix, and the two signals that keep it narrow

A second branch on:

- **the title opens with a run of capitals ending in a DOT.** The function's existing
  docstring records why a bare spaced `[A-Z]{1,4}` is wrong — it eats the first word of any
  title opening with a capital — and the dot is exactly what that form lacked. A real title
  almost never opens with an all-caps word terminated by a period.
- **the previous section row is a suffixed sibling of this numeral**
  (`150ZQP`.startswith(`150`)). A genuine bare `150.` cannot appear there: it would sort
  before `150ZA`, not after `150ZQP`.

Measured over **every acts and rules document** before a line was written: the candidate
fires on exactly **one** row in the whole corpus.

## The first version measured clean and did nothing

Worth recording, because the measurement did not catch it and the re-conversion did.

The first attempt read `last_section`. It converted the document, produced a
**byte-identical** output — 0 changed leaves, the phantom still there — and the register
never moved. A trace showed why:

```
TRACE code='150' last='149'   any='149'      head='Form'              -> '150'
TRACE code='150' last=None    any='150ZQP'   head='ZQR. Application'  -> '150ZQR'
```

`last_section` is **None** at that row. It is reset at every chapter, part and division
open, and this row is the first one after a `SUB-CHAPTER 1` caption — so it is None exactly
where the signal is needed. The corpus-wide measurement had used *leaf order*, which ignores
containers, and so measured a signal the parser could not actually see at that point.

The fix threads a new `last_section_any` — the last section code seen anywhere on the
contents, container boundaries included — and reads that instead.

**A candidate measured over the output is not the same as a candidate measured where the
parser stands.** That is the lesson worth keeping from this round.

## Gates

Five assertions added to `toc._demo()`, the module's existing pure-function pin:

- round 24's `79` / `A O mitted` → `79A` — **unchanged by this fix**, verified against
  `main`'s copy of the function side by side;
- the same input *without* the duplicate above it must NOT fire;
- `150` / `ZQR. Application` with `last_any="150ZQP"` and **`last_section=None`** → `150ZQR`
  — the None is the point, and is commented as such;
- a title merely opening with a capitalised word (`Application of the rules`) must not fire;
- an all-caps abbreviation (`NO. of items supplied`) whose previous row is not a suffixed
  sibling must not fire.

Verified against `main`: `('150', 'ZQR. Application')` there, `('150ZQR', 'Application')`
here, with `79A` identical in both.

## Verification

`pytest tools/tests -q` 231 passed, 1 skipped · `run_tests_smoke.py` `toc self-check passed`,
`OK legal_ingest: 12 self-check(s) passed` · `ruff check` (bare) clean · `data/ocr_cache` 0 B
· `discover_corpus.py --check` exit 0, and its CHANGED list is identical to `main`'s apart
from the one document this round re-converted.

## A note on this branch's `register.json`

It reads **10** (acts 6, rules 1, ordinance 3). Only the **rules** column is this round's:
the ordinance figure reflects the two ITO editions re-converted by
`fix/fbr-quote-prefixed-section-start`, which are already present in the **shared** corpus on
this disk. Regenerate after merge rather than reading this file as this round's measurement.
