# Phase 3 — a section start whose bracket carries an opening quote (register 13 → 11)

Written 2026-09-14. Branch `fix/fbr-quote-prefixed-section-start`. The first parser round in
the `fbr_ingest` fork since round 20.

Closes **2 of the 5** ordinance hits — both instances of s.214E. The other three (s.233AA
and s.122C ×2) are a **different cause** and are not touched here; see "Why this is not one
round" below, which is also why this had to land *first*.

---

## What was measured

Each edition was converted **twice at the same commit**, fix off and fix on — the only way
to attribute a change on a shared corpus.

| | 11.03.2019 | 30.06.2019 |
|---|---|---|
| leaves before → after | 413 → 413 | 432 → 432 |
| leaves gained / lost | 0 / 0 | 0 / 0 |
| leaves whose `plain_text` changed | **2** | **2** |
| s.214C | 2,547 → **1,195** chars (−1,352) | 2,547 → **1,195** (−1,352) |
| s.214E | 65 → **1,351** chars (+1,286) | 65 → **1,351** (+1,286) |

**Nothing else moved in either document.** The two editions change identically, which is the
cross-check that the cause is the source shape and not a coincidence of one file.

| lane | before | after |
|---|---|---|
| acts | 6 | 6 |
| rules | 2 | 2 |
| ordinance | 5 | **3** |
| **register** | **13** | **11** |

Per-invariant `FAIL` lines were diffed against a `main` baseline across all 103 documents:
acts and rules are **byte-identical**, and the ordinance lane differs by exactly the one
`FAIL (2)` line that is now gone.

## The cause

`_DOTFORM_RE` and `_BRACKETPAREN_RE` (`packages/fbr_ingest/builder.py:1130-1132`) step over
an optional `[` with `\s*` — and `\s*` cannot cross a quotation mark.

```
2019:   '4' 6.48pt x0=67.46   '[“' 9.96pt x0=71.06  cp=[0x5b, 0x201c]   '214E.' Arial-BoldMT
2020:   '4' 6.48pt x0=67.46   '['  9.96pt x0=71.06  cp=[0x5b]           '214E.' Arial-BoldMT
```

The FBR typesetter opened the substitution quote in the 2019 editions; the 30.06.2020
reprint dropped it. The text layer hands `[“` over as a **single token**. So
`_candidate_code` returned `None`, no section break was cut, and the whole of 214E's body
was swallowed by 214C.

Verified in the output, not inferred: 214C's `plain_text` ran to 2,547 characters and ended
with the literal `4[“214E. Closure of audit.─ Notwithstanding…`.

## The dash was a red herring, and the ledger pointed at it

`handover/` and the rounds 21-28 handoff both suggested the **box-drawing dash U+2500 `─`**
was the family here, on the strength of regression case `sec214E_heading_closure_of_audit`.

**It is not the cause of any of the five.** `fbr_ingest` already accepts `─ ― — –`
(`_HEADING_DASH_RE:1151`, `_CODE_DASH_RE:1420`, `_words_after_heading_dash:1423-1458`), and
the working 30.06.2020 control prints the **identical** `audit.─` terminator and parses
correctly. The only difference between a working edition and a broken one is the quote.

This is the fourth time on this board that the ledger's *count* reproduced and its
*mechanism* did not. Re-derive before coding.

Two dead constants were found next door and **left alone**: `DASHES` and `HEAD_SPLIT_RE`
(`builder.py:26-28`) have zero uses in the package. Deleting them is a tidy-up, not this
round's work.

## Why this is not one round with the other three

An exemption keys on `{invariant → reason}` **per document** (`runner._exempt_reasons`), so
it silences *every* hit of that invariant on that file. The 30.06.2019 edition carried
**both** s.214E (this live parser bug) and s.122C (an omitted-section stub). Exempting it
first would have **masked the defect this round fixes**.

So the order is forced: fix 214E, *then* exempt. After this round the 30.06.2019 edition
carries only 122C and the 11.03.2019 edition carries nothing at all.

## The heading is still the amendment citation, and that is correct

214E's `heading` field still reads `Inserted by the Finance Supplementary (Amendment) Act,
2018`. That is **not** a leftover: these two editions' arrangement-of-sections really does
print the amendment note as the title (p.13 and p.14), where the 2020 edition's TOC prints
`Closure of audit`. The rounds 21-28 convention is on the record — *source defects are
preserved, only the code is repaired* — the same call that left s.79A's `O mitted` alone.

The rendered `<h4>` does now carry the operative heading, matching the 2020 control's shape:

```html
<sup class="cite" title="Inserted by the Finance Supplementary (Amendment) Act, 2018.">333.4</sup>[“214E. Closure of audit.─
```

## Gates

Two regression cases in `tools/suite/cases/ordinance.json`, both **verified red** by staging
the pre-fix output back in and re-running:

- `sec214E_quoted_bracket_opens_its_own_section` — 214E's `plain_text` contains its own
  operative text.
- `sec214C_does_not_swallow_214E` — the companion half. A fix that opened 214E without
  releasing 214C would leave the text in **two places at once**, and no leaf count can see
  that; only this case can.

And **the first `_demo()` in `fbr_ingest`**. `run_tests_smoke._self_checks` discovers
`_demo()`s rather than listing them, and its own docstring recorded that "the Ordinance
pipeline has none" — so the fork shipped with **no module-level pinned behaviour at all**,
and its only coverage was a lane suite that SKIPS wherever the corpus is not staged, i.e. on
CI. It pins both admitted shapes and three that must stay refused, including the empty
amendment placeholder `7[1[ ] ]` that s.122C prints instead of a body — reading *that* as a
section start would invent one.

`run_tests_smoke.py` now reports `OK fbr_ingest: 1 self-check(s) passed`, up from 0.

## Re-conversion

Only the two affected editions, per file with an explicit `-o`. The fix was **committed
before** re-converting so `pipeline_revision` records a real SHA (`3683638c897d`) rather
than a `-dirty` stamp — a corpus stamped `-dirty` is not attributable.

**Round 20's drift for these two documents is zero.** Converting them at `main` without the
fix produced **0 changed leaves** against the committed corpus files at revision `4827840`.
So this re-conversion carries nothing but this fix — worth knowing before anyone treats the
ordinance lane's mixed revision as a reason not to touch it.

Verification: `pytest tools/tests -q` 231 passed, 1 skipped · `ruff check` (bare) clean ·
`du -sh data/ocr_cache` 0 B.
