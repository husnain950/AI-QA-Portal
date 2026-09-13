# Phase 3 — the acts-lane exemptions (register 13 → 8)

Written 2026-09-14. Branch `fix/phase3-acts-exemptions`.

Closes **5 of the 6** acts-lane register hits by *exemption with evidence*. The sixth
(Sales Tax Act 1990, 01.07.2014, s.10) is a live parser defect and is deliberately left
open for its own round.

`tools/suite/exemptions/acts.json` **did not exist before this round.** Round 15 predicted
it would be needed for `section_codes_ordered` and it was not — that class was closed by a
parser fix instead, and the file stayed unwritten for eleven rounds. These are the first
acts-lane exemptions.

---

## What was measured

| lane | before | after |
|---|---|---|
| acts | 6 | **1** |
| rules | 2 | 2 |
| ordinance | 5 | 5 |
| **register** | **13** | **8** |

`tools/tests`: 231 passed, 1 skipped — unchanged. `ruff check` (bare): clean.
`data/ocr_cache`: 0 B, unchanged. **No PDF was converted in this round**, and no parser
code was touched, so no lane could move except by the exemptions themselves.

## The three entries

### 1. Customs Act 1969 (30.06.2008), ss.181 and 189 — the source misprints the code

The body prints the wrong section number, at ordinary body size and at the ordinary left
margin, so there is nothing about the line's *shape* to reject:

| section | PDF page | the body prints | the contents page says |
|---|---|---|---|
| 181 | 185 | `35. Option to pay fine in lieu of confiscated goods.- Whenever an order…` | `181. Option to pay fine in lieu of confiscated goods. 161` |
| 189 | 191 | `37. Notice of conviction to be displayed.- (1) Upon the conviction…` | `189. Notice of conviction to be displayed. 167` |

Both are 12.00pt at x0 93.6 — the same size and margin every other section heading in the
document uses. The neighbours are unaffected: s.180 prints `180.`, s.182 prints `182.`,
s.188 prints `188.`, s.190 prints `190.`. So this is **not** a systematic offset that could
be corrected arithmetically; it is isolated wrong numbers.

**The defect is three sections wide, not two.** s.185D prints `36. In respect of a case
transferred to a Special Judge under sub-section(1)` on page 189. **No invariant reports
it**, because that leaf did pick up a body — so the register sees two thirds of this defect.
Recorded here so the next reader does not infer from the entry's two hits that the misprint
stops there.

**What was rejected.** The only route to reading these is to adopt the contents-page code
whenever a body code breaks monotonic order and the heading text matches. That is exactly
the shape rounds 23 and 25 shipped and round 27 had to guard, after one of them collapsed
860 of 1,102 rules to stubs in another lane. Two hits in one edition do not buy that risk.

**No expiry.** `metadata.source_kind` is `native-digital`; no OCR decision can clear it.

### 2. Public Finance Management Act 2019, s.26 — OCR-class, cannot be re-measured

`source_kind: scanned-ocr`, `pipeline_revision: null` — one of the 14 documents the
round-27 re-conversion deliberately skipped, so its output was written by an older parser
than the one in the tree.

PDF page 12 emits the heading terminator **glued into one 9.00pt token**: `system.—The`,
codepoints `0x73 0x79 0x73 0x74 0x65 0x6d 0x2e 0x2014 0x54 0x68 0x65`. The heading
swallowed the whole body.

**This entry is careful about what it claims.** `builder.DASHES` already contains U+2014, so
the *current* parser may well read this line correctly and this hit may be nothing more
than stale-revision drift. That cannot be tested: re-converting re-runs OCR, and
`data/ocr_cache` must stay at 0 B under the decision of record. The entry exists because
"tracked and deferred" is not a state this suite allows — **not** because the parser is
known to be wrong.

**Expiry: the OCR decision.** When OCR is taken in scope, re-convert this document *first*
and delete the entry if the hit clears.

### 3. Pakistan Single Window Act 2021, ss.27 and 28 — Schedule rows read as sections

Same class: `source_kind: scanned-ocr`, `pipeline_revision: null`, one of the 14 skipped.

**These are not sections of the Act.** They are rows of its Schedule — a two-column
`S. No. | Organization / Department / Ministry` table introduced by `[SCHEDULE]` and
`(see sections 2 (n) and 19}`. Its serial column is read as section codes:

```
section 27: Ministry of Defence                 <- heading-only, one line
section 28: Ministry of Defence Production      <- heading-only, one line
section 29: - Ministry of Foreign Affairs
            30. Ministry of Interior
            31. Ministry of National Health Services, Regulations and Coordination …
```

**The parse's own shape is the proof.** It emits ONE chapter, `PART I`, whose section codes
run `3..23` and then jump straight to `27, 28, 29` — ss.24, 25 and 26 are absent — and it
emits **zero schedules**.

The OCR text layer of that table gives a reader nothing to discriminate on. The same serial
column prints `I.` for 1, `I D.` for 10, `1I.` for 11, `1$.` for 18 and `23,` for 23,
alongside `Ministry of Foreign AffairS`, `Terminal'Operators`, and a running head reading
`PART q`. A serial column that cannot be told from a section code is not something a
pattern fixes on this text layer.

**Expiry: the OCR decision** — and the right fix then is almost certainly to recover the
Schedule *as a schedule*, not to patch the two leaves this entry names.

---

## What moved by zero, and why that is reported

The rules and ordinance lanes moved by **zero**, which is correct and worth stating: an
exemption is scoped by `applies_to` to one document, and nothing in this round touched
parser code, so no other lane *could* move. A round that folds a zero into a total
misattributes the rounds that did move it.

## No new test was added, on purpose

`tools/tests/test_suite_exemptions.py` is already lane-generic. It loops
`("acts", "rules", "ordinance")`, skips a lane whose file does not exist, and asserts for
every entry that the `invariant` names a real member of that lane's `ALL_INVARIANTS`, that
a non-empty `reason` exists, and — `test_shipped_exemptions_match_exactly_one_corpus_document`
— that `applies_to` matches **exactly one** staged corpus document. Creating `acts.json`
brought all three assertions to bear automatically. Adding a fourth test would have
duplicated a gate that already fires.
