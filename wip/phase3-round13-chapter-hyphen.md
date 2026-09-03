# Phase 3 round 13 — the separator the private copy never learned

175 swallowed chapter headings, 21 documents, two lanes. The register does not move.

## What was actually wrong

Three places in this repo answer "is this line a CHAPTER/PART/Division heading?".
One of them is right, and it is the one that has been asserting so since it was
written:

```python
# packages/legal_ingest/grammar.py
CHAPTER_RE = re.compile(rf"^\s*\[?\s*{spaced('CHAPTER')}[\s\-]+({NUMERAL}) ...")
...
    m = CHAPTER_RE.match("Chapter-II 29")        # grammar.py's own _demo
```

The other two are private copies, and both spell the separator `\s+`:

```python
# packages/legal_ingest/builder.py          -- the parser's cut
_STRUCTURAL_RE = re.compile(
    r"^(CHAPTER\s+[IVXLC0-9]+|PART\s+[IVXLC0-9]+[A-Z]{0,2}|Division\s+...)$")

# tools/suite/invariants/_common.py         -- the invariant that reports a missed cut
_STRUCT_LINE = re.compile(
    r"^(CHAPTER\s+[IVXLC0-9]+|PART\s+[IVXLC0-9]+[A-Z]{0,2}|DIVISION\s+...)$")
```

So the Sales Tax Act's `Chapter-II` was not a boundary. Nine chapter headings per
edition were swallowed into the preceding section's body — and
`no_structural_heading_in_body`, the invariant whose entire job is to find a
structural heading sitting in a body, reported **zero**, because it carried the
same narrow spelling.

Round 1's chapter numeral again: *the body scan, the tree and the invariant were
each reading one line differently.* Round 12's heading stripper again: *two
normalisers disagreeing about one spelling.* Third time, same shape.

The whole-line anchor (`^…$`) is why cross-references were never at risk —
`Chapter-V of this Act;` has never matched and still does not. Verified corpus-wide.

## Measured, invariant fix alone, on identical JSON

No re-conversion, `_STRUCT_LINE` widened and nothing else:

| lane | before | after |
|---|---|---|
| acts | 20 | **191** (`no_structural_heading_in_body` 0 → 171, 19 documents) |
| rules | 9 | **13** (0 → 4, 2 documents) |
| ordinance | 5 | **5** (0 → 0) |

Nineteen Sales Tax Act editions carry exactly nine each — `Chapter-II` through
`Chapter-X`, the entire chapter structure below CHAPTER I. The rules hits are
`94[CHAPTER-XXX`, `128[CHAPTER-XLI`, `150[CHAPTER- XLIII` (Customs Rules 2001)
and `CHAPTER - V` (Sales Tax Rules 2006). The ordinance zero is the point: the
Income Tax Ordinance prints `CHAPTER I` with a space, everywhere.

## The fix is two edits and they had to land together

`is_structural_boundary` does not stand alone. `discover` re-parses the line it
was just told about, with a **different** separator:

```python
core = re.sub(r"\s+", " ", _STRUCT_DECOR_RE.sub("", text)).strip()
kw = core.split()[0].upper()                            # "CHAPTER-II"
numeral = core.split(None, 1)[1] if " " in core else "" # ""
```

`"CHAPTER-II"` matches neither `"CHAPTER"` nor `"PART"`, so it falls through to
the `else:  # Division` branch and emits `Node(kind="division", code="Division ")`
— a nameless division that becomes `cur_division` and parents every following
section. Ten per edition. **Widening the boundary test alone reproduces round 1's
duplicate-container failure with certainty.**

`_split_container_heading` splits on `[\s\-]+` with `maxsplit=1`, which is what
keeps it a no-op on every line that already matched: the numeral's own suffix
separator stays in the numeral.

| line | before | after |
|---|---|---|
| `CHAPTER II` | `("CHAPTER", "II")` | `("CHAPTER", "II")` |
| `CHAPTER XVI-A` | `("CHAPTER", "XVI-A")` | `("CHAPTER", "XVI-A")` |
| `Division III A` | `("DIVISION", "III A")` | `("DIVISION", "III A")` |
| `Chapter-II` | `("CHAPTER-II", "")` → **Division** | `("CHAPTER", "II")` |
| `CHAPTER - V` | `("CHAPTER", "- V")` → code `CHAPTER - V` | `("CHAPTER", "V")` |

The cheapest witness that edit 2 landed is the run log. The three body-driven
editions used to log `body-driven structure: 0 chapters` and then have
`insert_missing_body_chapters` fill 10. They now log:

```
[acts] body-driven structure: 10 chapters, 127 sections
```

with no insert pass at all. `chapters_count` is 10 either way, so nothing in the
output would have said which mechanism produced it.

## Measured, after re-conversion

**21 documents, 2 lanes. Zero structural change anywhere.**

