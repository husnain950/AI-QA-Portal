# Remediation tasks

Executable checklist for [`wip/plan.md`](./plan.md). Dependency order — do not start a
phase until the one above it passes its gate.

Baseline: `main` at `942db87` (PR #45). Every count below was measured on 2026-08-29
with `python tools/run_suite.py <lane>` and `python tools/discover_corpus.py` against
the corpus staged on this machine — the Phase 3 register **after** the Phase 2 run.

Rules of engagement, unchanged:
- Never commit to `main`. One branch and one PR per phase.
- Every parser fix ships with its locking case or invariant **in the same PR**.
- An anomaly is closed only when it is **fixed** or **exempted with traced evidence**.
  There is no third state; "tracked and deferred" without an exemption entry is a red gate.
- Re-measure after every phase. Numbers here are a snapshot, not a promise.

---

## Phase 0 — structure discovery — **DONE**
Branch: `feat/phase0-structure-discovery`

- [x] Stage the full inventory — `tools/stage_corpus.py --from "<FBR repo root>"`
      — 33 documents copied, **190 staged**, 26 of them the Ordinance documents that
        had never been staged at all
- [x] `packages/legal_ingest/signature.py` — text-only structural measurement, 20 fields
- [x] `packages/legal_ingest/families.py` — 5 ordered families, confidence, group inheritance
- [x] `packages/legal_ingest/profiles.py` — `AMENDING`, and the docstring claiming Acts
      and Rules are "the same family of document" corrected
- [x] `packages/legal_ingest/discover.py` — `_front_matter_container`; profile-supplied
      `is_amendment`
- [x] `packages/legal_ingest/pipeline.py` — `profile=None` → classify; `metadata.family`
      / `family_confidence` / `amends`; `type` + `node_key` on every node
- [x] `tools/convert.py --profile auto`
- [x] `tools/discovery/{signatures.json, report.md, unexplained.json}` committed
- [x] `tools/run_tests_smoke.py` runs `discover_corpus --check` (SKIP with no corpus)

**Gate — all met:**
`discover_corpus --assert` → 190 documents, 0 problems ·
`--check` → no drift ·
`--reconcile` → every inventory document is staged ·
13 package self-checks pass ·
`ruff check tools/ apps/api packages/legal_ingest/{signature,families,pipeline,profiles,discover}.py` clean ·
all three lane suites measure **exactly** their `HEAD` numbers (verified by stashing the diff)

### What discovery found

| family | n | parseable |
|---|---|---|
| consolidated | 117 | yes |
| amending | 36 | yes — **new** |
| no_text_layer | 30 | no |
| urdu | 4 | no |
| unconvertible | 3 | no |
| **unexplained** | **0** | — |

- 58 document groups; **5 span more than one family**
- 9 scans placed by group inheritance (only where every measured edition agrees)
- 29 parseable documents flagged low-confidence — they parse, and they are listed
- **73 of 190 documents route differently** under `--profile auto`: 36 amending
  (25 acts + 11 ordinance), 37 refused rather than mis-parsed

---

## Phase 1 — rebuild the toolchain — **DONE**
Branch: `fix/local-stack-and-toolchain`

- [x] Rebuild `.venv` on the pinned interpreter — **3.14.7 → 3.12.13**
      (`/opt/homebrew/bin/python3.12`), the version `pyproject.toml` pins and
      CI and the container already run
- [x] Install pipeline + OCR extras — 58 packages
      — **every OCR pin resolved unchanged on cp312**: `numpy 2.5.1`,
        `onnxruntime 1.28.0`, `rapidocr-onnxruntime 1.2.3`, `opencv-python 5.0.0.93`,
        `pyclipper 1.4.0`, `shapely 2.1.2`. Nothing had to move, so no re-pin and no
        `ocr_review.py` run was owed
- [x] `packages/legal_ingest/requirements-ocr.txt` header corrected — the pins said
      they were measured on Python 3.13; they are now measured on the 3.12 that
      everything else runs
- [x] `tools/convert_all.py --profile {lane,auto}` — see *What Phase 1 also had to fix*
- [ ] Rebuild api/worker images — **not attempted, and not needed this round.** The
      Docker daemon is down on this host; nothing in Phase 1 or Phase 2 needs the
      containers. Left for whenever the portal side resumes.

**Gate:**
`.venv/bin/python --version` → **3.12.13** ·
`import numpy, onnxruntime, rapidocr_onnxruntime` clean ·
`tesseract --version` still **5.5.2 / leptonica 1.87.0**, `pdftotext 26.08.0` ·
`tools/discover_corpus.py --check` → **no drift** across the interpreter change ·
all three lane suites re-measured at **exactly** their pre-rebuild numbers —
acts **148**, rules **90**, ordinance **5** ·
`ruff check apps/api tools` clean ·
`pytest tools/tests` → **48 passed** (46 + the 2 new)

**Two things the gate could not clear, both pre-existing and both recorded rather
than papered over:**

- `make test-api` cannot run here: the Docker daemon is down, so all 445 errors are
  the same `connection to server at "127.0.0.1", port 5432 ... Connection refused`.
  Not a rebuild regression — no test failed for a code reason.
- `tools/tests/test_heading_leak_class.py::test_scan_heading_leaks_skips_without_corpus`
  asserts `main(["acts"]) == 0`, which is only true **where the corpus is absent**.
  With the corpus staged, `scan_heading_leaks` correctly finds 144 hits across 80
  files and returns non-zero, so the test fails. It is green on CI and red on any
  developer machine that actually has the corpus — the exact inversion this project
  already knows about. Fixing it is not Phase 1's job; it is logged here so the next
  person does not read it as a rebuild break.

### What Phase 1 also had to fix

Phase 2 was unrunnable as written, and one of the two reasons could have destroyed
data.

- **`tools/convert_all.py` had no `--profile`.** It hardcoded the child command
  (`convert.py <lane> <pdf> -o <dest>`), and it is the only practical way to convert
  168 source files. `--profile auto` existed on `tools/convert.py` only, which
  converts one PDF. **Fixed:** the flag is threaded through `convert()` the same way
  `--admit-below-floor` already was.
- **`--profile auto` on the `ordinance` lane would have emptied it.** That lane maps
  to `fbr_ingest`, whose `run` takes no profile, so `convert.py` exits 2 on each of
  its 45 files. That is not an `_is_env_failure`, so `_quarantine` would have moved
  **all 12 existing ordinance JSONs** out of `output/` — a flag typo costing a lane.
  **Fixed:** one guard in `main()`, before any file is touched, asking the pipeline
  the same question `convert.py` asks. Locked by
  `tools/tests/test_convert_all_profile.py`, which fails if either half is removed.

Nothing was converted this round, by decision. `data/corpora/` is byte-identical.

---

## Phase 2 — re-convert the lanes that can take a profile — **DONE for the text-layer half**
Branch: `fix/phase2-reconvert-text-layer`

Run and findings: [`wip/phase2-run.md`](./phase2-run.md).

**Scope taken, by instruction: every document that needs no OCR, in all three lanes.**
The 61 scanned documents (2,456 pages, `data/ocr_cache` still 0 B) were skipped with
`convert_all.py --skip-scanned`, which uses the exact per-page census rather than the
8-page sample. The corpus is therefore at **two** parser revisions and the register
below is a mixed-revision measurement.

- [x] **Fix `--profile auto` before paying for any OCR.** `families.py` hardcoded
      `consolidated → ACTS`; the family's profile is now an OVERRIDE and only
      `amending` names one, so the lane's binding survives. Refusal moved to
      `Family.parseable`, which is what `profile=None` had been doubling as. Locked by
      `tools/tests/test_profile_auto_resolves_the_lane.py`, which asserts the
      resolution over every record in the committed `signatures.json` — no corpus
      needed, so it runs on CI.
- [x] **Widen `do_verify_lanes`** — compares the RESOLVED profile now. With the
      hardcode restored it reports 34 rules + 22 ordinance documents routing
      differently; fixed, 73 of 190, unchanged from Phase 0.
- [x] **Back up the JSON, not the database.** 103 files snapshotted to
      `output/_pre_phase2/` on all three lanes before anything ran.
- [x] **Rules** — `convert_all.py rules --profile auto --skip-scanned`. 11 converted,
      1 refused (the Urdu edition, for a family reason). Zero new documents: the 36
      the numpy fix unblocked are exactly the scans this run skips. All 11 changed —
      Customs Rules 2001 went 1 → 15 chapters — and none of it is the profile:
      `--profile lane` at this revision is byte-identical bar the two family keys.
- [x] **Acts** — `convert_all.py acts --profile auto --skip-scanned`. 64 converted,
      4 refused, 80 → **78**. Seven amending instruments now carry
      `instrument_kind="amending"`; 18 more are behind OCR, two of them behind a
      single page each.
- [x] **Ordinance, best-effort** at the lane profile (it takes no profile at all).
      9 converted, 10 refused — 9 of those the ICT editions with the exact refusal
      Phase 0 measured. No new documents. The 9 hand-named duplicates the run created
      were retired against `metadata.filename` after the run, never before.
- [x] `discover_corpus.py --write` not needed: `--check` reports **no drift**, which
      is what finding 3 predicted (OCR never writes back into a PDF, and no OCR ran).
- [x] Re-measured all three suites; the register below is rewritten from that run.

**Gate — met:** `--profile auto` resolves RULES for a rules document, locked by a test ·
every source document either converts or is refused with a reason, and **no refusal
reason is an `ImportError`** · `signatures.json` diff empty · `--check` clean ·
`data/ocr_cache` 0 B.

**Not met, and named rather than hidden:** the acts lane lost two documents. Not the
80 → 78 finding 2 predicted — those two `no_text_layer` documents are scans and were
never attempted — but `Sales Tax Act,1990 as amended up to 30.06.2020` and
`The Sales Tax Act, 1990 (as amended up to 31st December, 2019)`, which the CURRENT
parser refuses (`TOC parse left 2 section(s) without a chapter container`) and an older
one converted. Controlled: `--profile lane` raises the identical error, so this is
parser drift, not the profile. Phase 3 item.

### What Phase 2 still owes — the OCR half

- [ ] **61 scanned documents, 2,456 OCR pages.** There is a cheap tail worth deciding
      on rather than inheriting: **35 documents need ≤ 10 pages each, 172 pages
      total** (~15 min at the measured 0.2 pg/s), including Finance Act 2022 and 2023
      at **one page each**. At ≤ 30 pages it is 50 documents / 504 pages. The
      remainder is the marathon: Finance Act 2017-18 (683), 2025 (290), 2015 (236),
      2016-17 (215), 2014 (148), 2020 (140).
- [ ] **Rebuild the 9 provisional acts documents** with `--admit-below-floor`. All are
      scans; the pass means nothing until OCR runs.
- [ ] The **ordinance lane's other 10 text-layer documents** need the Phase 4
      `fbr_ingest` decision, not a re-run.

---

## Phase 3 — the anomaly register
Branch: one per invariant class

**32 hits across 103 converted editions**, re-measured 2026-09-02 after round 14.
210 → 193 → 148 → 92 → 78 → 75 → 70 → 64 → 50 → 44 → 33 → 30 → 30 → **34** → 34 → 32.
Documents held: acts 80, rules 11, ordinance 12.

The +4 arrived with a new question, not a regression: PR #74 added
`preamble_carries_no_toc_tail` and it fires on four Customs Act editions that print the
tail of their Contents page in front of the enacting formula. #74 also took the ordinance
lane onto the output contract (12/12 `contract_version`, 6,941 nodes typed and keyed,
corpus identity hole 5,047 leaves → 89) and #75 closed the portal half of the same defect,
so `is_junk_leaf` no longer deletes those four preambles. Rounds 12 and 13 each moved the
register by zero and each closed a class no invariant could see.

Round 1: [`wip/phase3-chapter-numerals.md`](./phase3-chapter-numerals.md) — chapter
numerals, read the same way in the body scan, the tree and the invariant.
Round 2: [`wip/phase3-legal-reference.md`](./phase3-legal-reference.md) — the apparatus
caption, which was never in a body at all.
Round 3: [`wip/phase3-omissions-and-compilations.md`](./phase3-omissions-and-compilations.md)
— an unreadable glyph, and two documents that are not one instrument each.
Round 4: [`wip/phase3-split-codes.md`](./phase3-split-codes.md) — the text layer splits a
code, and a measured note that had gone out of date.
Round 5: [`wip/phase3-toc-furniture.md`](./phase3-toc-furniture.md) — the contents page's
own running title, read as a chapter.
Round 6: [`wip/phase3-chapter-order.md`](./phase3-chapter-order.md) — a part is not a
chapter, and a suffix is not a sum.
Round 7: [`wip/phase3-parenting-and-marker-runs.md`](./phase3-parenting-and-marker-runs.md)
— parented by where its code is printed, not by where it is.
Interlude: [`wip/phase3-gate-the-register.md`](./phase3-gate-the-register.md) — the register
is now committed and gated, and `make check` lints what CI lints.
Round 8: [`wip/phase3-omission-mirror.md`](./phase3-omission-mirror.md) — a repealed section
has nothing left to steal.
Round 9: [`wip/phase3-cursor-cascade.md`](./phase3-cursor-cascade.md) — one choice, seven
starved sections.
Round 10: [`wip/phase3-header-band.md`](./phase3-header-band.md) — a band measured from a
header that does not exist.
Round 11: [`wip/phase3-pageless-contents.md`](./phase3-pageless-contents.md) — 118 sections
the register could not see.
Round 12: [`wip/phase3-round12-body-heading-code.md`](./phase3-round12-body-heading-code.md)
— the argument the heading stripper never read.
Round 13: [`wip/phase3-round13-chapter-hyphen.md`](./phase3-round13-chapter-hyphen.md) —
the separator the private copy never learned.
Round 14: [`wip/phase3-round14-preamble-front-matter.md`](./phase3-round14-preamble-front-matter.md)
— the preamble that began on the contents page.

The pipeline→portal track ran separately and is closed:
[`wip/integration/plan.md`](./integration/plan.md) and
[`tasks.md`](./integration/tasks.md), PRs #59–#76.

**Picking this up cold?** [`wip/HANDOVER.md`](./HANDOVER.md) still has the **working
rules**, which are the part that has not aged (never edit `packages/` mid-conversion;
clear `__pycache__` after any mutate-and-restore; measure the invariant fix and the parser
fix separately; verify a lock by removing the fix; report fixes that moved the register by
zero). Its *numbers* are 23 PRs stale — it says 64 and lists 16 open items, both of which
predate rounds 8–13 and the whole integration track. This file and `plan.md` are current;
read those for state and HANDOVER §4 for method.

| Invariant | acts | rules | ordinance | total | was |
|---|---|---|---|---|---|
| `section_carries_its_body` | 8 (6) | 8 (4) | 5 (4) | **21** | 21 |
| `no_chapter_caption_in_section_heading` | 4 (4) | — | — | **4** | 4 |
| `preamble_carries_no_toc_tail` | 2 (2) | — | — | **2** | 4, and the defect was on 10 |
| `section_codes_ordered` | 3 (2) | — | — | **3** | 3 |
| `no_foreign_section_start_in_body` | — | 1 (1) | — | **1** | 1 |
| `clause_codes_plausible` | 1 (1) | — | — | 1 | 1 |
| `structure_counts` | — | — | — | **0** | 0 |
| `no_footnote_text_in_body` | — | — | — | **0** | 0 |
| `body_chapters_in_tree` | — | — | — | **0** | 0 |
| `no_code_fragment_in_section_heading` | — | — | — | **0** | 0 (was 31) |
| `no_structural_heading_in_body` | — | — | — | **0** | 0 (was 175) |
| **per lane** | **18** | **9** | **5** | **32** | 34 |

`no_chapter_caption_in_section_heading` gains one because round 4 made it visible: with
rule 150ZQZA finally binding, its heading is readable, and it is a FALSE positive — the
source prints that section's own title in capitals. Round 5 fixes the invariant.

48 of the `section_carries_its_body` drop is two compilations moved to
`tools/suite/exemptions/rules.json` on evidence already accepted for sibling invariants;
8 is the invariant learning to read `Omitte(cid:2)d`. The exemptions still run and still
print their hit counts — an exemption documents a failure, it does not hide its size.

Still a mixed-revision measurement: 61 scanned documents keep whatever revision last
wrote them, and the rules column is measured over 11 of that lane's 48 documents.

- [x] **Two Sales Tax Act editions the parser refused** — the 30.06.2020 and 31.12.2019
      editions print their first chapter as `4 [Chapter-I`, a footnote marker in front of
      the amendment bracket, so `CHAPTER_RE` missed it while `Chapter-II`…`Chapter-X`
      matched. Sections 1 and 2 were parentless and the document refused outright.
      `body_chapter_entries` now reads its line through `_STRUCT_DECOR_RE`, the same
      stripper `is_structural_boundary` — called three lines below it — already uses.
      **acts 78 → 80.**
- [x] **`body_chapters_in_tree` (21) — both causes closed.**
      *Acts (19):* the Customs Act 1969 prints `CHAPTER 1` in Arabic on page 23 and roman
      elsewhere, so `insert_missing_body_chapters` inserted a second, EMPTY chapter beside
      the real one — and reported 23 chapters against a contents page saying 22. Numerals
      now match across the notation gap only; `XIVA` and `XIV-A` stay two chapters, with a
      case that fails if that guard is removed. **Every Customs edition now reads 22.**
      *Rules (2):* `_tree_chapter_numeral` and `_norm_body_numeral` normalised the two
      sides of one comparison differently. Replaced by a single `_numeral_key`, −27 lines.
      Measured on identical JSON, that alone is 210 → 189.
- [x] **`section_carries_its_body` — the traced half. 111 → 55, no parser change.**
      `(cid:N)` is a glyph whose font subset has no ToUnicode entry, and it is
      **unrecoverable**: the Sales Tax Act 2014 producer emitted dozens of LinuxLibertine
      subsets whose glyph `<02>` maps to a different character in each (`r`, `8`, `4`,
      `l`), and the ones that print `(cid:2)` are exactly those missing that entry.
      `_is_omission` now drops it before matching, so `Omitte(cid:2)d` reads as the
      omission it is — **111 → 103**. Two further widenings were measured and rejected: a
      dot-run marker buys **zero** (those leaves are already caught by their heading), and
      intra-word spacing buys **one**, for a regex whose job is precision.
      48 more are two compilations — Customs Rules 2001 (44 index rows) and Federal Excise
      Rules 2005 (4 rows of a second instrument starting at PDF page 75) — exempted on the
      evidence their sibling invariants already carry.
      Adding those entries made the runner re-check the rest and report **two existing
      exemptions as stale** (`no_orphan_marker_li`, and Federal Excise's own
      `section_codes_ordered`); both deleted. All three lanes now report **0 stale**.
- [x] **The split code — 14 hits, and a measured note that had expired.** The text layer
      prints `150 ZQR.` for `150ZQR`, so `_candidate_code` returned `None` for an entire
      18-rule chapter. `_DOTSUFFIX_RE` already reads a split suffix but is bracket-gated,
      with a `ponytail:` note saying all 146 unbracketed instances were tariff rows —
      *"widen only if that changes"*. Re-measured over 186,984 lines: **it has changed.**
      Dropping the gate outright still gains 392 tariff rows, so the gate stays and a
      second, narrower unbracketed branch is added beside it: mandatory trailing dot,
      hyphen-or-space separator but never a dot, and 2–4 letters but never a lone capital.
      **48 gained, 0 lost**, each narrowing locked by a case that fails without it.
      Honest caveat: the acts lane did **not** move. 32 of the 48 gained lines were
      hyphenated Customs sections already binding by another route — lines newly matched
      is not the same measurement as sections newly bound.
- [x] **175 chapter headings that were never boundaries — and a fourth reader, traced.**
      `grammar.CHAPTER_RE` spells the keyword/numeral separator `[\s\-]+` and asserts so
      in its own `_demo`. `builder._STRUCTURAL_RE` and the suite's `_STRUCT_LINE` both
      spelled it `\s+`, so the Sales Tax Act's `Chapter-II` was not a segment boundary:
      nine chapter headings per edition were swallowed into the preceding section's body,
      and `no_structural_heading_in_body` — the invariant whose whole job is to find one
      — reported **zero**, blind for the same reason. Round 1's chapter numeral and round
      12's heading stripper, a third time.
      Measured invariant-alone on identical JSON: **0 → 175** (acts 171/19 documents,
      rules 4/2, ordinance **0** — the Income Tax Ordinance prints `CHAPTER I` with a
      space everywhere, so the `fbr_ingest` fork's identical copies are dormant, not
      correct, and are carried below).
      Two edits, and they had to land together: `is_structural_boundary` does not stand
      alone, because `discover` re-parses the line with `core.split()`, which on
      `Chapter-II` has no space to split on and yields `kw="CHAPTER-II"` — matching
      neither branch, falling through to Division and emitting a NAMELESS
      `Node(code="Division ")` that parents every following section. Widening the boundary
      test alone reproduces round 1's duplicate-container failure with certainty. The
      cheap witness that the split fix landed is the run log: the three body-driven
      editions now log `body-driven structure: 10 chapters` where they logged 0 and then
      had `insert_missing_body_chapters` fill 10.
      **21 documents re-converted, 0 refused, zero structural change** — leaf-code sets,
      container sets, `sections_count`, `chapters_count`, `schedules_count` all identical.
      Conservation `audit_all --family salestax` **19/19 at 100.000%**. Register **34 → 34**.
      See `wip/phase3-round13-chapter-hyphen.md` for the three things only running it
      found, including the conservation audit reading a canonicalisation as a 6-word loss.
- [x] **The preamble that began on the contents page — 10 documents, and the invariant
      saw 4.** Nine documents opened their preamble on front matter, including two
      Federal Excise editions whose ENTIRE preamble was the single token `vi`. Two
      causes, both the round-13 shape of one question answered two ways:
      *(1)* `pagemodel`'s footer strip read `_centred_int` → `grammar.folio_value`, which
      is ARABIC only, while front matter numbers its pages in roman — and `calibrate`
      has always recognised a roman folio when measuring where the footer band sits. The
      predicate now lives in `grammar.ROMAN_FOLIO_RE`, where `calibrate`'s own comment
      says folio grammar belongs; its looser test stays looser, deliberately (it asks
      where the band is, where a false positive costs a sample, not a line of text).
      The BAND could not be the test — `footer_min_top` is calibrated from body pages and
      the Customs 2008 folio prints at top 673.9 against a band starting at 702.5 — so
      the test is what a folio IS: roman, centred, last line of the page, bottom half.
      Measured: **65 roman-shaped lines over six editions' front matter, 64 of them
      folios, one a clause marker correctly kept.** Bounded at ccxcix and lowercase
      because `mix` is a valid roman numeral (MIX = 1009) and an ordinary word.
      *(2)* `calibrate._is_toc_row` could not see a SCHEDULE contents row
      (`THE FIRST SCHEDULE 213` carries no code), so a contents tail page measured ZERO
      rows and `first_body_page` began a page early. `grammar.SCHEDULE_TOC_RE` — the
      already-narrowed form, which still rejects the wrapped citation its own note
      records losing two chapters to — reused rather than rewritten. Measured over both
      profiles and all 90 resolvable documents: **4 changed, 86 unchanged.**
      **Invariant alone on identical JSON: 4 → 10. Parser fix: 10 → 2. Register 34 → 32.**
      Nine documents re-converted, 0 refused, conservation identical on all nine.
      The 2013-2016 editions **gained** section 224 (304 → 305 leaves): its contents row
      was inside the glued tail. A third invariant branch was needed or the gate would
      have reported ZERO on Customs 2008, which still carries the defect — removing the
      folio removed the only signal it had.
- [ ] **`preamble_carries_no_toc_tail` — the 2 that survive, same shape.** Customs
      30.06.2008 and Sales Tax 30.06.2023 each have a contents tail page carrying 2
      schedule rows against `detect_toc_pages`'s floor of `rows >= 3`. 2008's source
      prints `THE SECOND SHCEUDLE Omitted.` and `SCHEDULE_TOC_RE` rightly refuses the
      typo; loosening it re-admits the wrapped citation. Sales Tax 30.06.2023 is a NEW
      find, invisible before round 14 widened the invariant. The floor is load-bearing —
      `detect_toc_pages`'s comment records a lower one swallowing the Income Tax Rules'
      body title page and starting the body a page late — so a fix needs a signal other
      than row density.
- [ ] **The heading-terminator scan that walks through a boundary (3 hits).**
      `builder._find_heading_split` looks up to four lines ahead for a heading terminator.
      It stops at a grid table — its docstring argues that a table "can never be part of a
      heading" and that this is "the same rule on the build side" — but not at a
      structural heading, which cannot be part of one either. So Sales Tax `32AA`
      (`6[32AA. ***]`, an omission with no terminator of its own) borrows section 33's,
      and its heading comes out `*** Chapter-VII OFFENCES AND PENALTIES 33. Offences and
      penalties`. That is the whole 32AA cluster of
      `no_chapter_caption_in_section_heading`, across three Sales Tax editions.
      Round 13 measured the obvious guard (`return None` at a boundary) and it **loses
      section 32AA outright — 127 leaves → 126**: with no split the caller falls through
      the colon-dash branch and creates no entry at all. Needs an omission-aware fallback,
      not a guard.
- [ ] **The container-code guard**, which two independent measurements now argue for:
      a `PART-N` line is a boundary only where the enclosing chapter actually holds a part
      with that code.
      *(a)* It is what makes the PART separator widening safe. Widening PART scores **14
      real boundaries against 6 losses**, and the 6 are annexure FORMS — Customs Rules
      2001 leaf 34, a permission form whose item counter 8–11 runs ACROSS `PART-II`…
      `PART-V` and whose first part prints an EN DASH, and Sales Tax Rules 2006 form
      STR-11 (`PART-I`, `376[PART-II`). An exemption is the wrong tool: it silences the
      invariant while `_build_one` still slices the form into the next rule, conservation
      still reads 100.000%, and the hits vanish — the change would report itself as a
      success.
      *(b)* It is what would have kept round 13 from losing 32 words in Customs Rules
      2001 (74.101% → 74.087%): four chapter captions cut out as boundaries into a tree
      that holds 41 of ~44 chapters and cannot express them. Inside a known 62,519-word
      Phase 5 deficit on the one document whose containers are known to be inexpressible,
      but a real loss and reported as one.
      Needs `build_sections` to pass per-chapter container codes into `_build_one`.
- [ ] **The CHAPTER letter suffix — 57 hits, 24 documents, all real.**
      `_STRUCTURAL_RE`'s CHAPTER branch has no suffix class where the PART and Division
      branches beside it both carry `[A-Z]{0,2}`, so `CHAPTER XVI-A` is not a boundary
      either: it sits in section 155's body in **twenty Customs Act editions**, with
      `CHAPTER XIX-A` in 196J, plus the whole `XIV-A`..`XIV-D` / `V-A`..`V-C` / `VIII-A` /
      `X-A` / `XVII-A` / `XVII-B` family of Sales Tax Rules 2006 — the exact set
      `grammar.py`'s own comment records as unclassified. Held out of round 13 because it
      doubles the re-conversion from 21 documents to 44 and twenty of those are the
      Customs editions whose chapter tree rounds 1 and 6 rebuilt.
      Pinned by `test_structural_boundary_agrees_with_grammar.py::
      test_the_letter_suffixed_chapter_gap_is_still_open`, which asserts the current
      WRONG answer and so fails the moment the widening lands.
- [ ] **`fbr_ingest` carries both narrow copies, dormant.** Its `discover.py` has the
      identical broken keyword/numeral split and its `builder.py` the identical `\s+`
      regex, imported from its own fork rather than from `legal_ingest`. Measured at
      **zero** additional hits across all 12 ordinance documents, so re-converting the
      largest documents in the corpus would have moved nothing. Gated on the Phase 4b
      fork decision.
- [ ] **`section_carries_its_body` — the remaining 21.** The residue: 8 rules, 5 ordinance
      (`fbr_ingest`, sequenced after the Phase 4 decision on that fork), and 8 acts.
- [x] **A contents page with no page numbers — 118 sections, and 3 register hits.**
      `Sales Tax Act 1990 (30.06.2021)` parsed **9** section leaves; its eighteen sibling
      editions parse 110–151, and the sections are in the PDF. It has read 9 since before
      Phase 3 (5 before Phase 2). Its contents page prints dot leaders and NO folio, so nine
      rows survived out of ~140 and every one carried `printed_page = 1990` — the year, off
      the running title. `build_sections` is page-anchored, so entries expecting page 1995 of
      a 291-page document could never bind and 34,864 characters folded into s.19.
      `discover.py` is the body-driven fallback for editions that print no contents page; it
      was gated on the TOC producing *nothing*, and nine rows of garbage is not nothing. The
      gate now also fires when **no entry lands inside the document** — not "too few
      entries", because a flat instrument legitimately has three.
      **9 → 127 sections, one document changed corpus-wide, conservation 100.000%.** Locked
      by case `sta300621_pageless_toc_binds_late_sections`, which fails with the gate
      reverted. `no_chapter_caption_in_section_heading` gains one: s.32AA finally binds, so
      the same real leak already open on two sibling editions is now visible here too.
- [x] **31 headings carrying their own code tail — and two gates that could not fail.**
      `builder._body_heading_title(h4_inner, code)` **never referenced its `code`
      argument**: the strip ran off `_HEAD_CODE_PREFIX_RE`, whose `grammar.CODE`
      (`\d{1,4}-?[A-Z]{0,4}`) tolerates a hyphen but never a space. Where the text layer
      splits the code — `150 ZQR.` for 150ZQR, `156 A.` for 156A — it matched the digits
      and stopped, and the letters stayed in the title. `builder.py` already knew the
      shape: `_DOTSUFFIX_RE`'s own comment says the separator "may be a HYPHEN or a SPACE",
      and `_candidate_code` folds `150 ZQR` → `150ZQR` so the two sides agree on one
      spelling. The detector handled it; the heading stripper did not — the same
      two-normalisers disagreement as round 1's chapter numeral.
      **31 leaves, 15 documents, 2 lanes, one cause** (rules 17, acts 14, ordinance 0 —
      a separate fork). Every one `heading_source="body"`; a TOC-sourced heading is clean,
      which is why a section only shows it once it HAS a body to be read from — and why
      round 10 looked like the culprit when it had only given two stubs their bodies.
      Fixed by driving the strip from the code already passed, the way
      `discover._heading_from_words` already does for this exact disagreement, taking the
      LONGER of the code-driven and positional matches: the code-driven one alone strips
      *less* where the body prints a suffix the TOC's code lacks (`15A.` against code 15).
      Two measurements forced that shape, both caught by re-converting and diffing rather
      than by reasoning. The second: the separator run must not swallow the code's OWN
      terminator. The first attempt regressed Customs `193A`, whose body prints
      `193. Appeals to Collector` — `3` + `. ` + `A` matched and the heading came out
      `ppeals to Collector`. `discover._heading_from_words` carries the same construction
      and a comment claiming its len(code)-1 bound makes that impossible; the bound limits
      how MANY separator runs there are, not how far one reaches, so it does not hold for a
      code whose letter suffix also begins the title word. **That comment is now wrong in
      `discover.py` too** — same latent shape, not triggered there by this corpus.
      Conservation: **zero `plain_text` delta**, identical leaf sets; in rules exactly 17
      headings changed against 1,087 unchanged. Locked by
      `tools/tests/test_body_heading_code_strip.py` (fails two ways with the fix reverted)
      and invariant `no_code_fragment_in_section_heading`, which tests that the leftover is
      a PROPER SUFFIX of the leaf's own code rather than merely code-shaped — measured
      alone on unchanged JSON at 31, then 0.
- [x] **The register could not see a failing regression case.**
      `tools/tests/test_register_snapshot.py` is what gates the pipeline on CI, since the
      corpora are gitignored and the lane suites SKIP there. Its regex
      `\[ *FAIL \((\d+)\)\] +([a-z_]+)` matches an INVARIANT line, which carries a
      count, and never `[FAIL] <case_id>`, which is pass/fail. Cases are this project's
      locking mechanism — every fix ships pinned by one in the same PR — so the mechanism
      protecting every fix already made was gated by nothing, and **two cases were failing**
      when this round opened. A case's only correct value is zero, so it gets an assertion,
      not a snapshot; both readings now come from one suite run per lane.
- [x] **A case scoped by date matched the wrong document.** Round 11's lock carried
      `applies_to: "as amended up to 30.06.2021"`, and `runner.py` treats `applies_to` as a
      substring of `metadata.filename` — which the **Customs** Act 30.06.2021 also matches,
      and it has no s.73. The round-11 lock had been reporting a failure on a document it
      was never about. Now scoped to `Sales Tax Act, 1990 as amended up to 30.06.2021`,
      selecting exactly one. Every other scoped case swept: two match multiple documents
      and both are deliberate (`o05_sec9_interior_endash_not_a_terminator` over 20 Customs
      editions, `fe_r78_double_hyphen_heading_keeps_body` over 2), none matches zero.
- [ ] **No invariant can see a document that lost 93% of its sections.** The register moved
      3 while the document gained 118. `section_carries_its_body` reports leaves that exist;
      `structure_counts` compares the tree against a contents page that was itself the thing
      that failed. The obvious check does not survive measurement — "no chapter may be empty"
      fires on **29 of 103** documents, and twenty Customs editions agreeing on an empty
      `CHAPTER XIX-A` is evidence of a real omitted chapter, not a defect. What would catch
      it is a CROSS-EDITION fact (9 leaves where 18 siblings have ~140) and the suite has no
      place for one: invariants run per document. `signatures.json` already carries the
      group, so the comparison exists in the corpus and only the wiring does not.
- [x] **The header band — 11 hits, and a number with no measurement behind it.** Sales Tax
      Rules 01-01-2025 held 16 of the register's 64; `why_unbuilt --lane rules` (usable for
      the first time after round 9) reported 11 of its 12 stubs as "code never opens a body
      line", and `pdftotext` found every one of them printing on exactly the page the
      contents page predicts. They open at top 41.0–41.5 against `header_max_top = 43.6` —
      a flat `page_h * 0.055` that `calibrate` falls back to when no running header clears
      its 40% test, and `_is_header_line` dropped everything above it. That function is
      ledger P37 and states the right principle ("what a line says, not where it sits"), but
      its guard only applied where a header HAD been detected.
      `_is_header_line` is now shorter: blank or bare folio is furniture, otherwise only a
      measured key is. `calibrate` fills `header_keys` from RECURRENCE when nothing clears
      40% — measured, because 5 of the 50 documents that reach that branch do have a header
      the threshold missed (PFMA 2019's gazette masthead alternates recto/verso so neither
      half clears; Finance Act 2023 prints NATIONAL ASSEMBLY SECRETARIAT).
      **4 documents changed, +3,904 characters, 0 lost.** Locked by
      `tools/tests/test_header_band.py`. That document's 12 stubs are now 3, each traced:
      44A opens with a left double quote, 150ZQZI is printed `150ZQZl`, and 150W's code
      appears only in a footnote. Its contents page also lists 39E where the body prints
      `39K` with the same title.
