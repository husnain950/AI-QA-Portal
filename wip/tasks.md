# Remediation tasks

Executable checklist for [`wip/plan.md`](./plan.md). Dependency order — do not start a
phase until the one above it passes its gate.

Baseline: `main` at `e1aae5d`. All counts below were measured with
`python tools/run_suite.py <lane>` against the JSON on disk on 2026-08-28.

**Total open anomalies: 157 invariant hits + 4 classes no invariant can see.**

> **Acts lane update (branch `fix/anomaly-footnote-binding`).** 2B and 2D are closed.
> Acts went **64 → 36** hits over **33 → 13** documents, with no invariant regressing on
> any of the 80 staged editions. 25 scanned editions were **not** re-converted (OCR needs
> the Phase 0 venv), so they still carry pre-fix JSON and their hits are unchanged rather
> than re-measured. Ordinance and rules are untouched.
>
> | Invariant | Before | After |
> |---|---|---|
> | `section_carries_its_body` | 40 | 26 |
> | `footnote_on_citing_leaf` | 14 | **0** |
> | `no_foreign_section_start_in_body` | 9 | 9 |
> | `clause_codes_plausible` | 1 | 1 |

Rules of engagement:
- Never commit to `main`. One branch and one PR per phase (see plan §How the work lands).
- Every parser fix ships with its locking case or invariant **in the same PR**.
- An anomaly is closed only when it is **fixed** or **exempted with traced evidence**.
  There is no third state. "Tracked and deferred" without an exemption entry is a red gate.
- Re-measure after every phase. Numbers in this file are a snapshot, not a promise.

---

## Phase 0 — Unblock the local stack
Branch: `fix/local-stack-and-toolchain`

- [ ] Rebuild api/worker images so they contain `alembic/versions/0003_rules_corpus.py`
      — `make build && make up`
      — *fixes:* `crx-api-1` / `crx-worker-1` crash loop, `CommandError: Can't locate
        revision identified by '0003_rules_corpus'`
- [ ] Check `.env` for a stale explicit `STORAGE_BACKEND=s3` (it overrides the new
      `filesystem` default from `e1aae5d` and keeps MinIO in the blob path)
- [ ] Rebuild `.venv` on the pinned interpreter — currently **3.14.7**, must be **3.12**
      — `rm -rf .venv && /opt/homebrew/bin/python3.12 -m venv .venv`
- [ ] Install pipeline + OCR extras
      — `.venv/bin/pip install -r apps/api/requirements-dev.txt -r packages/requirements.txt -r packages/legal_ingest/requirements-ocr.txt`
      — *fixes:* all 37 rules conversion failures (`No module named 'numpy'`)
- [ ] If any OCR pin must move for 3.12, re-pin **together with** a fresh
      `tools/acts/ocr_review.py` run (an OCR model change silently changes statutory text)

**Gate:** `make health` green · `make test` passes ·
`.venv/bin/python -c "import numpy, onnxruntime, rapidocr_onnxruntime"` clean ·
`tesseract --version` still 5.5.2 / leptonica 1.87.0

---

## Phase 1 — One parser revision across all three lanes
Branch: `fix/corpus-reconvert-all-lanes`

- [ ] **Back up first** — `make backup-remote BASE_URL=<prod>` **and** a local `pg_dump`
      (`docs/operations.md`). Re-parsing resets sign-off and flips changed leaves to
      `pending`; the database is the only thing that cannot be rebuilt.
- [ ] Tell reviewers before, not after — changed leaves revert to `pending` and every
      document's `signoff_stage` drops to `draft` (`versions.py:196`)
- [ ] Re-convert **without** `--skip-existing` (it is a bare `.exists()` test,
      `convert_all.py:483`, and cannot tell an old-parser JSON from a current one):
  - [ ] `make convert-all LANE=ordinance` → expect **16/16** (now 12, all 28 days stale)
  - [ ] `make convert-all LANE=acts` → expect **85** (now 80)
  - [ ] `make convert-all LANE=rules` → expect **36/36** (now 11; 25 never converted)
