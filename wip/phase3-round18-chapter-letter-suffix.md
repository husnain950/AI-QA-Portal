# Phase 3, round 18 — the CHAPTER letter suffix

**PR #84.** Closes *Start here* row 1 (`handover/tasks.md` §3): the CHAPTER branch of
`builder._STRUCTURAL_RE` had no letter-suffix class where PART and Division beside it both
carry `[A-Z]{0,2}`, so a chapter added by amendment was not a boundary and its caption sat
in the preceding section's body.

**Register: 25 → PENDING.** The rise and the fall are reported separately below, because
this class is part wrong-invariant and part real defect and a single net total hides both.

## The ledger's prescribed fix was wrong, and the measurement it quoted was right

`handover/tasks.md` §3 step 1 says to "widen the CHAPTER branch's numeral to carry the same
suffix class as PART and Division" — that is, `[A-Z]{0,2}`. **Done literally, that finds 9
hits, not 57.**

`[A-Z]{0,2}` cannot cross a hyphen, and the suffix separator in this corpus usually *is* a
hyphen:

| form | count | `[A-Z]{0,2}` | measured fix |
|---|---|---|---|
| `CHAPTER XVI-A`, `CHAPTER XIV-BB`, `CHAPTER X-A` … | most | **no** | yes |
| `CHAPTER XIVA`, `CHAPTER VIB`, `CHAPTER VIIA` | few | yes | yes |
| `CHAPTER - VIAB` (spaced hyphen separator) | 1 | yes | yes |

The widening that reproduces the ledger's own number is `(?:-?[A-Z]{1,2})?` — fused or
hyphenated, **one or two letters, no spaced form**:

```
-  ^(CHAPTER[\s\-]+[IVXLC0-9]+|PART[\s\-]+…
+  ^(CHAPTER[\s\-]+[IVXLC0-9]+(?:-?[A-Z]{1,2})?|PART[\s\-]+…
```

Three things about that shape are load-bearing and were measured, not guessed:

- **No spaced suffix.** `grammar.ROMAN` allows `\s?-?[A-Z]{1,3}`, which under `IGNORECASE`
  eats the lowercase words *of / or / for* — the 28 ordinance false positives already
  recorded in `test_structural_boundary_agrees_with_grammar.py`. `Chapter VII of` and
  `Chapter X or` are refused only because a space cannot enter the suffix.
- **Two letters, not three.** The longest real suffix in the corpus is two (`AB`, `BB`,
  `AA`, `AC`, `AD`, `BA`). Three buys nothing and widens the `of/or/for` surface.
- **`{1,2}` not `{0,2}`.** `-?[A-Z]{0,2}` would also match a trailing bare hyphen
  (`CHAPTER XVI-`), which is not a form this corpus prints. Fail-closed.

## Grammar was already right — that is the whole disagreement

`grammar.CHAPTER_RE` has accepted every one of these since it was written; its `NUMERAL`
carries the suffix. The parser did not. Measured at this commit:

| line | `grammar.CHAPTER_RE` | parser, before | parser, after |
|---|---|---|---|
| `CHAPTER XVI-A` | **True** | False | **True** |
| `CHAPTER XIVA` | **True** | False | **True** |
| `CHAPTER - VIAB` | **True** | False | **True** |
| `Chapter IV-A` | **True** | False | **True** |
| `Chapter VII of` | True | **False** | **False** |
| `chapter 87 35` | True | **False** | **False** |

The last two rows are why the parser **must not delegate to the grammar**, only agree with
it on the suffixed forms. `test_grammar_is_the_authority_on_the_bare_chapter_form` makes
grammar the authority; this round makes the parser obey it on one more form.

## Two regexes were narrow, not one

The ledger names only `builder._STRUCTURAL_RE`. The suite's own `_STRUCT_LINE`
(`tools/suite/invariants/_common.py:447`) carries the identical narrow CHAPTER branch, and
`test_the_letter_suffixed_chapter_gap_is_still_open` asserted **both** answered False. So
both had to move, and that is what makes the register rise before it falls:
`no_structural_heading_in_body` — a class **round 13 closed at 0** — is the instrument that
sees this defect, and it could not see it while its own pattern was as narrow as the bug.

