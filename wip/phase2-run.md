# Phase 2, run — the text-layer half

Review page: <https://claude.ai/code/artifact/0ac61c36-ec91-40a5-a317-42b3642cd5b6>

Phase 2 as scoped in [`wip/tasks.md`](./tasks.md) is a ~5-hour OCR marathon: 2,456
image-backed pages across 61 documents, none of it banked (`data/ocr_cache` is 0 B).
**This run deliberately skips every one of them.** `convert_all.py --skip-scanned`
takes the exact per-page census — `scan_page_count`, every page, not the 8-page
sample — and converts only what needs no OCR, leaving the scans unconverted and
named.

What that buys, and what it costs, stated together:

- **Buys:** every text-layer document in all three lanes re-converted at one parser
  revision, and the amending instruments in the acts lane parsed as amending
  instruments for the first time.
- **Costs:** the ~61 scanned documents keep whatever revision last wrote them. The
  corpus is now at **two** parser revisions, and the register below is a
  mixed-revision measurement. That is the honest label; it is not a reason to
  distrust the numbers, because every document that moved is named.

`data/ocr_cache` is **still 0 B** after all three runs, which is the check that no
OCR was paid for by accident.

---

## The blocker that had to land first

`wip/phase2-findings.md` finding 1: `families.py` hardcoded `consolidated -> ACTS`,
and `convert.py` passed `profile=None`, which overrode the
`partial(pipeline.run, profile=RULES)` binding in `rules_ingest`. Every consolidated
rules document would have re-converted as an Act, across 12 fields of parsing
behaviour.

Fixed by making the family's profile an **override** rather than an answer:
`consolidated` names none and keeps whatever the lane bound; `amending` is the only
family that overrides anything. Refusal moved to a separate `Family.parseable`,
because `profile=None` had been carrying both meanings at once — and that conflation
is exactly why `consolidated` named `ACTS` in the first place: the only way to say
"parseable" was to name a profile, and there was only one to name.

Proof on a real PDF, not just in a test:

```
$ tools/convert.py rules "…/AML_CFT Sanction Rules, 2020.pdf" --profile auto
[rules] family consolidated (confidence 0.33) -> profile rules
…
instrument_kind = rules | notified_by = S.R.O. 950(I)/2020
```

`notified_by` is a RULES-only behaviour (`notifying_sro`). Under the old resolution
this document would have been parsed as an Act and lost it.

And the check that should have caught it now does. `discover_corpus --verify-lanes`
used to `continue` on `family == "consolidated"` — the family every rules document is
in. It now compares the **resolved** profile. Measured both ways:

