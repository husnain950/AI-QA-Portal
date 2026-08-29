# Phase 3, class 1 — chapter numerals, read the same way everywhere

Review page: <https://claude.ai/code/artifact/3b376f24-04be-4cec-80ec-2d6e5c9fed93>

Follows [`wip/phase2-run.md`](./phase2-run.md) (PR #45). Phase 2 left five items open;
this closes the first, and it turned out to be three defects with one shape — **the body
scan, the tree and the invariant each recognised a chapter numeral differently.**

| | before | after |
|---|---|---|
| acts documents | 78 | **80** |
| spurious empty chapters | 19 | **0** |
| `body_chapters_in_tree` | 21 hits | **0** |
| register | 210 | **193** |
| ordinance (the control) | 5 / 4 | 5 / 4 |
| `data/ocr_cache` | 0 B | 0 B |

## 1. A heading wearing a footnote marker was invisible

The two documents Phase 2 lost were not lost to the profile change, and not to anything
about OCR. The Sales Tax Act, 1990 prints its first chapter like this:

```
4 [Chapter-I
```

— an amendment footnote marker in front of the bracket. `grammar.CHAPTER_RE` tolerates
the bracket (a comment records it being widened for exactly that) but not the marker in
front of it, so **CHAPTER I never registered while `Chapter-II` through `Chapter-X`
did**. Sections 1 and 2 were left with no container, and `run` refused the whole document
rather than drop them:

```
RuntimeError: TOC parse left 2 section(s) without a chapter container (1, 2...)
```

That refusal is correct — legal text must not silently vanish — so the document produced
nothing at all, and Phase 2 quarantined the JSON an older revision had written.

**The fix is one expression, and the function was already importing what it needed.**
`body_chapter_entries` calls `is_structural_boundary` three lines below the match it was
getting wrong, and that helper reads its line through `_STRUCT_DECOR_RE`
(`^(?:[\d*]{1,3}\s*|\[+\s*)+`) precisely because "1[PART VA" is a real heading. The
chapter match now reads the line the same way.

Both editions convert again — 10 chapters, 126 and 124 sections — and the acts lane is
back to **80 documents**.

## 2. `CHAPTER 1` and `CHAPTER I` are the same chapter

The Customs Act 1969 prints its first chapter heading with an **Arabic 1** on page 23,
and roman numerals everywhere else, including its own contents page.
`insert_missing_body_chapters` matched numerals as strings, found nothing for `1`, and
inserted a chapter from scratch:

```
tree chapter codes: ['CHAPTER 1', 'CHAPTER I', 'CHAPTER II', ...]
                      ^^^^^^^^^ 'PRELIMINARY', 0 sections
                                  duplicate of 'CHAPTER I' 'PRELIMINARY', 2 sections
```

**19 editions, 19 spurious empty chapters** — and the reason every Customs edition
reported 23 chapters against a contents page that says 22. They now report 22.

### The regression this nearly shipped

The obvious fix — compare `_roman_value`, which already reads both notations — is
wrong, and the corpus says so. `XIVA` and `XIV-A` share a value but are **two different
chapters** of Sales Tax Rules 2006: the first omitted, the second the monitoring
chapter. `structure_counts`' own comment already records that "the dash is the only
thing telling them apart". A value-only match drops one of them from the tree.

Caught before the re-conversion finished, by reading that comment. The match now bridges
**only** the notation gap, with an `isdigit()` guard that makes same-notation numerals
compare as strings, and the non-collapse has its own locking case. Verified on the
document itself: 43 chapters, both `CHAPTER XIVA` and `CHAPTER XIV-A` present.

## 3. Two normalisers, one comparison, no agreement

`inv_body_chapters_in_tree` asks whether every chapter the body prints exists in the
tree. It normalised the two sides with different functions:

```
_tree_chapter_numeral("CHAPTER VIA")  ->  'VI-A'
_norm_body_numeral("VIA")             ->  'VIA'
```

So any chapter whose code carries an unhyphenated suffix was reported missing while
sitting in the tree, and any Arabic numeral was dropped from the comparison set
entirely. Both helpers were used by nothing else. They are replaced by **one**
`_numeral_key`, applied to both sides — 27 fewer lines, and the bug is not expressible
any more.

Measured on **identical JSON**, that fix alone takes the register from 210 to 189.

## The register, decomposed

The total moved 210 → 193, and the parts do not net out the way that suggests:

| step | measured on | total |
|---|---|---|
| Phase 2 close | old invariant, old JSON | 210 |
| invariant fix | new invariant, **same** JSON | **189** |
| parser fix | new invariant, re-converted | **193** |

**The +4 is not a regression**, and the per-document delta says why:

| document | before | after | |
|---|---|---|---|
| Sales Tax Act, 1990 (30.06.2020) | *absent* | 2 | a document not in the corpus cannot fail an invariant |
| The Sales Tax Act, 1990 (31.12.2019) | *absent* | 2 | same |
| Customs Act, 1969 (30th June 2008) | 5 | **4** | lost a `section_codes_ordered` hit with the phantom chapter |
| Sales Tax Rules 2006 (30-06-2025) | 4 | 5 | `CHAPTER XIV-AC`, newly visible, lands out of page order |

That last one is the honest cost of seeing more: the decoration strip lets the parser
recognise `CHAPTER VIB` and `CHAPTER XIV-AC`, and XIV-AC sits out of order exactly like
the XIV-AB/XIV-AD pair already on the register. One more instance of a defect already
recorded, not a new one.

Customs Rules 2001 went **15 → 41 chapters** in the same way, with no change in its hit
count at all.

| Invariant | acts | rules | ordinance | total | was |
|---|---|---|---|---|---|
| `section_carries_its_body` | 27 (10) | 79 (6) | 5 (4) | 111 | 111 |
| `no_footnote_text_in_body` | 45 (20) | — | — | 45 | 45 |
| `no_foreign_section_start_in_body` | 10 (10) | 10 (4) | — | 20 | 20 |
| `section_codes_ordered` | 7 (6) | — | — | 7 | 6 |
| `structure_counts` | — | 5 (2) | — | 5 | 4 |
| `no_chapter_caption_in_section_heading` | 3 (3) | 1 (1) | — | 4 | 2 |
| `clause_codes_plausible` | 1 (1) | — | — | 1 | 1 |
| `body_chapters_in_tree` | — | — | — | **0** | 21 |
| **per lane** | **93 / 28 docs** | **95 / 6 docs** | **5 / 4 docs** | **193** | 210 |

## Gates

| gate | result |
|---|---|
| package self-checks | 11 pass, including the three new cases |
| `pytest tools/tests` | 53 passed, 1 skipped |
| `discover_corpus.py --check` | no drift |
| acts corpus | **80** documents, up from 78 |
| ordinance | 5 / 4 of 12, unchanged — `fbr_ingest` shares no code with this |
| `data/ocr_cache` | 0 B |
| `ruff check packages/legal_ingest tools apps/api` | clean |
| rollback | `output/_pre_phase3/` on both re-converted lanes |

## What is still open in Phase 3

- `section_carries_its_body` (111) — the largest class, 79 of it on six rules editions.
- `no_footnote_text_in_body` (45, 20 acts editions) — classify into cause classes first.
- `no_foreign_section_start_in_body` (20) — and remember Phase 2 falsified the amending
  hypothesis for every document we can currently measure.
- `structure_counts` (5) — the XIV-AB / XIV-AC / XIV-AD ordering, now with a third
  instance.
- `section_codes_ordered` (7, 6 acts editions) — never triaged.
- `no_chapter_caption_in_section_heading` (4) and `clause_codes_plausible` (1).