- [ ] Rebuild the provisional lane explicitly — `make convert-all LANE=acts
      ARGS='--admit-below-floor'` for the 9 files in `output/_provisional/`. Without this
      they **silently keep whatever revision last wrote them** (`convert_all.py:451`).
      *Easiest anomaly in the whole plan to skip by accident.*
- [ ] Reconcile counts: every shortfall named with a reason in `_run/report.md`.
      A document that fails to convert is an anomaly, not an absence.
- [ ] Generalise `tools/acts/audit_all.py` to take the lane as an argument (the way
      `run_suite.py` already does) — it exists only for acts today, so ordinance and rules
      cannot produce `qa-conservation.json` at all. Do **not** copy it a third time.
- [ ] Write the machine-readable reports for each lane (this is what makes Phase 3 work):
      — `python tools/run_suite.py <lane> --json data/corpora/<lane>/reports/qa-invariants.json`
      — `python tools/<lane>/audit_all.py --json data/corpora/<lane>/reports/qa-conservation.json`
- [ ] `make sync` — content-hash reconciled (`sync_acts.py:296`); record the carryover
- [ ] **Re-measure all three lanes.** Every count in Phase 2 below is provisional until
      this is done — the ordinance and rules numbers are from pre-fix JSON.

**Gate:** three lanes converted at `e1aae5d` · counts reconciled · sync carryover recorded

---

## Phase 2 — Close every anomaly

Every fix: reproduce → fix → lock with a case/invariant → `run_suite` green
(`tools/suite/README.md` working habit).

### 2A · `(cid:N)` undecodable glyphs — **743 occurrences, 5 documents**
Branch: `fix/anomaly-cid-glyphs`

Not currently visible to any invariant. `no_pua_glyphs` guards the private-use *code-point*
range; `(cid:2)` is seven ASCII characters.

- [ ] Extend `inv_no_pua_glyphs` (`_common.py:38,53`) to also match `\(cid:\d+\)` — **do
      this first**, so the fix is measurable
- [ ] Guard `normalize_text` (`pagemodel.py:46`), the single glyph choke point both
      pipelines share, so no caller can bypass it
- [ ] Make a page whose extracted text contains `(cid:` require OCR — reuse the P03
      machinery ("the embedded layer gets no vote"), do not add a new path.
      Current trigger ANDs `_page_is_scan` (image ≥50%) with `page_needs_ocr` (<200 chars);
      an undecodable-glyph page passes neither.
- [ ] **Do not attempt a ToUnicode fallback** — verified: font `BAAAAA+LinuxLibertineG`
      has a CMap with 83 `bfchar` entries and `<02>` is simply absent. Nothing to fall back to.
- [ ] Bump `ocr.CACHE_VERSION` (`ocr.py:546`) **if** recogniser arguments changed —
      the cache key is `filename:size:mtime`, blind to parser changes

Affected: `The Sales Tax Act, 1990 amended up to July 01, 2014` (705) · Customs 2008 (26) ·
2009 (8) · 2011 (2) · 2012 (2). Examples: `R(cid:2)fund of input tax`, `Omitte(cid:2)d`,
`Chapt(cid:2)r-VII`.

- [ ] Verify: `grep -c "(cid:" data/corpora/*/output/*.json` → **0**

### 2B · Footnote-zone misplacement — **14 hits** ✅ DONE (`fix/anomaly-footnote-binding`)
Branch: `fix/anomaly-footnote-zone`

**Measured, not 16.** The fix cleared 14 `section_carries_its_body` hits across 13 Sales
Tax and Federal Excise editions (40 → 26 lane-wide). The 5 "class C" hits the plan folded
in here — STA 15.9.2021 ss. 3B, 4, 5, 6, 7 — are **a different root cause** and are still
open; see 2C-bis below.

