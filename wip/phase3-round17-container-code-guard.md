# Phase 3 round 17 — the PART heading that had to name a part the chapter really holds

Round 13 widened the CHAPTER separator from `\s+` to `[\s\-]+` and measured the same
widening for PART at **14 real boundaries against 6 losses**. It shipped the first and
held the second, because the 6 are the dangerous kind: both are annexure **FORMS**, and
slicing a form into the next rule leaves conservation at 100.000% and merely misplaces
the text. Nothing in the suite catches that, so the change would have reported itself as
a success.

This round ships the widening behind the guard the plan named as its enabler
([`handover/plan.md` P3-4](../handover/plan.md)), and re-measures it: **14 gained, 0
lost.**

## Why the guard has to be per-chapter

The two populations are not distinguishable by the spelling of the line. `Sales Tax Rules,
2006 (Updated upto 01-01-2025)` prints **both**:

| line | sits in | its chapter holds | verdict |
|---|---|---|---|
| `PART-I` | CHAPTER XI · PART I · rule 70 | `PART I`..`PART V` | real |
| `PART-II` | CHAPTER XI · PART I · rule 87 | ″ | real |
| `PART-III` | CHAPTER XI · PART II · rule 111A | ″ | real |
| `PART-V` | CHAPTER XI · PART III · rule 136 | ″ | real |
| `PART-I` | CHAPTER XVIII · rule 165 | *no parts at all* | form **STR-11** |
| `376[PART-II` | CHAPTER XVIII · rule 165 | ″ | form **STR-11** |

One document. So no exemption and no per-document rule can separate them — and a
**document-wide** set of part codes cannot either, because this document holds `PART I`
and `PART II` under CHAPTER XI and would vouch for the form's two lines. The container
tree, read per chapter, can.

`Customs Rules, 2001 (Updated Up to 30.06.2023)` is the same argument from the other
side: its rule 34 permission form prints `PART – II`..`PART-V` and its tree holds **zero
parts on all 41 chapters**, so every one of them is refused.

## The fix

Three edits in `packages/legal_ingest/builder.py`.

1. **`_STRUCTURAL_RE`** — the PART branch goes to `PART[\s\-]+`, matching the CHAPTER
   branch round 13 fixed. Division stays on `\s+`: it has no measured gain to earn a
   guard.
2. **`is_structural_boundary(text, container_codes=None)`** — a PART line whose separator
   is anything other than a plain space must be named in `container_codes` or it is not a
   boundary. `_GUARDED_PART_RE` is `^PART(?!\s+[IVXLC0-9])`, i.e. it matches every PART
   line that is *not* the long-accepted spaced form, so the guard is **fail-closed**: a
   separator nobody anticipated is guarded rather than admitted.
3. **`_part_codes_in_scope(containers, ordered_sections)`** — per section entry, the part
   codes its own container **and that container's ancestors** hold. `build_sections`
   computes it once and passes it to `_build_one` and to round 13's own starts fix-up
   loop.

Ancestors, not just the entry's own container, because the caption a missing cut swallows
belongs to the part the **next** section opens: the `PART-II` line sits at the end of rule
87, whose own container is `PART I`. Walking up to CHAPTER XI is what sees `PART II`.

`_norm_container_code` folds only the separator after the keyword. The numeral is left
alone — not arabic to roman (Sales Tax Special Procedures Rules 2007 numbers its parts
`PART 1`..`PART 3` on **both** sides) and not by value, because `XIVA` and `XIV-A` are two
different chapters of Sales Tax Rules 2006. A comparison that is too strict can only
refuse a boundary; one that is too loose invents one.

**Three callers deliberately pass nothing** and therefore keep the pre-round-17 answer:

- `discover` (`:575`) is where a body-driven edition's containers come *from*. Vouching a
  line with a container built from that same line is circular.
- `preamble_refs` (`:2089`, `:2109`) covers the region that precedes every container.
- `pipeline` (`:1334`, `:1605`) reads single lines with no container in hand.

`packages/fbr_ingest/builder.py:1395` carries the dormant copy and was **not** touched —
that fork is gated on P4-2.

## The measurement — same commit, fix off vs fix on

Each of the 5 documents was converted twice at `e09d156`, with only `_STRUCTURAL_RE`'s
PART branch reverted between runs. Nothing else differs, so the diff is the change.

| document | candidates | **cut** | kept | why kept |
|---|---|---|---|---|
| Sales Tax Rules 2006 (01-01-2025) | 7 | **4** | 3 | 2 × form STR-11; `PART – IV` en dash |
| Sales Tax Rules 2006 (30-06-2025) | 5 | **4** | 1 | `PART – IV` en dash |
| Customs Rules 2001 (30.06.2023) | 5 | **0** | 5 | rule 34's permission form, 0 parts in tree |
| STSP Rules 2007 (05.03.2015) | 3 | **3** | 0 | — |
| STSP Rules 2007 (30.06.2015) | 3 | **3** | 0 | — |
| | **23** | **14** | **9** | |

