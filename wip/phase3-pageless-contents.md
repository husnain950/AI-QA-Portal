# Phase 3, round 11 — 118 sections the register could not see

Review page: <https://claude.ai/code/artifact/5ed4aa5b-d47a-497a-99c8-d05217548cbd>

Follows [`wip/phase3-header-band.md`](./phase3-header-band.md) (PR #57).

**33 → 30.** The register moved by three. The document moved by **118 sections**, and that
gap is the point of this round.

## How it was found

Round 10 left `Sales Tax Act, 1990 as amended up to 30.06.2021` holding four hits, so it was
next. Tracing it, `why_unbuilt` returned nonsense — `sections=9`, `body_refs=0`, every entry
expecting page 1995 — and the output explained why:

```
leaves: 9   chapters: 14
  s.19  page=53    len= 34864  '19. *** 20. ***] 4[21. De-registration, blacklisting and susp…'
  s.33  page=1995  len=  1096  '33. Offences and penalties 33A. Proceedings against authority…'
  s.30  page=1995  len=   492  '30. Appointment of Authorities 30A. Directorate General, (Inte…'
```

Nine leaves. Its eighteen sibling editions parse **110 to 151**:

```
     9  Sales Tax Act, 1990 as amended up to 30.06.2021        <-- this one
   110  Sales Tax Act, 1990 (As amended vide Finance (Amendment) Ordinance…
   115  The Sales Tax Act 1990 (amended up to 1st July 2015)
   …
   145  Sales Tax Act 1990 amended upto 30-06-2025
   151  Sales Tax Act, 1990 amended upto 30th June, 2024
```

The sections are in the PDF — `grep` finds `30. Appointment of Authorities`,
`33. Offences and penalties` and `73. Certain transactions not admissible` in its 14,381
lines of text. And this is **not new**: the snapshots say 9 leaves at `_pre_phase3`,
`_pre_r4`, `_pre_r9` and `_pre_r10`, and 5 before Phase 2. It has been this way the whole
time.

## The cause: a contents page with leaders and no folio

```
Contents
Chapter I..............................................................................
Preliminary............................................................................
1.     Short title, extent and commencement. ..........................
2.     Definitions.....................................................................
```

Nothing after the leaders. Compare the sibling that works, five weeks later:

```
3B.    Collection of excess sales tax etc. ..................................... ..……..34
4.     Zero rating. ........................................................................ ..……..34
```

With no folio to read, nine rows survived out of ~140 and every one of them carried
`printed_page = 1990` — the **year**, taken off the running title *The Sales Tax Act, 1990*.
The salvaged codes are `['1','19','33','45B','65','3','22','30','48']`, which is also where
the `section_codes_ordered` hit `'3' out of order after '65'` came from.

`build_sections` is page-anchored. An entry expecting page 1995 of a 291-page document can
never bind, so 130 sections became nothing and their text folded into the leaves that did
bind — 34,864 characters of it into s.19.

## The fix: an unreadable contents page is a contents page you do not have

`discover.py` is described in `wip/plan.md` as *"a body-driven fallback for editions that
print no table of contents"*. It was gated on the TOC producing **nothing**:

```python
    if not ordered_sections:
```

Nine rows of garbage is not nothing, so the fallback never ran. The gate now also fires when
the page column points nowhere:

```python
    usable_pages = [e for e in ordered_sections
                    if e.printed_page and 1 <= e.printed_page + offset <= total_pages]
    if not ordered_sections or not usable_pages:
```

The test is deliberately **not** "too few entries" — a flat instrument legitimately has
three. It is "no entry lands inside this document", which cannot be true of a contents page
the parser read correctly.

## Measured: one document, 118 sections

Across acts and rules, **exactly one document changed**:

| document | section leaves | all leaves | chapters | characters |
|---|---|---|---|---|
| Sales Tax Act 1990 (30.06.2021) | **9 → 127** | 30 → 148 | 14 → 10 | 341,145 → 339,437 |

The four chapters that disappear were anonymous (`''`); five of the fourteen held no leaf at
all. The −1,708 characters are the synthesised `"<code>. <heading>"` placeholders those
leaves no longer need — conservation is unchanged:

```
--- BODY ---        source=48744  conserved=100.000%  missing=0
--- FOOTNOTES ---   source=11422  conserved=100.000%  missing=0
```

That document's own register hits go **4 → 1**, and the one that remains is *new*: with
s.32AA finally binding, `no_chapter_caption_in_section_heading` can see it, and it is the
same real leak already open on two sibling editions. A defect made visible is progress, and
it is why the acts column reads 3 rather than 4 for that class going down.

## The part worth arguing about

**The register moved 3. The document gained 118 sections.**

No invariant saw this, and the reason is structural: `section_carries_its_body` reports
leaves that exist, and 130 of them did not. `structure_counts` compares the tree against the
contents page — and the contents page parse was itself the thing that failed, so both sides
of the comparison were wrong together.

The obvious candidate check does not survive measurement. "No chapter may be empty" fires on
**29 of 103** converted documents:

| empty chapters | documents |
|---|---|
| 1 | 22 (twenty Customs editions all agree on `CHAPTER XIX-A`, two Sales Tax on `CHAPTER VIII-A`) |
| 2–5 | 6 (PFMA 2019, Sales Tax 2014, the two Sales Tax Rules, this edition at 5) |
| 9, 39 | Finance Act 2019; Customs Rules 2001, already exempted |

A twenty-edition agreement is evidence of a real omitted chapter, not of a defect, so the
check would open a hundred-hit register to find one document.

What would have caught it is a **cross-edition** fact — nine leaves where eighteen siblings
have a hundred and forty — and the suite has no place for one: invariants run per document.
`signatures.json` already carries the group, so the comparison exists in the corpus; it is
the wiring that does not. **Logged, not built**, and named here rather than left as an
observation: the register is a floor on what is wrong, not a measure of what is right.

## The register

| invariant | acts | rules | ordinance | total | was |
|---|---|---|---|---|---|
| `section_carries_its_body` | **8** | 8 | 5 | **21** | 23 |
| `no_foreign_section_start_in_body` | **—** | 1 | — | **1** | 2 |
| `section_codes_ordered` | **3** | — | — | **3** | 4 |
| `no_chapter_caption_in_section_heading` | 4 | — | — | 4 | 3 |
| `clause_codes_plausible` | 1 | — | — | 1 | 1 |
| **per lane** | **16** | **9** | **5** | **30** | 33 |

`no_foreign_section_start_in_body` reaches **zero on the acts lane**.

## Verified

- `ruff check` bare — clean · `pytest tools/tests -q` — 62 passed, 1 skipped
- the lock (`sta300621_pageless_toc_binds_late_sections`) fails with the gate reverted — the
  document returns to 9 sections; `__pycache__` cleared and the output restored after
- conservation **56/56** within gate (customs 20, salestax 19, excise 17)
- `discover_corpus.py --check` — no drift; `signatures.json` unchanged
- documents **80 / 11 / 12**, held · `data/ocr_cache` **0 B**
- rollback: `output/_pre_r11/`
