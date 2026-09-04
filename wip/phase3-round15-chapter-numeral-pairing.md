# Phase 3 round 15 — the chapter that was printed twice and the one that borrowed a numeral

`section_codes_ordered`'s three hits were never about a section code. All three were a
**chapter** wearing the wrong numeral, and the invariant could only see the consequence:
sections that walk backwards because their container sorts somewhere else.

## What the source pages say

The rule for this row was *decide per hit, and only from the page*. Three pages read:

| document | hit | printed page | what it prints |
|---|---|---|---|
| Customs 1969 (30.06.2025) | `'9' after '119'` | contents p3 | `CHAPTER III` / `DECLARATION OF PORTS, AIRPORTS, / LAND CUSTOMS-STATIONS, ETC.` then rows `9`, `10`, `11` |
| Sales Tax 1990 (01.07.2014) | `'3' after '32AA'` | body p51 | `Chapter-VI` / `APPOINTMENT OF 1[OFFICERS OF SALES TAX] & THEIR POWERS` then `30.` |
| Sales Tax 1990 (01.07.2014) | `'22' after '75'` | body p81 | `Chapter-IX` / `RECOVERY OF ARREARS` then `48.` |

**Every page is correct.** No printed defect, no exemption. The contents page puts ss.9-11
under CHAPTER III; the parser put them under CHAPTER XI. Body p51 is Chapter-VI; the
parser labelled it CHAPTER I. Body p81 is Chapter-IX; the parser labelled it CHAPTER III.

**So P3-6's framing in `plan.md` -- "the code was misread" -- is disproved.** Not one code
was misread. `plan.md` is corrected in this PR.

## Cause 1 — a chapter row did not close a section row that printed no folio

`packages/legal_ingest/toc.py`, the CHAPTER branch of `parse_toc`.

The Customs contents print one row with **no page number at all**:

```
3F      Hiring of technology specialists, auditors, accountants and
        goods evaluators on short term contract
```

`SECTION_NOPAGE_RE` handles that row and parks it in `pending_page` so the wrapped second
line can be joined onto its title. Nothing closed it. Seventeen rows later the contents
reach `CHAPTER III`; the CHAPTER branch resets `pending_heading_for` and `last_section` —
but **not `pending_page`**. So when `DECLARATION OF PORTS, AIRPORTS,` arrives it is offered
to *section 3F* first, `is_foreign_caption` correctly says an ALL-CAPS line is not part of
a section title, and `_open_caption_chapter` opens it as a chapter of its own.

`CHAPTER III` therefore came out **twice**: a coded shell carrying no heading and no
sections, beside a numeral-less node carrying III's caption and ss.9-14A.

`_open_caption_chapter` resets all three of these variables. This branch reset two of
them. The fix is the third:

```python
last_section = None
pending_page = None      # <- added
continue
```

Bisected to the exact triggering line: parsing the contents from line 145 (`3F`) onward
reproduces the split; from line 146 onward it does not.

## Cause 2 — a numeral-less chapter borrowed the numeral that was left over

`packages/legal_ingest/pipeline.py`, `insert_missing_body_chapters`.

A TOC that omits a `CHAPTER N` row leaves a numeral-less caption node, and the numeral is
filled in from the body. Two passes did that: a caption match, then — for whatever was
still empty — this.

```python
unused  = [num for _i, num, _c in entries if not _taken(num)]
empties = [ch for ch in chapters if not ch.code]
for ch, num in zip(empties, unused):
    _fill(ch, num)
```

**Pairing by list position is only right if the two lists correspond one-to-one, and they
need not.** Both hits are that:

* **Customs 30.06.2025** — cause 1's shell holds the numeral III, so III reads as already
  taken. The contents also omit IV, IX and XI; the caption match claims IV and IX, and the
  one numeral left over is **XI**. `zip` handed it to the DECLARATION node, so ss.9-14A
  were parented to `WAREHOUSING` — 70 pages from where they are printed — and the real
  CHAPTER III shipped empty.
