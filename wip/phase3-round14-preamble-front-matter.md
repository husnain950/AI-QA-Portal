# Phase 3 round 14 — the preamble that began on the contents page

Two modules that disagreed about a folio, a contents row nothing could read, and a
gate that would have reported zero on a document that still has the defect.

## What was actually wrong

Nine documents shipped a preamble that opens on front matter. Six of them are Customs
Act editions; measured across all twenty converted editions of that group:

| | preamble opens | n |
|---|---|---|
| correct | `1[Act No. IV of 1969]` — 314/315 chars | 14 |
| 2013–2016 | `THE CUSTOMS ACT, 1969 / Section Page / No. / 224 Extension of time limit. 212 / THE FIRST SCHEDULE 216 … / xxi` | 4 |
| 2008 | `THE FIRST SCHEDULE 213 / THE SECOND SHCEUDLE Omitted. 213 … / (xxii)` | 1 |
| 2007 | `(xxii)` | 1 |

Three more outside that group: **two Federal Excise Act editions whose entire preamble
is the single token `vi`** — the enacting formula never reached it at all — and Sales
Tax Rules 2006 (30-06-2025), whose legitimate S.R.O. preamble wears a leading `(xvii)`.

`preamble_carries_no_toc_tail`, added in #74, saw **four** of them. It keys on the
Contents column header `Section Page No.`, which is one *spelling* of the defect.

### Cause 1 — one module reads a roman folio, its neighbour does not

`pagemodel.build_page_model` strips the footer page number:

```python
# 2) capture + strip footer page number (centred bare integer near bottom)
v = _centred_int(ln)          # -> grammar.folio_value: ARABIC only
```

Front matter numbers its pages in **roman**. So a roman folio was never dropped as
furniture, survived into `body_refs`, and everything before the first section's anchor
becomes the preamble.

`calibrate` has known this the whole time — line 348 matches a roman folio when deciding
where the footer band sits. **Two modules, one question, two answers**, which is round
13's separator and round 1's chapter numeral again.