- [x] **`str_bracketed_chapters_classify` — the case was wrong, not the parser.** It
      asserted `ELECTRONIC OR OTHER MEANS`; pdfplumber returns `OROTHER` as one token
      (x0=238.8, x1=310.6), which is this document's documented `no_jammed_words` cause and
      already exempted. The case was failing on a defect it does not test. Corrected to what
      the source prints, with the measurement in its description.
- [ ] **`convert_all.py` cannot resume a re-conversion.** Two runs were killed mid-flight
      this round, leaving 49 of 80 acts documents at the new revision — the mixed-revision
      hazard the working rules open with. `--skip-existing` does not help: after a
      re-conversion every output exists. What worked was converting only outputs older than
      the parser's mtime. Two source files need care in any such loop — Customs Rules 2001
      and The Finance (Supplementary) Act 2022 are PDFs with **no `.pdf` extension**, so a
      `**/*.pdf` glob misses them silently.
- [x] **The cursor cascade — 6 hits, one choice.** The handover said Sales Tax 15.9.2021's
      pages "interleave" and to read the source first. They do not: `why_unbuilt.py` shows
      the whole block printing ~6 pages ahead of its own contents page, and s.3 is the one
      entry whose code opens two body lines (28, its real heading; 37, a cross-reference).
      `|37-34|=3` beats `|28-34|=6`, the tolerance ladder breaks at the first tolerance that
      hits, and the monotonic cursor jumps past ss.3A/3AA/3B/4/5/6/7. The ordering guard
      below the ladder rejects a match past where the next entry is EXPECTED and cannot see
      where it PRINTS. Fix: filter the candidates by a one-entry look-ahead before the
      ladder runs — a tie-break between candidates, never a rejection, skipped entirely
      with one candidate or where every candidate starves the next entry.
      **Gained 6, lost 0**; exactly one document changed corpus-wide, conservation
      100.000% on both sides. Locked by `tools/tests/test_build_sections_lookahead.py`,
      which fails with the filter removed.