* **Sales Tax 01.07.2014** — the contents classify **no** numeral at all, so all five
  chapter nodes arrive numeral-less. The body caption prints
  `APPOINTMENT OF 1 [OFFICERS OF SALES TAX] & THEIR POWERS` where the contents say
  `APPOINTMENT OF OFFICER OF SALES TAX & THEIR POWERS`: comparing the first six words
  pairwise gives **2 equal against `_captions_match`'s floor of 3**, so that node — which
  is CHAPTER VI — falls through. `zip` gave it the first numeral going spare, **I**, and
  s.30 landed in `PRELIMINARY`. The node holding ss.48-75 took **III** the same way, which
  is the `'22' after '75'` hit.

The replacement pairs a node with the numeral whose **body span actually prints that
node's own sections**, using `_codes_in_span` — which the function already defines and
which the loop below it already trusts for exactly this decision. The spans are disjoint,
so building all of them costs the one pass over `body_refs` that loop already spent.

A node with no sections of its own now keeps no numeral rather than borrowing one.

## Measured

**Register 32 → 29.** `section_codes_ordered` **3 → 0: the class is closed**, the sixth to
close. No other invariant moved in any lane.

| lane | before | after |
|---|---|---|
| acts | 18 | **15** |
| rules | 9 | 9 |
| ordinance | 5 | 5 |

| invariant | before | after |
|---|---|---|
| `section_codes_ordered` | 3 | **0 — closed** |
| `section_carries_its_body` | 21 | 21 |
| `no_chapter_caption_in_section_heading` | 4 | 4 |
| `preamble_carries_no_toc_tail` | 2 | 2 |
| `no_foreign_section_start_in_body` | 1 | 1 |
| `clause_codes_plausible` | 1 | 1 |

### What could be reached at all

