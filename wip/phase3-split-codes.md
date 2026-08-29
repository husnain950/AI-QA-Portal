# Phase 3, class 4 — the text layer splits a code, and a note that had gone out of date

Review page: <https://claude.ai/code/artifact/7ec0032b-f215-4fc7-8daf-d6d7b680119f>

Follows [`wip/phase3-omissions-and-compilations.md`](./phase3-omissions-and-compilations.md)
(PR #48). Register **92 → 78**.

| | before | after |
|---|---|---|
| register | 92 | **78** |
| `section_carries_its_body` | 55 | **41** |
| `no_foreign_section_start_in_body` | 20 | **19** |
| documents (acts / rules / ord.) | 80 / 11 / 12 | unchanged |
| conservation, body / footnotes | 100.000% / 100.000% | unchanged |

## 1. `150 ZQR` is section 150ZQR

Sales Tax Rules 2006 has an 18-rule chapter on video-surveillance monitoring, pages
143–152. Not one of its rules bound. The reason is a single space:

```
150 ZQR. Application.—The provisions of this Chapter shall apply to video surv
```

`_candidate_code` requires a section code contiguous, so it returned `None` for the whole
run — every rule became a heading-only leaf, and rule 150ZQP's body swallowed the lot.

## 2. The guard that said "widen only if that changes"

`_DOTSUFFIX_RE` already reads a split suffix. It is bracket-gated, and the bracket is
load-bearing — its comment explains at length that a dot- or space-separated suffix only
prints on an *inserted* section, which always carries its amendment bracket, while the
same shape unbracketed is a tariff or schedule row. It ends:

```
# ponytail: bracket-gated, so an UNBRACKETED dot-separated code is still missed.
# Measured over the corpus's 186,357 distinct body lines, all 146 unbracketed
# instances of the shape are tariff/schedule rows -- widen only if that changes.
```

So the first thing this round did was re-run that measurement, over 186,984 lines. **It has
changed.** Two real families now print the shape with no bracket at all: the `150 ZQ*` run
above, and 32 hyphenated Customs Act sections (`196-A. Statement of case to Supreme
Court…`).

The old note was still right about the danger, though — dropping the bracket gate outright
gains **392** lines, and they are exactly what it describes:

```
1 ITEM NAME 7.5 1 9.23 132.23
10. PDA Delivery System
102 THE GAZETTE OF PAKISTAN, EXTRA.. JUNE 26, 2014[PART |
```

So the gate stays and a **second, unbracketed alternative** is added beside it, narrower in
three ways. Each narrowing was measured against the row it keeps out:

| narrowing | what it excludes |
|---|---|
| the dot after the letter run is **mandatory** | the 392 tariff rows above |
| separator may be hyphen or space, **never a dot** | `2. A. Low Priced Cellular Mobile Phones`, a rate row — and the TOC's own `150. ZQR. Application [150ZQS. Definitions 110` |
| a space separator needs **2–4 letters**, never a lone capital | `20 T. V. Sets Nos.`, `42 G. I. Pipes and MS Pipes` — abbreviations, not suffixes |

Together: **48 lines gained, 0 lost.** 47 are the two families; the 48th is a TOC leader row
that mints the code `325AA`, which no TOC entry carries, so it is indexed and never read.

Each of the three narrowings has a case in `builder._demo()` that fails if it is removed —
verified by removing them one at a time.

## 3. What actually moved, and what did not

**The rules lane fell 47 → 33** — the 14 predicted hits, plus one mirrored
`no_foreign_section_start_in_body`.

**The acts lane did not move at all**, and that is worth stating plainly: 32 of the 48
gained lines were the hyphenated Customs sections, and every one of them was *already
binding by another route*. They were redundant alternatives, not fixes. The measurement
counted lines the regex newly matches, which is not the same as sections newly bound —
a distinction worth carrying into the next round.

**One hit became newly visible**, in both Sales Tax Rules editions:

```
section 150ZQZA: chapter caption in heading 'RESPONSIBILITIES OF THE VENDOR'
```

That is a **false positive**, and now that the rule binds we can see why: the source prints
`150 ZQZA. RESPONSIBILITIES OF THE VENDOR.–(1) Subject to these rules,` — the section's own
title is genuinely in capitals. `_CHAPTER_CAPTION_IN_HEADING` matches any run of three or
more capitalised words and cannot tell that from a leaked chapter caption. Round 5 fixes
the invariant to test what it means: *does the caps run match a caption actually on a
chapter node of this document?* Measured over every current hit, that separates them
cleanly — the three real leaks all match a chapter in their tree, and this one does not.

## 4. A process failure worth recording

The lock was verified by patching each narrowing out and re-importing. That left a **stale
`__pycache__`** holding the mutated module, so the pattern in memory was the lone-capital
version this round explicitly rejects, while the source on disk was correct.

`pytest` caught it — `_candidate_code("20 T. V. Sets Nos.")` returned `20T` instead of
`None`. But the first re-conversion had already run against that stale bytecode, so its
numbers could not be trusted. All `__pycache__` was cleared, the compiled pattern asserted
in a fresh process, and both lanes re-converted.

**The second run produced the identical register, 78.** The bogus `20T` / `42G` codes match
no TOC entry, so they were indexed and never read — exactly the reasoning used to accept
`325AA` above. The re-run cost 18 minutes and converted a piece of reasoning into a fact.

## Gates

| gate | result |
|---|---|
| `ruff check` (bare, as CI runs it) | clean |
| `pytest tools/tests` | 53 passed, 1 skipped |
| package self-checks | 11 pass, incl. the three new cases |
| `discover_corpus.py --check` | no drift |
| `signatures.json` | unchanged |
| conservation, body / footnotes | 100.000% / 100.000% |
| stale exemptions, all three lanes | 0 |
| documents | 80 / 11 / 12, held |
| `data/ocr_cache` | 0 B |
| rollback | `output/_pre_r4/` on both lanes |