| | acts | rules |
|---|---|---|
| documents converted | 19/19 | 2/2 |
| refused | **0** | 0 |
| `sections_count`, `chapters_count`, `schedules_count` | unchanged | unchanged |
| leaf-code sets, container sets | **identical** | **identical** |
| text moved out of section bodies | −5,758 leaf, −432 preamble | −217 |
| conservation, body and footnotes | **19/19 at 100.000%, 0 missing** | see below |

`no_structural_heading_in_body` 175 → **0**. Register **34 → 34**.

### Three things that only running it found

**1. The conservation audit read a canonicalisation as a loss.** The first audit
came back 18/19, with `Sales Tax Act, 1990 (Finance (Amendment) Ordinance, 2009)`
at 99.975% and six missing words, all of them the single token `Chapter`.

No text left the document. A boundary line is furniture: the tree represents it
as a node, and `audit_completeness.output_text` counts that node's `code`
precisely so the words net out. They net out only where the source also prints
the keyword in **upper case**. The Sales Tax Act prints `Chapter-II`; `discover`
mints `code="CHAPTER II"`; the audit's word multiset is case-sensitive. Once
those lines became boundaries, the canonicalisation showed up as a deficit — 6
tokens on the 2009 edition, 1–2 on ten of its siblings.

Folded on both sides, and only for `CHAPTER`/`PART`/`DIVISION`/`SCHEDULE`. The
hole that leaves is narrow and worth naming rather than burying: a title-case
`Chapter` dropped from **prose** is now masked by a node code — which is the same
tolerance the audit already had for the upper-case spelling. Re-run: **19/19 at
100.000%, 0 missing.**

**2. One document loses 32 words, and it is the Phase 5 compilation.**
`Customs Rules, 2001` goes 74.101% → 74.087%. The tokens are the captions
themselves — `CHAPTER XXX`, `CHAPTER XLI`, `CHAPTER XLIII`, `CHAPTER XLIV` and
their titles (`PAKISTAN TRANSIT TRADE … UZBEKISTAN`, `APPEALS AND ALLIED
MATTERS`, `Export Processing Zones`). They used to sit in a section body; they
are now cut out as boundaries, and **that document's tree does not hold those
four chapters**, so they land nowhere. It also *recovers* 7 tokens.

This is not a new class. Customs Rules 2001 is 44 separately-notified S.R.O. rule
sets behind one index, its tree holds 41 chapters and 62 sections of a 563-page
document, and it is already missing 62,519 words to exactly that defect —
`tools/suite/exemptions/rules.json` carries four entries naming Phase 5. The
+32 is inside a known 62,519, on the one document in the corpus whose containers
are known not to be expressible. Reported rather than netted into a total.

It is also the second measurement arguing for the same guard as the PART case
below, which is what makes that guard worth building.

**3. The Sales Tax Act 2014's preamble was nothing but the leak.** Eighteen of
the nineteen editions end their preamble
`…It is hereby enacted as follows:-\n4[Chapter-I\nPRELIMINARY` — the chapter's own
code and caption, emitted a second time. Cutting there is the fix, and it is the
−24 characters per edition above. On `The Sales Tax Act, 1990 amended up to July
01, 2014` the preamble was **24 characters and was only the leak**, so the node
is now absent entirely. `inv_preamble_present` stays green: it falls back to
scanning the first leaf for `WHEREAS` / `IT IS HEREBY ENACTED`, and that
edition's leaf 1 carries neither. Its recital sits outside the body scan range —
a pre-existing, separate defect that this round makes visible rather than causes.

## What was measured and deliberately not shipped

**PART and Division stay on `\s+`. 14 real boundaries against 6 losses, and the
6 are the dangerous kind.** Both are annexure FORMS:

- `Customs Rules, 2001` leaf 34 — `PART – II` (en dash), `PART-II`…`PART-V`, a
  permission form whose item counter **8, 9, 10, 11 runs across the parts**. That
  document has zero `parts` on all 44 chapters, and the en-dash first part would
  not match at all, so the cut would land mid-form.
- `Sales Tax Rules, 2006 (01-01-2025)` leaf 165 — form **STR-11**,
  `[See rule 18(2)]`, `PART-I` and `376[PART-II`.

An exemption is the wrong tool by construction: it silences the *invariant* while
`_build_one` still cuts the form and hands parts II–V to the next rule. Text stays
conserved at 100.000% and is silently misplaced, and the hits disappear — **the
change would report itself as a success.** Nothing in the suite catches a form
sliced into the next rule.

**The CHAPTER letter suffix. 57 further hits across 24 documents, all real.**
`_STRUCTURAL_RE`'s CHAPTER branch has no suffix class at all, where the PART and
Division branches beside it both carry `[A-Z]{0,2}`. So `CHAPTER XVI-A` is not a
boundary either: it sits in section 155's body in **twenty Customs Act editions**,
alongside `CHAPTER XIX-A` in 196J, and the whole `XIV-A`…`XIV-D` / `V-A`…`V-C` /
`VIII-A` / `X-A` / `XVII-A` / `XVII-B` family of Sales Tax Rules 2006 — the exact
set `grammar.py`'s own comment records as falling through unclassified.