- [x] **Two tools that could not do their job.** `why_unbuilt.py` called `calibrate` and
      `parse_toc` with no profile, so every RULES document — the lane holding 20 of the 44
      remaining hits — was diagnosed with Acts folio and leader settings; it now takes
      `--lane`. `audit_all.py`, which `tools/suite/README.md` names as the conservation gate
      to run after every regeneration, had been raising `ModuleNotFoundError` since
      `scripts/` became `tools/`. Both fixed; the acts lane re-audits 56/56 within gate.
- [x] **`no_footnote_text_in_body` (45) — closed, and none of it was in a body.**
      All 45 hits were the string `LEGAL REFERENCE` inside a citation tooltip's `title=`
      attribute; the invariant searched raw markup, so an attribute counted as body text.
      Zero appeared in rendered text. Stripping tags first is **193 → 148 on identical
      JSON**.
      Behind the false positive, a real defect it was not measuring: `build_page_model`
      moved the apparatus caption out of the body into `footnote_lines`, where it lands
      *before* the first marker — and a pre-marker line is by definition a continuation,
      so it came back as `^cont` and was spliced onto the previous page's last note.
      **473 footnote texts across 20 Customs editions.** The caption belongs in neither
      zone and is now dropped from both (`_drop_apparatus_captions`).
      The first version of the fix guarded `parse_footnotes` instead and left the caption
      in `footnote_lines`; `audit_completeness.py` compares that against the output's
      footnote texts and correctly read it as **48 lost words per edition**. Dropping one
      layer earlier keeps conservation at 100.000% on both sides.
      Also deleted a hardcoded `known_gaps` skip inside the check (Income Tax Ordinance
      11.03.2019, Division XXI) — re-measured as **stale**, matching no branch of the
      invariant before or after. A skip buried in a function cannot report itself stale;
      an `exemptions/` entry does.
