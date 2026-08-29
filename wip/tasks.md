# Remediation tasks

Executable checklist for [`wip/plan.md`](./plan.md). Dependency order — do not start a
phase until the one above it passes its gate.

Baseline: `main` at `863b8fe` (PR #44). Every count below was measured on 2026-08-29
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

**210 hits across 36 of 101 converted editions**, re-measured 2026-08-29 immediately
after the Phase 2 run. Down from 243 across 37 of 103, and the composition changed more
than the total did.

| Invariant | acts | rules | ordinance | total | was |
|---|---|---|---|---|---|
| `section_carries_its_body` | 27 (10) | 79 (6) | 5 (4) | 111 | 109 |
| `no_footnote_text_in_body` | 45 (20) | — | — | 45 | 109 |
| `body_chapters_in_tree` | 19 (19) | 2 (1) | — | 21 | **new** |
| `no_foreign_section_start_in_body` | 10 (10) | 10 (4) | — | 20 | 19 |
| `section_codes_ordered` | 6 (4) | — | — | 6 | **new** |
| `structure_counts` | — | 4 (2) | — | 4 | **new** |
| `no_chapter_caption_in_section_heading` | 1 (1) | 1 (1) | — | 2 | 5 |
| `clause_codes_plausible` | 1 (1) | — | — | 1 | 1 |
| **per lane** | **109 / 26 docs** | **96 / 6 docs** | **5 / 4 docs** | **210** | 243 |

Two labels the numbers do not carry on their own:

- **Three classes are new because they were DORMANT, not because anything broke.**
  `inv_body_chapters_in_tree` reads `metadata.body_chapter_numerals` and its docstring
  makes it a deliberate no-op on JSON without the key, "so old output does not fail the
  lane until it is reconverted". Re-conversion woke it up: **31 hits the previous
  register could not see.**
- **It is still a mixed-revision measurement.** 61 scanned documents keep whatever
  revision last wrote them, and the rules column is measured over 11 of 48 documents.

- [ ] **Two Sales Tax Act editions the current parser REFUSES** —
      `TOC parse left 2 section(s) without a chapter container (1, 2...)` on the
      30.06.2020 and 31.12.2019 editions. This is not a register hit; it costs the
      corpus two documents, which makes it the highest-value item here. Controlled as
      parser drift, not profile (`--profile lane` raises the identical error).
- [ ] **`body_chapters_in_tree` (21) — two causes, both small.**
      *Acts (19, one hit each):* `insert_missing_body_chapters` reads a body line
      printing the numeral as Arabic `1`, finds no roman `I`, and inserts a **second,
      empty** `CHAPTER 1 / PRELIMINARY` beside `CHAPTER I / PRELIMINARY`. That is also
      why every Customs edition went 22 → 23 chapters.
      *Rules (2):* a false positive — `_tree_chapter_numeral("CHAPTER VIA")` returns
      `VI-A` while `_norm_body_numeral("VIA")` returns `VIA`, so the two sides of one
      comparison normalise differently and a chapter that IS in the tree is reported
      missing.
- [ ] **`no_footnote_text_in_body` (45, 20 acts editions)** — classify into cause
      classes before fixing. It shed 64 hits to re-conversion alone; what is left is
      what the current parser actually does.
- [ ] **`section_carries_its_body` (111)** — the rules lane carries 79 over 6 editions
      and the acts lane 27 over 10. Check whether one zoning cause explains both.
- [ ] **`no_foreign_section_start_in_body` (20).** **The amending hypothesis is
      falsified for the documents we can measure.** The seven amending instruments that
      converted are clean on this invariant; all ten acts hits are in *consolidated*
      statutes — seven Customs editions (2019–2025, one hit each) and three Sales Tax
      editions. It may still hold for the 18 amending instruments behind OCR, but it is
      no longer a reason to schedule this class first.
- [ ] **`structure_counts` (4)** — Sales Tax Rules 2006 places `CHAPTER XIV-AB`
      (printed page 123), `XIV-AC` (123) and `XIV-AD` (125) *after* `XIV-B` (129),
      `XIV-C` (154) and `XIV-D` (158). The invariant already forgives a numeral that
      goes backwards while the pages go forwards, so it is firing on the case it exists
      for: the tree assembled out of document order.
- [ ] **`section_codes_ordered` (6, 4 acts editions)** — new, never triaged.
- [ ] `no_chapter_caption_in_section_heading` (2) and `clause_codes_plausible` (1, on
      Finance Act 2024 — now correctly parsed as amending, and its single hit is the
      only failure across all seven amending instruments).
- [ ] Re-examine the 29 low-confidence documents in `tools/discovery/report.md` §5
      against their re-converted output. Low confidence is not a defect; it is a list
      of the documents whose output deserves a human read.

**Gate:** every remaining hit is fixed, or has an entry in
`tools/suite/exemptions/<lane>.json` whose reason is traced to the source PDF

---

## Phase 4 — flip the default, and close the pipeline→portal loop
Branch: `feat/profile-auto-default`, then `fix/pipeline-to-portal`

- [ ] Make `--profile auto` the default once Phase 3 is at zero-or-exempted, and
      collapse the lane→package mapping to family→profile. Phase 2 removed the reason
      not to: the family now overrides the lane's profile rather than replacing it, so
      the default flip no longer silently re-parses a lane.
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
- [ ] The transport work from the previous plan, unchanged: `make sync` after
      re-conversion, a mounted corpus volume in production, and an HTTP path that
      writes `version_metrics` so the portal can show pipeline health at all

**Gate:** a parser fix merged to `main` is visible in the portal without a manual step