Held out because it doubles the re-conversion from 21 documents to 44, and twenty
of those are the Customs editions whose chapter tree rounds 1 and 6 rebuilt. That
interaction earns its own conservation run, not a ride on this one. Pinned in
`test_structural_boundary_agrees_with_grammar.py::test_the_letter_suffixed_chapter_gap_is_still_open`,
which asserts the current WRONG answer and therefore fails the moment the widening
lands — the number then moves in the same PR that moved it.

**Delegating to `grammar` outright.** Measured over 639,722 body lines:
delegation gains 347 lines where the current spelling gains 78, but **32 of the
additions are false positives** — `Chapter VII of`, `Part V of`, `Chapter X or`,
`Division III of` (28, ordinance) and `chapter 87 35` (4, acts). `grammar.ROMAN`'s
suffix class `[A-Z]{1,3}` under `re.IGNORECASE` eats the lowercase words
`of`/`or`/`for`. The grammar patterns are tuned for **contents rows**; this test
runs on **body prose**. Revisit when `ROMAN`'s suffix becomes `(?-i:[A-Z]{1,3})`.

**`fbr_ingest`.** Its `discover.py` carries the identical broken split and its
`builder.py` the identical narrow regex, imported from its own fork. Measured:
the widened `_STRUCT_LINE` finds **zero** additional hits across all 12 ordinance
documents. Re-converting the largest documents in the corpus for a measured no-op
is what the handover says to report rather than ship. Both dormant copies are
carried in `wip/tasks.md`, gated on the Phase 4b fork decision.

## Why the register does not move, and what the 3 hits I expected turned out to be

The prediction was `no_chapter_caption_in_section_heading` 4 → 1, on the strength
of this leaf:

```
32AA  text     '6[32AA. ***]\nChapter-VII\nOFFENCES AND PENALTIES'
      heading  '*** Chapter-VII OFFENCES AND PENALTIES 33. Offences and penalties'
```

The **body is fixed** — `plain_text` is now exactly the omission `6[32AA. ***]`.
The heading is not, and it comes from somewhere else entirely:
`builder._find_heading_split` scans up to **four lines forward** for a heading
terminator. Line 0 (`6[32AA. ***]`) has none, so the scan walks through
`Chapter-VII` and `OFFENCES AND PENALTIES` and stops at line 3's
`33. Offences and penalties.–`, and `_multiline_heading` joins everything before
it.

**A fourth reader that does not stop at a boundary** — and its own docstring
already states the principle for the neighbouring case: *"The scan stops at a
grid-extracted TABLE, which can never be part of a heading — `discover` already
refuses to let one open a section or carry a structural heading, and this is the
same rule on the build side."* A structural heading can never be part of a
section heading by exactly that argument.

The obvious guard was measured and does not survive:

```python
if li and is_structural_boundary(seg[li].line.text()):
    return None
```

Sales Tax Act 30.06.2021 converts to **126 leaves instead of 127 — section 32AA
disappears.** With `split is None` the caller falls to the colon-dash branch,
that fails too, and no entry is created: an omitted section has no heading
terminator of its own, so refusing the borrowed one leaves nothing to open it
with. Fixing this needs an omission-aware fallback, not a guard. Round 14/15.

So the register holds at **34**, deliberately, with the defect class closed
corpus-wide and the invariant that can see it shipping at 0 in the same PR —
the same shape as round 12.

## Locked by

| lock | fails if you revert |
|---|---|
| `builder._demo` — 10 boundary lines, 7 non-boundaries, 4 PART forms held out | edit 1 |
| `legal_ingest.discover._demo` (new module self-check) — the (KEYWORD, numeral) split | edit 2, and `maxsplit=1` |
| `_common._demo_structural_line` — the pattern, **and** that the tariff exception's `split(" ")` must not learn about hyphens | edit 3 |
| `tools/tests/test_structural_boundary_agrees_with_grammar.py` (new) | all three, plus the deferred suffix gap |

Each verified by removing its fix, one at a time, with `__pycache__` cleared
between runs. The last file is the one that would have caught this twelve rounds
ago: three modules spelled one idea three ways and nothing compared them.

The `_common` docstring is corrected too. Its tariff-reference exception claimed
*"every genuine chapter boundary prints `CHAPTER`"* — the Sales Tax Act prints
`Chapter-II`, so that was false. The skip stays correct only because its
`split(" ")` cannot split a hyphen; widening it to match the pattern's own
separator silences 171 of these 175 hits. Now asserted rather than assumed.

## Verified

`pytest tools/tests` **81 passed, 1 skipped, 0 failed** ·
`test_register_snapshot.py --write` a byte no-op, register **34** ·
`ruff check` bare (CI's form, covers `packages/`) clean ·
`discover_corpus.py --check` **no drift** ·
`data/ocr_cache` **0 B** ·
`audit_all --family salestax` **19/19 within gate, all at 100.000%** ·
`output/_refused/` **no new entries**.

Converted from `.worktrees/r13` at a committed revision, so every re-converted
document carries a real `pipeline_revision` rather than a `-dirty` stamp.