`_STRUCT_LINE`'s `PART\s+` spelling was deliberately left alone: widening it reports the
nine annexure-FORM part lines in the rules lane as defects.

Two sites needed **no** change, checked before touching them:

- `discover._split_container_heading` already keeps the suffix in the numeral
  (`maxsplit=1`, docstring: `"CHAPTER XVI-A" -> ("CHAPTER", "XVI-A")`). This is round 1's
  nameless-`Division` failure and it was already covered.
- `toc._chapter_numeral` only uppercases and Arabic→Roman, so `XIVA` and `XIV-A` stay
  **distinct** nodes — the "never match numerals by value" trap.

## Measurement A — the invariant alone, on identical JSON

Widen `_STRUCT_LINE`, re-run all three lanes against **unchanged** output:

| lane | before | after | delta |
|---|---|---|---|
| acts | 15 | **37** | +22 |
| rules | 5 | **40** | +35 |
| ordinance | 5 | 5 | 0 |
| **total** | **25** | **82** | **+57** |

Every one of the 57 is `no_structural_heading_in_body`, across **24 documents** — 20 Customs
Act editions and 4 rules editions. **That is the ledger's "57 hits / 24 documents",
reproduced exactly**, four rounds after it was measured, by the corrected pattern and not by
the prescribed one.

The ordinance lane does not move: it runs `packages/fbr_ingest`, whose dormant copy at
`builder.py:1395` was **not** touched (gated on P4-2, measured at zero additional hits).

## Scope — 24 documents, not the ledger's 44

