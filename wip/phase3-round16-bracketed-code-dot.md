# Phase 3 round 16 — the rule whose number was renamed inside the bracket

Four `section_carries_its_body` hits, two editions, **one printed shape**. The Sales Tax
Special Procedures Rules 2007 print rules 58U and 58V like this:

```
110[CHAPTER XIV
SPECIAL PROCEDURE FOR THE GOODS SPECIFIED IN S. NO. 13 OF THE
FIFTH SCHEDULE TO THE ACT
111[58U]. Application:--The provisions of this Chapter shall apply to
manufacturers of goods specified against S. No. 13 of the Fifth Schedule of
the Act.
112[58V]. Conditions and limitations for availing zero-rating facility:--(1)
```

with the footnotes that explain it:

```
111. Rule 59 re-named as Rule „58U‟ by Notification No. S.R.O. 188(I)/2015, dated 5th March, 2015 …
112. Rule 60 re-named as Rule „58V‟ by Notification No. S.R.O. 188(I)/2015, dated 5th March, 2015 …
```

S.R.O. 188(I)/2015 **renamed** rules 59 and 60 rather than inserting new ones, so the
amendment bracket wraps the *number* and closes before the terminating dot. Every other
inserted section in the same document prints the ordinary shape — bracket open, never
closed: `106[58S. Application.--`.

**Both source pages are correct.** No exemption was written, and none was needed.

## The defect was a misread, not a miss

`builder._candidate_code_raw` tries five patterns in order. On `111[58U].`:

| pattern | why it declines |
|---|---|
| `_DOTSUFFIX_RE` | wants a separator inside the code (`18.A`, `25 AA`); `58U` has none |
| `_DOTFORM_RE` | its mandatory `\.` sits exactly where the `]` is |
| `_BRACKETPAREN_RE` | wants a closing `)`, not `]` |
| `_BRACKETED_DOTLESS_RE` | **matches** — and wrongly |

`_BRACKETED_DOTLESS_RE` is `_HEAD + \[\s*(CODE)\s*["'‘“]?\s*[A-Z]`. `CODE` allows an empty
letter run, so the engine backtracks it to the digits and reads the suffix letter as the
title's opening capital. `111[58U].` returned the code **`58`** — a real rule of Chapter IX,
forty pages earlier.

So 58U and 58V bound to nothing, and the consequence cascaded one section further than the
invariant could see:

| leaf | what it actually held, before |
|---|---|
| `58U` | `58U. Application` — the TOC heading, 16 chars |
| `58V` | `58V. Conditions and limitations for availing zero-rating facility` — 65 chars |
| `58W` | **58U's and 58V's bodies**, 5,534 chars, carried across the chapter boundary |
| `58X` | chapter XV's third caption line, **plus 58W's and 58X's bodies** |

The carry is `build_sections`' structural-boundary rule (`builder.py:1980`): text between a
structural heading and the next matched section start is handed to that next section. With
chapter XIV holding no matched start at all, the next one was 58W.

## The fix

One pattern, tried after every pattern that already reads a shape correctly and before the
one that reads this shape wrongly:

```python
_BRACKETED_CODE_DOT_RE = re.compile(_HEAD + rf"\[\s*({CODE_SUFFIXED})\s*\]\s*\.")
```

Two guards, both measured:

* **both brackets are mandatory** — narrower than the `\[?` `_DOTFORM_RE` already allows.
* **the code must carry a letter suffix.** A bracket that wraps the code alone is a
  *renumbering*, and a section renumbered into an existing run always takes a suffix. This
  is the same requirement `_BRACKETPAREN_RE` above it already states.

## The measurement — 290,982 distinct lines, all 187 source files

Every PDF under `data/corpora/{acts,rules,ordinance}` was read with `pdfplumber` and its
text lines de-duplicated — **not** `output/*.json` `plain_text`, which collapses the spacing
the parser sees. Each candidate line was scored against `main`'s `_candidate_code`.

This took two passes. The first read 168 files and the second the **19 whose names carry no
`.pdf` extension**; the filter that missed them is written up under *Found, not fixed*.
The 19 contribute 52,572 lines and **zero** candidates, under every variant below.

