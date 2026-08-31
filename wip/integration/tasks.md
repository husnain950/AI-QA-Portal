# Integration tasks — the execution ledger

**This file is updated as work happens, never after.** If a box is ticked, the thing is
merged on `main`. If an assumption is disproven, the row changes and `plan.md` changes
with it.

Architecture: [`wip/integration/plan.md`](plan.md). Pipeline state (out of scope here):
[`wip/HANDOVER.md`](../HANDOVER.md).

## Rules of engagement

- Never commit to `main`. One branch and one PR per phase.
- Never edit `packages/` while a conversion runs (`wip/HANDOVER.md` §4 — cost ~30 min,
  twice). Clear `__pycache__` after any mutate-and-restore verification.
- Every behaviour change ships with the test that fails without it, **in the same PR**.
- A gate that cannot fail is a no-op. If a new check cannot be made to fail on purpose,
  it does not count as a gate.
- Measure the contract fix and the parser fix separately, on identical inputs for the
  first.
- Report changes that moved a number by zero. Folding them into a total misattributes
  the ones that moved it.

---

## Baseline, measured 2026-08-31 at `4825a82`

| | |
|---|---|
| documents converted | 80 acts / 11 rules / 12 ordinance = 103 |
| leaves | 10,474 acts / 1,119 rules / 4,958 ordinance = **16,551** |
| leaves with `node_key` | 10,385 (74/80 docs) / 1,119 (11/11) / **0 (0/12)** = 11,504 |
| leaves with **no** stable identity | **5,047 — 30% of the corpus** |
| duplicate `node_key` | **0** across all 11,504 |
| false "changed" leaves, one insert per document | **386** by `source_key`, **0** by `node_key`; 16 documents churn 100% |
| API + tools tests | **507 passed, 1 skipped, 0 failed** |
| web tests | 134 vitest |
| anomaly register | **30** (16 acts / 9 rules / 5 ordinance) — must not move except deliberately |

Reproduce the corpus numbers: `python3 wip/integration/measure/{census,churn}.py`.

### The baseline failure, and how it was closed

At `4825a82` the suite was **1 failed, 500 passed**: `test_register_snapshot` measured 44
against a committed 64. Traced to its cause rather than regenerated away — **PRs #55–#58
(Phase 3 rounds 8–11, 64 → 50 → 44 → 33 → 30) were open, CI-green and unmerged, and the
corpus on disk was their output.** `main` was four rounds behind its own data.

Merged in order on 2026-08-31: #55, **#60** (a re-open of #56, which GitHub auto-closed
when its base branch was deleted on merge of #55), #57, #58. Each needed `main` merging in
first; conflicts were `register.json` / `wip/plan.md` / `wip/tasks.md` (take the newer
round, which is built on the older) and `.gitignore` (take `main`'s root-anchored
transcript pattern). Suite now **507 passed, 0 failed**, register **30**.

Two things it leaves behind, both of which PR-A and PR-H answer:

- nothing on disk said which parser wrote it → `pipeline_revision`, `converted_at`
- the gate is green on CI and red only where the corpus exists, so a four-round
  divergence was invisible to every automated check → PR-H

---

## PR-0 — The ledger

- [x] branch `integration/ledger` from a freshly pulled `main`
- [x] `wip/integration/plan.md` — the architecture record
- [x] `wip/integration/tasks.md` — this file
- [x] gitignore the untracked `2026-08-30-125158-*.txt` transcript (`wip/HANDOVER.md` §6:
      a bare `git add -A` would commit it today) — dated-prefix pattern, so a deliberately
      named document is still tracked
- [x] `wip/integration/measure/{census,churn}.py` — every headline number reproducible
- [x] baseline measured on this host: Docker started, Postgres 17 up, full suite run
- [x] PR opened and merged — #59

---

## PR-A — Write the contract and stamp it  *(no portal change)*

Closes **P2** (two output schemas) and **P10**'s provenance half. Merged as #61.

- [x] `docs/pipeline-contract.md` — structure, metadata, identity with its guarantees
      *and its non-guarantees*, reprocessing, deletion, partial failure, versioning
