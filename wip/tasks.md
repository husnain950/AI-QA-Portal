# Remediation tasks

Executable checklist for [`wip/plan.md`](./plan.md). Dependency order — do not start a
phase until the one above it passes its gate.

Baseline: `main` at `915b17d` (PR #41). Every count below was measured on 2026-08-29
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

## Phase 1 — rebuild the toolchain
Branch: `fix/local-stack-and-toolchain`

- [ ] Rebuild `.venv` on the pinned interpreter — currently **3.14.7**, must be **3.12**
      — `rm -rf .venv && /opt/homebrew/bin/python3.12 -m venv .venv`
- [ ] Install pipeline + OCR extras
      — `.venv/bin/pip install -r apps/api/requirements-dev.txt -r packages/requirements.txt -r packages/legal_ingest/requirements-ocr.txt`
      — *unblocks:* every `no_text_layer` document, **and** the amending instruments
        that refuse today (`Finance Act, 2023`, `The Tax Laws (Amendment) Act, 2020`:
        `OCR failed on page N: No module named 'numpy'`)
- [ ] Rebuild api/worker images if the local stack is still crash-looping on
      `alembic … '0003_rules_corpus'` — `make build && make up`
- [ ] If any OCR pin must move for 3.12, re-pin **together with** a fresh
      `tools/acts/ocr_review.py` run (an OCR model change silently changes statutory text)

**Gate:** `.venv/bin/python -c "import numpy, onnxruntime, rapidocr_onnxruntime"` clean ·
`tesseract --version` still 5.5.2 / leptonica 1.87.0 ·
`make test` passes · `python tools/discover_corpus.py --check` still reports no drift

---

## Phase 2 — re-convert all three lanes under the family profiles
Branch: `fix/corpus-reconvert-all-lanes`

- [ ] **Back up first** — `make backup-remote BASE_URL=<prod>` **and** a local `pg_dump`.
      Re-parsing resets sign-off and flips changed leaves to unreviewed.
- [ ] Re-convert every lane with `--profile auto`, at one parser revision
- [ ] Re-run `python tools/discover_corpus.py --write` and review the diff to
      `signatures.json` — OCR gives 30 documents a real text layer for the first time,
      so families may legitimately move. A moved document needs a reason, not a shrug.
- [ ] Re-measure all three suites and rewrite the register below

**Gate:** every source document either converts or is refused with a family reason ·
no lane regresses against the numbers in Phase 3 · `--check` clean after `--write`

---

## Phase 3 — the anomaly register
Branch: one per invariant class

**243 hits across 37 of 103 converted editions**, measured 2026-08-29 against the JSON
currently on disk. Higher than the 157 the previous register recorded, because PR #41
added `no_chapter_caption_in_section_heading` and tightened `no_footnote_text_in_body`,
and because much of the on-disk JSON predates several parser fixes.

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
- [ ] The transport work from the previous plan, unchanged: `make sync` after
      re-conversion, a mounted corpus volume in production, and an HTTP path that
      writes `version_metrics` so the portal can show pipeline health at all

**Gate:** a parser fix merged to `main` is visible in the portal without a manual step