| candidate | gained (line had no code) | changed (line had a different code) |
|---|---|---|
| bare `CODE`, both brackets | **1** | 12 |
| **`CODE_SUFFIXED`, both brackets — shipped** | **0** | **12** |
| `_DOTFORM_RE` with an optional `]` | 2 | 17 ¹ |

**The shipped form gains nothing and changes twelve lines, all twelve correct:**

```
'58'  -> '58U'   111[58U]. Application:--The provisions of this Chapter shall apply to
'58'  -> '58V'   112[58V]. Conditions and limitations for availing zero-rating facility:--(1)
'58'  -> '58U'   118[58U]. Application:--…                       (the 30th June 2015 edition)
'58'  -> '58V'   119[58V]. …
'19'  -> '19D'   [19D]. Application for initiation of Mutual Agreement Procedure (MAP).-
'19'  -> '19E'   1[19E]. Action by the Competent Authority of Pakistan on an application
'19'  -> '19F'   1[19F]. Form of application for initiation of MAP Proceedings.-
'19'  -> '19G'   1 [19G]. Form of Irrevocable Bank Guarantee.-
```
(and four more spellings of the same four Income Tax Rules lines).

¹ measured standalone rather than in position, so its 18A→18 / 83A→83 / 51DAP→51 rows are an
artefact of `_DOTSUFFIX_RE` not running first. Its `42].` gain is not: with `_OPEN`'s `\[?`
branch, a closing bracket becomes legal with no opening one.

## What was rejected

**Bare `CODE`.** It gains exactly one line in the whole corpus, and that line is a penalty
**table row serial**: Sales Tax 01.07.2014 prints `2[21].Where any person repeats an offence`
inside section 33's offences table, forty pages past section 21's own page. This is the
family `_BRACKETPAREN_RE`'s own comment records as having once cost the 2007 edition thirty
sections. The suffix requirement is what separates a renumbering from a serial.

**Widening `_DOTFORM_RE` with an optional `]`.** It reaches `discover.py` as well as the
builder, which is the tidier place for a root-cause fix — but `_OPEN` already makes the
*opening* bracket optional, so an optional closer lets a wrapped amendment quotation's own
`]` open a section (`42].`, measured). Keeping the bracket mandatory needs a two-branch
alternation, and `_DOTFORM_RE`'s single capture group is read positionally at
`discover.py:623`.

