# Phase 3, round 19 — the round-10 rules residue

**PR #85.** Closes *Start here* row 1 (`handover/tasks.md` §5). **Register 25 → 22** — the
first movement in three rounds, and it is an **exemption with evidence**, not a fix.

Sales Tax Rules 2006 (01-01-2025) has three heading-only leaves. The invariant
`section_carries_its_body` is **right** about all three: the body text really is in the
preceding leaf. In each case the *source* hides the rule's own code from the body reader,
and no parser change can read it without making the parser wrong about correct documents.

## Re-confirmed against the pages — and two of the three traces were wrong

The row's instruction was *"re-confirm each against the source page — the traces exist but
the pages are the authority."* That was worth doing.

| hit | the ledger said | the page says |
|---|---|---|
| **44A** | opens with a left double quote | **correct** |
| **150W** | "150W's code appears only in a footnote" | **wrong** — the code is in the body, with its **leading digit dropped** |
| **150ZQZI** | printed `150ZQZl`; an **OCR-class** defect that "may expire on the OCR decision" | spelling **correct**; expiry **wrong** — the document is `native-digital` and is never OCR'd |

### 44A — a left double quotation mark before the code

PDF **page 66**, first line of the rule:

```
[CHAPTER VIA
AUDIT SELECTION AND CONDUCT
“44A. -Selection and conduct of audit.-(1) This rule shall apply to selection of cases for audit by the FBR
```

Its contents row, **page 5**, reads `44A. Selection and conduct of audit` — which is where
the heading-only leaf gets its heading. The body line opens with U+201C, so the code reader
never sees `44A.` at the start of a line.

### 150W — the source drops the leading digit of its own code

PDF **page 109**:

```
(2) The invoice data shall be stored in such manner that information at the time of
original transmission of invoice is re-created at the time of departmental audit.
228[50W. Audit.-- The integrated supplier shall allow physical and online remote access to the
```

`228[` is the amendment marker and bracket; the code that follows is **`50W`**, not `150W`.
The contents row on **page 10** reads `150W. Audit`. So the defect is a **dropped digit in
the body heading**, and the ledger's "appears only in a footnote" is not what the page shows.

That distinction matters for the fix that was never available: accepting `50W` as rule 150W
means accepting a code whose digits disagree with its own contents row, which is precisely
the check that keeps look-alike lines out (`code_sort_key`'s monotonic advance).

### 150ZQZI — a lowercase L, and a real `150ZQZL` one page later

PDF **page 151**:

```
150ZQZl. Functions of the licensing committee.— 333[(1) Board shall nominate a licensing
```

PDF **page 152**:

```
150ZQZL. Right granted to the licensee.— (1) A licensee shall have the right to install,
```

**Those are two different rules.** The row's standing instruction — *do not "fix" `150ZQZl`
by collapsing `l`→`I`* — now has the argument that makes it structural rather than stylistic:
collapsing them **collides `150ZQZl` with the real `150ZQZL`**, and one of the two would
lose its body. Round 18's `XIVA` vs `XIV-A` lesson, in a different alphabet.

Its contents row on **page 13** also carries the printer's typo `liceensing`, which is where
the leaf's heading `Functions of the liceensing committee` comes from.

## No expiry, on evidence

The document's `metadata.source_kind` is **`native-digital`**. It has a text layer, it was
never OCR'd, and `data/ocr_cache` is 0 B and stays that way under the recorded OCR decision.
So the lowercase `l` is genuinely in the source, not an OCR misread — **this entry can never
expire on the OCR decision**, and the ledger's note that it might was wrong on both halves.

All three are permanent printing errors. The entry is written with no expiry condition.

## One entry, not three

The row said *"write three entries"*. The format keys an exemption on
`applies_to` + `invariant`, and all three hits are `section_carries_its_body` on one
document, so three entries for one pair is not a shape the file has — `test_suite_exemptions.py`
resolves exemptions by that pair.

One entry therefore covers all three, and **the three are enumerated inside the reason on
purpose**: exempting the pair silences a *future* fourth hit on this document too, so the
reason names exactly which three it was written for and says that a fourth would be a new
defect it does not describe. That is the honest cost of the format, written down rather than
left implicit.

## The register

| lane | before | after |
|---|---|---|
| acts | 15 | **15** |
| rules | **5** | **2** |
| ordinance | 5 | **5** |
| **total** | **25** | **22** |

`section_carries_its_body` as a class: **17 → 14**. `tools/suite/register.json` regenerated
in this PR — and it had to be: the snapshot test **failed first**, reporting
`section_carries_its_body: 1 != 4` on the rules lane, which is the design working.

The remaining rules-lane hits are one `section_carries_its_body` on the 30-06-2025 edition
and the one `no_foreign_section_start_in_body`, neither of which is this row. The latter is
worth a note for whoever takes it: its message is *"section 13: body contains the start of
section 44A, which is itself heading-only: `44A Steel ingots / bala M. Tons`"* — and that
line is a **rate-table row**, not rule 44A. It is the same 44A defect seen from the other
side, but the line it names is a coincidence of code, so do not read it as evidence about
where 44A's body went.

## Verified

```
pytest tools/tests -q            98 passed, 1 skipped
pytest test_suite_exemptions.py  6 passed
ruff check                       All checks passed   (bare)
run_suite.py × 3                 15 / 2 / 5 = 22
discover_corpus --check          no drift
du -sh data/ocr_cache            0B
```

No document was re-converted: this round changes no parser code, so the corpus is untouched
and every number above is measured on round 18's output.

## Stacked on round 18

This branch is cut from `fix/phase3-round18-chapter-letter-suffix`, not from `main`,
deliberately. The corpus on disk is round 18's, and there is only one copy of it — measuring
this row against `main`'s parser would mean measuring round-18 JSON with pre-round-18 code.
Merge #84 first.
