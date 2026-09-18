# Round 41 — a second prose size too close to the body is a second body, not a footnote

**Row 13**, the top of the board and 27% of the unmeasured population. Sales Tax Rules 2006
(01-01-2025) rendered **761 unresolved markers and 0 footnote records**. It now renders
**367 records, 321 bound citations and 57 unresolved markers**, and it is the **only
document in the corpus that changes**.

## The defect

`calibrate` takes the top two word sizes over a 36-page sample as body and footnote prose.
This document sets its rules at **12.0pt** and prints **two whole pages — p31 and p152, 991
words between them — at 11.0pt**. So over the sample 11.0 is the second commonest size:

```
12.0 × 7,649    11.0 × 1,168    9.0 × 846    10.0 × 680    8.0 × 502    7.0 × 237
```

The fit returned the pair **12.0 / 11.0**, a gap of 1.0 under `SIZE_GAP_MIN`, and
`calibrate` concluded *the document has no footnote zone*: `zone_mode "none"`,
`footnote_text_max 0.0`, `footnote_marker_max_size 0.0`. Every marker on every page then
had nowhere to resolve to.

**No invariant could see this.** All nine footnote invariants were green on this document
for the life of the corpus, because it recorded nothing for them to look at — the trap
`working-rules.md` states as *"an invariant with nothing to measure is not passing, it is
unmeasured"*.

### The ledger's diagnosis was half right

`tasks.md` row 13 said **11.04pt is the page FOLIO**. A folio is one word per page. This is
**1,168 words, 525 of them on p31 alone**. It is not the folio — it is *another regime's
body*. The row was right that the document has two size regimes and right that the returned
pair is not a body/footnote pair; it was wrong about which text does the damage, and that
matters, because "fix the sampling" was measured and is the wrong fix (below).

## The fix

The gap test was **already the right discriminator — it was consulted in the wrong place.**
Reaching it meant giving the *document* up, when the evidence says only that this
*candidate* is not a footnote size. So skip that candidate and take the next one that clears
the gap, if two guards agree it is one:

| guard | what it rejects | the document that proves it |
|---|---|---|
| **mass** — ≥1% of sampled words | decoration promoted to prose | Finance Act 2022: below its 10.0pt runner-up sit **5.5pt (12 words)** and 6.1pt (11). Promoting either cuts its zone boundary 10.5 → 8.25 for nothing |
| **position** — ≥50% of its words in the bottom 40% of the page | body text that merely happens to be small | Finance Act 2024: **573 words at 8.0pt, 5.5% of the sample** — past the mass floor — but only **31%** sit low, because they are **schedule tariff rows** |

**Neither guard is redundant, and the position guard was not a hunch — it was measured as a
regression first.** An earlier version of this round shipped the mass floor alone, converted
Finance Act 2024 and found **10 false footnote records** reading
`S. No. Taxable Income Rate of Tax` and `(vi). Feeder 8479.8990`, with **51 table rows
shredded**. That is the Finance Act 2019 failure mode, which this corpus already carries: it
has a footnote zone today and **95 of its "footnote records" are tariff table rows**
(`Breeding bulls 0102.2910 0% Nil`), none of them bound to anything.

Across the corpus **eight candidates are rejected by the mass floor alone and four by the
position test alone**.

### Separation, measured

Share of the candidate size's words falling in the bottom 40% of the page:

| document | candidate | share low | verdict |
|---|---|---|---|
| Federal Excise 30-06-2025 | 8.0pt | **96%** | real zone (has one today) |
| **Sales Tax Rules 01-01-2025** | **9.0pt** | **63%** | **promoted — this round** |
| Finance Supplementary (2nd Amdt) | 7.5pt | 27% | rejected |
| Finance Act 2020 | 7.0pt | 37% | rejected |
| Finance Act 2024 | 8.0pt | 31% | rejected (was the regression) |
| Inland Revenue Uniform Rules 2021 | 10.0pt | 0% | rejected |

## Four other rules were measured first, and all four were worse

The ledger said *"fix the sampling, not the thresholds."* Sampling was tried first:

| rule | documents moved | zones gained | zones **lost** |
|---|---|---|---|
| **A** — histogram restricted to pages whose dominant size is `body_size` | 32 | 14 | **2, one staged** — Finance Act 2019 |
| **E1** — page must carry ≥4 body-size words | 20 | 12 | 0 — **but does not fix the target** |
| **F / G** — score candidates by page co-occurrence with the body | 57 / 52 | 10 / 10 | 3 / 3 |
| **this round** | **1** | **1** | **0** |

Rule A fails for an instructive reason: it excludes pages whose dominant size is the
*footnote* size, and the Customs Act prints its notes on **whole collector pages** (p59 is
746 words, all 9.0pt). Excluding them drops 9.0's support from 4,367 words to 34 and hands
the second slot to **8.0pt, which is Customs' MARKER size, not its footnote prose**. F and G
put *every* Customs edition on 8.0pt for the same reason.

## Measured

Five documents converted twice — once from a worktree at `cb11b49` (`main`), once from this
tree, both with the main tree's interpreter. Run provenance (`converted_at`,
`pipeline_revision`) normalised out of the comparison, since it differs by construction.

