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
| API + tools tests | **1 failed, 500 passed, 1 skipped** — see the known failure below |
| web tests | 134 vitest |
| anomaly register | committed **64**, measured **44** — see the known failure below |

Reproduce the corpus numbers: `python3 wip/integration/measure/{census,churn}.py`.

### Known baseline failure — do not "fix" it here

`tools/tests/test_register_snapshot.py` fails at `4825a82`, before any change in this
work. Committed 64, measured 44. Cause, measured: **85 of 103 documents were re-converted
on 2026-08-30 19:54–21:54, after PR #54 merged at 12:58**, and `register.json` was never
regenerated.

It stays red. Nothing here moved it, and regenerating a snapshot for a movement no PR
caused is precisely what it exists to prevent. **Every PR below must show this one failure
and no other.** It belongs to the pipeline half — logged for `wip/HANDOVER.md`, not fixed
here.

That it is red only on a machine with the corpus staged — CI skips all three lane suites
because `data/corpora/` is gitignored — is P10 restated from the other side, and is what
PR-H fixes.

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
- [ ] PR opened and merged

---

## PR-A — Write the contract and stamp it  *(no portal change)*

Closes **P2** (two output schemas) and **P10**'s provenance half.

- [ ] `docs/pipeline-contract.md` — plan.md §4.1 in full
- [ ] `metadata.contract_version` / `pipeline_revision` / `converted_at` / `lane` in
      `legal_ingest.pipeline` **and** `fbr_ingest.pipeline`
- [ ] move `stamp_identity` (pipeline.py:1712, 20 lines, already correct) to a module both
      packages import; call it from `fbr_ingest._node_to_dict`
- [ ] `order` on every leaf, minted where the pipeline still holds sub-page position
- [ ] atomic write in `tools/convert.py:114` (tmp + `os.replace`)
- [ ] `contract_complete` invariant in `tools/suite/invariants/_common.py`
- [ ] **verify the gate fails on purpose** — strip a `node_key`, confirm red
- [ ] regenerate `tools/suite/register.json` in the same PR; the 14 stale acts documents
      register as hits until re-converted. Record the new total here and in `plan.md`.
- [ ] no re-conversion (confirmed decoupled)

Open question, to answer with measurement, not argument: does `fbr_ingest` produce any
duplicate `node_key`? Never measured — the invariant is what will tell us.

---

## PR-B — Identity: match on `node_key`   ← highest value

Closes **P1**.

- [ ] Alembic migration: `sections.node_key`, `footnotes.node_key`, indexed per document
- [ ] `json_parser` carries `node_key`; `_stable_id` keys on it when present, `source_key`
      otherwise. **Existing rows keep their ids — nothing is re-minted.**
- [ ] `apply_parsed_document` match order `node_key` → `source_key` → `_legacy_section_key`
- [ ] `versions.diff_documents` uses the same key, so diff and ingest keep agreeing
- [ ] regression tests on `data/fixtures/acts`: insert / delete / move / reorder at
      chapter, part, division and section level
- [ ] the Finance Act 2022 shape as a named fixture: 12-of-15 churn today → 0 changed,
      1 added. **This test must fail on `main`.**

---

## PR-C — Withdrawal, so absence propagates

Closes **P4**.

- [ ] `documents.withdrawn_at` (nullable timestamp, never a delete)
- [ ] sync computes the corpus stem set **per synced lane** and withdraws the difference,
      scoped by `--only` so a one-lane sync never touches another lane
- [ ] a reappearing stem clears it — idempotent, reversible
- [ ] library query excludes withdrawn by default; API exposes the flag
- [ ] review page shows a withdrawn banner instead of a silently stale parse

---

## PR-D — One production identity, and deploy it

Closes **P3**. Confirmed authorised to deploy.

- [ ] `/documents/upload` and `/replace-json` accept `source_type` + `source_key`
- [ ] `push_corpus` sends the deterministic identity
- [ ] `acts_metrics` matches in production — the health UI exists and nothing feeds it
- [ ] PR-C reconciliation applies to the push path
- [ ] `make backup-remote` **before** anything else
- [ ] `--dry-run` diff reviewed
- [ ] CI green on `main`, then deploy, then re-verify counts + health badges live

---

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
| deleting `_legacy_section_key` and the `source_key` bridge | only when a query shows zero rows relying on them |
| deleting `is_junk_leaf` / `normalize_heading` from the API | they compensate for real pipeline defects. Make them **counted** first; delete per-cause as the pipeline closes each. Deleting blind regresses QA's view. |
| 64-hit register residue, Phase 4a/4b/5, OCR | out of scope, confirmed. See `wip/HANDOVER.md`. |

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