**14 gained, 0 lost** — round 13's number, reproduced four rounds later, and the 6 it
warned about are all in the `kept` column.

Every line the cut removed is a `PART-N` code line plus the caption the tree already holds
as that part's heading:

```
CHAPTER VI > 35            - 'PART-1'   - 'ADVERTISEMENTS ON TELEVISION AND RADIO'
CHAPTER VI > PART 1 > 37   - 'PART-2'   - 'CUSTOMS AGENTS AND SHIP-CHANDLERS'
CHAPTER VI > PART 2 > 39   - '34[PART-3'- 'SERVICES PROVIDED BY STEVEDORES'
CHAPTER XI > PART I > 70   - 'PART-I'   - 'RECOVERY'
CHAPTER XI > PART I > 87   - 'PART-II'  - 'ATTACHMENT AND SALE OFMOVABLE PROPERTY'
CHAPTER XI > PART II > 111 - 'PART-III' - 'ATTACHMENT AND SALE OFIMMOVABLE PROPERTY'
CHAPTER XI > PART III >136 - 'PART-V'   - 'MISCELLANEOUS'
```

53 words left leaf text; **10 of them were re-homed rather than dropped** — on the
01-01-2025 edition the two-line caption `ATTACHMENT AND SALE OFMOVABLE` / `PROPERTY` does
not match the tree's one-line heading, so round 13's fix-up loop hands it to rules 88 and
112 instead of discarding it. That is the loop's existing, measured behaviour, and it is
the safe side of the choice.

## Conservation

Measured with `tools/acts/audit_completeness.py --pdf`, off run against on run:

| document | off | on |
|---|---|---|
| STSP Rules 2007 (05.03.2015) | 100.000% | **100.000%** |
| STSP Rules 2007 (30.06.2015) | 100.000% | **100.000%** |
| Sales Tax Rules 2006 (01-01-2025) | 99.998% (1 word) | **99.998% (1 word)** |
| Sales Tax Rules 2006 (30-06-2025) | 100.000% | **100.000%** |
| Customs Rules 2001 (30.06.2023) | 74.087% | **74.087%** — output byte-identical |

Unchanged on every one. The dropped captions net out against the container nodes exactly
as `audit_completeness`'s own `_CONTAINER_KEYWORDS` comment anticipates. Customs Rules
2001's two runs differ only in `metadata.converted_at`.

**And conservation is not the evidence that matters here.** Round 13's warning is that
slicing a form keeps it at 100.000%. The evidence that no form was sliced is the line-level
`kept` column above, not these percentages.

## What was measured and rejected

### Extending the guard to CHAPTER — rejected, and it corrects the plan

`plan.md` P3-4 gives two arguments for this row. The second is that the guard "is what
would have kept round 13 from dropping four chapter captions in Customs Rules 2001
(conservation 74.101% → 74.087%), whose tree holds 41 of ~44 chapters and cannot express
them." **Measured, that is not true.**

The tree holds 41 chapters and the body prints 44: `CHAPTER VIII`, `CHAPTER XIV` and
`CHAPTER XX` have no node. Guarding the CHAPTER branch on the document's chapter codes
moves conservation 74.087% → **74.099%**, which looks like the recovery the plan predicts.
It is not. The 28 tokens it "recovers" are a **duplication**:

```
preamble.plain_text   10 lines -> 16 lines
  + 'CHAPTER I'
  + 'PRELIMINARY'
  + '1. Short title and commencement.-(1) These rules may be called the Customs Rules,2001.'
  + '(1A) Scope.- Unless specifically provided in the rules for Pakistan Customs'
  + 'computerized System, 2005, these rules shall apply.'
  + '(2) They shall come into force at once.'
```

`preamble_refs` passes no container codes, so guarding CHAPTER flips its `CHAPTER I` line
to *not a boundary*, the preamble stops ending there, and it swallows the chapter caption
**and rule 1's opening text — which rule 1 also still holds.** The multiset audit only
checks presence, so it scores the second copy as conserved. This is round 13's preamble
leak, re-created, and reported as a 0.012% success. Not one leaf changed.

The second reason not to do it stands even if the preamble side were fixed: putting three
unexpressible chapters' heading lines back into bodies would raise
`no_structural_heading_in_body` from **0**, trading 32 words on the one document already
carrying four Phase-5 exemption entries for new register hits. **Customs Rules 2001's four
dropped chapter captions are a Phase 5 problem, not a guard problem.**

### Widening the separator class to en/em dashes — rejected, zero gain

`PART – IV` (en dash) appears in both Sales Tax Rules 2006 editions and is the reason the
count is 14 and not 16. Adding the dash to the class would not gain them anyway: **neither
edition's CHAPTER XI holds a `PART IV` node** (01-01-2025 holds I, II, III, V; 30-06-2025
holds I, II, III), so the guard refuses both. Zero gain for a wider character class, so
the class stays narrow. Pinned in `builder._demo`.