- [x] `packages/legal_contract.py` — the contract's code half, imported by both
      pipelines. `stamp_identity` + `slug` MOVED here from `legal_ingest.pipeline`, not
      copied; `legal_ingest`'s own `_demo` lost the identity block that now lives with
      its owner and asserts more than it did.
- [x] `metadata.contract_version` from the parser; `lane` / `pipeline_revision` /
      `converted_at` from `tools/convert.py`, which is the only thing that knows them
- [x] `fbr_ingest` calls `stamp_document` at the same point `legal_ingest` does
- [x] atomic write in `tools/convert.py` (tmp + `os.replace`, cleaned up on any
      `BaseException` so an interrupted run leaves no scratch file in the corpus)
- [x] `contract_complete` invariant, bound in all three lanes
- [x] **verified the gate fails on purpose** — 4 ways: duplicate `node_key` on a legacy
      document, a stripped `type`/`node_key` on one that claims v1, missing metadata,
      and passing where it should pass
- [x] `EXPECTED_COUNTS` in `test_suite_invariants.py`: 58/58/45 → 59/59/46
- [x] register regenerated: **30, unchanged.** The invariant adds 0 hits by design —
      see the note below.
- [x] no re-conversion (confirmed decoupled)

**Measured, end to end.** One document per lane converted with the new code and compared
against what is already in the corpus: strip `type`, `node_key` and the four metadata
keys and the files are **byte-identical**. The change adds; it does not parse differently.

**The open question is answered.** `fbr_ingest` had never been measured for `node_key`
collisions because it never emitted any. Income Tax Ordinance 2001 (30-06-2018) now
converts to **525 nodes, 525 node_keys, 525 distinct, 0 duplicates**, and passes the full
contract check.

**Why the invariant scores zero today, deliberately.** Stamping the contract does not
re-convert the corpus, so no document on disk claims v1. Requiring the keys of every
document anyway scored **139 hits all saying one thing** — "not re-converted yet" — and
buried the 30 real ones. So a document that *claims* the contract is held to all of it,
and one that does not is held only to what is checkable without it: that the `node_key`s
it does carry are unique. The gate starts failing on the first document converted with
this code, which is when it has something to say.

## PR-B — Identity: match on `node_key`   ← highest value

Closes **P1**.

- [x] Alembic `0004_section_node_key` + `sections.node_key`, unique per document
      (partial, so pre-contract rows do not collide on NULL)
- [x] `json_parser` carries `node_key`; `_stable_id` mints from it when present, under
      a distinct `node:` namespace so the two can never collide. **Existing rows keep
      their ids — nothing is re-minted.**
- [x] `apply_parsed_document`: **one identity scheme per document**, not a fallback
      chain. See the two bugs below.
- [x] `versions.diff_documents` keys the same way, so diff and ingest agree
- [x] `tools/fixture_corpus.py` builds its documents with `stamp_document` — the
      contract's own code, so the one corpus CI can run cannot drift from it
- [x] 9 regression tests in `test_node_key_identity.py`: insert, delete, reorder,
      real edit, identical reprocess, the pre-contract fallback, and the migration
      ingest. **4 of them fail with the fix stubbed out** (verified, `__pycache__`
      cleared); the other 5 pass either way, which is right — they are the guards
      that nothing existing broke.
- [ ] delete `_legacy_section_key` and the `source_key` fallback — not yet; see Deferred

### Two bugs the tests caught before merge

**A unique-index collision the change itself introduced.** Once leaves are matched
structurally, a leaf that kept its identity can still move position, so its new
`source_key` is one the row beside it is still holding — and rows are updated one at a
time, so `uq_sections_source` fires mid-transaction. Inserting a single leaf at the top
of a chapter reproduced it (`IntegrityError`). A Postgres unique INDEX cannot be
deferred and a partial unique CONSTRAINT does not exist, so both keys are released in
one statement before the rewrite and written back inside the same transaction.

**A positional fallback that let a new leaf steal its neighbour's row.** With the chain
`node_key` → `source_key` → legacy, a genuinely new leaf inserted at position 0 missed
on `node_key` and then *matched the row of the leaf that used to be there*, inheriting
its approval, while that leaf was written as new. The fix is not a better fallback, it
is not having one: **the positional match is a migration affordance, live only while no
stored row carries a `node_key` at all.**

### Measured end to end, through the real sync