Both fixes live in `packages/legal_ingest`. The **ordinance lane runs
`packages/fbr_ingest`**, which carries its own `toc.py` and its own
`insert_missing_body_chapters`, so it is not reachable by either fix — its 5 hits were
never candidates. The fork's copies are **not** touched here; that is
[P4-2](../handover/plan.md#p4-2--decide-the-fbr_ingest-fork--a-routing-problem)'s call.

For acts and rules, each document's contents were parsed **twice at the same commit**,
once with cause 1's fix and once without, and the chapter list and section parenting
compared. Same `toc_lines`, same code, so there is no mixed-revision confound — it is
old-decision against new-decision on identical input.

| | documents |
|---|---|
| `parse_toc` output changes (cause 1) | **8** |
| unchanged, but yields a code-less chapter (cause 2's only reach) | **7** |
| provably untouchable by either fix | **76** |

Those **15** were re-converted, per file with an explicit `-o`. **0 failures, 0 refusals.**
The other 76 keep their revisions, as every round has done.

### Structure, before → after

Only 5 of the 15 changed structurally. **The other 10 moved by zero** and are reported
here rather than folded into a total.

| document | chapters | leaves | code-less | empty | backward jumps |
|---|---|---|---|---|---|
| Customs 1969 30.06.2025 | 22 | **325 (same)** | 0 | **1 → 0** | **1 → 0** |
| Sales Tax 1990 01.07.2014 | **11 → 10** | **116 (same)** | **1 → 0** | **3 → 0** | **2 → 0** |
| Sales Tax 1990 30.06.2021 | 14 → 10 ¹ | 127 | 0 | 0 | 0 |
| Sales Tax Rules 2006 30-06-2025 | 37 → 38 | 327 (same) | 3 → 4 | 4 → 5 | **2 → 1** |
| Federal Excise Rules ×2 | 17 / 18 | same | same | same | 1 (unmoved) |
| the other 10 | — | — | — | — | **all zero movement** |

¹ measured by the TOC sweep; four duplicate shells collapsed. Its output was already
free of backward jumps, so the register never saw it.

**Leaf counts are unchanged on both target documents** — 325 and 116. The sections moved
container; none was gained or lost. That is the check round 13 failed (127 → 126), and it
is why it is here.

Sales Tax Rules 2006 (30-06-2025) is the one document that gained a code-less chapter
(3 → 4) while its backward jumps fell 2 → 1. That is cause 2's rule working as intended:
a node with no sections of its own now keeps **no** numeral rather than borrowing one, and
the numeral it used to borrow goes to a node created for it. Net: one fewer misordering,
one more honestly-unnamed container. Its remaining jump is not this class.

## What was rejected

**An exemption.** This row was ranked as possibly needing one — `'3' after '32AA'` is
equally the shape of a cursor cascade and of a genuine printing error, and only the page
distinguishes them. All three pages are correct, so an exemption would have recorded a
defect as a property of the source. None was written.

**Widening `_captions_match`.** Sales Tax's caption pair misses its 3-word floor by one
word (`OFFICER` against `1 [OFFICERS`). Lowering the floor to 2, or normalising the
amendment bracket out of the body caption, would have fixed that one hit — and would have
made a 2-word coincidence enough to bind a chapter anywhere in 103 documents. The floor
is untouched; the fallback beneath it was the defect.

**Reparenting by page order.** Tempting, because the symptom is a page-order break. But
tree-walk and page-sort order legitimately disagree on 21 of 103 documents, which is
already recorded as P5's reading-order limb. Page order is not the authority here; the
body span is.

**Porting either fix to `packages/fbr_ingest`.** Measured as unreachable — the ordinance
lane's 5 hits are a different package and a different decision (P4-2).

## Locked by

| lock | fails if you revert |
|---|---|
| `toc._demo` — the folio-less `3F` row followed by `CHAPTER III` and its caption | cause 1: `CHAPTER III` comes back as `['CHAPTER III', '']` |
| `pipeline._demo` — caption-only contents whose body caption misses the word floor | cause 2: s.30 is parented to `CHAPTER I` |
| `tools/suite/register.json` | the register, at 29 |

**Each verified by removing its own fix, one at a time.** With cause 1 stubbed out,
`toc._demo` goes red and `pipeline._demo` stays green; with cause 2 reverted to the old
`zip`, the reverse. Neither test stands in for the other, and neither is redundant.

## Conservation

**Identical before and after on all 15 documents** — body and footnotes, same PDF, same
auditor, two JSONs. `changed=0`.

Twelve are at 100.000% / 0 missing on both sides. The three that are not carry
**pre-existing, byte-identical** deficits, present before this round and unchanged by it:

| document | body | footnotes |
|---|---|---|
| Customs Rules 2001 30.06.2023 | 74.087% / 62,551 missing — **the figure round 13 left** | 100.000% |
| Sales Tax Rules 2006 30-06-2025 | 100.000% | 99.963% / 4 |
| Sales Tax Rules 2006 01-01-2025 | 99.998% / 1 | 100.000% |
| Customs 1969 30.06.2022 | 99.998% / 1 | 100.000% |

Customs Rules 2001 is the document round 13 dropped four chapter captions in
(74.101% → 74.087%). **This round did not move it either way** — it is
[P3-4](../handover/plan.md#p3-4--the-container-code-guard)'s to repair, and it is reported
here precisely so that it is not credited to this round.

## Verified

`pytest tools/tests` **86 passed, 1 skipped** (the intentional skip) ·
register regenerated to **29** in this PR ·
`ruff check` **bare** clean ·
`discover_corpus.py --check` **no drift** ·
`data/ocr_cache` **0 B** ·
`output/_refused/` **no new entries** ·
15 documents re-converted, **0 failures** ·
conservation **identical on all 15**.

## What this corrects in the handover

- `plan.md` **P3-6 said "the code was misread"**. No code was misread; three chapters were
  mislabelled. Corrected in this PR.
- `tasks.md` task 1 predicted the fix would be per-hit — *"decide per hit"*, with
  `acts.json` exemptions likely, and noted `tools/suite/exemptions/acts.json` does not
  exist yet. **It still does not exist, and did not need to.** One shared cause, two
  fixes, three hits.
- `wip/tasks.md:664` states this class as **4** hits; the register said **3**. The register
  was right, and it is now **0**.
