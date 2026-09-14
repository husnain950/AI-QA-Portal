# Rounds 29-34 merged, and the corpus re-converted under the merged tree

**PRs #93-#99, merged 2026-09-14. Register 13 → 0.** This artifact is the merge itself and
the measurement that follows it; the seven rounds have their own artifacts, linked below.

## What was merged, and why in this order

| order | PR | what it changes | register after |
|---|---|---|---|
| 1 | #93 | `ReviewToolbar.jsx` — approve gates on CRITICAL flags only | 13 |
| 2 | #95 | `invariants/_common.py` — `_table_cell_lines` sees a flattened ROW | 12 |
| 3 | #96 | `fbr_ingest/builder.py` — section start behind a glued opening quote | 10 |
| 4 | #98 | `legal_ingest/toc.py` — multi-letter split suffix that kept its dot | 9 |
| 5 | #97 | `exemptions/ordinance.json` (new) — omitted-section stubs | 6 |
| 6 | #94 | `exemptions/acts.json` (new) — Customs 2008, PFMA, PSW | 1 |
| 7 | #99 | `exemptions/acts.json` +1 — Sales Tax 2014 s.10 | 0 |

Two constraints fixed that order, and only one of them was recorded anywhere:

- **Code before exemptions.** An exemption silences a *whole invariant for a whole document*
  (`runner.py:63-75`): the count does not shrink, the invariant disappears from the
  measurement. Exempting first would have hidden a live defect. #96 before #97 is the sharp
  case — the 30.06.2019 ITO edition carries both s.214E (a real parser bug) and s.122C (an
  omitted stub), so #97's exemption on that document would have silenced 214E too and the
  parser fix would have measured as a no-op.
- **Merge commits, not squashes.** #97 contains #96's commits and #99 contains #94's. A
  squashed parent leaves the child re-applying the same content under a new hash.

## The conflicts were all one file and one sentence

Every PR after the first conflicted, and always in the same two places: `register.json`'s
`"total"` line, and the register count written into `handover/README.md`, `tasks.md`,
`open-work.md`. **No two PRs touched the same source file** — the seven code changes are
disjoint, so nothing about the merge required a judgement about code.

Resolved arithmetically at each step (the table above is that arithmetic), with the real
measurement deferred to one live run at the end. Measuring mid-stack would have been wrong
in a specific way worth recording: **the corpus is shared across branches**, one copy on
disk, so by the time #95 merged the output for #96's and #98's documents had already been
re-converted with their fixes. An early branch measures better than it deserves.

## The re-convert: 103 documents, not 187

`convert_all.py <lane>` targets **every PDF in the lane** — 46 ordinance, 93 acts, 48 rules,
187 in all — and only **103** have output. Running it bare would have added 84 documents to
the corpus, and the register would then have been measuring a different document set: the
13 → 0 claim becomes unmeasurable, not merely uncertain. So the run was driven per file over
the staged set, reusing `convert_all`'s own discovery and its exact `scan_page_count` census.

**Three ordinance outputs carry a legacy filename.** `Income Tax Ordinance 2001 - amended
upto 30.06.2024.json` is what is on disk; `out_path` would now write `Income Tax Ordinance,
2001 Amended upto 30.06.2024.json`. Converting them under the new name would have left the
old file in place and the ordinance lane would hold **15** documents, three of them
duplicates of the other three. They were re-converted with `-o` onto the name already there.
The same trap sits under any future full re-convert of that lane.

## The 14 stale acts documents are all image-backed — not 8 of them

`handover/README.md` splits the 14 acts documents that rounds 21-28 skipped into **8
OCR-backed** (out of scope) and **6 with no `source_kind` recorded**, which reads as six
documents that are merely unlabelled and could be re-converted. They cannot.
`convert_all.scan_page_count` is an exact per-page census, not a sample, and it reports
image-backed pages on **all 14**:

```
Benami Transactions (Prohibition) Act 2017      Finance Act 2011-12
Finance Act 2013                                Finance Act 2014
Finance Act 2022                                Finance Act 2023
Finance Act 2025                                Finance Supplementary Act 2023
The Finance (Supplementary) Act 2022            Income Tax (Third Amendment) Act 2016
Public Finance Management Act 2019              The Pakistan Single Window Act 2021
The Tax Laws (Amendment) Act 2020               The Tax Laws (Amendment) Act 2023
```

A file with even one image-backed page cannot convert without the OCR extras, so under the
standing no-OCR decision all 14 stay at their old revision permanently — not eight of them.

**This settles board row 6** (`delete _legacy_section_key`), which is blocked on those
documents staying stale. It is not blocked pending a census; it is blocked for as long as the
OCR decision stands. Writing the query that row asks for will confirm the block, not lift it.

## Nine of the thirteen were closed by exemption, not by the parser

| closed by | hits | where |
|---|---|---|
| exemption with evidence | **9** | ordinance stubs 3 (#97), acts 5 (#94), Sales Tax 2014 s.10 1 (#99) |
| code | **4** | ITO s.214E ×2 (#96, parser), rules 150 (#98, parser), rules 13 (#95, invariant) |

Those nine are still printed, under the runner's `EXEMPT INVARIANTS` banner. **"Register 0"
means nothing un-excused is failing. It does not mean the corpus is clean**, and a fourth hit
appearing on an exempted document would be silent.

## Two rejections, kept because they cost more than the fixes

- **Widening `_BRACKETPAREN_RE` for Sales Tax 2014 s.10** would mint **83 phantom sections**
  inside s.2's definition clauses. The bare parenthesised code is refused for a measured
  reason — it once blocked thirty sections into stubs. Exempted instead (#99).
- **A `toc.py` candidate for the `150ZQR` split measured clean over leaf ordering** and did
  nothing, because `last_section` is None after a `SUB-CHAPTER` caption resets it. The
  shipped fix reads `last_section_any`, which container boundaries do not reset (#98).

## Three stale pointers in `handover/`, found and fixed

- `_legacy_section_key` has **two** call sites, not one: `document_store.py:224` builds the
  index for every row on every sync, `:257` is the lookup. The ledger named only `:257`.
- `test_the_letter_suffixed_chapter_gap_is_still_open` and
  `test_the_en_dash_chapter_gap_is_still_open` **do not exist** — round 18 spent the first
  and the second was never written — yet three files still forbade repairing them
  (`tasks.md`, `working-rules.md`, `plan.md`). The rule they carried is kept; the names are
  replaced with the pins that exist.
- The marker row's blocker in `open-work.md` ("the definitions are on other pages: find them
  first") is **spent**: the notes print `66A.` uppercase at 9pt, so no case-fold is needed.