- [x] **`no_foreign_section_start_in_body` 19 → 5 — the pair disagreed with itself.**
      Ten hits had a victim that is a REPEALED section: Customs s.20 reads
      `15[20. 112[Omitted]` in seven editions while s.2 prints the amendment marker in
      `such other 20[officers of Customs as may be notified by the Board;]`, plus Sales Tax
      s.3A, s.42 and Sales Tax Rules 14A. `section_carries_its_body` has skipped omissions
      since it was written; its documented mirror never asked, so one half of the pair
      reported what the other half had already dismissed. One guard, reusing the same
      `_is_omission` predicate — **64 → 54 on identical JSON, no re-conversion.**
      Four more were the mirror of an exemption that was never written down: the same two
      compilations round 3 exempted for `section_carries_its_body`, firing here from the
      same index rows (`'7. Jurisdiction ______'`, `'15.06.2002.'`, and Federal Excise's
      page-75 second instrument). Same traced evidence, same Phase 5 deletion condition —
      **54 → 50.**
      The amending hypothesis stays falsified for every document we can measure; it may
      still hold for the 18 amending instruments behind OCR.
      The five survivors are all real: Sales Tax 15.9.2021 s.3B (the cursor cascade), Sales
      Tax 30.06.2021 s.30 (a TOC row bound as a body) and three in Sales Tax Rules
      01-01-2025 (footnote text read as a section start).
