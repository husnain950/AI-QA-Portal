# Pipeline → Web-App Integration: the architecture

**Status:** the architecture that now exists. **Every problem in §3 is closed** — P1–P4
and P6–P11 outright, P5 but for its reading-order limb, which is measured and deferred
rather than open. Each is marked with the PR that did it. `wip/integration/tasks.md` is the execution ledger;
`wip/integration/tasks.md` is the execution ledger and is the one to trust for *what is
done*. When an assumption here is disproven by measurement, this file changes — it is not
a historical record. (The frozen record is the per-PR artifact beside it.)

Started 2026-08-31, from `main` at `4825a82` (PR #54). Every number below was measured on
the corpus at that commit; the command that produces each is in §9.

## Context

`crx` is two systems joined by a directory glob. A pipeline (`packages/legal_ingest`,
`packages/fbr_ingest`, `tools/`) converts FBR statutory PDFs into JSON under
`data/corpora/<lane>/output/*.json`. A QA portal (`apps/api` FastAPI + Postgres,
`apps/web` React) flattens that JSON into rows reviewers annotate and approve.

PRs #42–#54 did eight rounds of strong work on the **left half** — schema families, the
anomaly register 210 → 64, now gated on CI by `tools/suite/register.json`. The **right
half** — the seam between a merged parser fix and a reviewer's screen — has not been
touched since PR #37, which diagnosed it precisely and shipped no code:

> "PR #34 fixed section-body misattribution. The portal still shows the old text.
> **The fix is not broken — it never travelled.**"

This work is that seam. QA is about to exercise it adversarially in production, and the
seam today has no written contract, positional leaf identity, two ingest paths that
produce different rows, no deletion semantics, and a frontend that re-derives — from
drifted copies — six things the backend already computes correctly.

**Scope (confirmed):** the integration seam only. The register residue (64 then, **34**
now), Phase 4a/4b,
Phase 5 and the OCR backlog stay exactly where `wip/HANDOVER.md` left them.
**Re-conversion (confirmed):** decoupled — nothing here blocks on it.
**Production (confirmed):** PR-D deploys to the live Northflank portal.

---

## 1. The end-to-end flow as it actually exists

```
 PDF (data/corpora/<lane>/{Acts,Rules,…}/*.pdf)
   │  tools/convert.py <lane> <pdf>   ← the lane (a folder) picks the package
   ▼
 legal_ingest.run (acts, rules)   |   fbr_ingest.run (ordinance)
   → stamp_identity()             |     (NO stamp_identity — no type, no node_key)
   ▼
 data/corpora/<lane>/output/<stem>.json      ◄── THE CONTRACT BOUNDARY
   │   non-atomic write (convert.py:114); no manifest; no parser revision
   │
   │  tools/sync_corpus.py --metrics → corpus_sync → sync_acts.run_sync
   │    discover_acts_repo (glob output/*.json, pair by metadata.filename)
   │    → json_parser.parse_json_document   ← drops leaves, rewrites headings, re-sorts
   │    → versions.create_version           ← content-hash gate, one active version
   │    → document_store.apply_parsed_document   ← upsert + carryover
   ▼
 Postgres: documents / document_versions / sections / footnotes / annotations
   │  FastAPI /api/documents/{id}/sections   (ORDER BY sort_order)
   ▼
 apps/web: React Query (staleTime 30s) + Zustand mirror + a third sanitizer
   ▼  QA reviewer
```

And a **second, divergent path — the one production actually runs**:

```
 local Postgres ──> make push-remote ──> POST /api/documents/upload (deployed portal)
                    backend/push_corpus.py    source_type='upload', source_key=NULL
                                              identity = documents.name, a display string
```

---

## 2. What the previous work got right

None of this should be undone:

- **`Family` (what a document is) composed with `Profile` (what its printer does)**, with
  the #45 correction that a profile is an *override*, not an answer. Classification reads
  content, never filenames.
- **The exemption discipline.** "Fixed, or exempted with evidence traced to the source
  PDF. There is no third state." An exempt invariant that starts passing reports itself
  stale. This is the best mechanism in the repo, and the plan below reuses it to gate the
  contract rather than inventing a schema validator.
- **`register.json` + `test_register_snapshot.py`.** A cached artifact cannot tell you its
  generator is wrong; a snapshot can.
- **`document_store.apply_parsed_document`.** The carryover model — re-anchor changed
  leaves, orphan annotations off removed leaves *with a content snapshot*, report the
  cost on the version row — is genuinely well designed, and `_carries_human_qa_state`
  correctly refuses to treat a parser-assigned `has_issues` as human intent.
  **The defect is not this code. It is the key it matches on.**
- **`versions.create_version`'s unchanged-bytes gate.** Re-running a sync manufactures no
  empty versions.
- **`html_sanitizer.py`'s narrow `flex: 0 0 N%` exception**, preserved because a footnote
  table's column width is *data recovered from the PDF*, not decoration.
- **`tools/fixture_corpus.py`.** A deterministic generated micro-corpus CI can actually
  run. It is the vehicle for the entire test strategy below.
- **`DashboardPage.renderBody()`** — the one surface that distinguishes "empty" from
  "failed", with the right copy: *"This is a load failure, not an empty library."*
  It is the standard the rest of the app should meet.

---

## 3. Architectural problems

### P1 — ~~Leaf identity is positional~~ — CLOSED (#62)

`json_parser._stable_id(document_id, source_key)`, where `source_key` is a JSON-pointer
path: `/chapters/0/sections/3`. Insert one leaf and every later key names a *different*
leaf. Measured across the real corpus (101 documents, 16,430 leaves), inserting one leaf
into each document's first populated chapter:

| | reported | truth |
|---|---|---|
| 16 documents | **100% of the document "changed"** | 0 changed, 1 added |
| mean document | **25% of its leaves "changed"** (median 2%) | 0 changed, 1 added |
| across 84 documents / 11,502 leaves | **386 leaves falsely "changed"** | 0 |
| the same test keyed on `node_key` | **0 falsely changed** | ✅ |

Reproduce: `python3 wip/integration/measure/churn.py`.

A false "changed" is not cosmetic: `apply_parsed_document` resets approvals to `pending`,
revokes approval inheritance, and re-anchors annotations **against the wrong leaf's
text**. `versions.diff_documents` reports the same lie to the reviewer.

`node_key` — the ancestor chain by code, `ch:vii/pt:i/s:114` — was shipped by PR #42 *for
exactly this reason* and is consumed by nobody:

```
$ grep -rn node_key --include=*.py --include=*.jsx .
packages/legal_ingest/pipeline.py   ← 9 hits, all inside the emitter
```

Verified unique across all 16,430 leaves in the two lanes that emit it. Zero duplicates.

### P2 — ~~No canonical contract; two output schemas~~ — CLOSED (#61)

`docs/pipeline-readme.md` documents the *ordinance* schema and says so ("written for the
standalone ordinance repository… `legal_ingest` has since diverged"). It omits `type`,
`node_key`, `family`, `instrument_kind`, `calibration`, and states no stability, ordering,
deletion or versioning guarantee. On disk:

| lane | docs | leaves | leaves with `node_key` | nodes | typed | duplicate keys |
|---|---|---|---|---|---|---|
| acts | 80 | 10,474 | 10,385 (74/80 docs) | 11,843 | 11,733 | 0 |
| rules | 11 | 1,119 | 1,119 (11/11) | 1,325 | 1,325 | 0 |
| **ordinance** | 12 | 4,958 | **4,958 (12/12)** — PR-J | 6,941 | **6,941** | 0 |
| **total** | **103** | **16,551** | **16,462** | | | **0** |

At the time this was written, **5,047 leaves — 30% of the corpus — had no stable identity
at all**, the whole ordinance lane among them. PR-J re-converted that lane; **89 leaves in
6 documents remain**, all of them pre-Phase-0 acts documents that OCR blocks. Zero
duplicate `node_key` across all 16,462, so the key is sound where it exists.

The 6 acts documents without one also have `family: null` — **pre-Phase-0 artifacts still
in the live corpus.** Nothing in `metadata` records which parser revision produced a file,
so a mixed-revision corpus is undetectable and every sync ingests it silently. That is not
hypothetical here: on the day this work started **the corpus on disk was four parser
rounds ahead of `main`** and nothing on disk said so — see §3, P11. `wip/HANDOVER.md` §4
names this hazard for *measurement*; it applies identically to *ingest*.

Reproduce: `python3 wip/integration/measure/census.py`.

### P3 — ~~Two ingest paths; production runs the weaker~~ — CLOSED (#64, #65, #70, #71)

| | `make sync` (`sync_acts`) | `make push-remote` (`push_corpus`) |
|---|---|---|
| identity | `uuid5("acts_corpus:<json stem>")` | **`documents.name`**, a display string |
| `source_type` / `source_key` | `acts_corpus` / stem | `upload` / **NULL** |
| pipeline health | `acts_metrics` matches on `source_key` | **never matches — badges empty in prod** |
| re-run | idempotent, versioned, carryover | *"the upload route resets every section to pending"* |
| deletion | none | prints orphans, *"this tool never deletes"* |

`backup-review-state.yml` runs nightly *solely* because re-pushing destroys reviewer work.
A backup job load-bearing for correctness is the clearest possible signal that the ingest
path is wrong. PR #37's finding, still open.

### P4 — ~~Nothing is ever withdrawn~~ — CLOSED (#63)

No code path removes a `documents` row when its JSON leaves `output/`. Phase 2 moved two
acts documents to `output/_refused/` (80 → 78) and holds 9 in `_provisional/`. Any
document refused, renamed or quarantined keeps its rows, its stale parse and its
"approved" badges forever. A reviewer cannot tell a current document from an abandoned one.

### P5 — ~~Parsing decisions in the presentation layer~~ — CLOSED (#75), except reading order

`apps/api/backend/services/json_parser.py` makes three pipeline-grade judgements the
pipeline's invariants and register cannot see:

- **`is_junk_leaf`** *silently dropped* leaves — invisible to the register, to the
  conservation audits, and to the reviewer. It fired **4 times** on the whole corpus, and
  all four were the *preamble* of a Customs Act edition, deleted with its enacting formula
  because a Contents tail is glued to its front. It is now `assess_toc_tail`, an
  informational `toc_tail_in_leaf` flag: the leaf reaches the reviewer with the defect
  named on it. PR-J's `preamble_carries_no_toc_tail` still counts the cause, which is
  and remains the pipeline's.
- **`normalize_heading`** was written to strip TOC chrome, and measured over the corpus
  **not one of its 42 rewrites was TOC chrome** — eleven parser rounds closed every case
  it was built for. 35 of the 42 were the `[...]` **omission marker** being destroyed by
  two attackers, the dot-leader substitution *and* the trailing `.strip(" .·•…")` mop-up
  (`Directorate General [...] Internal Audit` -> `[ ] Internal Audit`; the truncated form
  -> a bare `[`). Both are guarded on one rule: an unclosed `[` means those dots are the
  marker. 42 → 7, all 35 markers intact. The client's `tocLabels.cleanHeading` — a live
  second copy running the same regex on the already-cleaned string, and the last of P6's
  six forks — is deleted. The function itself stays: with zero true positives it has no
  job left, but deleting it today would put `] Tax credit not allowed` on a reviewer's
  screen. That is a parser round away, not an API change.
- **`_apply_reading_order`** re-derives document order by sorting on `start_page`. Its own
  docstring: *"sub-page position is not recoverable from the export."* **The pipeline
  knows the reading order and throws it away; the API guesses it back.**

### P6 — ~~The frontend re-derives six backend answers~~ — CLOSED (#66)

Every one of these files carries a *"mirrors / keep in sync with"* comment. **The comment
is the diagnosis, not the fix.** Verified:

| client file | backend owner | current divergence |
|---|---|---|
| `utils/editions.js` | `services/editions.py` | client kept the **unanchored `dated` regex the backend fixed and documented**: `"Sales Tax Rules, 2006 UPDATED UPTO …"` → `"sales tax rules, 2006 up"`, splitting Rules editions across families in the Library. Client also lacks `_CANONICAL_RULES`, merging Withholding Rules with Special Procedures Rules. |
| `utils/corpusLanes.js` | `library_query.LANE_SQL` | server classifies NULL-lane rows by title; client collapses them all to `other_acts`. **Filtering by "Customs" returns a card badged "Other Acts."** Root cause: `PAGE_SELECT` selects raw `d.corpus_lane` and never exposes `LANE_SQL AS lane`. |
| `utils/editions.js` (year) | `library_query.YEAR_SQL` | server sorts on the first `19xx|20xx`, client badges the year next to `amended upto`. "Edition — newest" produces an order that contradicts the labels on the cards. |
| `utils/tocLabels.js` | `json_parser.normalize_heading` | a line-for-line port, re-run on text the backend already cleaned at ingest. A 5,393-leaf regression was fixed **on the client only**; the backend copy still has the narrow form. |
| `utils/qualityFlags.js` | `parse_quality.CRITICAL_FLAGS` | copied constant; `ReviewToolbar` then gates approval on a *broader* set than the one it says it mirrors. `normalizeQualityFlags` accepts four wire shapes for a field the API emits in exactly one. |
| `utils/documentTags.js` | `library_query.HEALTH_SQL` / `REVIEW_SQL` | three parallel implementations kept in step by comment. |

Plus ~150 lines of **dead** client-side filter/sort in `utils/documentFilters.js`
re-implementing the whole `library_query` matrix — referenced only by its own passing
test suite; no page calls it.

The shape is consistent: **the backend computes the right answer, then either declines to
put it on the wire or the client recomputes it from a fork that has since drifted.**

### P7 — ~~Inverted sanitizer coverage destroying pipeline data~~ — CLOSED (#67)

- `HtmlPanel.jsx:69` — the **main section body** — does `container.innerHTML = htmlContent`
  with **no client sanitizer at all**.
- `FootnotePanel.jsx:47` and `AiFixPanel.jsx:193` — the two small panes — *do* sanitize,
  with a **narrower** allowlist than the API's. The client's `KNOWN_CLASSES` is missing
  `fn-table, omitted-bracket, explanation, defn, formula, frac, legend`, which the API
  preserves with an explicit note: *"measured at 11,349 occurrences across the two
  corpora."* All seven have live CSS rules.
- Worst case: `FootnotePanel` is the **only** consumer of `.fn-table`, and the client
  strips both the class *and* — via `FORBID_ATTR: ['style']` — the `flex: 0 0 N%` column
  widths that `html_sanitizer.py:64-72` was written specifically to protect as *"data,
  not decoration."* The backend's own fidelity flags cannot detect this loss.
- `data-ref` is allowlisted end-to-end and read by nobody: `footnoteCite.js` re-derives
  cite→footnote linkage by fuzzy `textContent` matching, which mis-links whenever markers
  repeat in a leaf.

### P8 — ~~Stale review state in the workspace~~ — CLOSED (#68)

`documentStore.refreshReviewData` **invalidates 2 query keys and then refetches 4**:

```js
invalidateQueries(['document', docId])          // ✅
invalidateQueries(['sections',  docId])         // ✅
fetchSection(docId, target)         → ['section', docId, sectionId]        // ❌ never invalidated
fetchSectionsByPage(docId, page)    → ['sections-by-page', docId, page]    // ❌ never invalidated
```

`'sections' !== 'section'`, so prefix matching misses both. `fetchQuery` honours
`staleTime: 30_000`, so those two "refetches" return the **pre-write** cached value and
write it back into Zustand, **reverting the optimistic patch**. Press `A` within 30s of
opening a leaf and the TOC says `approved` while the section pane and toolbar say the old
status — precisely the failure the consolidation comment claims to have fixed. Server-derived
fields (`effective_status`, `reviewer_verdict`, `annotation_count`, quality-flag elevation)
never reach the UI at all until the cache ages out.

### P9 — ~~A dead section id renders the previous leaf~~ — CLOSED (#68)

Sections are hard-deleted (`document_store.py:557`) and ids are minted from `source_key`,
so any structural change retires ids. When the URL names a retired id: `fetchSection` 404s,
`documentStore.js:120-123` logs to console and returns `null`, and **`activeSection` is
never cleared**. The pane keeps rendering the *previous* leaf's HTML, footnotes and toolbar
while the URL and "Leaf N of M" refer to the dead id — **a reviewer can approve or annotate
the wrong leaf after a resync.** On a fresh load it instead shows *"Select a section from
the Table of Contents"* — an empty state for a 404.

The backend already models this case for annotations (`anchor_status='orphaned'` +
`orphan_context`, rendered as *"Sec {code} (removed)"*). The section-level equivalent was
never wired up.

### P10 — ~~No atomicity, provenance, or CI gate at the corpus interface~~ — CLOSED (#61, #69)

`tools/convert.py:114` writes `open(out, "w")` straight into `output/`; `sync_acts` globs
the same directory. A sync concurrent with `convert_all` reads a half-written corpus. There
is no run manifest, no `converted_at`, no parser revision — so "what changed between two
runs" is unanswerable at the seam. And `data/corpora/` is gitignored, so all three lane
suites SKIP on CI and `convert_all` / `sync_corpus` appear in **zero** workflow files.

Also: sync polling has no idempotency key, no abort signal, no re-attachment after a
reload, and `sync_running` is a mount-time snapshot — so a second concurrent corpus sync
is one click away, and the toast silently drops the Rules counts.

### P11 — ~~The register gate is red on `main`~~ — CLOSED 2026-08-31

At `4825a82` the full suite was **1 failed, 500 passed**: `test_register_snapshot`
measured 44 against a committed 64. The corpus and the code did not describe each other.

Traced, not guessed: **PRs #55–#58 — Phase 3 rounds 8 to 11, register 64 → 50 → 44 → 33
→ 30 — were open, CI-green and unmerged**, and the corpus on disk was their output
(converted 2026-08-30 19:54–21:54; round 11 committed at 21:57). `main` was four rounds
behind its own data. The measured 44 was not any round's number: it was `main`'s
invariants read over a round-10 corpus.

Merged in order — #55, #60 (a re-open of #56, which GitHub auto-closed when its base
branch was deleted), #57, #58. The suite is now **507 passed, 1 skipped, 0 failed** and
the register is **30**.

Two things this leaves behind, both of which the contract answers:

1. **Nothing on disk said which parser wrote it.** That is precisely what
   `metadata.pipeline_revision` and `converted_at` are for, and it is why they are in
   the contract rather than being nice-to-have.
2. **The gate did its job and no one saw it.** It is green on CI, because
   `data/corpora/` is gitignored and all three lane suites SKIP there — so a
   four-round divergence between code and corpus was invisible to every automated
   check the project runs. That is P10 restated, and PR-H is what closes it.

---

## 4. Target architecture

One contract, one identity, one ingest path, explicit withdrawal, and a frontend that
renders what the API sends. No compatibility layers beyond a single deletable bridge.

```
 PDF ──► pipeline ──► output/<stem>.json  ◄── CANONICAL CONTRACT (documented + gated)
                        metadata: contract_version, pipeline_revision, converted_at, lane
                        every node: type, node_key      ← identity
                        every leaf: order               ← ordering
                        atomic write (tmp + os.replace)
                        ▼
                     ONE ingest: validate → version → reconcile → upsert
                        identity = node_key      (source_key = migration bridge only)
                        ordering = pipeline order (API never re-derives)
                        absence  = withdrawal     (never a silent survival)
                        ▼
                     Postgres ──► API sends every derived value it computes
                        ──► web app renders it and derives nothing
```

### 4.1 The canonical output contract

Written to `docs/pipeline-contract.md`, enforced by a new suite invariant so the existing
register machinery gates it.

**Structure.** `{metadata, preamble, chapters[], schedules[]}`; containers nest `parts[]`
/ `divisions[]` / `sections[]`; a leaf is any node carrying `html`.

**Metadata — required on every document, both parsers:** `contract_version` (int, bumped
only on a breaking change), `pipeline_revision` (git sha of the converting tree),
`converted_at` (ISO-8601 UTC), `lane`, plus today's `filename`, `total_pages`,
`sections_count`, `chapters_count`, `schedules_count`. Everything past this is optional
and consumers must tolerate absence (`family`, `calibration`, `ocr`, `instrument_kind`,
`amends`, `notified_by`).

**Identity.** Every node carries `type` (`chapter`/`part`/`division`/`schedule`/`section`)
and `node_key` (ancestor chain by code; `~root` for synthetic roots, `~2` ordinal for
repeated sibling codes).
*Guarantee:* stable across reprocessing for a leaf whose position in the legal hierarchy
has not changed; unique within a document (an invariant, not a hope).
*Explicit non-guarantee:* **not** stable across editions of the same law — cross-edition
identity is `section_variants`' job and is out of scope.

**Ordering.** Every leaf carries `order`, a 0-based integer in document reading order,
minted by the pipeline, which knows page *and* sub-page position. Consumers sort by it and
never re-derive.

**Reprocessing.** Byte-identical JSON ⇒ no new version, no row writes, no events. Changed
JSON ⇒ exactly one new version; leaves matched by `node_key`; the carryover report is the
complete account of what human state moved.

**Deletion.** A `node_key` present in version *n* and absent in *n+1* is removed; its
annotations are orphaned with a content snapshot, never deleted. A document stem present
in a previous sync and absent now is **withdrawn**, not deleted: `documents.withdrawn_at`
is set, it leaves the default library view, and it returns automatically if the stem
reappears.

**Partial failure.** One unparseable document fails alone and is named in `problems[]`;
the run exits non-zero. A truncated JSON is a failure, never a silent zero-section
document.

**Backwards compatibility.** One bridge: a leaf with no `node_key` falls back to
`source_key` matching. Deleted once every lane emits `node_key` and a query shows zero
rows relying on it.

### 4.2 Integration boundaries

| layer | owns | must not |
|---|---|---|
| pipeline | text extraction, structure, identity, ordering, heading normalisation | know the portal exists |
| `output/*.json` | the contract, versioned and provenance-stamped | be written non-atomically |
| `sync_acts` + `json_parser` | validate against the contract, flatten, reconcile, version | *decide* what is a section, or re-derive ordering |
| `document_store` | human QA state across a reparse | re-parse |
| API routes | serialisation, authorisation, pagination — **and sending every value they compute** | transform content, or compute a value and withhold it |
| `apps/web` | presentation, selection, annotation UX | re-derive anything the API states |

---

## 5. Implementation phases

Start from a fresh `main`:
`git checkout main && git pull && git checkout -b integration/contract`.
One PR per phase, each with a before/after artifact under `wip/integration/` linked from
the PR body, per project convention.

### PR-0 — The ledger
`wip/integration/plan.md` (this document, as the living architecture record) and
`wip/integration/tasks.md` (the execution ledger, updated *as work happens*, never after).
Also gitignore the untracked `2026-08-30-125158-*.txt` transcript that `wip/HANDOVER.md` §6
flags — a bare `git add -A` would commit it today.

### PR-A — Write the contract and stamp it *(no portal change)*
- `docs/pipeline-contract.md`: §4.1 in full.
- `metadata`: `contract_version`, `pipeline_revision`, `converted_at`, `lane` in both
  `legal_ingest.pipeline` and `fbr_ingest.pipeline`.
- Move `stamp_identity` (20 lines, already correct) to a module both packages import;
  call it from `fbr_ingest`. Closes the 4,958-leaf identity hole.
- `order` on every leaf, minted where the pipeline still holds sub-page position.
- Atomic write in `tools/convert.py` (tmp + `os.replace`).
- New `contract_complete` invariant in `tools/suite/invariants/_common.py`; regenerate
  `tools/suite/register.json` **in the same PR**. The 14 stale acts documents will register
  as hits until re-converted — that is the correct, visible answer, reported not hidden.
- **No re-conversion.** The API tolerates absence via the bridge.

### PR-B — Identity: match on `node_key`  ← the highest-value change
- Alembic migration: `sections.node_key`, `footnotes.node_key`, indexed per document.
- `json_parser` carries `node_key` through; `_stable_id` keys on it when present, on
  `source_key` otherwise — **existing rows keep their ids; nothing is re-minted.**
- `apply_parsed_document` match order: `node_key` → `source_key` → `_legacy_section_key`.
  The first ingest after this backfills `node_key` onto matched rows; thereafter the
  structural key wins.
- `versions.diff_documents` uses the same key, so diff and ingest keep agreeing.
- Regression tests on `data/fixtures/acts`: insert / delete / move / reorder at chapter,
  part, division and section level, plus the Finance Act 2022 shape (12-of-15 churn) as a
  named fixture asserting 0 changed / 1 added. **These fail today.**

### PR-C — Withdrawal, so absence propagates
- `documents.withdrawn_at`; sync computes the corpus stem set **per synced lane** and
  withdraws the difference (scoped by `--only`, so a one-lane sync never touches another).
- A reappearing stem clears it. Idempotent and reversible.
- Library query excludes withdrawn by default; API exposes the flag; the review page shows
  a withdrawn banner instead of a silently stale parse.

### PR-D — One production identity, and deploy it
- `/documents/upload` and `/replace-json` accept `source_type` + `source_key`.
- `push_corpus` sends the deterministic identity, so production rows become
  indistinguishable from synced rows: `acts_metrics` matches (pipeline health badges light
  up — *"the UI already exists; nothing feeds it"*), re-push is idempotent, review state
  survives, and `backup-review-state.yml` stops being load-bearing.
- PR-C's reconciliation applies to the push path too.
- **Order of operations:** `make backup-remote` first → `--dry-run` diff → land on `main`
  with CI green → deploy → re-verify counts and health badges against the live portal.

### PR-E — Send the derived values; delete the client forks
The single change that kills P6: **`PAGE_SELECT` exposes `LANE_SQL AS lane`,
`YEAR_SQL AS edition_year`, `HEALTH_SQL`, `REVIEW_SQL`** and the section payload carries
the already-normalised heading and the one canonical quality-flag shape. Then delete:
`corpusLanes.documentLane` heuristics, `editions.js`'s family/year derivation,
`tocLabels.cleanHeading`, `qualityFlags.normalizeQualityFlags`'s four-shape tolerance and
duplicated `CRITICAL_FLAGS`, `documentTags`' facet re-derivation, and the ~150 dead lines
of `documentFilters.js` with the test suite that proves code nothing runs. Reconcile
`ReviewToolbar`'s approval gate with the backend set it claims to mirror.

### PR-F — One sanitizer allowlist, and fix the inverted coverage
- `html_sanitizer.py` owns the allowlist and emits it as JSON; `sanitizeHtml.js` imports
  it. A test asserts the two agree. (Both sanitizers stay — stored HTML is a trust
  boundary; only the divergence goes.)
- Preserve the `fn-table` `flex: 0 0 N%` widths through the client sanitizer, since the
  backend deliberately preserved them as data.
- `HtmlPanel.jsx` uses `sanitizeLegalHtml` like every other pane.
- `footnoteCite` reads `data-ref` — carried end-to-end and currently ignored — instead of
  fuzzy `textContent` matching.

### PR-G — Stale review state and sync observability
- Fix `refreshReviewData`: invalidate `['section', …]` and `['sections-by-page', …]` too,
  or drop the Zustand mirror for these and read React Query directly. **Prefer the
  deletion** — the mirror is the bug's cause, not its victim.
- A 404 on `fetchSection` clears `activeSection` and renders an explicit *"this leaf was
  removed by a newer version"* state with a link to the nearest live leaf — mirroring the
  `orphan_context` treatment annotations already get.
- Surface the errors currently swallowed into empty states (the `documentsError` field
  added for exactly this has no reader); distinguish "empty" from "failed" on the TOC,
  section pane, page view, notes tab and corpus-status line.
- Corpus sync gets an idempotency key, an abort signal, `onProgress`, live `sync_running`
  polling, re-attachment after a reload, and a toast that includes the Rules counts.
- Drop one of the two stacked retry layers (~90s to first error today).

### PR-H — The adversarial matrix, on CI
`data/fixtures/acts` is generated and not gitignored, so this is the one harness CI can run
end to end. A mutation helper builds each case from the fixture corpus, drives it through
`sync_acts` → API, and asserts:

first ingest · identical re-ingest (0 versions, 0 row writes) · leaf edit · insert at every
level · delete · move · reorder · chapter rename · malformed JSON · truncated JSON · empty
document · 10k-leaf document · duplicate stem across corpora · concurrent sync of one
document · interrupted sync then retry · rollback via `activate_version` · withdrawal then
reappearance · request for a withdrawn document · **web-app URL naming a deleted section**.

Wired into `.github/workflows/ci.yml` beside the existing `smoke` job.

---

## 5b. What this actually left behind

Measured on the live portal, before and after:

| | before | after |
|---|---|---|
| documents | 106 | **115** |
| `source_type` | all `upload` | all **`acts_corpus`** |
| documents with `source_key` | **0** | **115** |
| pipeline health populated | **0** | **92** (79 within gate, 13 outside, 23 unmeasured) |
| `lane` / `edition_year` on the wire | — | **115** |
| documents with more than one version | 0 | **85** |
| sections | 17,859 | **22,171** |
| approvals | 21 | 18 — the three whose text genuinely changed reset, which is correct |

The 85 new versions are eleven rounds of parser fixes arriving in production. That is
PR #37's sentence answered: *"The fix is not broken — it never travelled."* It
travelled.

`health populated: 92` is the other half of the same sentence. The badges the Library
already rendered had nothing behind them because `acts_metrics` reads a reports
directory a deployment does not have; #70 gave the numbers a wire and #71 made it
survive the rate limiter.

### The gates that now exist

| gate | what it catches |
|---|---|
| `contract_complete` (all 3 lanes) | a document claiming the contract that does not meet it; a duplicate `node_key` on any document |
| `test_register_snapshot` | the anomaly register moving without a PR that moved it |
| `test_sanitizer_policy` | the client allowlist drifting from the backend's |
| `test_integration_matrix` | 18 seam states, **on CI**, with no private data |
| `test_node_key_identity` | a structural change churning leaves that did not change |
| `test_withdrawal` | one corpus's sync withdrawing another's documents |
| `preamble_carries_no_toc_tail` (all 3 lanes) | a Contents tail glued in front of the enacting formula — the cause; the portal now flags the leaf instead of deleting it |
| `test_json_parser` omission-marker cases | the `[...]` "omitted by amendment" marker being eaten by a heading normaliser, from either of its two attackers |

`test_integration_matrix` is the one that was missing entirely: `data/corpora/` is
gitignored, so every lane suite SKIPs on CI and nothing between "a parser fix merged"
and "a reviewer sees it" was checked. The matrix builds its own corpus, so it runs
anywhere. (Name the gate rather than its position — this sentence said "the last of
those" until a row was appended beneath it.)

---

## 6. Migration strategy

Additive first; subtractive only on evidence.

1. PR-A adds keys. Old JSON stays valid; the register makes the gap visible.
2. PR-B adds a column and a matching *preference*. Ids are never re-minted; the first
   post-deploy sync backfills `node_key` through the `source_key` match.
3. `_legacy_section_key` and the `source_key` fallback are deleted only when a query shows
   zero rows without `node_key`. Until then they stay untouched.
4. PR-C's withdrawal is a nullable timestamp, not a delete. Fully reversible.
5. Re-conversion onto the contract (the 14 stale acts documents and the ordinance lane) is
   a **separate scheduled run** following the established protocol — `output/_pre_<round>/`
   snapshot, all three lanes re-measured, register regenerated in the same PR. Not a
   prerequisite for any PR above.

---

## 7. Risks

- **Never edit `packages/` while a conversion runs** (`wip/HANDOVER.md` §4 — done twice,
  cost ~30 min each). All parser edits land and verify *before* any conversion; no
  conversion overlaps a sync.
- **Clear `__pycache__` after any mutate-and-restore verification** — stale bytecode has
  already survived a re-conversion here once.
- **Phase 4b interaction.** The decided-but-unwired `fbr_ingest` routing change would give
  9 ICT documents `node_key` for free. PR-A stamps `fbr_ingest` anyway so the seam is
  correct under either outcome — but 4b must not land mid-way through PR-A.
- **PR-D touches a live deployment.** Backup first, dry-run diff, CI green on `main`, then
  deploy, then re-verify.
- **`node_key` collisions in the ordinance lane have never been measured** (zero across
  16,430 leaves elsewhere). PR-A's invariant makes a collision a hard failure rather than a
  silent overwrite.
- **The register will move** when PR-A's invariant lands. Reported in the same PR that
  moves it, per the established rule.
- **PR-E/F/G touch reviewer-facing behaviour.** Each ships with a Playwright assertion, and
  the fixture corpus makes the before/after visible without private data.

---

## 8. Acceptance criteria

- `docs/pipeline-contract.md` exists and matches what the code emits; a suite invariant
  fails when it does not.
- Both parsers emit `contract_version`, `pipeline_revision`, `converted_at`, `lane`, and
  `type` + `node_key` + `order` on every node.
- Inserting, deleting, moving or reordering one leaf produces exactly that change in the
  version diff and the carryover report — **0 false "changed"**, on a test that fails today.
- Re-syncing an unchanged corpus creates no version and writes no rows.
- A document removed from `output/` is withdrawn within one sync and returns automatically
  when it reappears.
- Production rows are shaped identically to synced rows; `make push-remote` twice is a
  no-op that preserves review state; pipeline health badges are populated in production.
- One sanitizer allowlist, asserted equal by a test; `fn-table` column widths survive to
  the reviewer's screen.
- No client file re-derives a value the API computes; the "keep in sync with" comments are
  gone because the duplicates are.
- Acting on a leaf never leaves the TOC and the section pane disagreeing; a dead section id
  produces an explicit removed-leaf state, never another leaf's content.
- The adversarial matrix runs on CI against the fixture corpus and is green.
- `wip/integration/plan.md` describes the architecture that exists; `tasks.md` is accurate
  at every commit.
- The register is unchanged except where a PR deliberately moves it, and that move is
  reported in the same PR. It stands at **34** (PR-A moved it by 0, PR-J by +4, PR-K by 0).

---

## 9. Verification

```sh
# per PR
.venv/bin/pytest apps/api/backend/tests tools/tests -q
.venv/bin/python tools/run_tests_smoke.py
.venv/bin/ruff check                              # BARE — matches ci.yml
make test-web

# the seam, end to end, no private corpus needed
make seed-fixtures
.venv/bin/pytest apps/api/backend/tests/test_integration_matrix.py -q
cd apps/web && npm run smoke                      # Playwright: dashboard + review

# the seam, against the real corpus
.venv/bin/python tools/sync_corpus.py --metrics --dry-run
.venv/bin/python tools/run_suite.py acts          # and rules, ordinance
du -sh data/ocr_cache                             # must stay 0 B

# production (PR-D only)
make backup-remote BASE_URL=…
.venv/bin/python -m backend.push_corpus --base-url … --dry-run
```