Root cause traced: `_footnote_note_marker_tops` tests only a line's **first word**. Body
line `567[omitted..] may post Officer of…` at 12.0pt qualifies because `567` is small and
left-margin and `_is_amendment_note` fires on the verb `omitted`. Zone top returns
**277.7** instead of the real rule at **589.87** — 21 body lines, all of s.40C, go to
`parse_footnotes`.

- [x] Took the line-size gate: `_line_max_size(ln) <= cal.footnote_text_max` inside
      `_is_footnote_marker_line`, the shared choke point, so `_pull_footnote_start`
      (`pagemodel.py:350`) gets it too
- [x] **Rejected** the second option (narrow rule before the marker anchor). The comment
      at `_footnote_zone_top` records why the marker anchor is deliberately first and names
      the two documents it regresses — Division XVII 31.12.2019 and Division XIV
      30.06.2020. The *docstring* is what drifted; it was corrected instead.
- [x] Verified against `pagemodel._demo` (9 self-checks) **and** the Customs
      `zone_mode="size"` path — Customs never reaches the marker branch and did not move
- [ ] Give ledger R08 a real detector: `no_footnote_text_in_body` keys on the single
      literal `"Table substituted by the Finance Act"` (`_common.py:595`) and cannot see
      the ordinance lane's **523 leaves in 12 documents**  *(still open)*
- [ ] `packages/fbr_ingest/pagemodel.py:161` is a **separate copy** with the same defect
      and drives the ordinance lane. Left alone: that lane's JSON is stale, so no honest
      before/after exists until Phase 1 re-converts it.  *(follow-up)*
- [x] Verified: STA s.40C carries its 1,153-char provision (15.9.2021), s.40D likewise

Affected: s.40C ×10 editions + s.40D (30-06-2025) · STA 15.9.2021 ss. 3B, 4, 5, 6, 7

### 2C-bis · STA 15.9.2021 ss. 3B, 4, 5, 6, 7 — **5 hits, reclassified**
Branch: unassigned

The plan filed these under 2B as "same zoning family, opening pages". **Traced with
`tools/acts/why_unbuilt.py`: it is not a zoning bug at all.** The bodies print on PDF pages
34, 34, 35, 35, 37 and *are* found there, but the section cursor has already advanced past
them (`why_unbuilt` on s.4: `exp 40 found [34, 37] cursor 606 — all 2 occurrence(s) BEFORE
cursor (blocked)`). The leaves then take their page from the TOC folio plus the calibrated
`offset=6`, which is wrong in this region — hence `start_page` 40/40/41/41/43 pointing into
s.8's text. This is the section-cursor family (ledger P06's neighbour), not `_footnote_zone_top`.

- [ ] Decide: cursor fix, or an `exemptions/acts.json` entry naming the TOC-drift defect

### 2C · Trace-then-decide — **10 hits**
Branch: `fix/anomaly-traced-residuals`