- [x] **`register.json` has a generator.** Seven rounds hand-copied the `FAIL (n)` counts.
      `test_register_snapshot.py` already had `_measure()`; the generator is the test read
      backwards — `python tools/tests/test_register_snapshot.py --write`.
- [x] **`structure_counts` (5 → 0) — two fixes, and only the second moved the number.**
      *A part is not a chapter.* `PART_RE` required the numeral to end the line, so
      `PART-II ATTACHMENT AND SALE OF MOVABLE PROPERTY ..... 73` fell through to the caption
      branch and opened a chapter, lifting 64 rules out of CHAPTER XI. Two measured
      narrowings: the caption group needs `(?-i:…)` (unscoped it matches
      `Part 1 of Second China Overseas Ports` and 47 schedule rows), and a caption is only
      accepted when leaders or a folio follow (without it, Income Tax Rules 2002's running
      header `PART-I   SECOND SCHEDULE` on 457 pages takes `part_lines` 43 → **595**).
      **13 gained, 0 lost.** Sales Tax Rules: 43 → 41 chapters, 2 spurious containers → 4
      real part nodes, 339 sections held — **and the register did not move.**
      *A suffix is not a sum.* `insert_missing_body_chapters` sorted chapters by
      `_roman_value`, which folds a suffix into two decimals by SUMMING its letters:
      `XIV-AA` and `XIV-B` both 14.02, `XIV-AB`/`XIV-BA`/`XIV-C` all 14.03. Ordering on
      `(base numeral, suffix letters)` reproduces the contents page exactly.
      `_roman_value` itself is unchanged — round 1's Arabic/roman guard depends on it. The
      `ch.code` tiebreak had to come out: `XIVA` and `XIV-A` share a key and a string
      compare orders them by punctuation, not by the contents page. `list.sort` is stable,
      so equal keys keep the TOC's order. Both facts locked.
      `signatures.json` moved deliberately: 11 documents, `part_lines` plus
      `container_order` `CP → PC`, **0 family changes**.
