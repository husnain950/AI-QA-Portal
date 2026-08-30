# Phase 3, class 7 — parented by where its code is printed, not by where it is

Review page: <https://claude.ai/code/artifact/8bc72195-6386-4052-b9d5-9dfdd6e42994>

Follows [`wip/phase3-chapter-order.md`](./phase3-chapter-order.md) (PR #51).

Two fixes, and both were found by disbelieving a message. `section_codes_ordered` said a
section was out of order; it was in the wrong chapter. `section_carries_its_body` said a
section had no body; its body was two lines away, behind a space.

## 1. A definition clause is not a section

`section_codes_ordered` reported `3 out of order after 33A` on four Sales Tax editions.
Section 33A binds its **real** body — `2[33A. Proceedings against authority and persons.–`
at page 75, 911 characters — but sits under `CHAPTER I PRELIMINARY`, which otherwise holds
sections 1 and 2 at page 2.

Tracing `discover_structure` on a TOC-less edition:

```
discover: 0 chapters, 126 sections
  parent=None <- ['1', '2', '3', '3B', '4', '5', '6', '7', '7A', '8']
```

**Every section comes back parentless**, so `insert_missing_body_chapters` builds the whole
tree — and it assigns sections to chapters by *which codes are printed in each chapter's
span*:

```python
span = _codes_in_span(idx, next_idx)
for entry in ordered_sections:
    if entry.code in span and (entry.parent is prev or entry.parent is None):
        entry.parent = node
```

The Sales Tax Act defines "supply chain" as clause `[(33A)` **inside section 2**, and
`_candidate_code` reads that as the code `33A`. So `33A` is in CHAPTER I's span. CHAPTER I
is processed first and claims it; CHAPTER VII — where s.33A is actually printed, 55 pages
later — then finds the parent already set and skips it.

**The fix:** an entry that carries an `anchor` knows where it is, so place it by position
and never by code membership. Only body-discovered entries have anchors; TOC entries have
none and keep the behaviour they have always had.

### The lock passed with the fix removed

The first fixture had two chapters, CHAPTER I and CHAPTER VII. It passed either way,
because with only two chapters the second pass reassigns 33A anyway — its parent *is* the
previous chapter, which the `entry.parent is prev` clause allows. The real document has ten
chapters in between, so `prev` is not the chapter that claimed it.

Adding a CHAPTER II reproduces the defect, and the lock now fails when the anchor branch is
stubbed out. A lock that cannot fail is worth less than no lock, because it is believed.

## 2. Two markers, one space — and a measurement against the wrong text

Customs s.202B was a heading-only stub in four editions, its body left inside s.202A. The
body line prints two amendment markers separated by nothing but a space, so
`grammar.MARKER_PREFIX` — which recognises a run separated by `,` or `&` — never closed it.

Round 4 measured the naive widening at **1 fix : 17 false positives** and correctly refused
it: penalty-table rows (`25, 38 1[38A or 40B].`) and statistics rows
(`1,314,273 1,482,319 12.8`) all have the same shape. The narrow form admits the branch
**only** behind a lookahead for `[CODE. Capital`, which over the corpus matches exactly one
line.

### The first attempt matched the rendered output and missed the document

`why_unbuilt.py` reported `202B  254  []  NONE  code never opens a body line` while
`_candidate_code` returned `202B` on the line I had tested. The two disagreed because they
were not the same line:

```
parser's line text   '42 53 [202B. Reward to officers ...'     <- space before the bracket
rendered plain_text  '42 53[202B. Reward to officers ...'      <- the rendering collapses it
```

Every gained/lost measurement in this phase has used `output/*.json` plain_text as its
corpus. That is a good approximation and it is **not** what the parser sees. The lookahead
was anchored hard on `[`, so it matched the JSON and missed the PDF.

The corrected pattern allows whitespace on both sides of the run's tail, still matches only
that one line across 186,971, and the lock pins **both** spellings so neither can regress.

## 3. A stale report hid a broken generator

`wip/tasks.md` still asks to re-examine **"the 29 low-confidence documents in
`tools/discovery/report.md` §5"**. That section now lists **two**.

The filter is `flagged` intersected with `BY_LABEL[family].profile`. Phase 2 (PR #45) made
a family's profile an **override** — only `amending` names one, and `consolidated` is
`None` because the lane's own profile is right for it. So since that PR the predicate has
been truthy for `amending` alone, dropping **27 of the 29 rows**: every low-confidence
consolidated document.

Nobody saw it because `report.md` had not been regenerated since Phase 0. It kept printing
the old 29 while its generator produced 2. Round 6's `--write` surfaced the break, which
means PR #51 shipped a report with 27 rows missing — the data in `signatures.json` was
always complete (67 parseable low-confidence documents); only the view was wrong.

The fix is one word — `.profile` → `.parseable`, the field Phase 2 added for exactly this
question:

```
consolidated   profile=None       parseable=True
amending       profile=<Profile>  parseable=True
```

This is the third time in this phase that an artifact which is not regenerated has failed
to report that its source is broken — after the two stale exemptions in round 3 and the
stale in-code skip in round 2. The pattern is worth stating plainly: **a cached artifact
cannot tell you its generator is wrong.**

## Results

| | before | after |
|---|---|---|
| register | 70 | **64** |
| `section_carries_its_body` (acts) | 19 | **15** |
| `section_codes_ordered` | 6 | **4** |
| `report.md` §5 rows | 2 | **29** |
| documents (acts / rules / ord.) | 80 / 11 / 12 | unchanged |

Both fixes verified on the documents that motivated them:

```
202B   len    46 -> len  1256   '42 53[202B. Reward to officers and officials ...'
33A    CHAPTER I -> CHAPTER VII  (page 75, unchanged)
```

## Gates

| gate | result |
|---|---|
| `ruff check` (bare, as CI runs it) | clean |
| `pytest tools/tests` | 53 passed, 1 skipped |
| package self-checks | 13 pass, incl. the three new cases |
| `signatures.json` | **unchanged** — the §5 fix is a reporting filter, not a measurement |
| `report.md` | +27 rows in §5, nothing else |
| stale exemptions, all three lanes | 0 |
| documents | 80 / 11 / 12, held |
| `data/ocr_cache` | 0 B |
| rollback | `output/_pre_r7/` on both lanes |

## What is left (64)

| invariant | acts | rules | ord. | total |
|---|---|---|---|---|
| `section_carries_its_body` | 15 | 17 | 5 | 37 |
| `no_foreign_section_start_in_body` | 10 | 9 | — | 19 |
| `section_codes_ordered` | 4 | — | — | 4 |
| `no_chapter_caption_in_section_heading` | 3 | — | — | 3 |
| `clause_codes_plausible` | 1 | — | — | 1 |