| `--verify-lanes` | rules | ordinance | total |
|---|---|---|---|
| with the hardcode restored | **34 would parse as acts** | 22 would parse as acts | 129 of 190 |
| as fixed | 0 | 0 | 73 of 190 (Phase 0's number, unchanged) |

---

## rules — 11 of 48, and every one of them changed

| | before | after |
|---|---|---|
| documents in `output/*.json` | 11 | 11 |
| converted this run | — | 11 (+1 refused) |
| skipped, needs OCR | — | 36 (391 pages) |
| register hits | 90 / 6 docs | **96 / 6 docs** |

The one refusal is the Urdu edition, and it is refused **for a family reason**, which
is the gate this phase owed:

```
RuntimeError: refusing 'Asset Declaration (Procedure and Conditions) Rules, 2019
- S.R.O 578(I)_2019 - Urdu Version.pdf': urdu is not parseable (arabic_script)
```

Nothing was quarantined — `output/_refused/` is empty. Total run time 321 s.

**Zero new documents, and that is expected.** The 36 documents Phase 1's numpy fix
unblocked are *exactly* the scans this run skips. What the rules lane got instead is
its 11 documents at one revision — and all 11 changed:

| document | what moved |
|---|---|
| Customs Rules, 2001 (30.06.2023) | chapters **1 → 15**, sections 61 → 62 |
| Sales Tax Rules, 2006 (01-01-2025) | chapters 40 → 43 |
| Sales Tax Rules 2006 (30-06-2025) | chapters 33 → 37 |
| Federal Excise Rules 2005 (30.06.2015) | chapters 16 → 18 |
| Federal Excise Rule (10.07.2014) | chapters 16 → 17 |
| the other six | `metadata.family` added; body identical |

**None of that is the profile.** Control: the same PDF converted with
`--profile lane` at this revision is **byte-identical** to the `--profile auto`
output once the two additive family keys are removed. Every difference above is the
stale JSON catching up with the parser — which is the entire point of re-converting
at one revision, and it confirms `wip/phase2-findings.md` §8: zero rules documents
are amending, so `--profile auto` changes no routing on this lane at all.

### The register moved 90 → 96, and all six are new information

| invariant | before | after |
|---|---|---|
| `section_carries_its_body` | 78 (6) | 79 (6) |
| `no_foreign_section_start_in_body` | 10 (4) | 10 (4) |
| `no_chapter_caption_in_section_heading` | 2 (2) | **1 (1)** |
| `structure_counts` | — | **4 (2)** |
| `body_chapters_in_tree` | — | **2 (1)** |

The two new classes are not a regression. `inv_body_chapters_in_tree` reads
`metadata.body_chapter_numerals`, and its docstring says a document without that key
is a deliberate no-op "so old output does not fail the lane until it is reconverted".
The old rules JSON predates the key, so the invariant was **dormant**. Re-conversion
woke it up. Both new classes were triaged rather than just counted:

- **`structure_counts` (4) — real, and a genuine defect.** Sales Tax Rules 2006 puts
  `CHAPTER XIV-AB` (printed page 123), `XIV-AC` (123) and `XIV-AD` (125) *after*
  `XIV-B` (129), `XIV-C` (154) and `XIV-D` (158) in the tree. The invariant already
  forgives a numeral that goes backwards while the pages go forwards — the statute's
  own doing — so it is firing on the case it exists for: the tree assembled out of
  document order. **Phase 3.**
- **`body_chapters_in_tree` (2) — a false positive in the invariant.** Both sides of
  its comparison normalise differently: `_tree_chapter_numeral("CHAPTER VIA")` returns
  `'VI-A'` while `_norm_body_numeral("VIA")` returns `'VIA'`, so any chapter whose
  code carries an unhyphenated suffix is reported missing while sitting in the tree.
  `CHAPTER VIA` and `CHAPTER VIAB` are both present. **Phase 3, one line.**

---

## acts — 64 of 93, and the amending profile finally applied

| | before | after |
|---|---|---|
| documents in `output/*.json` | 80 | **78** |
| converted this run | — | 64 (+4 refused) |
| skipped, needs OCR | — | 25 (2,065 pages) |
| register hits | 148 / 27 docs | **109 / 26 docs** |

Run time 788 s. Of the 78 documents, 64 were rewritten this run and 14 were already
byte-identical at this revision.

### The payload, and what skipping OCR cost of it

Seven documents now carry `metadata.instrument_kind = "amending"` — the first time
any document in this corpus has been parsed as the amending instrument it is:

```
Anti-Money Laundering (Second Amendment) Act, 2020    Finance Act, 2019   (chapters 1 -> 9)
Anti-Terrorism (Third Amendment) Act, 2020            Finance Act, 2021
Finance Act 2024                                      The Tax Laws (Amendment) Act, 2024
Finance Act, 2018-19
```

Seven, not twenty-five. **Eighteen of the 25 amending instruments are blocked by a
handful of scanned pages** — and two of them by exactly one page each:

| document | OCR pages |
|---|---|
| Finance Act, 2022 (952 pages) | **1** |
| Finance Act, 2023 | **1** |
| Income Tax Amendment Act, 2016 | 1 |
| Income Tax (Second Amendment) Act, 2016 | 2 |
| The Tax Laws (Amendment) Act, 2023 | 6 |
| Finance Supplementary Act, 2023 | 9 |
| Income Tax (Third Amendment) Act, 2016 | 9 |
| …and 11 more, up to Finance Act 2017-18 at 683 |

Measured across both lanes there is a **cheap tail**: 35 documents need ≤ 10 OCR
pages each, 172 pages in total — roughly 15 minutes at the measured 0.2 pg/s, against
2,456 pages for the whole set. **Decided: not this round.** Every scanned document
stays unconverted, by instruction; the tail is recorded here and in `wip/tasks.md` so
it is a decision someone can take later rather than a fact nobody measured.

### Four refusals, and two of them are a real finding

| document | refusal |
|---|---|
| Custom Act 1969 …(Urdu Version) | `urdu is not parseable (arabic_script; full_translation)` |
| Table of content for Customs Act 1969-Urdu Version | `urdu is not parseable (arabic_script)` |
| **Sales Tax Act,1990 as amended up to 30.06.2020** | `TOC parse left 2 section(s) without a chapter container` |
| **The Sales Tax Act, 1990 (as amended up to 31st December, 2019)** | same |

The two Urdu editions never had JSON, so nothing was lost. The two Sales Tax Act
editions **did**, and their JSON is now in `output/_refused/` — which is why the acts
lane reads 78 and not 80.

**This is not the 80 → 78 that `wip/phase2-findings.md` finding 2 predicted.** That
one was about the two `no_text_layer` documents being refused before OCR, and it did
not happen: both are scans, so `--skip-scanned` never attempted them and their JSON is
untouched. These are two different documents and a different cause.

It is also **not** `--profile auto`. Both classify `consolidated` at confidence 1.0,
so they resolve to `ACTS` — the same profile the lane binds. Control: converting one
with `--profile lane` at this revision raises the identical error. **The current
parser cannot convert two Sales Tax Act editions that are shipping in the corpus
today**, and the JSON on disk was written by an older revision that could. The
quarantine is correct behaviour — `output/*.json` must not contain output the parser
would refuse to produce (ledger P08) — and the fix is Phase 3 work.

### The register moved 148 → 109

| invariant | before | after | |
|---|---|---|---|
| `no_footnote_text_in_body` | 109 (20) | **45 (20)** | −64 |
| `section_carries_its_body` | 26 (9) | 27 (10) | +1 |
| `no_foreign_section_start_in_body` | 9 (9) | 10 (10) | +1 |
| `no_chapter_caption_in_section_heading` | 3 (3) | **1 (1)** | −2 |
| `clause_codes_plausible` | 1 (1) | 1 (1) | — |
| `body_chapters_in_tree` | — | **19 (19)** | new |
| `section_codes_ordered` | — | **6 (4)** | new |

`no_footnote_text_in_body` losing 64 of its 109 hits is the single largest movement in
the register, and it is pure staleness: those 20 documents were carrying output written
before the footnote-binding fixes already merged to `main`. Nothing was fixed this
round; the corpus caught up with the parser.

**All 19 `body_chapters_in_tree` hits are one defect with one cause**, and it is worth
stating precisely because it also explains why every Customs edition gained a chapter
(22 → 23):

```
tree chapter codes: ['CHAPTER 1', 'CHAPTER I', 'CHAPTER II', ...]
                      ^^^^^^^^^ code 'CHAPTER 1', heading 'PRELIMINARY', 0 sections
                                  duplicate of 'CHAPTER I', heading 'PRELIMINARY', 2 sections
```

`insert_missing_body_chapters` reads a body line printing the numeral as an Arabic
`1` and, finding no roman `I` match, inserts a **second, empty** PRELIMINARY chapter.
The invariant that reports it cannot see it either: `_tree_chapter_numeral` returns
`None` for a non-roman numeral and drops it from the set it compares against. One
normalisation, 19 documents, 19 spurious chapters. **Phase 3.**

---

## ordinance — 9 of 46, no new documents, and a naming collision resolved

Best-effort, at the lane profile: `fbr_ingest.run` takes no profile, so
`--profile auto` is refused up front by Phase 1's guard and was not attempted.

| | before | after |
|---|---|---|
| documents in `output/*.json` | 12 | **12** |
| converted this run | — | 9 (+10 refused) |
| skipped, needs OCR | — | 27 |
| register hits | 5 / 4 docs | **5 / 4 docs** |

**Ten refusals, nine of them the same one Phase 0 measured**, word for word:

```
RuntimeError: TOC parse left 3 section(s) without a chapter container (1, 2, 3...)
```

All nine are ICT (Tax on Services) Ordinance editions — flat, TOC-less documents that
`fbr_ingest` has no body-driven fallback for, and which `legal_ingest` converts. The
tenth is `Tax Laws (Amendment) Ordinance, 2025`, an amending instrument this pipeline
cannot express. **This is the Phase 4 decision, measured again rather than argued**:
until `fbr_ingest` is merged or replaced, 10 of this lane's 19 text-layer documents
cannot convert at all. None of the ten had prior JSON, so nothing was quarantined.

### The duplicate the naming rule would have created

Not one of the 12 ordinance JSONs on disk was named what `convert_all.out_path` would
name it — they are hand-normalised (`Income Tax Ordinance 2001 - amended upto
04.05.2024.json`) against a source of `Income Tax Ordinance, 2001 Amended upto
04.05.2024.pdf`. Their `metadata.filename` matches the staged PDFs, so they are the
same editions under a second naming rule, and converting the lane produced **21 files
for 12 editions**.

Resolved after the run rather than before, so a failed conversion could not cost an
edition: for each old name, the new JSON with the same `metadata.filename` was
compared, and only then was the old one removed — every one of them still banked in
`output/_pre_phase2/`. Nine pairs matched and were retired; three old files have no
re-converted twin (their PDFs are scans) and were kept.

The nine pairs are **structurally identical** — same sections, chapters and schedules
in all nine, down to the count. They differ in `metadata.source_kind` (a new key) and
in the HTML of 20 leaves out of 466. The ordinance pipeline has barely moved since
those files were written, which is the control this lane still provides.

---

## The register, all three lanes

**210 hits across 36 of 101 converted editions**, down from 243 across 37 of 103.

| Invariant | acts | rules | ordinance | total |
|---|---|---|---|---|
| `section_carries_its_body` | 27 (10) | 79 (6) | 5 (4) | 111 |
| `no_footnote_text_in_body` | 45 (20) | — | — | 45 |
| `body_chapters_in_tree` | 19 (19) | 2 (1) | — | 21 |
| `no_foreign_section_start_in_body` | 10 (10) | 10 (4) | — | 20 |
| `section_codes_ordered` | 6 (4) | — | — | 6 |
| `structure_counts` | — | 4 (2) | — | 4 |
| `no_chapter_caption_in_section_heading` | 1 (1) | 1 (1) | — | 2 |
| `clause_codes_plausible` | 1 (1) | — | — | 1 |
| **per lane** | **109 / 26 docs** | **96 / 6 docs** | **5 / 4 docs** | **210** |

Read it with two labels attached:

1. **It is a mixed-revision measurement.** 61 scanned documents keep whatever revision
   last wrote them. Every document that moved is named above.
2. **Three of its eight classes did not exist in the last register.** They are not new
   defects; `body_chapters_in_tree` is explicitly a no-op on JSON without
   `metadata.body_chapter_numerals`, so it was **dormant** on stale output and woke up
   on re-conversion. That is the argument for re-converting at one revision, stated as
   a number: 31 hits the previous register could not see.

## Gates

| gate | result |
|---|---|
| `discover_corpus.py --check` | **no drift** — as finding 3 predicted, OCR never writes back into a PDF |
| `discover_corpus.py --verify-lanes` | **73 of 190**, unchanged from Phase 0; **0 rules documents** route wrongly |
| `data/ocr_cache` | **0 B** — no OCR was paid for by accident |
| every source document converts or is refused with a reason | yes; **no refusal is an `ImportError`** |
| `pytest tools/tests` | 53 passed, 1 skipped |
| package self-checks | 11 pass |
| rollback | `output/_pre_phase2/` on all three lanes, 103 files |

`make test-pipeline` is still red, and honestly so: it runs the three lane suites, and
the register is open. That is Phase 3's job, not a break.

## What Phase 2 still owes

- **The 61 scanned documents, 2,456 OCR pages.** Including the cheap tail: 35
  documents at ≤ 10 pages each, 172 pages, ~15 minutes — Finance Acts 2022 and 2023
  are one page each.
- **`--admit-below-floor`** for the 9 provisional acts documents. All are scans, so
  the pass is meaningless until OCR runs.
- **The ordinance lane's other 10 text-layer documents**, which need the Phase 4
  `fbr_ingest` decision, not a re-run.

## What this run opened for Phase 3

1. **Two Sales Tax Act editions the current parser refuses** (`TOC parse left 2
   section(s) without a chapter container`). Costs the corpus two documents today.
2. **`body_chapters_in_tree`, 21 hits, two distinct causes.** Acts (19): a spurious
   empty `CHAPTER 1` inserted beside `CHAPTER I`, Arabic against roman. Rules (2): a
   false positive — `_tree_chapter_numeral("CHAPTER VIA")` gives `VI-A` while
   `_norm_body_numeral("VIA")` gives `VIA`, so the two sides of one comparison
   disagree.
3. **`structure_counts`, 4 hits.** Sales Tax Rules 2006 places `CHAPTER XIV-AB`
   (printed page 123), `XIV-AC` (123) and `XIV-AD` (125) after `XIV-B` (129), `XIV-C`
   (154) and `XIV-D` (158). The invariant already forgives a numeral that goes
   backwards while the pages go forwards, so it is firing on exactly what it is for.
4. **`section_codes_ordered`, 6 hits on 4 acts editions** — never triaged.
5. The standing register: `section_carries_its_body` (111), `no_footnote_text_in_body`
   (45), `no_foreign_section_start_in_body` (20).

### And one hypothesis this run falsified

`wip/plan.md` and `wip/tasks.md` both argue that
`no_foreign_section_start_in_body` is "the literal signature of an amending instrument
parsed as a consolidated one" and that Phase 2 might close those hits with no parser
change. **Measured, it does not.** The seven amending instruments that converted this
round are *clean* on that invariant — clean on everything, in fact, except one
`clause_codes_plausible` hit on Finance Act 2024. All ten acts hits sit in
**consolidated** statutes: seven Customs Act editions (2019 through 2025, one hit each,
almost certainly one recurring cause) and three Sales Tax Act editions.

The hypothesis is not disproved for the 18 amending instruments still behind OCR. But
it can no longer be the reason to schedule this invariant first, and Phase 3 should
treat it as an ordinary defect in the consolidated lane.