Three fixture documents synced into a scratch database, every section approved, then a
section inserted at the top of a chapter and re-synced:

```
before: 7 sections, all approved
sync:   added 0, updated 1, skipped 2, failed 0
after:  8 sections -- 7 of 7 kept BOTH their id and their approval, 1 added as pending
```

A second sync of an unchanged corpus is `skipped 3, added 0, updated 0`.

## PR-C — Withdrawal, so absence propagates

Closes **P4**.

- [x] `documents.withdrawn_at` (nullable timestamp, never a delete) and
      `documents.corpus_origin` — Alembic `0005_document_withdrawal`
- [x] `corpus_sync.reconcile_corpus` withdraws what a corpus no longer holds,
      **scoped by `corpus_origin`**, and restores what came back
- [x] `sync_validated_pair` clears `withdrawn_at` for a document it wrote, and its
      `skipped` fast path refuses to skip a row that is withdrawn or has no origin —
      the same idiom `corpus_lane` already used
- [x] only reconciles a corpus that was actually read; an unreadable root yields no
      stems, and withdrawing on a listing that never happened would empty the portal
- [x] library query excludes withdrawn by default, and the clause is **not**
      skippable by facet exclusion — a facet that counted them would not match the
      page it labels
- [x] API exposes `withdrawn_at`; the review page shows a banner instead of a
      silently stale parse
- [x] 9 backend tests + 2 frontend tests

### Why `corpus_origin` and not `corpus_lane`

`corpus_lane` looks like it would do the job. It does not: it is the Library's browse
facet (Customs, Sales Tax, Income Tax Rules...) and a row's lane says nothing about
which corpus root the file was synced from. Without a real origin,
`sync_corpus.py --only rules` would compute "everything not in the rules corpus" and
**withdraw all 80 acts documents**. There is a test named after exactly that.

### Measured end to end, through the real sync

```
sync 1   added 3, withdrawn 0
         (move one JSON to output/_refused/, as the pipeline does)
sync 2   added 0, skipped 2, withdrawn 1
         library shows 2 of 3 documents; 7 sections STILL STORED
         (move it back)
sync 3   library shows 3 documents again
```

Nothing is deleted at any point. The annotations, findings and exported evidence that
point at a withdrawn document are the audit trail for a legally binding corpus; losing
them to a conversion rerun with the wrong flag would be far worse than showing a
document marked withdrawn.

## PR-D — One production identity, and deploy it

Closes **P3**. Confirmed authorised to deploy.

- [x] `/documents/upload` accepts `source_key` + `corpus_origin`; with them it mints
      the same `uuid5` `sync_acts` does, computes the same `source_hash`, and an
      upload for a document that already exists becomes a **version**, not a row
- [x] an origin with no key is refused — it would be a row reconciliation counts but
      can never match, so the next sync of that corpus would withdraw it immediately
- [x] `push_corpus` sends the identity it holds locally, matches remote documents on
      `source_key` rather than on `documents.name` (a display string), and skips
      withdrawn documents
- [x] `acts_metrics` matches in production — the health UI exists and nothing fed it
- [x] PR-C reconciliation applies to the push path
- [x] 8 + 3 tests, including that the seeded `source_hash` equals what a local sync
      computes (if they disagreed, the first local sync would rewrite every pushed
      document and manufacture a version for each)
- [x] the three places that documented the old behaviour corrected: the Makefile,
      `docs/architecture.md`, and the backup workflow's own rationale
- [ ] `make backup-remote` before anything else
- [ ] `--dry-run` diff reviewed
- [ ] merge (deploy is automatic on green CI on `main`), then re-verify live

### What changes in production

| | before | after |
|---|---|---|
| id | `uuid4()` | `uuid5("acts_corpus:<stem>")` — the same one a local sync mints |
| `source_type` / `source_key` | `upload` / NULL | `acts_corpus` / the stem |
| pipeline health | never matched | matches |
| re-push | a second row; review state reset | a version; review state carried |
| withdrawal | invisible to it | reconcilable |

A document uploaded by hand still has no corpus identity and keeps the old shape
exactly — there is a test for that too.

## PR-E — Send the derived values; delete the client forks

Closes **P6**. One change, not six patches: the API stops withholding what it computes.