- [x] **`section_codes_ordered` 6 → 4 — a definition clause is not a section.**
      `discover_structure` returns **0 chapters and 126 parentless sections** on a TOC-less
      edition, so `insert_missing_body_chapters` builds the whole tree and assigns sections
      by which codes are *printed* in each chapter's span. The Sales Tax Act defines
      "supply chain" as clause `[(33A)` inside section 2, so `33A` is in CHAPTER I's span;
      CHAPTER I claims it and CHAPTER VII, 55 pages later, finds the parent already set.
      An entry carrying an `anchor` is now placed by **position**, never by code
      membership; TOC entries have no anchor and keep the old behaviour.
      The lock needed strengthening first: with only two chapters the second pass
      reassigns 33A anyway, so the fixture passed with the fix removed. A third chapter
      reproduces the real document's shape.
      Remaining 4: Customs 2025 `'9' after '119'`, Sales Tax 2021 `'3' after '65'`, and
      Sales Tax 2014 `'3' after '32AA'` + `'22' after '75'` — different documents, not yet
      traced.
- [x] **`202B` — the marker run round 4 was right to refuse.** Round 4 measured the naive
      `MARKER_PREFIX` widening at **1 fix : 17 false positives**. The narrow form admits a
      whitespace-separated run **only** behind a lookahead for `[CODE. Capital`, which over
      186,971 lines matches exactly one. **acts `section_carries_its_body` 19 → 15.**
      A methodological correction came with it: every gained/lost measurement in this phase
      has used `output/*.json` plain_text, and that is **not** what the parser sees — the
      parser's line is `42 53 [202B.` while the rendering collapses it to `42 53[202B.`.
      The first lookahead anchored hard on `[`, matched the JSON and missed the PDF.