The predicate now lives in `grammar.py`, where `calibrate`'s own comment already says
folio grammar belongs (*"`pagemodel` reads the same forms per page and cannot import
this module"*). `calibrate`'s looser test stays looser, deliberately: it asks *where is
the footer band*, where a false positive costs one sample; `pagemodel` asks *delete this
line*, where a false positive deletes text.

**The band could not be the test.** `footer_min_top` is calibrated from body pages and
front matter is set to a different depth — the Customs 2008 folio prints at top 673.9
against a band starting at 702.5. So the test is what a folio *is*: roman, centred,
alone on the **last** line of the page, below the vertical midpoint. Measured over the
front matter of six editions: **65 roman-shaped lines, 64 of them folios running
i…xxii on consecutive pages**, and one a Sales Tax clause marker `(iii)`, correctly kept
because it is neither last nor in the bottom half.

Bounded at ccxcix and lowercase, for a reason worth writing down: **`mix` is a valid
roman numeral** (MIX = 1009) and an ordinary English word, and an uppercase `I` is a
drop cap. A plain `[ivxlcdm]+` — which is what `calibrate` uses — eats all three.

### Cause 2 — a contents row nothing could read

The folio was only the last line of that page. The rows above it are the contents tail,
and they are still there after cause 1 is fixed.

`detect_toc_pages` is **correct**; the tail page is not part of what it counts. Measured
per page on Customs 2008:

```
pdf p21  lines=25 rows=13 ratio=0.52    <- contents
pdf p22  lines=24 rows=14 ratio=0.58    <- contents          detect_toc_pages = 22
pdf p23  lines= 6 rows= 0 ratio=0.00    <- contents TAIL, read as body
```

Zero rows on a page that is nothing but contents, because `_is_toc_row` reads a row as
`code, title, folio` and a **schedule** contents row carries no code:
`THE FIRST SCHEDULE 213`.

The pattern for it already existed. `grammar.SCHEDULE_TOC_RE` is the anchored,
already-narrowed form — its own note records the wrapped citation
(`THE FIFTH SCHEDULE TO THE ACT……… 45`) that the unanchored version read as a schedule
title, switching the parser into schedule mode mid-body and losing two chapters. Reused
rather than rewritten, and it still rejects that line here.

**Measured over both profiles and all 90 resolvable documents: 4 changed, 86 unchanged.**
The four are exactly the 2013–2016 editions.

## Measured

**Invariant fix alone, on identical JSON — 4 → 10.** It was reporting four of ten.

| lane | saw | actually |
|---|---|---|
| acts | 4 | **9** |
| rules | 0 | **1** |
| ordinance | 0 | 0 |

**Parser fix — 10 → 2.** Nine documents re-converted, **0 refused**.

| | before | after |
|---|---|---|
| Customs 2013 / 2014 / 2015 / 2016 preamble | 484 / 507 chars | **314** — the length its 14 correct siblings carry |
| Customs 2007 | 321 | 314 |
| Federal Excise 2005 ×2 | 2 (`vi`) | node correctly absent |
| Sales Tax Rules 2006 30-06-2025 | 828 | 821 |
| Customs 2008 | 433 | 426 — folio gone, rows remain |

**Register 34 → 40 → 32.**

### Section 224 came back

The 2013–2016 editions went **304 → 305 section leaves**. Section 224's contents row was
inside the glued tail, so it never parsed; counting that page as front matter binds it.
A gain, and the cheapest proof the page-count fix landed rather than only the folio strip.

### Conservation

**Identical before and after on all nine**, body and footnotes. Six Customs editions at
100.000% / 0 missing on both sides. The three that are not at 100% carry **pre-existing,
byte-identical** deficits — Federal Excise 1 × `TABLE`, Sales Tax Rules 4 footnote
fragments — present before this round and unchanged by it.

## The two that survive, and why

Both are the same shape: the contents tail page falls under `detect_toc_pages`'s density
floor, and that floor is load-bearing.

- **Customs 1969 (30.06.2008)** — its source prints `THE SECOND SHCEUDLE Omitted.`, and
  `SCHEDULE_TOC_RE` rightly refuses the typo, which leaves the page with 2 rows against a
  floor of 3. Loosening the pattern to admit it would re-admit the wrapped citation its
  own note records losing two chapters to.
- **Sales Tax Act 1990 (30.06.2023)** — a **new find**, invisible before this round:
  `THE TWELFTH SCHEDULE……………....246` and `THE THIRTEENTH SCHEDULE...248` sit in front of
  `The Sales Tax Act, 1990`. Two rows, same floor.

`detect_toc_pages`'s own comment explains why `rows >= 3` is not negotiable: the Income
Tax Rules prints a body TITLE page straight after its contents, three of whose 38 lines
match the row shape, and a lower floor swallows it and starts the body a page late.

## The gate that would have reported zero

Removing the folio removed the only signal the invariant had on Customs 2008 — a
document that **still carries four contents rows in its preamble**. Left there, this
round would have closed the class on paper while one document silently kept the defect.

A third branch reads a schedule contents row directly out of the preamble text. It is
deliberately looser than the parser's (it tolerates the `SHCEUDLE` typo) because it only
*reports*; the parser's must not, because it *cuts*.

One limitation is pinned rather than hidden: `(iv)` alone on a line is indistinguishable
from a folio in the JSON. The parser separates them by geometry — centred, last line,
bottom half — and an invariant cannot see geometry. Measured at **9 roman-shaped lines
over 1,292 preamble lines corpus-wide, every one a folio**, so the check is worth more
than the risk. `test_a_subsection_marker_alone_on_a_line_is_still_reported_as_a_folio`
is where that trade-off is written down.

## Locked by

| lock | fails if you revert |
|---|---|
| `grammar._demo` — `vi`/`xxi`/`(xxii)` match, `mix`/`civil`/`I`/`vii)` do not | the bounded predicate |
| `calibrate._demo` — a schedule contents row IS a contents row, the wrapped citation is not | cause 2 |
| `tools/tests/test_preamble_toc_tail.py` — 10 tests, four of them new | either invariant branch |
| `tools/suite/cases/acts.json` ×3 on Customs 30.06.2014 | the preamble trim, the enacting formula surviving it, and section 224 binding |

Each verified by removing its fix. The parser lock was verified end to end: with the
folio strip removed, Federal Excise 31.12.2019 converts to a preamble of `'vi'` again and
the invariant fires on it.

One case was written and then deleted rather than weakened: an absent preamble makes
every `preamble_*` check return "no preamble present", so a case cannot assert that the
Federal Excise node is correctly gone. `inv_preamble_present` already covers it, by
scanning the first leaf for `WHEREAS` / `IT IS HEREBY ENACTED`.

## Verified

`pytest tools/tests` **86 passed, 1 skipped, 0 failed** ·
register regenerated to **32** ·
`ruff check` bare clean ·
`discover_corpus.py --check` **no drift** ·
`data/ocr_cache` **0 B** ·
`output/_refused/` **no new entries** ·
conservation identical on all nine documents.