The "44 documents, 20 of them Customs" in the ledger is a **round-13-era estimate** ("it
doubles the re-conversion from 21 documents to 44") made before round 13 shipped. Measured
at this commit the way rounds 15 and 17 measured theirs — which body lines actually flip
answer between the old and new pattern — the scope is:

| lane | documents | flipped lines |
|---|---|---|
| acts | 20 | 39 |
| rules | 4 | 41 |
| **total** | **24** | **80** |

The flipped-line set and the invariant-hit set are the **same 24 documents**, which is the
cross-check that the scope is right. 80 raw lines against 57 reported hits is
`inv_no_structural_heading_in_body`'s one-hit-per-leaf `break`, not a discrepancy.

Source files were resolved through `convert_all.py --list` rather than a `**/*.pdf` glob —
19 source files in this corpus carry no `.pdf` extension, and several of these Customs
editions also carry a **leading space** in the filename.

## Measurement B — the parser, after re-converting the 24

| lane | baseline | after A (invariant) | after B (parser + re-convert) |
|---|---|---|---|
| acts | 15 | 37 | **15** |
| rules | 5 | 40 | **5** |
| ordinance | 5 | 5 | **5** |
| **total** | **25** | **82** | **25** |

**Rise +57, fall −57, net zero.** The final run is identical to the baseline *class for
class and document for document* — diffed, not eyeballed — and
`no_structural_heading_in_body` is back to **0**, now enforced by a pattern as wide as the
defect instead of one as narrow as it. `register.json` therefore needed no regeneration,
which is the same outcome round 17 had and for the same reason.

**This is a round that moved the register by zero, on purpose.** Reporting it as such is the
standing rule; folding it into a total would misattribute the rounds that did move it.

## What actually changed — the line-level evidence

Conservation is *not* the evidence here (round 13's warning: slicing a form keeps text at
100.000%). This is:

| | before | after |
|---|---|---|
| swallowed suffixed-CHAPTER boundary lines, 24 documents | **80** | **0** |
| leaves | 7,088 | **7,088** (+0) |
| chapter nodes | 544 | **544** (+0) |
| duplicate chapter codes | 0 | **0** |
| words sitting in a body that belong to the tree | 756 | **0** |

**Nothing was gained or lost — it was un-duplicated.** Every one of these chapters was
*already* in the tree, off the contents page; the body was printing its caption a second
time. That is why leaves and chapter nodes are flat and only body words fall. It is the
safest shape this class of fix can have, and it is why no `section_carries_its_body` hit
moved: no section's *body* was ever missing, it had too much.

Conservation, `tools/acts/audit_completeness.py --pdf`, off run vs on run:

| document | off | on |
|---|---|---|
| Sales Tax Rules 2006 (01-01-2025) | 99.998% (1 word) | **99.998% (1 word)** |
| Sales Tax Rules 2006 (30-06-2025) | 100.000% | **100.000%** |
| Customs Act 1969 (30.06.2025) | 100.000% | **100.000%** |

Unchanged, as expected: `audit_completeness` counts container headings too, so a caption
moving from a body into the tree nets out exactly.

## Re-converted

**24 documents**, all at one revision (`e9d7e74cde01-dirty`): 20 Customs Act editions and
4 rules editions (both Sales Tax Rules 2006 editions, both STSP Rules 2007 editions).
Snapshots of what they overwrote are in `output/_pre_18/`.

## Locked by

- `tools/tests/test_suffixed_chapter_cuts_the_section.py` — **new**, 3 cases through
  `build_sections`, not through the predicate, per round 17's lesson. Verified to fail with
  the widening reverted and pass with it restored (`__pycache__` cleared between, per the
  standing trap).
- `tools/tests/test_structural_boundary_agrees_with_grammar.py` — the four gap lines moved
  from `KNOWN_GAP_SUFFIXED_CHAPTERS` into `BOUNDARIES`, as its own assertion message
  instructed. `test_parser_and_invariant_agree` also goes red without the fix.

`pytest tools/tests` → **98 passed, 1 skipped**, from a measured pre-round baseline of
**95 passed, 1 skipped**. (`handover/README.md` §4 and `tasks.md` step 8 both said **92**;
that number was stale before this round and is corrected in this PR.) `ruff check` bare
clean; `data/ocr_cache` still 0 B.

## Located and deliberately not fixed — the en-dash separator

The same scan turned up a **second** gap on the same line of code, and it is not the suffix:

| line | count | documents |
|---|---|---|
| `CHAPTER – VI` | 20 | 20 Customs Act editions |
| `CHAPTER – VII` | 20 | the same 20 |
| `CHAPTER – V` | 1 | Sales Tax Rules 2006 (30-06-2025) |
| `CHAPTER – VIAB` | 1 | Sales Tax Rules 2006 |
| **total** | **42** | **21** |

These are **real boundaries** — the next line is the caption (`DRAWBACK`, `ARRIVAL AND
DEPARTURE OF CONVEYANCE`, `REFUND`) — and `[\s\-]+` is ASCII, so none of them is one.

**It was left open on evidence, not for lack of time.** `grammar.CHAPTER_RE` rejects them
too: its own separator is `[\s\-]+`, and its `[–—]` branch reads an en dash as introducing a
same-line **title**, not as a separator. Round 18's whole argument is that the parser should
agree with the grammar; closing this one has to move the *grammar* first, and that is a
different decision on a regex three readers share. Round 17's finding that the en/em dash
widening "gains zero" was about **PART** and does **not** transfer — it was the container
guard that refused those, and the CHAPTER branch has no such guard.

Pinned as `KNOWN_GAP_ENDASH_CHAPTERS` in
`test_structural_boundary_agrees_with_grammar.py`, with a `test_the_en_dash_chapter_gap_is_still_open`
that fails the moment it is closed — the same discipline that made this round's row
impossible to lose.

## Rejected

- **`grammar.ROMAN`'s suffix class verbatim** (`\s?-?[A-Z]{1,3}`). Its spaced branch under
  `IGNORECASE` eats *of / or / for* — 28 ordinance false positives, already on record. The
  shipped class admits no space and at most two letters.
- **Delegating to `grammar.CHAPTER_RE`.** It also accepts `Chapter VII of` and
  `chapter 87 35`, which the parser must keep refusing.
- **Porting to `packages/fbr_ingest/builder.py:1395`.** Gated on P4-2 and measured at zero
  additional hits; the ordinance lane did not move in either measurement.
- **Widening `_STRUCT_LINE`'s `PART\s+` branch** while in that line. It is narrow
  deliberately — widening it reports the nine annexure-FORM part lines in the rules lane as
  defects.