- [x] **The contents page's own title, read as a chapter — and the invariant's proxy.**
      Two fixes, measured separately.
      *Parser:* `82A out of order after 224` was a chapter-parsing problem, not an ordering
      one. A TOC page break landing inside a wrapped section row leaves the running title
      `THE CUSTOMS ACT,1969` on its own line; it is ALL-CAPS, so `is_foreign_caption`
      accepts it and `_open_caption_chapter` opens a chapter for it. `_page_furniture`
      exists for exactly that line — its docstring even names s.82A — but the two call
      sites order the tests differently, and the one reached on a wrapped row tested
      furniture *after* the caption branch had already fired. Customs 2008: **24 → 22
      chapters** (its contents lists 22), 82A back in CHAPTER IX, 167–192 in CHAPTER XVIII,
      **0 anonymous containers**, 297 sections preserved, 5 hits → 2.
      *Invariant:* `no_chapter_caption_in_section_heading` fired on any run of 3+ capitalised
      words. It now asks what its name asks — is the run a caption that appears on a chapter
      of this document? The three real leaks all match a chapter in their own tree;
      `150ZQZA`/`RESPONSIBILITIES OF THE VENDOR` does not, because the source sets that
      rule's own title in capitals. Alone: rules **2 → 0**, acts holds at 3.
      The locking fixture had to change with it — it pinned a leak in a document containing
      no chapter with that caption, which cannot happen (`_open_caption_chapter` opens a
      node even when the contents omit the `CHAPTER N` row). It now contains the chapter,
      and still fails if that chapter is removed.
