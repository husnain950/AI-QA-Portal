# Round 44 — a footnote zone must contain footnotes, not a table set below body size

Finance Act 2019 shipped **95 footnote records. Five bound to anything, and not one read
like a note.** It now ships **0**, and **no body text moves** — every one of the 95 was a
duplicate copy of schedule table text that never left the body.

The defect was found during round 41 and deferred with the note *"it is worth its own row"*.
This is that row.

## What the records were

```
ref=237.1     "Breeding bulls 0102.2910 0% Nil"
ref=237.2     "Hatching (Fertilized) egg for 0407.1100 3% Nil\ngrandparent and parent…"
ref=255.2     "Cocoa powder, not containing added sugar 1805.0000 5 Nil"
ref=206.^cont "S. No. Description PCT Code Customs Conditions\nDuty (%)\n(1) (2)\n(3) (4)\n(5)…"
```

The last one swallowed **the table's own numbering row**.

The document sets its schedules' tariff tables at **8.0pt against an 11.0pt body**, so the
size split `calibrate` finds is textbook — `body_size 11.0, footnote_size 8.0, boundary 9.5,
zone_mode "size"` — and everything under it is *table*. **A clean split can still be wrong
about what it separates, and nothing asked the zone what it held.**

## The discriminator was already in the tree

`pagemodel._is_amendment_note` carries the measurement this turns on, in its own docstring:

> *"97.7% of real footnotes match; a body rate/penalty TABLE cell ("Where any person fails to
> furnish…") never does, so this is the signal that a marker block is footnotes and not a
> table."*

It is consulted **per marker line** and never asked about the document's zone as a whole.
`calibrate` already imports from `pagemodel`, so using it needs no new dependency.

## Two other rules were measured first, and both were destructive

| candidate | result |
|---|---|
| round 41's **position test** applied to the primary fit | demotes **38 documents, 26 staged** — including **every Customs Act edition at 31–44%** |
| a per-page **"footnote starts below body text"** test | separates Finance Act 2019 (0%) from Customs (80–100%) but still demotes **9 staged documents** whose records are **92–100% real notes** |

The position test fails because **Customs prints its notes on whole collector pages** after
each body run, where there is no body text for them to sit below. Round 41's guard is sound
as a *promotion* test — "may this candidate be promoted?" — and destructive as a *demotion*
rule. That distinction is the round's main lesson.

The per-page test fails because a dense apparatus starts high on the page: a note continuing
from the previous page begins at the top, so the test reads a real zone as a false one.

## The rule, and why each half is load-bearing

`zone_mode == "size"` **AND** ≥100 sampled zone lines **AND** <2% of them carrying an edit
verb → the document has no footnote zone.

**The line floor is what makes this safe, and it is not hypothetical.** Customs Rules 2001
prints its apparatus **once at the end, at BODY size** — which is exactly what round 37
taught the parser to read — so its *size* zone holds **24 lines and not one note**, while the
document itself carries **419 records and 656 citations**. Demoting on that evidence would
have undone round 37.

Measured over the **141 acts and rules sources with a text layer** (`fbr_ingest` is a fork
with no `calibrate`, so the ordinance lane cannot be reached):

| | demoted | staged |
|---|---|---|
| **this rule** | **2** | **1** |

and both thresholds sit in a wide gap:

| document | zone lines | edit-verb share | outcome |
|---|---|---|---|
| Customs Rules 2001 | **24** | 0% | kept — under the floor |
| Anti-Money Laundering (2nd Amdt) 2020 | 23 | 0% | kept — under the floor (0 records anyway) |
| The Finance (Supplementary) Act 2022 | 21 | 0% | kept — under the floor (0 records anyway) |
| The Tax Laws (Amendment) Act 2020 | 35 | 0% | kept — under the floor (0 records anyway) |
| Custom Act 1969 (Urdu) | 96 | 0% | kept — under the floor |
| **Finance Act, 2019** | **595** | **0.2%** | **demoted** |
| PSW (Deputation/Secondment) | 335 | 0.0% | demoted — **not staged** |
| Income Tax Rules 2002 (Aug 2008) | 597 | **5.4%** | kept — above the share cut |

`zone_mode "rule"` is out of scope: there the separator rule is the evidence, not the size
split. Finance Act 2022 measures 0/166 in rule mode and is untouched.

## Measured

Four documents converted twice — baseline from a worktree at `348c792`, round 44 from this
tree, both with the main tree's interpreter, run provenance normalised out.

| document | result |
|---|---|
| **Finance Act, 2019** | **changed** |
| Customs Act, 1969 30.06.2019 | byte-identical |
| **Customs Rules, 2001 30.06.2023** | byte-identical — the document the floor protects |
| Sales Tax Rules, 2006 01-01-2025 | byte-identical — round 41's document |

| | before | after |
|---|---|---|
| `zone_mode` | `size` | **`none`** |
| footnote records | **95** | **0** |
| bound `<sup class="cite">` | 5 | 0 |
| `<p>` | 618 | 303 |
| leaves · `<table>` · `<tr>` · **body words** | | **all unchanged** |

**Nothing is lost, because the records were duplication.** Each record carried a `text` and
an `html` copy of text that also remained in the body:

| probe | before | after |
|---|---|---|
| `Breeding bulls` | 4 | **2** |
| `Cocoa powder` | 9 | **2** |
| `Carrageenan Food Gel` | 4 | **2** |
| `Description PCT Code` | 66 | **56** |

Two is the floor: the body's own `plain_text` plus its `html`. All 2,122 words that leave the
file are those duplicate copies, and **3 words are gained** (the metadata stamp).

## No invariant saw this, in either direction

`run_suite.py acts` on the pre-round and post-round JSON is **identical**: `ALL PASS |
invariants 65/65 | exempt 0 (0 hits)`. Ninety-five records made of tariff rows, five of them
bound, and the register reads zero both ways. The evidence for this round is the record diff,
not the register — the same shape `working-rules.md` records for round 36.

**Deliberately not adding an invariant for it.** The only place a size zone is created now
carries the guard, with a unit test that fails on the removal of either half, so a
corpus-level reader would be green by construction and would have nothing to say. Recorded as
a choice rather than an omission.

```
pytest tools/tests     321 passed, 1 skipped   (315 + this round's 6)
run_tests_smoke.py     ordinance 12, acts 80, rules 11 -- Pipeline gate passed
ruff check             All checks passed!
```

| mutation | fails |
|---|---|
| the check removed entirely | `test_a_zone_of_tariff_rows_is_not_a_footnote_zone`, `test_the_floor_is_exactly_where_it_says` |
| the line floor removed | `test_a_thin_zone_is_never_demoted`, `test_lines_above_the_cut_are_not_the_zone` |

## What this leaves

- **The PSW (Deputation/Secondment) Rules** are demoted too and are **not staged**, so the
  change is shipped-but-unmeasured for that document. Stated, not implied.
- **Finance Act 2019 keeps no footnotes at all.** If the edition does print an apparatus
  somewhere this round has not found it: 595 sampled zone lines carry one edit verb between
  them.