**Porting it to `packages/fbr_ingest`.** Its `_candidate_code` (`builder.py:1133`) has no
`_BRACKETED_DOTLESS_RE` at all, so the ordinance lane would *miss* this shape rather than
misread it — and no ordinance source file prints it. Unreachable and unneeded; the fork
itself stays [P4-2](../handover/plan.md#p4-2--decide-the-fbr_ingest-fork--a-routing-problem)'s
decision.

## What moved

| | before | after |
|---|---|---|
| register total | 29 | **25** |
| rules `section_carries_its_body` | 8 | **4** |
| `run_suite.py rules` | 9 | **5** |
| `run_suite.py acts` | 15 | 15 — **zero** |
| `run_suite.py ordinance` | 5 | 5 — **zero** |

Two documents re-converted, per file with an explicit `-o`. **0 failures, 0 refusals.**

| document | hits before | after |
|---|---|---|
| SALES TAX SPECIAL PROCEDURES RULES,, 2007 UPDATED UPTO 05.03.2015 | 2 | **0 — ALL PASS** |
| Sales Tax Special Procedures Rules, 2007 (amended up to 30th June 2015) | 2 | **0 — ALL PASS** |

**Leaf counts are unchanged** — 92 and 88. Sections changed nothing but their text; none was
gained or lost. That is the check round 13 failed (127 → 126).

The only text delta on either document is **83 characters**, and it is a deletion of exactly
this, whitespace-normalised:

```
 58U. Application 58V. Conditions and limitations for availing zero-rating facility
```

— the two placeholder headings the empty leaves used to carry. No body text moved in or out.

## Conservation, and why it could not have caught this

| | body | footnotes |
|---|---|---|
| 05.03.2015, before **and** after | 100.000% / 0 missing | 100.000% / 0 missing |
| 30th June 2015, before **and** after | 100.000% / 0 missing | 100.000% / 0 missing |

Byte-for-byte identical on both sides — because `audit_completeness.py` compares the source
words against the output as **multisets**. This defect never dropped a word; it filed 5,534
characters under the wrong leaf. **A conservation audit cannot see a placement error**, and
that is worth writing down: it passed at 100.000% for as long as the defect existed.

## Locked by

| lock | fails if you revert |
|---|---|
| `tools/tests/test_bracketed_code_dot.py` | 2 of its 6 tests — `111[58U].` returns `'58'` again |
| `tools/suite/cases/rules.json` — `stsp_58u_renamed_rule_carries_its_body_{111,118}` | rule 58U's `plain_text` loses `manufacturers of goods specified against S. No. 13` |
| `tools/suite/register.json` | the register, at 25 |

**Each verified against the pre-fix output, not asserted.** The new unit tests were written
first and run red on `main`'s builder; the two suite cases were run against
`output/_pre_16/` and both report *plain_text missing '…'*.

## Found, not fixed

**Chapter XV's third caption line still leaks into its first section.** Both editions print

```
113[CHAPTER XV
SPECIAL PROCEDURE FOR SALES TAX ON COTTONSEED OIL EXPELLED
BY OIL EXPELLING MILLS AND COMPOSITE UNITS
OF GINNING AND EXPELLING
58W. Application.— …
```

and rule 58W's text still opens `OF GINNING AND EXPELLING`. The structural-boundary carry in
`build_sections` steps over at most **two** consumed container-title lines (`pending = 2`);
this caption runs to three. **Pre-existing** — before this round the same string opened rule
58X — and no invariant sees it. It belongs with
[P3-4](../handover/plan.md#p3-4--the-container-code-guard), which is the container-title row.

**Six editions of Income Tax Rules 2002 print the same shape and are not in the corpus.**
Rules 19D–19G (the Mutual Agreement Procedure rules) print `[19D].`, `1[19E].`, `1[19F].`,
`1[19G].` in all six editions under `data/corpora/rules/Rules/Income Tax Rules, 2002/`, and
every one of them currently reads as rule **19**. This fix repairs them — but none has an
`output/*.json`, so converting them would push six new documents into the corpus and at the
portal. **Not converted, and they score zero here.** The rules lane converts 11 of 48.

**Nineteen source files have no `.pdf` extension, not two.** `handover/tasks.md` named
Customs Rules 2001 and The Finance (Supplementary) Act 2022. A walk of the three lanes for
this round's measurement counts **6 in acts, 12 in rules, 1 in ordinance** — five Customs
Act editions, four Sales Tax Rules 2006 editions, seven Recruitment Rules SROs, and the
Islamabad Capital Territory Ordinance among them. The first sweep here missed all 19,
because the obvious repair for a `**/*.pdf` glob —

```python
if name.lower().endswith(".pdf") or "." not in name: ...
```

— fails on exactly these names: the dot is in the *date*
(`Customs Act, 1969 as amended up to 30.06.2021`). The rule is corrected in
`handover/tasks.md`, with the trap named. The re-read of those 19 found **zero** candidate
lines, so no measurement here rests on it.

**`make convert-*` from a worktree silently runs the wrong interpreter.** `PYTHON` is set
only `ifneq (,$(wildcard $(ROOT)/.venv/bin/python))` and `ROOT` is the worktree, which has
no `.venv` — so it falls through to `python3` and dies on `ModuleNotFoundError: No module
named 'pdfplumber'`. Loud here, but the same `ROOT` powers `PYTHONPATH`, and *that* one
resolves correctly to the worktree's `packages/`. Also corrected in `handover/tasks.md`.

## Verified

`pytest tools/tests` **92 passed, 1 skipped** (86 + this round's 6; the skip is the
intentional one) · `pytest apps/api/backend/tests` **522 passed** ·
register regenerated to **25** in this PR · `ruff check` **bare** clean ·
`discover_corpus.py --check` **no drift** · `data/ocr_cache` **0 B** ·
2 documents re-converted, **0 failures** · conservation identical on both.

`run_tests_smoke.py` still exits non-zero — expected and pre-existing while the register is
non-zero (README §4).

The portal was not touched, so the web suite was not run.

## What this corrects in the handover

- `tasks.md` task 4 said *"one cause, two editions"*. **Correct** — and the same cause also
  reaches four rules in six unstaged editions of a third document, which the row did not
  predict.
- `plan.md` P3-1b is closed. The class `section_carries_its_body` is **21 → 17**: acts 8,
  rules 4, ordinance 5.
