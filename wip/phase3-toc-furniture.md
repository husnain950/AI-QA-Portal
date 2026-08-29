# Phase 3, class 5 — the contents page's own title, read as a chapter

Review page: <https://claude.ai/code/artifact/9e731f72-d9cb-4c52-89ce-0d18012516fe>

Follows [`wip/phase3-split-codes.md`](./phase3-split-codes.md) (PR #49). Register
**78 → 75**, and the Customs 2008 edition goes from 24 parsed chapters to the 22 its
contents page actually lists.

| | before | after |
|---|---|---|
| register | 78 | **75** |
| `no_chapter_caption_in_section_heading` | 5 | **3** |
| `section_codes_ordered` | 7 | **6** |
| Customs 2008 chapters parsed | 24 | **22** |
| anonymous chapters in that edition | 2 | **0** |

## 1. `82A out of order after 224`

The message named a section-ordering problem. It was a chapter-parsing problem.

Section 82A sat at tree position **262**, after the document's last section, while printing
on page 91. It was not in CHAPTER IX where it belongs — it was in an **anonymous container**
appended to the end of the tree. So were sections 167–192, in a second one. The parse
reported **24 chapters against a contents page listing 22**.

Both anonymous containers open at a TOC page break, and both breaks land *inside* a wrapped
section row:

```
82.    Procedure in case of goods not cleared or warehoused or
                              (viii)
             THE CUSTOMS ACT,1969          <- ALL-CAPS: a "foreign caption"
       transshipped or exported or removed from the port within
       twenty days after unloading or filing of declaration.    66

82A.   Omitted.                                                 67   <- lands in it
```

The contents page's own running title is ALL-CAPS, so it satisfies `is_foreign_caption`
and `_open_caption_chapter` opens a chapter for it. Everything until the next real chapter
heading parents there.

## 2. The filter already existed, at the wrong end of one test

`toc.py` has `_page_furniture` for exactly this line. Its docstring names this document and
this section:

> The 2007 Customs contents centre "THE  CUSTOMS   ACT,1969" on all 22 of theirs […] so the
> copy that lands after the last section row of a page was glued to that row — s.82A's
> heading came out "Omitted THE CUSTOMS ACT,1969".

The set is consulted at **two** call sites, and they order the tests differently:

| site | order |
|---|---|
| the `last_section` path | `extra in furniture` → **then** `is_foreign_caption` |
| the `pending_page` path | `is_foreign_caption` → then `extra not in furniture` |

The second is reached when a page break lands inside a *wrapped* row — precisely the case
here — and by then the caption branch has already fired. The fix is to test furniture first,
as the other site already does.

**Customs 2008 now parses 22 chapters**, `82A` is back in CHAPTER IX (pages 86–91), `167–192`
in CHAPTER XVIII (173–192), zero anonymous containers, all 297 sections preserved. That
edition drops from 5 hits to 2.

This is round 1's shape again: not a missing rule, but two places applying the same rule in
a different order.

## 3. The invariant was a proxy for what its name says

Measured separately, on identical JSON.

`_CHAPTER_CAPTION_IN_HEADING` fires on any run of three or more capitalised words. What the
check *means* is that a chapter's caption leaked into a section heading — and a section
whose own title is printed in capitals matches the proxy exactly as well:

```
150 ZQZA. RESPONSIBILITIES OF THE VENDOR.–(1) Subject to these rules,
```

That is Sales Tax Rules 2006 setting that rule's title in capitals, reported in **both**
editions once round 4 let the rule bind at all.

So the check now asks the question its name asks: **is this caps run a caption that appears
on a chapter of this document?** Over every hit on the register that separates them cleanly:

| document | section | caps run | on a chapter? |
|---|---|---|---|
| Customs 2012 | 82A | `CLEARANCE OF GOODS FOR HOME-CONSUMPTION` | **yes** |
| Sales Tax 2020 | 32AA | `VII OFFENCES AND PENALTIES` | **yes** |
| Sales Tax 2019 | 32AA | `VII OFFENCES AND PENALTIES` | **yes** |
| Sales Tax Rules ×2 | 150ZQZA | `RESPONSIBILITIES OF THE VENDOR` | no |

Invariant fix alone: rules **2 → 0**, acts holds at **3** — every real leak still gating.

### The locking fixture was wrong, and that is a finding

`_demo_heading_leak_class` pins this detector with a synthetic document: section 14A with
`PROHIBITION AND RESTRICTION OF IMPORTATION AND EXPORTATION` glued to its heading — and **no
chapter carrying that caption**. Under the new check it stopped firing.

That is worth stating rather than patching away. It asks whether the leak can happen while
the chapter is absent from the tree. It cannot: Customs omits the `CHAPTER IV` row from its
contents, but `_open_caption_chapter` still opens a node for the bare caption, so the
chapter is present — verified on all three editions that carry the defect today. The
fixture was missing the very thing that makes its document a leak. It now includes it, and
still fails if that chapter is removed.

## 4. What this did not fix

Stated plainly, because the class is not closed:

- **`section_codes_ordered` 7 → 6.** Only the Customs 2008 hit was this cause. The five
  Sales Tax hits are a *different* misplacement: `CHAPTER I PRELIMINARY` holds
  `['1', '2', '33A']` spanning pages 2–75 — section 33A (page 75) is parented to CHAPTER I
  instead of CHAPTER VII. Round 6.
- **`structure_counts` 5, unchanged.** The rules lane still shows the anonymous-container
  symptom (three in each Sales Tax Rules edition, plus `CHAPTER V-C` at page 47 sitting
  among pages 61–65), so a second path reaches `_open_caption_chapter`. Round 6.
- 36 anonymous chapters remain corpus-wide, but most are **legitimate**: a flat act — the
  Finance Acts and amending instruments — is given exactly one synthetic root by design.

## Gates

| gate | result |
|---|---|
| `ruff check` (bare, as CI runs it) | clean |
| `pytest tools/tests` | 53 passed, 1 skipped |
| package self-checks | 13 pass |
| `discover_corpus.py --check` | no drift |
| `signatures.json` | unchanged |
| conservation, body / footnotes | 100.000% / 100.000% |
| stale exemptions, all three lanes | 0 |
| documents | 80 / 11 / 12, held |
| `data/ocr_cache` | 0 B |
| rollback | `output/_pre_r5/` on both lanes |
