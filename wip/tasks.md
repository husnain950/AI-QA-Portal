# Remediation tasks

Executable checklist for [`wip/plan.md`](./plan.md). Dependency order — do not start a
phase until the one above it passes its gate.

Baseline: `main` at `a7d5d2e` (PR #42). Every count below was measured on 2026-08-29
with `python tools/run_suite.py <lane>` and `python tools/discover_corpus.py` against
the corpus staged on this machine.

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

## Phase 2 — re-convert the lanes that can take a profile
Branch: `fix/corpus-reconvert-all-lanes`

Retitled. **Phase 2 covers `acts` and `rules` only.** The `ordinance` lane routes to
`fbr_ingest`, which takes no profile at all, and merging that fork is a Phase 4
decision (`README.md:283` still lists it as a v1 non-goal). Re-converting it under
`--profile auto` is not deferred out of caution — it is not expressible.

### What the toolchain rebuild unblocked, measured

| lane | source files | JSON on disk | blocked, and why |
|---|---|---|---|
| acts | 93 | 80 | **25 editions carry image-backed pages — 2,065 pages needing OCR.** Finance Act 2017-18 alone is 683, then 2025 (290), 2015 (236), 2016-17 (215), 2014 (148), 2020 (140) |
| rules | 48 | 11 | **36 refuse on `No module named 'numpy'` — 391 OCR pages**, plus 1 genuine refusal (the Urdu edition, 20,107 chars read and 0 reaching the document) |
| ordinance | 45 | 12 | not a Phase 2 target |

The rules lane is the headline. Its 36 blocked documents include **every** Income Tax
Rules 2002 edition (6) and **every** Sales Tax Rules 2006 edition (6) — the lane's
whole consolidated backbone — each dying on one or two scanned pages inside a
200–480 page document (`OCR failed on page 482 of 'Income Tax Rules, 2002 Amended
upto 24.11.2023.pdf'`), plus 12 PSW/SRO instruments that are single scanned pages.
The 11 documents the rules lane does convert are the leftovers.

`data/ocr_cache` is **0 B**, so none of this work is banked: all **2,456** pages
(2,065 acts + 391 rules) will be paid in full, once, on the first run.

- [ ] **Back up first** — `make backup-remote BASE_URL=<prod>` **and** a local
      `pg_dump`. Re-parsing resets sign-off and flips changed leaves to unreviewed.
- [ ] **Rules first, and separately.** 36 documents, **391 OCR pages** (measured with
      `convert_all.scan_page_count` over the whole lane, not sampled) — a fifth of the
      acts cost, and it roughly triples the lane. Half of it is the six Income Tax Rules
      2002 editions at 46 / 44 / 29 / 27 / 23 pages. Do it as its own run so its result
      is legible before the acts OCR marathon starts.
      `convert_all.py rules --profile auto`
- [ ] **Then acts**, budgeting for 2,065 OCR pages at `--ocr-batch 1` (the flag's own
      help says raising it measured *worse*). Use `--skip-existing` so an interrupted
      run resumes rather than restarting under a changed revision.
- [ ] Re-run `tools/discover_corpus.py --write` and review the `signatures.json` diff.
      `signature.measure` is text-layer only, so a document that gains a text layer
      through OCR **can legitimately change family** — most of the 30 `no_text_layer`
      documents should stop being `no_text_layer`. A moved document needs a reason,
      not a shrug.
- [ ] Re-measure all three suites and rewrite the register below

**Gate:** every source document either converts or is refused with a family reason ·
no lane regresses against the numbers in Phase 3 · `--check` clean after `--write`

---

## Phase 3 — the anomaly register
Branch: one per invariant class

**243 hits across 37 of 103 converted editions**, re-measured 2026-08-29 on Python
3.12 after the rebuild — identical to the pre-rebuild numbers, so the register is a
property of the parser and the corpus, not of the interpreter. Higher than the 157 the
previous register recorded, because PR #41 added `no_chapter_caption_in_section_heading`
and tightened `no_footnote_text_in_body`, and because much of the on-disk JSON predates
several parser fixes.

**The rules column is provisional and will move a lot.** It is measured over 11 of 48
documents; Phase 2 adds 36, including every Income Tax Rules 2002 and Sales Tax Rules
2006 edition. Do not spend a branch on a rules invariant before those exist — the six
editions carrying all 78 `section_carries_its_body` hits are a sixth of the lane it
will be.

| Invariant | acts | rules | ordinance | total |
|---|---|---|---|---|
| `no_footnote_text_in_body` | 109 (20 docs) | — | — | 109 |
| `section_carries_its_body` | 26 (9) | 78 (6) | 5 (4) | 109 |
| `no_foreign_section_start_in_body` | 9 (9) | 10 (4) | — | 19 |
| `no_chapter_caption_in_section_heading` | 3 (3) | 2 (2) | — | 5 |
| `clause_codes_plausible` | 1 (1) | — | — | 1 |
| **per lane** | **148 / 27 docs** | **90 / 6 docs** | **5 / 4 docs** | **243** |

- [ ] **`no_foreign_section_start_in_body` (19) — re-measure before touching.**
      "A leaf contains the START of another section in its body" is the literal
      signature of an amending instrument parsed as a consolidated one: the other
      section is the one being quoted. Phase 2 may close these without a parser change.
- [ ] `no_footnote_text_in_body` (109, 20 acts editions) — classify into cause classes
      before fixing; 109 hits over 20 documents is a zoning family, not 109 defects
- [ ] `section_carries_its_body` (109) — the rules lane carries 78 of them over 6
      editions; check whether the same zoning cause explains both lanes
- [ ] `no_chapter_caption_in_section_heading` (5) — landed with PR #41, never triaged
- [ ] `clause_codes_plausible` (1, Finance Act 2024) — an amending instrument; expect
      Phase 2 to change what this measures

- [ ] Re-examine the 29 low-confidence documents in `tools/discovery/report.md` §5
      against their re-converted output. Low confidence is not a defect; it is a list
      of the documents whose output deserves a human read.

**Gate:** every remaining hit is fixed, or has an entry in
`tools/suite/exemptions/<lane>.json` whose reason is traced to the source PDF

---

## Phase 4 — flip the default, and close the pipeline→portal loop
Branch: `feat/profile-auto-default`, then `fix/pipeline-to-portal`

- [ ] Make `--profile auto` the default once Phase 3 is at zero-or-exempted, and
      collapse the lane→package mapping to family→profile
- [ ] Decide `fbr_ingest` on the evidence now committed in `signatures.json`: the 9 ICT
      Ordinance editions are `consolidated`/flat and structurally identical to the
      Acts-lane PSW and VDDA instruments, and nothing like the 13 Income Tax Ordinance
      editions they share a lane with. Merging the fork is still a v1 non-goal
      (`README.md:283`); this phase only decides it with numbers instead of guesses.
      **This is now also what gates the ordinance lane.** Phase 2 cannot re-convert it
      under `--profile auto` because `fbr_ingest.run` takes no profile — the guard added
      in Phase 1 refuses the run rather than letting 45 children fail and quarantine the
      lane's 12 JSONs. Until this decision lands, the ordinance lane is frozen at
      whatever last converted it.
- [ ] The transport work from the previous plan, unchanged: `make sync` after
      re-conversion, a mounted corpus volume in production, and an HTTP path that
      writes `version_metrics` so the portal can show pipeline health at all

**Gate:** a parser fix merged to `main` is visible in the portal without a manual step