- [ ] **`section_codes_ordered` (4) — untraced.** Round 5 closed
      only the Customs 2008 hit. The five Sales Tax hits are `CHAPTER I PRELIMINARY`
      holding `['1', '2', '33A']` across pages 2–75: section 33A (page 75) is parented to
      CHAPTER I instead of CHAPTER VII.
- [ ] `clause_codes_plausible` (1, Finance Act 2024). The jump `7->8517` is an HS tariff
      heading read from a **table row**; the check excludes schedules but not table-derived
      codes (ledger P06).
- [ ] Re-examine the 29 low-confidence documents in `tools/discovery/report.md` §5
      against their re-converted output. Low confidence is not a defect; it is a list
      of the documents whose output deserves a human read.
      **§5 was listing 2, not 29** — round 7 fixed the generator. Its filter tested
      `BY_LABEL[family].profile`, but Phase 2 made the profile an *override* (`None` for
      `consolidated`), so 27 rows had been dropped since PR #45. `report.md` had not been
      regenerated since Phase 0, so it kept printing the old 29 while its generator
      produced 2. `.profile` → `.parseable`, the field Phase 2 added for this question.

- [x] **Gate the register itself.** `data/corpora/*/output/` is gitignored, so
      `run_tests_smoke.py` SKIPs all three lane suites on CI and seven rounds of
      210 → 64 were enforced by prose and a human reading it.
      `tools/suite/register.json` now holds the measurement and
      `tools/tests/test_register_snapshot.py` replays it — skip with no corpus, compare
      with one, fail in **either** direction. An improvement failing it is the point: the
      number then moves in the same PR that moved it. Verified by perturbing the snapshot
      and by clearing the corpus paths.
- [x] **`make check` now lints what CI lints.** It ran `ruff check apps/api tools`; CI runs
      it bare, and `pyproject`'s `src` makes the bare form cover `packages/` too. Planting
      a violation in `packages/legal_ingest/` proved it: the Makefile's form reported
      "All checks passed", CI's found it.

**Gate:** every remaining hit is fixed, or has an entry in
`tools/suite/exemptions/<lane>.json` whose reason is traced to the source PDF

---

## Phase 4 — flip the default, and close the pipeline→portal loop
Branch: `feat/profile-auto-default`, then `fix/pipeline-to-portal`

- [ ] Make `--profile auto` the default once Phase 3 is at zero-or-exempted, and
      collapse the lane→package mapping to family→profile. Phase 2 removed the reason
      not to: the family now overrides the lane's profile rather than replacing it, so
      the default flip no longer silently re-parses a lane.
- [x] ~~The transport work~~ — **done as its own track**, `wip/integration/` PRs #59–#76:
      the output contract and provenance, `node_key` leaf identity, withdrawal, one ingest
      path in production, the sanitizer, review state, a CI gate at the corpus interface,
      and PR-J taking the ordinance lane onto the contract (12/12 `contract_version`,
      corpus identity hole 5,047 leaves → 89). The bullet below predates it and its
      description of the ordinance lane as blocked is now only half true — that lane
      converts and syncs; what is still open is which *fork* parses it.
- [ ] Decide `fbr_ingest` on the evidence now committed in `signatures.json`: the 9 ICT
      Ordinance editions are `consolidated`/flat and structurally identical to the
      Acts-lane PSW and VDDA instruments, and nothing like the 13 Income Tax Ordinance
      editions they share a lane with. Merging the fork is still a v1 non-goal
      (`README.md:283`); this phase only decides it with numbers instead of guesses.
      **This is now also what gates the ordinance lane, and Phase 2 measured the
      cost.** Run best-effort at the lane profile, the lane converts 9 of its 19
      text-layer documents; the other 10 refuse, nine of them the ICT editions with the
      exact error Phase 0 recorded (`TOC parse left 3 section(s) without a chapter
      container`) and the tenth an amending Ordinance this pipeline cannot express.
      `--profile auto` is still not expressible here — `fbr_ingest.run` takes no
      profile, and Phase 1's guard refuses the run rather than letting 46 children fail
      and quarantine the lane.
**Gate:** a parser fix merged to `main` is visible in the portal without a manual step
— **met for the transport half** (#70 wired pipeline health, #64/#65 production identity
and `If-Match`); what remains is the profile default and the fork decision above.

---

## Phase 5 — the instrument tree level

Deferred here by decision: Phase 3 exempts around it, Phase 4 ships first, then this.

A compilation is not one instrument. Customs Rules 2001 binds 44 separately-notified
S.R.O. rule sets behind one index; Federal Excise Rules 2005 starts a second instrument at
PDF page 75 with its own contents page. The tree has no level above chapter, so those
documents' index rows become section leaves with no body, and their codes cannot ascend
document-wide.

- [ ] A level above chapter, so a compilation parses as N instruments
- [ ] The six walkers that hardcode `chapter/part/division/section` as the child keys
- [ ] The portal renderer
- [ ] Re-convert the compilations

**Gate: the deletion of the five `tools/suite/exemptions/rules.json` entries that name
this phase** — `section_carries_its_body`, `section_codes_ordered` and
`no_foreign_section_start_in_body` on Customs Rules 2001, and `section_carries_its_body`
and `no_foreign_section_start_in_body` on Federal Excise Rules 2005. (It said "four" and
then listed three; round 8 added the two mirror entries and counted them.) That is the
honest test that it worked, and the suite will report them stale on its own once it has.