- [ ] `PAGE_SELECT` exposes `LANE_SQL AS lane`, `YEAR_SQL AS edition_year`, `HEALTH_SQL`,
      `REVIEW_SQL`; section payload carries the normalised heading and one quality-flag shape
- [ ] delete `corpusLanes.documentLane` heuristics
- [ ] delete `editions.js` family/year derivation (it carries the unanchored `dated` bug
      the backend fixed and documented)
- [ ] delete `tocLabels.cleanHeading`
- [ ] delete `qualityFlags` duplicated `CRITICAL_FLAGS` + four-shape tolerance
- [ ] delete `documentTags` facet re-derivation
- [ ] delete `documentFilters.js` (~150 dead lines) and the test suite proving code no
      page runs
- [ ] reconcile `ReviewToolbar`'s approval gate with the backend set it claims to mirror

---

## PR-F — One sanitizer allowlist, and fix the inverted coverage

Closes **P7**.

- [ ] `html_sanitizer.py` owns the allowlist, emits it as JSON; `sanitizeHtml.js` imports it
- [ ] test asserts the two agree (both sanitizers stay — stored HTML is a trust boundary)
- [ ] `fn-table` `flex: 0 0 N%` widths survive the client sanitizer (data, not decoration)
- [ ] `HtmlPanel.jsx:69` uses `sanitizeLegalHtml` like every other pane
- [ ] `footnoteCite` reads `data-ref` instead of fuzzy `textContent` matching

---

## PR-G — Stale review state and sync observability

Closes **P8** and **P9**.

- [ ] `refreshReviewData` — prefer deleting the Zustand mirror over patching the
      invalidation; the mirror is the cause, not the victim
- [ ] a 404 on `fetchSection` clears `activeSection` and renders an explicit removed-leaf
      state, mirroring the `orphan_context` treatment annotations already get
- [ ] surface the ~12 swallowed errors; `documentsError` exists for this and has no reader
- [ ] distinguish "empty" from "failed" on TOC, section pane, page view, notes, corpus status
- [ ] corpus sync: idempotency key, abort signal, `onProgress`, live `sync_running`,
      re-attachment after reload, Rules counts in the toast
- [ ] drop one of the two stacked retry layers (~90 s to first error today)

---

## PR-H — The adversarial matrix, on CI

Closes **P10**'s gate half. `data/fixtures/acts` is generated and not gitignored, so this
is the one harness CI can run end to end.

- [ ] mutation helper over the fixture corpus
- [ ] first ingest · identical re-ingest (0 versions, 0 row writes) · leaf edit
- [ ] insert / delete / move / reorder at every level · chapter rename
- [ ] malformed JSON · truncated JSON · empty document · 10k-leaf document
- [ ] duplicate stem across corpora · concurrent sync of one document
- [ ] interrupted sync then retry · rollback via `activate_version`
- [ ] withdrawal then reappearance · request for a withdrawn document
- [ ] web-app URL naming a deleted section
- [ ] wired into `.github/workflows/ci.yml` beside the existing `smoke` job

---

## Deferred, with reasons

| item | why not now |
|---|---|
| re-conversion onto the contract (14 stale acts docs, ordinance lane) | multi-hour, freezes parser work; confirmed decoupled. Own PR, established protocol: `output/_pre_<round>/` snapshot, three lanes re-measured, register regenerated in the same PR. |
| deleting `_legacy_section_key` and the `source_key` bridge | only when a query shows zero rows relying on them. Today 19 of 103 documents (the whole ordinance lane + 6 pre-Phase-0 acts) still have no `node_key`, so the bridge is load-bearing until the re-conversion runs. |
| `footnotes.node_key` | the plan called for it; measurement says no. Footnotes are already matched by `(section_id, marker)`, which is structural — a positional index was never used. Nothing to fix. |
| exposing `node_key` on the API | no consumer yet. The column exists; whichever PR needs it (a stable React key, the overlay re-key) adds the three lines. |
| re-keying `section_overlays` off `section_source_key` | same positional flaw as P1, and an approved AI fix could land on the wrong leaf after an insertion — **but it degrades safely**: `original_leaf_fingerprint` is compared on every sync, so a shifted overlay goes `stale` and re-flags the section rather than silently applying. Its own table, its own migration, its own PR. |
| deleting `is_junk_leaf` / `normalize_heading` from the API | they compensate for real pipeline defects. Make them **counted** first; delete per-cause as the pipeline closes each. Deleting blind regresses QA's view. |
| an explicit `order` field on every leaf | measured before building it: tree-walk order and the API's page-sort order disagree on **21 of 103 documents**, and heavily — 222 of 327 positions in Sales Tax Rules 2006, 62 of 62 in Customs Rules 2001. Which is *right* cannot be settled from the JSON; it needs the source pages. So `docs/pipeline-contract.md` states the rule actually in force (sort by `start_page`, stably) rather than minting a field nobody has validated. Own PR, with its own measurement. |
| register residue (30), Phase 4a/4b/5, OCR | out of scope, confirmed. See `wip/HANDOVER.md`. |