Use `tools/acts/why_unbuilt.py` (PR #34 repaired its `sys.path`, so it runs now).
Each ends as a parser fix **or** an `exemptions/acts.json` entry. No third option.

- [ ] Customs s.202B `Reward to Customs Officers and Officials` — 2022, 2023, 2024, 2025 (4)
- [ ] FEA s.43A `Issuance of duplicate of [Federal Excise] documents` — 01.07.2017, 11.03.2019 (2)
- [ ] Customs 2008 ss.181, 189 (2)
- [ ] Customs 2024 s.196K — source prints `'to Omitted 96u'` (1)
- [ ] Customs 2025 s.79 — source prints `'A O mitted'` (1)

### 2D · `footnote_on_citing_leaf` — **14 hits, one bug** ✅ DONE (`fix/anomaly-footnote-binding`)
Branch: `fix/anomaly-orphan-footnote-adoption`

**The plan's diagnosis was wrong.** `adopt_orphan_footnotes` picking the first
page-covering leaf is not the cause — it is the completeness net that catches what the
citation loop drops, and it needed no change. The cause is in `_build_one`: its
citing_page+1 lookup (A20) reads the raw page index, while the rendered `<sup>` resolves
the same marker through `footnote_map`, the run-merged view that keeps one note per marker.
Where the next page prints a marker the run already bound elsewhere, the two disagree and
the leaf holds a note it never cited.

- [x] Require the note the citation resolved to be **among** the next page's candidates
      before accepting any of them
- [x] Membership, not identity — page 97 of Customs 30-06-2014 prints marker `4` twice and
      s.83A cites it once, so both notes are s.83A's. An identity test orphaned the second
      and cost 4 new failures on 4 editions.
- [x] Collector branch left alone — filtering it the same way detached 18 notes across 15
      Customs editions. Both figures measured, not predicted.
- [x] Verified: **14 → 0** across all 80 staged editions, no document regressed

### 2D-bis · `no_foreign_section_start_in_body` (acts) — **9 hits, 9 documents**
Branch: folded into 2B/2C, whichever fix moves the leaf

The companion invariant to `section_carries_its_body`: that one names the *starved* leaf,
this one names the *thief* holding its text. The two usually clear together — a body-binding
fix that gives the victim its text also removes the foreign start from the thief — but they
are counted separately and must be **verified** separately, not assumed.

- [x] Re-ran after 2B and 2D landed: **9 → 9, unchanged.** The two invariants did *not*
      clear together here — each residual still needs its own trace.
- [ ] Customs 30.06.2019, 30.06.2020, 30.06.2021, 30.06.2022, 30.06.2023, 30.06.2024,
      30th June 2025 (1 each) · STA 15.9.2021 (1) · +1
- [ ] Each residual ends as a parser fix or an `exemptions/acts.json` entry — no third option

### 2E · `clause_codes_plausible` / ledger P06 — **1 hit + 1 silent miss**
Branch: `fix/anomaly-clause-cursor`

- [ ] Finance Act 2024 fails today — fix or exempt
- [ ] **Finance Act 2025 passes while missing clauses 1, 3 and 5** — it emits codes
      `2,4,6,7,8,9,10,11,12,13` and does not trip the invariant (opens at ≤3, no gap >8).
      Widen the invariant to catch a gap at the *start* of a flat act's run.
- [ ] Address the cause: quoted insertions and tariff rows parse as ordinary dot-form
      section starts (ledger's "top remaining Phase-2 item")

### 2F · Rules lane — **88 hits, and 25 unconverted documents**
Branch: `fix/anomaly-rules-lane`

- [ ] **Re-measure after Phase 1** — most of the 88 predate the fix and 25 documents have
      never been converted at all, so the true count is unknown
- [ ] `section_carries_its_body` 78 hits / 6 docs
- [ ] `no_foreign_section_start_in_body` 10 hits / 4 docs
- [ ] Ledger **R07** (duplicate rule numbering in compilations — Customs Rules 2001 has it
      on 43 of 62 leaves) needs an "instrument" tree level above `chapter`. If deferred
      again, defer it **in writing** as an exemption with its reason — not as a red gate.
- [ ] Re-check the 8 existing entries in `exemptions/rules.json`; the suite reports a
      stale exemption, and a stale one gets deleted

### 2G · Exemption files for the other two lanes
Branch: folded into the phase that needs it

- [ ] Create `tools/suite/exemptions/acts.json` (does not exist)
- [ ] Create `tools/suite/exemptions/ordinance.json` (does not exist)
- [ ] Every entry clears the documented bar (`tools/suite/README.md:188`): *the invariant
      is right and the document is genuinely outside what the pipeline can read today,
      traced to the source PDF first — never that a check is inconvenient*
- [ ] `tools/tests/test_suite_exemptions.py` enforces each `applies_to` matches **exactly
      one** staged document

### 2H · Put the anomaly ledger under version control — **not optional**
Branch: `docs/anomaly-ledger`

`data/corpora/acts/reports/anomalies.md` is 668 lines / 149 KB, is the audit trail for a
legally binding corpus, and is **gitignored** (`.gitignore:31`).

- [ ] Move to `docs/anomaly-ledger.md` (or `tools/suite/ledger/`) and commit it
- [ ] Fix the dangling references that already point into it: 20 cases in
      `tools/suite/cases/acts.json` carry `"source": "reports/anomalies.md O0x/R0x"`, and
      `invariants/acts.py:58`, `rules.py:84`, `pagemodel.py:486`, `disposition.py:3` all
      cite ledger row ids
- [ ] It contains diagnoses, not corpus text — nothing private ships with it

**Phase 2 gate:** `python tools/run_suite.py <lane>` green on all three lanes, with every
residual carrying a traced exemption entry.

---

## Phase 3 — Make the portal show pipeline health
Branch: `feat/portal-pipeline-health`

No new UI. `apps/web/src/utils/versionHealth.js` and `components/ui/QualityMetrics.jsx`
already render invariant counts, conservation percentages and a version-over-version
delta. Only the data path is missing.

- [ ] Confirm the loop closes with **no code change** once Phase 1 step "write reports"
      is done — `make sync` already passes `--metrics` and `acts_metrics.ingest` already
      reads both report files
- [ ] **Surface exemptions, or they vanish exactly where they matter most.** `runner.run`
      moves an exempted invariant into `results["exempt_invariants"]` (`runner.py:71-75`)
      and `acts_metrics.read_invariants` reads only `results["invariants"]` — so a
      document with a traced source defect renders as **`invariants 54/54`, a clean green
      badge**, and the reviewer never learns the defect exists. Carry
      `exempt_invariants` (name + reason) through `acts_metrics.ingest` into
      `version_metrics.detail` and render it beside the badge.
- [ ] Emit each exemption as a `source_defect` finding — `disposition.py` already defines
      it as *"PDF itself is wrong; parse is faithful; **lawyer must be told**"* and its
      docstring already says it mirrors `anomalies.md`. This is the link that makes
      "the lawyer must be told" actually happen.
- [ ] Make the reports a by-product of the gate, not a remembered chore: `make gate`
      (or `convert-all`) always writes both report files, so an unmeasured conversion
      cannot happen

**Gate:** open a re-parsed document → corrected text · `invariants 55/55` · any exemption
named with its reason · a `metricsDelta` row quantifying what PR #34 bought

---

## Phase 4 — Give production a real corpus
Branch: `feat/prod-corpus-volume`

Production mounts one volume, `crx-api-data` at `/app/data`. There is no mount at
`/data/corpus/*`, so `corpus_root_configured()` is false and `POST /api/corpus/sync`
returns 400. `e1aae5d` helps: `crx-web` now shares that volume and it is now the canonical
blob store.

- [ ] Mount the corpus **inside the existing volume** at `/app/data/corpus/<lane>`;
      point `CORPUS_ORDINANCE` / `CORPUS_ACTS` / `CORPUS_RULES` there
- [ ] Re-verify the security boundary: nginx serves only
      `^/uploads/(pdf|json|evidence|render)/[0-9a-f]{64}\.(pdf|json|zip|png)$`
      (`apps/web/nginx.conf:35`) and 404s everything else under `/uploads/` without
      touching disk. `/app/data/corpus/` is not under `/uploads/` and has no matching
      `location`, so the source PDFs are **not** published. Re-check after any nginx change.
- [ ] Size it: corpus **959 MB** (acts 468 · rules 345 · ordinance 146) + blobs ~1 GB
      ≈ **2 GB of 6 GB**. The blob store is append-only, so each full re-parse adds
      ~**181 MB** and never reclaims it — ~20 cycles of headroom.
- [ ] Plan retention for superseded version blobs — they are still referenced by
      `document_versions` history and cannot be deleted blindly
- [ ] Add admin-gated `POST /api/v2/corpus/files` (lane + relative path + file) and
      `tools/push_corpus_files.py` that uploads only what is absent or hash-different.
      **Validate every path against the lane root** — a `..` must be rejected, not normalised.
- [ ] Ship `reports/qa-invariants.json` to the volume so `POST /api/corpus/sync`
      (already defaults `metrics: true`, `routes/corpus.py:47`) lights up prod badges
- [ ] ⚠️ **Adopt the existing rows — do not create duplicates.** Prod's documents came
      from `push-remote` as `source_type='upload'`, `source_key=NULL`. A corpus sync looks
      up `WHERE source_type=? AND source_key=?` (`sync_acts.py:285`), finds nothing, and
      inserts a **second copy of all 80 documents**, stranding every reviewer verdict.
      One-time script: match by `name`, set `source_type='acts_corpus'`,
      `source_key=<json stem>`, `corpus_lane=<lane>`, **keep the existing `id`** (works
      because `sync_acts.py:291` uses `existing["id"]` when a row is found).
  - [ ] Run `corpus_sync.source_key_collisions()` (`corpus_sync.py:59`) before writing
  - [ ] **Dry-run against a restored `pg_dump` first** — the only irreversible step in
        this plan
- [ ] Retire or wire the dead seed path — `SEED_CORPUS_*` has zero readers,
      `Corpus.seed_path()` (`corpus_registry.py:89`) is never called, `make seed-archive`
      skips rules, and `data/seed/` holds 586 MB of stale 2026-08-10 artifacts.
      Delete it or implement it — not both.

**Gate:** prod document count did **not** double, verified against a restored dump, and a
known reviewer verdict survived

---

## Phase 5 — Make the loop hold
Branch: `chore/gate-and-docs`

- [ ] **Make the gate able to go red.** `tools/run_tests_smoke.py` treats a missing corpus
      as SKIP and the corpora are gitignored, so CI gates package self-checks and nothing
      else. Cheapest first: a `make gate` required before `push-remote` with committed
      report files → a scheduled run on the corpus machine publishing `qa-invariants.json`
      → a self-hosted runner with the corpus mounted.
- [ ] Extend `tools/fixture_corpus.py` so the committed micro-corpus reproduces one
      instance of each anomaly class (misattributed body, misplaced footnote zone,
      `(cid:N)`). Today `make seed-fixtures` builds 3 clean acts that can never fail anything.
- [ ] Fix the stale docs that caused this misunderstanding:
  - [ ] `AGENTS.md:96` — "All three lanes are green against a staged corpus"; measured,
        **43 of 103 documents fail**
  - [ ] `.gitignore:43` and `.env.example:47` reference `make deploy-prod`, which no longer exists
  - [ ] `data/seed/README.md:3` claims auto-seed-on-boot; line 48 and `runtime.py:20` say the opposite
  - [ ] `apps/api/Dockerfile:23` — same false auto-seed claim
- [ ] State the contract in `README.md`: a parser fix reaches reviewers only via
      **convert → measure → sync → push**. Merging is step zero, not the last step.

---

## Final verification (end to end, in order)

- [ ] `make health` → ready; api and worker no longer restarting
- [ ] `.venv/bin/python -V` → 3.12.x; OCR imports clean
- [ ] `make convert-all LANE=<lane>` → ordinance 16/16 · acts 85 · rules 36/36,
      zero unexplained failures in `_run/report.md`
- [ ] `python tools/run_suite.py <lane>` → `RESULT: ALL PASS` on all three, or every
      residual named in `exemptions/<lane>.json` with a traced reason
- [ ] `grep -c "(cid:" data/corpora/*/output/*.json` → **0**
- [ ] STA s.40C carries its ~1,400-char provision
- [ ] **Regression guard:** Customs 2007 s.14A still carries its 468 chars (the PR #34
      case — it must not regress)
- [ ] `make sync` → carryover reported
- [ ] Portal: corrected text · `invariants 55/55` · exemptions named · `metricsDelta` row
- [ ] `cd apps/web && npm run smoke` → PDF canvas non-blank, parsed pane has content
- [ ] Prod: push corpus files → `POST /api/corpus/sync` → verify against a restored dump
      that the document count did not double and a known verdict survived