| document | result |
|---|---|
| **Sales Tax Rules, 2006 (01-01-2025)** | **changed** — below |
| Finance Act 2024 | **byte-identical** (the regression the position guard removed) |
| Customs Act, 1969 30.06.2019 | byte-identical |
| Federal Excise Act, 2005 30-06-2025 | byte-identical |
| Customs Rules, 2001 30.06.2023 | byte-identical |

**The other 136 acts and rules sources need no conversion to be accounted for.** The change
is confined to `_prose_sizes`; every value `calibrate` derives downstream follows from
`(body_size, footnote_size)`. Both were measured on all 141 sources with a text layer before
and after: **140 identical, 1 changed.** Identical calibration on identical input is
identical output, and the four controls confirm it empirically.

### The document

| | before | after |
|---|---|---|
| `footnote_size` / `zone_mode` | 11.0 / `none` | **9.0 / `size`** |
| footnote records | **0** | **367** |
| `<sup class="marker">` (unresolved) | **761** | **57** |
| `<sup class="cite">` (bound) | **0** | **321** |
| leaves | 347 | 347 |
| body `plain_text` words | 71,374 | 59,288 |
| footnote text words | 0 | 12,529 |
| **combined words** | **71,374** | **71,817** (+443) |

**321 of 378 markers resolve (85%).** The 565 word-instances present before and absent after
are reversed-glyph fragments (`oC`, `ecn`, `sn`, `/d`) — rotated form-field labels that used
to land in the body as garbage.

### The table numbers are a fix, not a loss

`<table>` 64 → 39 and `<tr>` 569 → 311 looks alarming. Three leaves account for all of it
and each was read:

| leaf | tables | rows | what happened |
|---|---|---|---|
| 13 | 3 → **1** | 69 → **69** | **three page-split fragments merged into one 69-row table.** The footnote block that used to interrupt it is now notes |
| 17 | 2 → **1** | 10 → **10** | same, merged |
| 165 | 57 → 35 | 480 → 222 | the annexed STR forms — the lost tables are rotated-glyph noise (`/r e d lo h er re an h tr S` is "S t r a n g e r h o l d e r /" reversed) |

Content is conserved and checked by probe: `Tea blended`, `Industrial Gases`,
`CNG dealers`, `Natural Gas` each appear the same number of times before and after, and each
is still **inside a `<table>`** in leaf 13 / leaf 17.

### The cost, stated

**Three of the 367 records are wrong.** All three are `^cont` continuations on leaf 165, the
annexed forms, carrying form content rather than a note — e.g.
`Government of Pakistan\nFederal Board of Revenue STR-3\nTaxpayer De-Registration Form`.
They are a consequence of a *size*-based zone on a document whose annexed forms are set near
the footnote size; a positional zone mode would fix them and does not exist. **359 of 367
(98%) are textbook amendment notes** (`Substituted for the words and figures "and section
40" by Notification No. S.R.O. 494(I)/2015`). Misplacement, not loss — and `no_footnote_text_in_body` is
the invariant that would make it loud.

## The rider did not fire

`tasks.md` row 13 warned: giving this document a zone opens round 35's `Word.upper_ok` gate
(`pagemodel.py:113`), and the **56 section cross-references** it measured being lifted into
`<sup>` (`72A` ×30) come back.

**Measured: they do not.** Section-code-shaped uppercase tokens inside a `<sup>`: **0 before,
0 after.** `upper_ok` is `footnote_marker_max > 0.0 AND size < footnote_size`. The zone test
now passes — but `footnote_size` is **9.0**, and those codes print at 9.0pt, which is not
*strictly smaller*. The gate's own docstring predicted exactly this: *"that rules document
calibrates `footnote_size` to 11.0, not 9.0, so the size test alone admits its 9.0pt
codes."* **Correcting `footnote_size` closes the rider by itself** — the zone condition was
carrying a document the size condition can now hold on its own.

## Gates

`run_suite.py rules` on the pre-round and post-round JSON: **identical**, `ALL PASS |
invariants 63/63 | cases 2/2 | exempt 2 (6 hits)`. The difference is not in the result, it is
in what was measured: the nine footnote invariants ran against **0** records before and
**367** after.

```
run_tests_smoke.py     ordinance 12, acts 80, rules 11 -- all pass
pytest tools/tests     315 passed, 1 skipped   (310 + this round's 5)
ruff check             All checks passed!
discover_corpus --check  exit 1, the SAME 27 documents as main -- this is row q3
                         (round 40, PR #107); this branch adds no drift
```

Each guard has a test that fails when **that guard alone** is removed:

| mutation | fails |
|---|---|
| retry removed entirely | `test_a_second_body_is_skipped_for_the_real_footnote_size`, `test_the_floor_scales_with_the_sample` |
| position guard removed | `test_a_candidate_that_is_not_at_the_foot_of_the_page_is_not_promoted` |
| mass floor removed | `test_a_candidate_below_the_mass_floor_is_not_promoted` |

## What this leaves

- **57 unresolved markers** on this document, down from 761. Not traced — a later row.
- **3 false records on leaf 165**, above. They need a positional zone mode, not a threshold.
- **Finance Act 2019 still carries 95 false footnote records** made of tariff table rows. It
  has a zone *today*, so this round cannot reach it — the retry only ever fires where there
  is no zone. It is the same defect class the position guard now prevents, already shipped,
  and it is worth its own row.
- **The ordinance lane is untouched**: `packages/fbr_ingest` is a fork with no `calibrate`.