## Discovered during the work

**2026-08-31 — my own first census was wrong, twice.** The coverage script tested only
whether the *first* walked leaf carried a `node_key`, so it reported 66/80 acts documents
when the answer is 74/80, and named 8 documents as missing it that in fact have it
(Finance Act 2022, PSW Act 2021 and six others). The churn headline moved 455 → 386 with
the corrected walk. Both scripts are now committed under `measure/` rather than quoted
from memory, and `plan.md` carries the corrected figures. The lesson is the project's own:
a number in prose cannot tell you its generator is wrong.

**2026-08-31 — the register gate is red on `main`.** 85 of 103 documents were re-converted
after PR #54 without regenerating `register.json`. Recorded as the known baseline failure
above; not fixed here. Worth raising against `wip/HANDOVER.md`, whose §5 protocol
("regenerate `register.json` in the same PR") was not followed by whatever ran that
conversion.

**2026-08-31 — Docker was down on this host** (as `wip/HANDOVER.md` Phase 1 recorded).
Started it and brought up `docker compose up -d postgres`, so `make test-api` runs locally
now. Phase 1's unchecked box — rebuild the api/worker images — is still unchecked.

**2026-08-31 — the register discrepancy was four unmerged PRs, not drift.** Written up in
the baseline section above. The lesson worth carrying: the first explanation that fit the
evidence ("re-converted after #54 without regenerating") was true and useless. `git
reflog` named the actual branches in one command, and `gh pr list` showed all four still
open. Read the history before theorising about the artifact.

**2026-08-31 — `order` was scoped out of PR-A on measurement.** See Deferred. The plan
asserted the pipeline "knows the reading order and throws it away"; that is probably
true, but 21 documents disagree between the two candidate orders and picking one blind
would change what reviewers see. Stating the rule in force beat inventing a field.

**2026-08-31 — `is_junk_leaf` and `normalize_heading` stay for now.** They are P5 and the
plan says to make them counted before deleting them. Nothing in PR-A touches them; PR-E
is where they get measured.

**2026-08-31 — the fixture corpus was pre-contract, which made CI test only the
fallback.** `tools/fixture_corpus.py` wrote its JSON by hand, so the one corpus CI can
run carried no `node_key` and exercised the `source_key` path exclusively. It now calls
`stamp_document` — the contract's own code — so it cannot drift. It deliberately does
NOT call `stamp_run_provenance`: `converted_at` and `pipeline_revision` would break the
byte-identical-on-every-machine promise `.gitignore` makes about the generator. That the
two are separable is why PR-A made them separate functions.

**2026-08-31 — the API Docker image was verified, not just reasoned about.**
`docker build -f apps/api/Dockerfile` completes clean with the `legal_contract` copy
added. Docker had been down on this host since `wip/HANDOVER.md` Phase 1; it is up now,
which also clears that phase's one unchecked box.

**2026-08-31 — the web test suite cannot be run as a gate on this host.** 17 of 191
vitest tests fail identically on clean `main`: `window.localStorage` is undefined
because this machine runs Node 26 and Node 26 needs `--localstorage-file`. CI pins
Node 22 and is green. Environment only, pre-existing, and **not worked around** —
changing the project's vitest config to suit one machine's Node version is how a real
signal gets hidden later. Individual test files run fine
(`npx vitest run src/test/<file>`), which is what PR-C used; the suite is CI's job.
