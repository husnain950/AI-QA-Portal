# Phase 3 — the ordinance lane's omitted-section stubs (ordinance 3 → 0)

Written 2026-09-14. Branch `fix/phase3-ordinance-omitted-stubs`, **stacked on**
`fix/fbr-quote-prefixed-section-start`.

Closes the last three ordinance hits by *exemption with evidence*. **The ordinance lane is
now at zero.**

`tools/suite/exemptions/ordinance.json` did not exist before this round.

---

## What was measured

| lane | before this round | after |
|---|---|---|
| acts | 6 | 6 |
| rules | 2 | 2 |
| ordinance | 3 | **0** |

No parser code touched and no PDF converted in this round.

## The ordinance five were two causes, and the order was forced

The board carried "the ordinance five" as one row for four rounds. It is **two unrelated
causes**:

- **s.214E ×2** — a live parser bug: the body prints `4[“214E.` with the opening quote glued
  into the amendment bracket. Fixed in the parent branch.
- **ss.233AA and 122C ×2** — **not parser bugs at all.** These are omitted sections with no
  printed body. This round.

**The order was not a preference.** An exemption keys on `{invariant → reason}` **per
document** (`runner._exempt_reasons`), so it silences *every* hit of that invariant on that
file. The 30.06.2019 edition carried **both** s.122C and s.214E. Writing this file first
would have **masked the parser bug the parent branch fixes** — and the suite would have gone
quiet while a real defect stayed shipped.

## The three, traced at their pages

| edition | section | TOC row still lists it | the words survive only here |
|---|---|---|---|
| 30.06.2022 | 233AA | p.17 `233AA. Collection of tax by NCCPL 424` | p.452, 8.04pt: `Section 233AA omitted by the Finance Act, 2021. The omitted section read as follows:` + `“233AA. Collection of tax by NCCPL.—NCCPL shall collect advance tax…` |
| 30.06.2019 | 122C | p.10 `122C. Provisional assessment 205` | p.229 `…The substituted section “122C” read as follows:` and p.230 `Section 122C omitted by Finance Act 2017,the omitted section 122C is read as under:`, both 8.04pt |
| 31.12.2019 | 122C | p.9, same row | p.230 and p.231, same two quotes, pages shifted by one |

Every other mention in those documents is a cross-reference — for 233AA, pages 513
(`The rate of deduction under section 233AA shall be 10%…`) and 735 (`(h) tax deducted under
section 233AA;`); for 122C, pages 216, 225, 234, 251 and 327.

The live text prints only empty amendment placeholders. The section's words exist **only at
8.04pt inside a footnote quote**, against a 9.96pt body — which the body reader correctly
excludes. The leaf exists solely because the arrangement of sections still lists the section
under its **pre-omission title**, and `builder._build_one`'s TOC fallback emits a stub.

## The invariant's own diagnosis is wrong here, and the entries say so

`section_carries_its_body` prints *"its text is probably inside the preceding section"*. For
these three the text is **nowhere** — the section no longer exists. An exemption that lets a
wrong diagnosis stand unremarked is half an exemption, so each reason states it.

## Why `_is_omission` — the mechanism built for exactly this — cannot cover them

`_common.py:1283` `_is_omission` reads the leaf's **heading and `plain_text`**. These
headings are the real pre-omission titles, with no "omitted" word anywhere in them.

The contrast is exact, and it is not about the sections at all:

| document | section | heading | exempt by `_is_omission`? |
|---|---|---|---|
| 30.06.2022 | **233A** | `omitted by the Finance Act, 2021` | **yes** |
| 30.06.2022 | **233AA** | `Collection of tax by NCCPL` | no |
| 30.06.2019 | **214D** | `Omitted by the Finance Act, 2018` | **yes** |
| 30.06.2019 | **122C** | `Provisional assessment` | no |

s.233A is omitted, on the same page of the same document, and passes — for no better reason
than that the FBR updated its contents row and did not update 233AA's. **The discriminator
is the source's TOC hygiene**, not a property of the sections or of the parse.

That is worth recording as an argument for an instrument, not as a complaint: the honest
signal for "this section was omitted and its body is a placeholder" is the footnote that
says so, and no invariant reads it.

## No expiry

All three are `native-digital` sources and none is OCR-class. No correct parse can produce a
body for a section the edition does not print, so nothing can ever clear these entries
except the FBR reprinting the document.

## Verification

`run_suite.py ordinance` — three documents each report `exempt 1 (1 hits)`, lane **ALL
PASS**. `pytest tools/tests -q` 231 passed, 1 skipped. `ruff check` (bare) clean.
`du -sh data/ocr_cache` 0 B.

`tools/tests/test_suite_exemptions.py` is lane-generic and already covers this file: it
asserts each entry names a real member of `ALL_INVARIANTS`, carries a non-empty reason, and
that `applies_to` matches **exactly one** staged corpus document. No new test was added.