### Widening the suite's `_STRUCT_LINE` to match — rejected

`tools/suite/invariants/_common.py` keeps the narrow `PART\s+` spelling deliberately.
Widening it would report the **nine** annexure-FORM part lines above as defects, which
they are not. So the parser and the invariant still agree on a hyphenated PART read with
no container — and what they now agree on is a **blind spot rather than a gap**: if the
guard ever fails to cut a real one, the invariant reports zero. That is stated in
`test_structural_boundary_agrees_with_grammar.py` where the four lines sit, and the vouched
half is pinned document-level instead.

## What moved

**The register did not move: 15 / 5 / 5 = 25, identical before and after.** That is what
the row predicted — 0 hits of its own; it is an *enabler*. `tools/suite/register.json` is
unchanged and needed no regeneration.

Five rules-lane documents were re-converted and are now at `e09d156b31e1-dirty`.

## Locked by

`tools/tests/test_hyphenated_part_needs_a_container.py` — 3 cases, all through
`build_sections`, on six body lines that are byte-identical between the two runs. Only the
container tree differs.

Each half was verified by removal, and each removal fails a *different* case:

| removed | fails |
|---|---|
| the widening (`PART[\s\-]+` → `PART\s+`) | `test_a_vouched_part_line_cuts_the_section` |
| the guard (`return True` unconditionally) | `test_an_unvouched_part_line_does_not_cut_the_section` |
| **the wiring** (`container_codes=frozenset()` into `_build_one`) | `test_a_vouched_part_line_cuts_the_section` |

The third row is why the test goes through `build_sections` rather than calling the
predicate: every unit test of `is_structural_boundary` alone passes happily while
`_part_codes_in_scope` is wired to nothing and the gain is zero.

`builder._demo` adds 16 assertions: the four form lines refused unvouched, refused by a
chapter holding *other* parts, and admitted by the right code; the numeral never folded
(`PART-1` is not vouched by `PART I`, `PART-IV-A` not by `PART IVA`); the spaced form
still True with an **empty** set, which is what sixteen rounds of chapter and part cuts
depend on.

## Found, not fixed

**Twenty hyphenated PART lines sit in Finance Act *schedule* bodies**, in four acts-lane
documents — a different reader, not reached by this round.

| document | lines |
|---|---|
| Finance Act, 2021 | 8 — `PART-I`..`PART-VIII`, Fifth Schedule and its TABLE-III |
| Finance Act 2025 | 7 — `Part-1`, `Part-Il`, `Part-lll`, `Part-IV`..`Part-VIlI`, Fifth Schedule |
| Finance Act, 2019 | 4 — Fifth Schedule, inside its own `PART I` and `PART VI` nodes |
| Finance Act, 2014 | 1 — `Part-11`, Second Schedule |

`schedules.py` has always accepted the hyphen (`_PART_RE`, `:64`), and `_kind()` returns
`"part"` for **18 of the 20** — so for those 18 the pattern is *not* the cause and the
cause is not yet known (candidates: `_is_heading_size`'s 8.5pt gate at `:85`, or the
schedule zoning). Do not assume it is the same defect as this round's.

Two things that *are* explained:

- `Part-1` and `Part-11` fail because `_PART_RE`'s numeral is `[IVXL]+` with **no digit
  branch**, where the `_TABLE_RE` beside it has one.
- `Part-Il`, `Part-lll` and `Part-VIlI` are OCR letter confusion — lowercase `l` for
  capital `I` — and `_kind()` accepts them as roman only because it is `IGNORECASE`. They
  would normalise to the codes `PART IL` / `PART LLL`. Per the standing rule, do **not**
  collapse `l`→`I` to fix them.

## Verified

```
pytest tools/tests -q                    95 passed, 1 skipped   (was 92 + 1; +3 new)
ruff check                               All checks passed      (bare, matches ci.yml)
run_suite.py acts / rules / ordinance    15 / 5 / 5 = 25        (unchanged)
run_tests_smoke.py                       3 errors, one per lane (pre-existing; register non-zero)
tools/suite/register.json                unchanged, total 25
du -sh data/ocr_cache                    0B
```

`git status` clean in both trees; the corpus outputs were confirmed byte-identical to the
`on` run after the CHAPTER experiment was reverted and `__pycache__` cleared.

## What this corrects in the handover

- **`plan.md` P3-4's second bullet is wrong.** The guard would not have kept round 13 from
  dropping Customs Rules 2001's four chapter captions; extending it to CHAPTER re-creates
  the preamble leak and reports the duplication as conservation. That document's captions
  are Phase 5.
- The row's headline "0 hits" is confirmed exactly: the register is unchanged at 25.
- `tools/tests/test_structural_boundary_agrees_with_grammar.py`'s note that the four PART
  forms are "deliberately still out of scope (14 gained : 6 lost)" is now historical; they
  are in scope and refused on evidence.
