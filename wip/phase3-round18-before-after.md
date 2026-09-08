# Round 18 — before / after

Companion to [`phase3-round18-chapter-letter-suffix.md`](phase3-round18-chapter-letter-suffix.md).
Every number measured on this machine at `e9d7e74`, the two runs differing only in the
CHAPTER branch of `builder._STRUCTURAL_RE` and of the suite's `_STRUCT_LINE`.

## The register — measured in two halves, because one number hides both

| lane | baseline | invariant widened (identical JSON) | parser widened + 24 re-converted |
|---|---|---|---|
| acts | 15 | 37 | **15** |
| rules | 5 | 40 | **5** |
| ordinance | 5 | 5 | **5** |
| **total** | **25** | **82** | **25** |

**Rise +57, fall −57, net zero.** `tools/suite/register.json` unchanged, so it needed no
regeneration. The final run is identical to the baseline *class for class and document for
document* — diffed, not eyeballed.

The +57 is entirely `no_structural_heading_in_body`, over **24 documents** (20 Customs Act
editions, 4 rules editions). **That is the ledger's own "57 hits / 24 documents"**,
reproduced four rounds after it was measured — and reproduced only by the corrected pattern.
The prescribed one (`[A-Z]{0,2}`, "the same suffix class as PART and Division") finds **9**,
because it cannot cross the hyphen in `CHAPTER XVI-A`.

## What actually moved — 80 lines to 0

| | before | after |
|---|---|---|
| swallowed suffixed-CHAPTER boundary lines | **80** | **0** |
| leaves | 7,088 | **7,088** (+0) |
| chapter nodes | 544 | **544** (+0) |
| duplicate chapter codes | 0 | **0** |
| body words belonging to the tree | 756 | **0** |

| lane | documents | lines |
|---|---|---|
| acts — 20 Customs Act editions | 20 | 39 |
| rules — Sales Tax Rules 2006 × 2, STSP Rules 2007 × 2 | 4 | 41 |
| | **24** | **80** |

## Before / after, one leaf

`Customs Act, 1969 as amended up to 30th June, 2025`, CHAPTER XVI · section 155 — the real
case, 7 body lines down to 4:

```diff
  restriction imposed by or under any law, nor shall such goods or stores be brought to
  any place in Pakistan for the purpose of being so carried or shipped.
- 1[CHAPTER XVI-A
- PROVISIONS RELATING TO THE CUSTOMS COMPUTERIZED SYSTEM
- AND AUDIT AND ACCESS TO DOCUMENTS
```

And the node that was already there the whole time:

```
CHAPTER XVI-A  heading: 'PROVISIONS RELATING TO THE CUSTOMS COMPUTERIZED SYSTEM
                         AND AUDIT AND ACCESS TO DOCUMENTS'
```

**Nothing was gained or lost — it was un-duplicated.** The chapter comes off the contents
page and the body was printing its caption a second time. That is why leaves and chapter
nodes are flat, why 756 words leave bodies, and why **no `section_carries_its_body` hit
moved**: no section's body was ever missing anything, it had too much.

## Conservation — unchanged, and not the evidence

| document | off | on |
|---|---|---|
| Sales Tax Rules 2006 (01-01-2025) | 99.998% (1 word) | **99.998% (1 word)** |
| Sales Tax Rules 2006 (30-06-2025) | 100.000% | **100.000%** |
| Customs Act 1969 (30.06.2025) | 100.000% | **100.000%** |

`audit_completeness` counts container headings too, so a caption moving from a body into the
tree nets out exactly. Per round 13's warning, the evidence that nothing was sliced is the
line-level table above, not these percentages.

## The gate

`tools/tests/test_suffixed_chapter_cuts_the_section.py` — **new**, 3 cases, all through
`build_sections` rather than the predicate, per round 17's lesson that a predicate test
passes whether or not the answer reaches the cut.

| removed | fails |
|---|---|
| the parser widening | `test_a_suffixed_chapter_line_cuts_the_section` |
| the parser widening | `test_the_fused_and_spaced_separator_forms_cut_too` |
| either widening | `test_parser_and_invariant_agree` (existing) |

Verified by reverting `_STRUCTURAL_RE` and re-running: **3 failed, 4 passed**; restored:
**7 passed**. `__pycache__` cleared between, per the standing trap.

The negative case — `test_a_chapter_cross_reference_still_sits_in_the_body` — stays green in
both states by design: it guards against over-cutting, which is the failure a wider suffix
class would introduce, not the one the widening fixes.

## Rejected, measured

- **`grammar.ROMAN`'s class verbatim** (`\s?-?[A-Z]{1,3}`). Its spaced branch under
  IGNORECASE eats *of / or / for* — 28 ordinance false positives, already on record.
- **Delegating to `grammar.CHAPTER_RE`.** It accepts `Chapter VII of` and `chapter 87 35`,
  which the parser must keep refusing. Agreement on the suffixed forms, not delegation.
- **Porting to `packages/fbr_ingest/builder.py:1395`.** Gated on P4-2; the ordinance lane
  did not move in either half of the measurement.
- **Widening `_STRUCT_LINE`'s `PART\s+`** while in that line — it would report the nine
  annexure-FORM part lines in the rules lane as defects.

## Located, pinned, left open

The **en-dash separator**: `CHAPTER – VI` / `– VII` / `– V` / `– VIAB`, **42 real boundaries
across 21 documents**, whose captions (`DRAWBACK`, `ARRIVAL AND DEPARTURE OF CONVEYANCE`,
`REFUND`) sit in bodies today.

Left open on evidence: `grammar.CHAPTER_RE` **rejects these too**, so unlike round 18's row
it cannot be closed by making the parser agree with the grammar — the grammar has to move
first, and it is shared by three readers. Round 17's "en/em dash gains zero" was measured on
**PART** and does not transfer: the container guard refused those, and the CHAPTER branch has
no guard. Now *Start here* row 9, pinned as `KNOWN_GAP_ENDASH_CHAPTERS`.

## Verified

```
pytest tools/tests -q     98 passed, 1 skipped   (95 baseline, +3 new)
ruff check                All checks passed      (bare)
run_suite.py × 3          15 / 5 / 5 = 25        (unchanged)
discover_corpus --check   no drift
du -sh data/ocr_cache     0B
```

The pre-round baseline is **95**, not the **92** that `handover/README.md` §4 and
`tasks.md` step 8 both stated — round 17 added three tests and did not update them. Both
files are corrected in this PR.
