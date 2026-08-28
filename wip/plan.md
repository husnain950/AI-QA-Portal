# Pipeline → Portal: close the loop, then close every anomaly

## Context

PR #34 (`f1f29c0`, merged as `5b30ee8`) fixed section-body misattribution in the Acts
pipeline. The portal still shows the old text. **The fix is not broken — it never
travelled.**

*Re-checked against `main` at `e1aae5d` (PR #35, "Serve PDFs as static assets"). That
commit touches transport only — `apps/web/nginx.conf`, `middleware/security.py`,
`blob_store.py`, and the deploy configs. **It touches no file under `packages/` or
`tools/`**, so every measurement below still stands. It does change two things this plan
depends on, both in our favour, and they are folded into Phase 0 and Phase 4.*

Proven on this machine: `data/corpora/acts/output/Customs Act ,1969 (Amended upto 30th
June 2007).json` already carries the corrected parse — s.14A holds its own 468-char
provision instead of a heading-only stub. The corrected JSON is sitting on disk. It has
not reached the database, and the database is not what production is serving either.

Five independent breaks sit between a merged parser fix and a reviewer's screen. Every
one is confirmed by reading the code, not inferred:

| # | Break | Evidence |
|---|---|---|
| 1 | **The local API and worker are in a crash loop.** Nothing can display anything. | `docker ps`: `crx-api-1 Restarting (3)`, `crx-worker-1 Restarting (1)`. Logs: `alembic.util.exc.CommandError: Can't locate revision identified by '0003_rules_corpus'`. The images are 7 days old and predate `apps/api/backend/alembic/versions/0003_rules_corpus.py`; Postgres already records that revision. |
| 2 | **`make sync` was never run after the re-conversion.** The corrected JSON is on disk only. | Sync is the only writer of section rows: `tools/sync_corpus.py` → `corpus_sync.sync_one` → `sync_acts.run_sync` → `versions.create_version` → `document_store.apply_parsed_document`. |
| 3 | **CI/CD ships code, never data.** Merging to `main` cannot regenerate a corpus. | `.github/workflows/deploy-northflank.yml` runs exactly two commands (`northflank_deploy.py check`, `deploy --sha`). `convert_all`, `convert.py`, `sync_corpus`, `seed-archive` appear in **zero** workflow files. |
| 4 | **Production has no corpus at all, and the "auto-seed" that was supposed to give it one is dead code.** | `apps/api/Dockerfile:26` `COPY data/seed/ /seed/corpus/` — but `data/seed/*` is gitignored and Northflank builds from git via kaniko, so the image gets 4 placeholder files. And `Corpus.seed_path()` (`corpus_registry.py:89`) has **zero callers**: `SEED_CORPUS_*` is set in four places and read by nobody. `runtime.py:20` states boot is deliberately read-only. |
| 5 | **Production can never show pipeline health, by construction.** | Prod was filled by `make push-remote`, which creates `source_type='upload'` with `source_key=NULL` (`routes/documents.py:331,378`). `acts_metrics.ingest` matches documents by `source_key`, so every row is `unmatched`. There is also no HTTP endpoint that writes `version_metrics` at all. |

Break 5 is the literal answer to *"if we fix something in the Pipeline the changes should
reflect on our portal."* The portal **already has** the UI for exactly that —
`apps/web/src/utils/versionHealth.js` renders `invariants 54/55`, body/footnote
conservation, and a version-over-version `metricsDelta` ("what did the fix buy us").
Nothing feeds it. No new UI is needed; the data path is missing.

Underneath the plumbing, the corpus is not at one parser revision and is not complete:

| Lane | Source PDFs | Converted | State |
|---|---|---|---|
| acts | 85 | 80 (+9 `_provisional`) | **post-fix** (converted 15:32, from the working tree that became `f1f29c0`) |
| ordinance | 16 | 12 | **28 days stale** (all 12 JSONs mtime `2026-07-30 19:25:42`), 4 PDFs never converted |
| rules | 36 | 11 | **pre-fix**, 37 of 48 conversions failed |

Every rules failure has one cause: `RuntimeError: OCR failed on page N … No module named
'numpy'` (`data/corpora/rules/output/_run/report.md`). The OCR extras were never
installed, and `.venv` is **Python 3.14.7** while `pyproject.toml` requires 3.12 and both
CI and the container run 3.12. Tesseract 5.5.2 / leptonica 1.87.0 *is* installed and
matches `requirements-ocr.txt` exactly.

**Decisions taken (yours, recorded here so the work is unambiguous):**
1. Production gets a **mounted corpus volume** and runs the real sync itself.
2. **All three lanes** are rebuilt at the merged commit.
3. Every anomaly is **classified, then fixed or exempted with traced evidence** — the
   repo's own documented bar (`tools/suite/README.md:188`).
4. `(cid:N)` gets a **hard invariant plus OCR of the affected pages**.

---

## The anomaly register — all 157 measured hits, nothing omitted

Measured just now with `python tools/run_suite.py <lane>` against the JSON currently on
disk. This is the ground truth the roadmap has to drive to zero-or-exempted.

### Acts — 64 hits across 33 of 80 documents

| Invariant | Hits | Docs |
|---|---|---|
| `section_carries_its_body` | 40 | 20 |
| `footnote_on_citing_leaf` | 14 | 11 |
| `no_foreign_section_start_in_body` | 9 | 9 |
| `clause_codes_plausible` | 1 | 1 (Finance Act 2024) |

The 40 `section_carries_its_body` hits break into seven classes, each with a known cause:

| Class | n | Where | Root cause | Disposition |
|---|---|---|---|---|
| **A. `(cid:2)` font decoding** | 11 | Sales Tax Act 1990 (July 01 2014) — ss. 3AA, 10, 15, 16, 17, 18, … | Font `BAAAAA+LinuxLibertineG` ships a ToUnicode CMap with 83 `bfchar` entries and **`<02>` is simply absent**. pdfminer emits the literal `(cid:2)`. The glyph is `e`. | Fix via OCR (§Phase 2A) |
| **B. Footnote-zone misplacement (STA s.40C/40D)** | 11 | s.40C in 10 STA editions + s.40D in 30-06-2025 | `_footnote_zone_top` anchors on `_footnote_note_marker_tops`, which tests only the **first word** of a line. Body line `567[omitted..] may post Officer of…` at 12.0pt qualifies because `567` is small and left-margin and `_is_amendment_note` fires on the verb `omitted`. Zone top returns **277.7** instead of the real rule at **589.87**; 21 body lines — all of s.40C — are handed to `parse_footnotes`. | Parser fix (§Phase 2B) |
| **C. STA 15.9.2021 opening block** | 5 | ss. 3B, 4, 5, 6, 7 | Same zoning family, opening pages. | Parser fix (§Phase 2B) |
| **D. Customs s.202B** | 4 | 2022, 2023, 2024, 2025 | `Reward to Customs Officers and Officials` — untraced. | Trace first (§Phase 2C) |
| **E. FEA s.43A** | 2 | 01.07.2017, 11.03.2019 | `Issuance of duplicate of [Federal Excise] documents` — untraced. | Trace first (§Phase 2C) |
| **F. Pre-fix parses (ledger R10)** | 3 | PFM 2019 s.26; PSW 2021 ss.27, 28 | These documents could not be regenerated on an OCR-less host, so they still carry the **pre-fix** parse. | Disappears on re-conversion (§Phase 1) |
| **G. Customs source oddities** | 4 | 2008 ss.181/189; 2024 s.196K (`'to Omitted 96u'`); 2025 s.79 (`'A O mitted'`) | Malformed omission markers in the source. | Trace first (§Phase 2C) |

`footnote_on_citing_leaf` — **all 14 are one bug, not eleven.** Every failure has the
identical shape: the note is attached to the leaf *immediately preceding* the one that
cites it (`46.5 attached to 43 but cited by 45A`, `85.3 attached to 49A but cited by 50`,
…). `builder.adopt_orphan_footnotes` (`builder.py:2312`) attaches an uncited note to the
first leaf whose `start_page..end_page` covers the note's page; an inflated span on the
previous section wins the race. `builder.py:2981` already carries a comment flagging
exactly this.

### Ordinance — 5 hits across 4 of 12 documents

`section_carries_its_body` 5 / 4 docs. **Measured on 28-day-old, pre-fix JSON — this
number is not trustworthy until Phase 1 re-converts the lane.**

### Rules — 88 hits across 6 of 11 documents

| Invariant | Hits | Docs |
|---|---|---|
| `section_carries_its_body` | 78 | 6 |
| `no_foreign_section_start_in_body` | 10 | 4 |

Plus 8 existing exemptions in `tools/suite/exemptions/rules.json` (still run, still
counted, just not gating). And **25 of 36 rules PDFs have never been converted at all**,
so this lane's true hit count is unknown until Phase 1.

### Anomalies no invariant can currently see

These do not appear in the 157 and would be silently shipped:

| ID | Anomaly | Size | Why it is invisible |
|---|---|---|---|
| **R09** | `(cid:N)` undecodable glyphs rendered as statutory text | **743 occurrences in 5 acts documents** (705 in STA 2014 alone: `R(cid:2)fund of input tax`, `Omitte(cid:2)d`, `Chapt(cid:2)r-VII`) | Zero `cid` handling exists in `packages/`, `tools/` or `apps/api/`. `no_pua_glyphs` guards the private-use *code-point* range; `(cid:2)` is seven ASCII characters. |
| **R08** | Footnote-zone misplacement, document-wide | acts 49 leaves / 21 docs; **ordinance 523 leaves / 12 docs** | `no_footnote_text_in_body` keys on the single literal string `"Table substituted by the Finance Act"` (`_common.py:595`). `audit_completeness` unions body+footnotes on its footnote side, so a body line filed as a footnote still counts as "conserved". |
| **R07** | Duplicate rule numbering in compilations | Customs Rules 2001 (43 of 62 leaves); FE Rules 2005 (rules 1–4 twice) | The tree has no level above `chapter` for "instrument". Currently absorbed by two `section_codes_ordered` exemptions. |
| **P06** | Finance Act clause cursor absorbs amended instruments' section numbers and tariff rows | Ledger's "top remaining Phase-2 item" | Partly caught now: `clause_codes_plausible` fires on Finance Act 2024. Finance Act 2025 currently emits codes `2,4,6,7,8,9,10,11,12,13` — **clauses 1, 3 and 5 are missing** and it does not trip the invariant (opens at ≤3, no gap >8). |
| — | Conservation is unmeasured | `qa-conservation.json` last written 2026-08-10 | `tools/<lane>/audit_completeness.py` / `audit_all.py` re-read every source PDF and are run by hand. |

---

## Phase 0 — Unblock the local stack

Nothing else can be verified while the API is down.

1. `make build && make up` — rebuild the api/worker images so they contain
   `alembic/versions/0003_rules_corpus.py`. Confirm with `make health`
   (`/health/ready` reports the Alembic revision).
   Rebuilding now also picks up `e1aae5d`, which changed the storage default:
   `docker-compose.yml` moved `STORAGE_BACKEND` from `s3` to `filesystem`, the API image
   no longer bakes `s3`, and an **empty** `STORAGE_BACKEND` is now treated as unset rather
   than crashing `get_storage()`. Check the local `.env` — a stale explicit
   `STORAGE_BACKEND=s3` there still overrides the new default and keeps MinIO in the path.
2. Rebuild the virtualenv on the **pinned** interpreter and install the OCR extras:
   ```bash
   rm -rf .venv && /opt/homebrew/bin/python3.12 -m venv .venv
   .venv/bin/pip install -r apps/api/requirements-dev.txt \
                         -r packages/requirements.txt \
                         -r packages/legal_ingest/requirements-ocr.txt
   ```
   `requirements-ocr.txt` pins `numpy==2.5.1`, `onnxruntime==1.28.0`,
   `opencv-python==5.0.0.93`; those pins were measured on Python 3.13 and several have no
   3.14 wheels — this is why the rules lane died. Tesseract is already correct.
3. `.venv/bin/python -c "import numpy, onnxruntime, rapidocr_onnxruntime"` must succeed,
   and `tesseract --version` must still report 5.5.2 / leptonica 1.87.0 (the pins are
   deliberate: *"an OCR model change silently changes the text of a statute"*).

**Gate:** `make health` green, `make test` passes.

## Phase 1 — Put all three lanes on one parser revision

Order matters: convert → measure → sync. Never sync an unmeasured corpus.

1. **Back up first.** `make backup-remote BASE_URL=<prod>` and a local `pg_dump`
   (`docs/operations.md`). Re-parsing resets sign-off and flips changed leaves to
   `pending`; the database is the one thing that cannot be rebuilt.
2. **Re-convert every lane, from source, with no `--skip-existing`:**
   ```bash
   make convert-all LANE=ordinance
   make convert-all LANE=acts
   make convert-all LANE=rules
   ```
   `--skip-existing` is a bare `out_path(p).exists()` test (`convert_all.py:483`) — it
   cannot tell a JSON written by an old parser from a current one. Using it here would
   re-create exactly the mixed-revision corpus we are trying to eliminate.
3. **Rebuild the provisional lane explicitly.** `make convert-all LANE=acts
   ARGS='--admit-below-floor'` for the 9 documents under `output/_provisional/`. Those
   files are *not* produced by an ordinary run, so without this flag they **silently keep
   whatever revision last wrote them** (`convert_all.py:451`). This is the single easiest
   anomaly to skip by accident.
4. **Reconcile the counts.** Expect ordinance 16/16, acts 85 (+ provisional), rules 36/36.
   Every shortfall must land in `_run/report.md` with a named reason — a document that
   fails to convert is an anomaly, not an absence.
5. **Write the machine-readable reports** (this is what makes Phase 3 possible):
   ```bash
   python tools/run_suite.py <lane> --json data/corpora/<lane>/reports/qa-invariants.json
   python tools/acts/audit_all.py --json data/corpora/acts/reports/qa-conservation.json
   ```
   Note the asymmetry: `audit_all.py` (the many-edition conservation gate that writes
   `qa-conservation.json`) exists **only** under `tools/acts/`. `tools/ordinance/` has
   just `audit_completeness.py` (one document at a time) and `tools/rules/` has neither.
   So ordinance and rules can produce invariant badges but not conservation badges until
   `audit_all.py` is generalised the way `run_suite.py` already was — one runner, lane as
   an argument. Do that rather than copying the file a third time.
6. `make sync` — content-hash reconciled (`sync_acts.py:296`), so unchanged documents are
   a no-op. Changed leaves reset to `pending` and annotations re-anchor
   (`document_store.py:236`, `:367`); orphaned annotations keep a 4,000-char snapshot.

**Gate:** all three lanes converted at `5b30ee8`, hit counts re-measured, `make sync`
reports its carryover.

## Phase 2 — Close every anomaly

Every fix lands with its check in the same change (`tools/suite/README.md` working habit):
reproduce → fix → lock with a case or invariant → `run_suite` green.

### 2A. `(cid:N)` — invariant, then OCR
- Extend `inv_no_pua_glyphs` (`_common.py:38,53`) to also match `\(cid:\d+\)`. This is
  ledger R09's own proposed next step and turns 743 silent corruptions into a loud
  failure. Do this **first** so the fix is measurable.
- Then make a page whose extracted text contains `(cid:` require OCR. This reuses the
  machinery ledger **P03** already built for the same class of problem ("the embedded
  layer gets no vote — two scorable engines decide"), rather than adding a new path.
  The trigger currently ANDs `_page_is_scan` (image ≥50% of page) with
  `page_needs_ocr` (<200 chars); an undecodable-glyph page passes neither.
- **Do not attempt a ToUnicode fallback.** It was checked: the CMap exists and the entry
  is absent. There is nothing to fall back to.
- Guard `normalize_text` (`pagemodel.py:46`) — the single glyph choke point both
  pipelines share — so the fix cannot be bypassed by a caller.

### 2B. Footnote-zone misplacement (classes B, C; ledger R08)
Two candidate one-line root-cause fixes, both covering all 11 STA leaves at once:
- Require the marker **line** to be footnote-sized
  (`_line_max_size(ln) <= cal.footnote_text_max`). `_footnote_note_marker_tops` already
  applies exactly this test to the *next* line (`pagemodel.py:269`) but not to the marker
  line itself.
- Or make the code match its own docstring: `_footnote_zone_top`'s docstring
  (`pagemodel.py:419`) says the marker anchor is a **fallback used only when no narrow
  rule is found**, but the code consults `note_tops` first, unconditionally. Here a narrow
  rule *was* found (589.87) and ignored. This is the same documented-vs-implemented drift
  class that PR #34 fixed in `_DOTFORM_RE`.

Verify against `pagemodel._demo` and the Customs `zone_mode="size"` path before
committing — `_is_footnote_marker_line`'s callers are shared across lanes.

Then give R08 a real detector, because `no_footnote_text_in_body` currently keys on one
hard-coded string and cannot see the ordinance lane's **523 leaves in 12 documents**.

### 2C. Trace-then-decide (classes D, E, G — 10 hits)
Customs s.202B ×4, FEA s.43A ×2, Customs source oddities ×4. Use
`tools/acts/why_unbuilt.py` (PR #34 repaired its `sys.path`, so it runs now) to get the
per-TOC-entry reason. Each one ends as **either** a parser fix **or** an
`exemptions/acts.json` entry naming the traced source defect. No third option.

### 2D. `footnote_on_citing_leaf` — one bug, 14 hits
Constrain `adopt_orphan_footnotes` (`builder.py:2312`) so an inflated `end_page` cannot
out-rank the leaf that actually renders the citation: prefer a covered leaf that cites the
ref, and fall back to page-span only when none does.

### 2E. `clause_codes_plausible` / P06
Finance Act 2024 fails today. Finance Act 2025 **passes while missing clauses 1, 3 and 5**
— confirmed by reading its JSON. Widen the invariant to catch a gap at the *start* of a
flat act's run, then address the clause-cursor cause (quoted insertions and tariff rows
parse as ordinary dot-form section starts).

### 2F. Rules lane (78 + 10 hits, and 25 unconverted documents)
Re-measure after Phase 1 — most of the 88 predate the fix. Ledger **R07** (duplicate
numbering in compilations) needs the "instrument" tree level and is a design change; if it
is deferred again, it must be deferred **in writing** as an exemption with its reason, not
left as a red gate.

### 2G. Create `tools/suite/exemptions/acts.json` and `ordinance.json`
Neither exists. Every exemption must clear the documented bar — *the invariant is right
and the document is genuinely outside what the pipeline can read today, traced to the
source PDF first, never that a check is inconvenient* — and
`tools/tests/test_suite_exemptions.py` enforces that each `applies_to` matches **exactly
one** staged document.

### 2H. Put the ledger under version control — **this one is not optional**
`data/corpora/acts/reports/anomalies.md` is 668 lines / 149 KB, is the audit trail for a
legally binding corpus, and is **gitignored**. It is already load-bearing: 20 cases in
`tools/suite/cases/acts.json` carry `"source": "reports/anomalies.md O0x/R0x"`, and
`tools/suite/invariants/acts.py:58`, `rules.py:84`, `pagemodel.py:486` and
`disposition.py:3` all cite ledger row ids. Those are dangling references into an
untracked file. Move it to `docs/anomaly-ledger.md` (or `tools/suite/ledger/`) and commit
it. It contains diagnoses, not corpus text, so nothing private ships with it.

**Gate:** `python tools/run_suite.py <lane>` green on all three lanes, with every
non-green hit carrying a traced exemption entry.

## Phase 3 — Make the portal show pipeline health

No new UI. `apps/web/src/utils/versionHealth.js` and
`apps/web/src/components/ui/QualityMetrics.jsx` already render invariant counts,
conservation percentages and a version-over-version delta. The data path is what is
missing.

- `make sync` already passes `--metrics`, and `acts_metrics.ingest` already reads
  `reports/qa-invariants.json` + `reports/qa-conservation.json`. Phase 1 step 5 writes
  them. Locally this closes the loop with **no code change** — that is why step 5 is in
  Phase 1 rather than here.
- Make the reports a by-product of the gate rather than a remembered chore: have
  `make convert-all` (or a `make gate` target) always write both report files, so a
  conversion that is not measured cannot happen.

- **Surface exemptions, or they vanish exactly where they matter most.** `runner.run`
  moves an exempted invariant out of `results["invariants"]` into
  `results["exempt_invariants"]` (`runner.py:71-75`), and `acts_metrics.read_invariants`
  reads only the former. So a document with a traced source defect would render as
  **`invariants 54/54` — a clean green badge** — and the reviewer would never learn the
  defect exists. For a legally binding corpus that is the worst possible failure mode: the
  exemption mechanism is honest at the CLI and silently reassuring in the UI.
  Fix by carrying `exempt_invariants` (name + reason) through `acts_metrics.ingest` into
  `version_metrics.detail`, and rendering it beside the badge.

  The portal already has the right vocabulary for this and it already points at the
  ledger: `apps/api/backend/services/disposition.py` defines `source_defect` — *"PDF
  itself is wrong; parse is faithful; **lawyer must be told**"* — and its docstring says
  it "mirrors Acts_fbr anomalies.md". A suite exemption **is** a `source_defect`. Emitting
  one as a `source_defect` finding on the affected document is the link that makes "the
  lawyer must be told" actually happen, using machinery that already exists on both sides.

**Gate:** open a re-parsed document in the portal and see `invariants 55/55`, see any
exemption named with its reason rather than hidden, and see the `metricsDelta` line
quantifying what PR #34 bought.

## Phase 4 — Give production a real corpus (your chosen path)

Production today mounts exactly one volume, `crx-api-data` at `/app/data`
(`northflank.template.json:39`). There is **no** mount at `/data/corpus/*`, so
`corpus_root_configured()` is false and `POST /api/corpus/sync` returns 400.

`e1aae5d` makes this phase easier and safer than it was when the plan was drafted:
`crx-web` is now attached to that same volume, and the volume is now the **canonical**
blob store (`STORAGE_BACKEND` defaults to the local-disk backend). One shared volume is
now the established pattern rather than a change of direction.

1. **Mount the corpus inside the existing 6 GB volume** — `/app/data/corpus/<lane>` — and
   point `CORPUS_ORDINANCE` / `CORPUS_ACTS` / `CORPUS_RULES` there. This needs no new
   volume and no template restructure; the volume is already `ReadWriteOnce`, is now
   attached to all three services, and its writability is proven by the blob store. It
   also already carries non-blob working directories (`.staging/`, `.cache/`,
   `.preflight/`), so a `corpus/` sibling is precedent, not novelty.

   **Confirmed not web-exposed.** nginx serves only paths matching
   `^/uploads/(pdf|json|evidence|render)/[0-9a-f]{64}\.(pdf|json|zip|png)$`
   (`apps/web/nginx.conf:35`), and *everything else* under `/uploads/` gets a plain 404
   that never touches disk. `/app/data/corpus/` is not under `/uploads/` at all and has no
   `location` matching it, so putting the corpus on the shared volume does **not** publish
   the source PDFs. Re-verify this after any nginx change — it is the security boundary
   the commit message itself names.

   **Size it before mounting.** Sync **requires the source PDF on disk**
   (`sync_acts.discover_acts_repo:154` pairs by exact `metadata.filename` and never
   guesses), so PDFs, JSON and `reports/` must all fit alongside the blobs:

   | On the volume | Size |
   |---|---|
   | Corpus (all 3 lanes: PDFs + JSON + reports) | acts 468 MB, rules 345 MB, ordinance 146 MB — **959 MB** |
   | Blob store today (`data/uploads`) | 493 MB |
   | Blob store after all 3 lanes sync (one PDF blob each, ~778 MB of PDFs + JSON) | ~1 GB |
   | **Steady state** | **~2 GB of 6 GB** |

   The headroom is real but finite, and it shrinks on a schedule: the blob store is
   **content-addressed and append-only**, so every re-parse writes a *new* JSON blob for
   every changed document and never reclaims the old one — roughly **181 MB per full
   re-parse cycle** (the size of all `output/*.json`). That is about 20 cycles of headroom.
   Plan a retention story for superseded version blobs before it becomes an incident,
   noting that old blobs are still referenced by `document_versions` history and cannot be
   deleted blindly.
2. **Add an admin-gated file-transfer route** (`POST /api/v2/corpus/files`, lane +
   relative path + file) and a `tools/push_corpus_files.py` that walks a local lane
   directory and uploads only what is absent or hash-different. Validate every path
   against the lane root before writing — this is a trust boundary; a `..` in a
   relative path must be rejected, not normalised.
3. **Then prod runs the real thing:** `POST /api/corpus/sync` already enqueues the worker
   job and already defaults `metrics: true` (`routes/corpus.py:47`), so shipping
   `reports/qa-invariants.json` to the volume makes the health badges appear in
   production. This is the piece that has never existed.
4. **Adopt the existing rows — do not create duplicates.** Prod's documents came from
   `push-remote` as `source_type='upload'`, `source_key=NULL`. A corpus sync looks up
   `WHERE source_type=? AND source_key=?` (`sync_acts.py:285`), finds nothing, and inserts
   a **second** copy of all 80 documents — stranding every reviewer verdict and annotation
   on the orphaned originals.
   The safe reconciliation is a one-time script matching by `name` and setting
   `source_type='acts_corpus'`, `source_key=<json stem>`, `corpus_lane=<lane>` while
   **keeping the existing `id`**. That works because `sync_acts.py:291` uses
   `existing["id"]` when a row is found and only mints the deterministic uuid5 for
   inserts. Run `corpus_sync.source_key_collisions()` (`corpus_sync.py:59`) before
   writing — it raises before any write if two stems collide.
   Dry-run it against a restored `pg_dump` first. This step is where review state can be
   lost, and it is the only step in the plan that can lose it irreversibly.
5. Retire the dead seed path or make it real: `SEED_CORPUS_*` has no reader,
   `make seed-archive` covers only ordinance+acts (never rules), and
   `data/seed/README.md:3` still claims auto-seed-on-boot while `runtime.py:20` and the
   same README at line 48 say the opposite. Delete `data/seed/` (586 MB of stale
   `2026-08-10` artifacts) and its dead env vars, or wire it — but not both.

## Phase 5 — Make the loop hold

Everything above is a one-time repair. This is what stops the drift returning.

1. **The gate must be able to go red.** `tools/run_tests_smoke.py` treats a missing corpus
   as SKIP, and the corpora are gitignored, so CI gates the package self-checks and
   nothing else. Options, cheapest first:
   - a `make gate` (convert → suite → audit → reports) that must pass before
     `push-remote`, with the report files committed so the numbers are reviewable;
   - a scheduled run on the machine that holds the corpus, publishing
     `qa-invariants.json` as an artifact;
   - a self-hosted runner with the corpus mounted, making the pipeline lane blocking.
2. **Extend `tools/fixture_corpus.py`** so the committed micro-corpus reproduces at least
   one instance of each anomaly class (misattributed body, misplaced footnote zone,
   `(cid:N)`). Then CI gates the *invariants* on every PR even without private data —
   today `make seed-fixtures` builds 3 clean acts that can never fail anything.
3. **Fix the stale documentation that caused this misunderstanding.** `AGENTS.md` claims
   "All three lanes are green against a staged corpus"; measured, 43 of 103 documents fail.
   `.gitignore:43` and `.env.example:47` reference `make deploy-prod`, deleted in Phase 1
   cleanup. `data/seed/README.md:3` contradicts itself at line 48.
4. **State the contract in `README.md`**: a parser fix reaches reviewers only via
   convert → measure → sync → push. Merging is step zero, not the last step.

---

## Companion checklist

The executable form of this roadmap is [`wip/tasks.md`](./tasks.md): every phase broken
into checkboxes, each carrying its file path, its verification command, and its exit
criterion, in dependency order. Phase 2 has one checkbox per anomaly class with its hit
count, so "not a single anomaly skipped" is auditable rather than asserted.

This document is the *why* and the evidence; `tasks.md` is the *what next*.

## How the work lands

No commits on `main`. Each phase gets its own branch off the current `main` (`e1aae5d`)
and its own PR, so the diffs stay reviewable and a parser change is never mixed with a
deploy change:

| Branch | Contents |
|---|---|
| `fix/local-stack-and-toolchain` | Phase 0 — image rebuild notes, Python 3.12 venv, OCR extras |
| `fix/corpus-reconvert-all-lanes` | Phase 1 — report generation wiring; the regenerated corpora are gitignored, so the PR carries the tooling and the measured numbers, not the data |
| `fix/anomaly-<class>` (one per class) | Phase 2 — each parser fix with its locking case/invariant; `(cid:N)`, footnote-zone, orphan-footnote adoption, and the exemption files are separate PRs |
| `docs/anomaly-ledger` | Phase 2H — move the ledger into version control |
| `feat/portal-pipeline-health` | Phase 3 — exemption surfacing through `acts_metrics` |
| `feat/prod-corpus-volume` | Phase 4 — template, transfer route, adoption script |
| `chore/gate-and-docs` | Phase 5 — CI gate, fixture anomalies, stale-doc fixes |

Phase 2's PRs are the ones that change statutory text. Each must state, in the PR body,
the before/after hit counts and the specific leaves it moves — the standard PR #34 set.

## Verification

End-to-end, in order — each step must pass before the next:

1. `make health` → `/health/ready` green, api and worker no longer restarting.
2. `.venv/bin/python -V` → 3.12.x; `import numpy, onnxruntime, rapidocr_onnxruntime` clean.
3. `make convert-all LANE=<lane>` → `_run/report.md` shows zero unexplained failures;
   ordinance 16/16, acts 85, rules 36/36.
4. `python tools/run_suite.py <lane>` → `RESULT: ALL PASS` on all three, or every residual
   named in `exemptions/<lane>.json` with a traced reason.
5. Targeted regression check — the anomalies must be *gone*, not merely uncounted:
   ```bash
   grep -c "(cid:" data/corpora/*/output/*.json          # expect 0
   ```
   and confirm STA s.40C carries its ~1,400-char provision, and Customs 2007 s.14A keeps
   its 468 chars (the PR #34 case — it must not regress).
6. `make sync` → carryover reported; `make health`.
7. Open a re-parsed document in the portal: corrected text in the parsed-HTML pane,
   `invariants 55/55` badge, and a `metricsDelta` row on the version list.
8. `cd apps/web && npm run smoke` → Playwright asserts the PDF canvas rendered and the
   parsed pane has content.
9. Production: push the corpus files, `POST /api/corpus/sync`, then verify against a
   **restored dump** that document count did not double and that a known reviewer verdict
   survived.

## Risks

- **Re-parsing resets review state.** Every new version sets `signoff_stage='draft'` and
  clears `signoff_reviewed_by` / `signoff_legal_by` unconditionally (`versions.py:196`),
  and any leaf whose text changed reverts to `pending`. For a legally binding corpus this
  is correct — a verdict about text that no longer exists is not a verdict — but it is a
  real cost and reviewers should be told before, not after. Back up first.
- **Phase 4 step 4 is the one irreversible step.** Dry-run against a restored dump.
- **OCR is slow and memory-bound.** `--ocr-batch` defaults to 1 for a measured reason (4
  workers were 59% *worse*); the per-file timeout is 5400 s and Finance Act 2025 is 289
  OCR'd pages. Budget hours, and do not raise the batch size on intuition.
- **Re-pinning OCR deps changes statutory text.** If any pin has to move for Python 3.12,
  it must be re-pinned together with a fresh `tools/acts/ocr_review.py` run, per the
  requirements file's own instruction.
- **`ocr_cache` will not invalidate on a parser change.** Its key is
  `CACHE_VERSION|filename:size:mtime|page|dpi|repair` (`ocr.py:549`). That is correct for
  structural fixes, but if Phase 2A changes recogniser arguments, `CACHE_VERSION` must be
  bumped or the cache will serve pre-fix words.
