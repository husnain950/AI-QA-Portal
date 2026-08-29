# Phase 3, class 6 — a part is not a chapter, and a suffix is not a sum

Review page: <https://claude.ai/code/artifact/2c45bd6b-3cf5-4be3-8edd-d8e7bdb2267b>

Follows [`wip/phase3-toc-furniture.md`](./phase3-toc-furniture.md) (PR #50). Register
**75 → 70**, and `structure_counts` closes at **0**.

| | before | after |
|---|---|---|
| register | 75 | **70** |
| `structure_counts` | 5 | **0** |
| Sales Tax Rules chapters | 43 | **41** |
| its anonymous containers | 3 | **1** (the legitimate one) |
| its part nodes | 0 | **4** |
| sections | 339 | 339 |

Two fixes. The first was necessary and moved the register by **zero**, which is stated here
rather than folded into the total.

## 1. A PART row with its caption on the same line

Round 5 closed one path into `_open_caption_chapter`. The rules lane still had anonymous
containers, and they were **PART headings**:

```
PART-I   RECOVERY ............................................. 71
PART-II  ATTACHMENT AND SALE OF MOVABLE PROPERTY .............. 73
PART-III ATTACHMENT AND SALE OF IMMOVABLE PROPERTY ............ 78
```

`PART_RE` required the numeral to end the line, so a part row carrying its caption fell
through to the heading-continuation branch — where ALL-CAPS text satisfies
`is_foreign_caption`. Each opened a chapter, lifting **64 rules** out of CHAPTER XI into two
top-level containers.

Two narrowings, both measured over 212,547 distinct corpus lines:

| narrowing | what it excludes | cost of omitting it |
|---|---|---|
| the caption group is `(?-i:…)` | the pattern is `IGNORECASE` for the keyword's sake, so an unscoped `[A-Z]` class matches lowercase | `Part 1 of Second China Overseas Ports` and 47 sibling schedule rows |
| a caption is accepted only when **leaders or a page number** follow | a running page header is not a contents row | Income Tax Rules 2002 prints `PART-I   SECOND SCHEDULE` atop 457 pages — `part_lines` 43 → **595** |

Final: **13 lines gained, 0 lost**, every gain a real contents row.

Sales Tax Rules 2006 now parses **41 chapters instead of 43**, with the two spurious
containers replaced by **4 real part nodes**, and all 339 sections preserved.

**And the register did not move.** The rules were in the right chapter, but their chapter
was still in the wrong place — which is the second fix.

## 2. A suffix is alphabetical, not additive

The conversion log said the TOC parsed **40 chapters with 1 inserted from the body**, so the
reordering was happening *after* parsing. `insert_missing_body_chapters` ends by sorting
every chapter by `_roman_value`, which folds a suffix into two decimal places by **summing
its letter values**:

| | value | | | value |
|---|---|---|---|---|
| `XIV-AA` | 14.02 | = | `XIV-B` | 14.02 |
| `XIV-AB` | 14.03 | = | `XIV-BA`, `XIV-C` | 14.03 |
| `XIV-AC` | 14.04 | = | `XIV-BB`, `XIV-D` | 14.04 |

Sorting on that interleaved two families — `XIV-B, XIV-AB, XIV-BA, XIV-C, XIV-AC, XIV-BB,
XIV-D, XIV-AD` — against a contents page that lists `XIV-AB ..105`, `XIV-AC ..105`,
`XIV-AD ..107` **before** `XIV-B ..111`. Chapters printed on pages 123–125 came out after
ones on 129–158, which is exactly what `structure_counts` reports.

A suffix is a sequence, not a sum. Ordering on `(base numeral, suffix letters)` reproduces
the source order exactly:

```
XIV, XIVA, XIV-A, XIV-AA, XIV-AB, XIV-AC, XIV-AD, XIV-B, XIV-BA, XIV-BB, XIV-C, XIV-D
```

`_roman_value` itself is **unchanged**. It is correct for the nearest-previous-chapter
search it was written for, and round 1's Arabic/roman `_taken` guard depends on its current
behaviour. Only the sort key is new.

### The tiebreak that had to come out

The first version added `ch.code` as a final tiebreak and got `XIVA` and `XIV-A` backwards.
They share a key, and a string compare orders them by punctuation — `-` sorts before `A` —
rather than by the contents page, which lists `XIVA` first. Round 1 established those are
**two different chapters** of this document.

`list.sort` is stable, so with no tiebreak equal keys keep the TOC's own order, which is the
authority here. Both facts are locked: the twelve-chapter sequence, and the `XIVA` /
`XIV-A` pair that fails if the tiebreak returns.

## 3. `signatures.json` moved, deliberately

The `PART_RE` change makes `signature.py` count part rows it previously missed, so
`discover_corpus.py --check` reported drift. Regenerated with `--write` and reviewed:

- **11 documents changed**, all `part_lines`, plus `container_order` `CP → PC` on the eight
  Sales Tax Rules editions.
- **0 family changes.** Every document keeps its family and confidence, so
  `test_profile_auto_resolves_the_lane` — which replays these records — still passes.

The 595-count over-match was caught *before* regenerating, by reading the diff rather than
accepting it.

## Gates

| gate | result |
|---|---|
| `ruff check` (bare, as CI runs it) | clean |
| `pytest tools/tests` | 53 passed, 1 skipped |
| package self-checks | 13 pass, incl. the two new cases |
| `discover_corpus.py --check` | no drift (after the deliberate `--write`) |
| conservation, body / footnotes | 100.000% / 100.000% |
| stale exemptions, all three lanes | 0 |
| documents | 80 / 11 / 12, held |
| `data/ocr_cache` | 0 B |
| rollback | `output/_pre_r6/` on both lanes |

## What is left (70)

| invariant | acts | rules | ord. | total |
|---|---|---|---|---|
| `section_carries_its_body` | 19 | 17 | 5 | 41 |
| `no_foreign_section_start_in_body` | 10 | 9 | — | 19 |
| `section_codes_ordered` | 6 | — | — | 6 |
| `no_chapter_caption_in_section_heading` | 3 | — | — | 3 |
| `clause_codes_plausible` | 1 | — | — | 1 |

**Lead for the next round.** The five Sales Tax `section_codes_ordered` hits are a
parenting error, not a body error: section 33A binds its real body at page 75 but is
parented to CHAPTER I. That edition reports `toc_pages_scanned: 0` — it is a TOC-less
edition rebuilt by `discover.py`, so the parenting comes from body discovery, not
`parse_toc`. Note the document also prints `[(33A) "supply chain" means …` as a *definition
clause* of section 2, inside CHAPTER I.
