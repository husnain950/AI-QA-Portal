# Refactor tasks

Working ledger for the repo-wide refactor. Delete or fold into the final summary when Phase 9 lands —
this is not meant to become a second source of truth alongside `README.md`.

**Baseline** on `main` @ `8112585`:

| Check | Result |
|---|---|
| `pytest apps/api/backend/tests tools/tests -q` | **439 passed** |
| `npm run test` (apps/web) | **134 passed / 23 files** |
| `npm run lint` + `npm run build` (apps/web) | **clean** |
| `tools/run_tests_smoke.py` | ordinance **12 ✅** · acts **80 ✅** · rules **❌ (7 invariant failures)** |
| `ruff check --statistics` | 27 findings, all in `packages/` |
| `ruff check apps/api tools` | clean |
| tracked LOC (`py,jsx,js,mjs,css`) | **84,702** |

Golden corpus JSON under `data/corpora/*/output/`: **90 acts · 12 ordinance · 11 rules = 113**.
sha256 manifests in the session scratchpad (`manifest-{acts,ordinance,rules}.txt`) — the net for
Phase 4, since the agreed verification bar is suite-level rather than a full byte-compare.

Pre-existing rules failures (baseline, not regressions): `section_codes_ordered` (32 + 5 hits),
`no_jammed_words` (1 + 3 + 1), `no_split_ordinals` (1 + 1), `no_orphan_marker_li` (1).

## Ground rules

- A phase is checked off only once its verification gate has actually run, with numbers recorded.
  "Done" without numbers is not done.
- LOC deltas come from `git diff --stat`, not from the plan's estimates. Correct the estimate in
  place when reality differs.
- Anything found mid-phase and deliberately not done goes under **Deferred** with a one-line reason.
- If a phase moves acts/ordinance conversion output, name the invariant and edition inline.

---

## Phase 0 — Freeze the baseline · **done**
- [x] Re-run all five checks, record above
- [x] sha256 manifests for acts + ordinance + rules output
- [x] `tasks.md` created
- Correction: golden JSON count is 113 (90 acts), not the 228 estimated in the plan.

## Phase 1 — Delete dead/broken · **done**
- [x] `apps/api/backend/Dockerfile` (zero refs; pre-monorepo ancestor)
- [x] `apps/api/backend/requirements.txt` (byte-identical to `apps/api/requirements.txt`)
- [x] `apps/api/backend/requirements-dev.txt`
- [x] `apps/api/backend/migrations/` (pycache-only residue of 8 migrations deleted in `8f37a0c`)
- [x] `apps/api/backend/audit_parse_quality.py`
- [x] `apps/web/scripts/toc_acts_audit.mjs` + report + `toc_acts_shots/` (19 tracked PNGs)
- [x] Broken tools: `acts/density_table.py`, `acts/why_missing.py`, `acts/structure_diff.py`,
      `acts/add_scanned_tab.py`, `ordinance/add_test_case.py`, `import_finding_case.py`,
      `import_qa_report.py` (shim)
- [x] Dead tools: `sample_pages_qa.py`, `check_html_sanitizer.py`
- [x] CodeRun: `deploy_coderun.sh`, `filter_deploy_env.py` + test, Makefile `deploy-prod`
- [x] `.env.example`: dead `OCR_CACHE_DIR` → working `ACTS_OCR_CACHE=./data/ocr_cache`
- [x] `.gitignore`: `prod-review-snapshot.json/`, `prod-verify.json/` (pulled forward from Phase 9)
- [x] Fixed dangling doc refs in `README.md` and `data/seed/README.md`

**Result: 42 files, −3,410 / +156 lines. Code LOC 84,702 → 83,110 (−1,592).**
pytest **436** · web **134 ✅** lint/build ✅ · gate ordinance **12 ✅** acts **80 ✅** rules ❌ · ruff clean

pytest 439 → 436 is exactly the 3 tests in the deleted `tools/tests/test_filter_deploy_env.py`
(verified by counting `def test_` in `git show HEAD:...`). Not a regression.

### Three plan corrections — things the plan called dead that are not

- **`tools/acts/ocr_review.py` KEPT.** It is the *producer* of `data/corpora/acts/reports/
  ocr-disagreements-*.md`, which `backend/services/ocr_ingest.py` parses into findings during
  `sync_acts` (`sync_acts.py:508`). 11+ such reports exist on disk. "No caller" only because it is
  manually driven — deleting it would have removed the only way to regenerate a live input.
- **`make seed-archive` KEPT** (only `deploy-prod` deleted). `apps/api/Dockerfile:24` still does
  `COPY data/seed/ /seed/corpus/` and sets `SEED_CORPUS_*`; `seed-archive` is the sole populator of
  `data/seed/`. Deleting it would have removed a live capability, not dead code.
- **`tools/acts/why_unbuilt.py` KEPT** — import-clean, and it explains `build_sections` decisions,
  which is the exact code Phases 4 and 6 change. Useful as a diagnostic during that work.

## Phase 2 — One lane registry · **done**
- [x] `Corpus.source_path()` / `output_path()` / `package` on the registry
- [x] `Corpus.path()` anchors relative values to the repo root (was CWD-relative)
- [x] `tools/corpus_paths.py` → adapter over the registry (was a 2-lane table of its own)
- [x] `tools/{acts,rules,ordinance}/run_tests.py` × 3 inline resolvers → `output_dir(lane)`
- [x] `tools/run_tests_smoke.py` `PIPELINES` + `_corpus_dir` → iterate `CORPORA`
- [x] `tools/acts/convert_all.py` bootstrap → registry
- [x] `tools/sync_corpus.py` per-lane flags generated from `CORPORA` (CLI surface identical)
- [x] Deleted `corpus_sync.default_{ordinance,acts,rules}_path` (3 one-line aliases)
- [x] `corpus_sync` passes `corpus.source_path()` instead of `pdf_dir=None`
- [x] `docker-compose.yml`: YAML anchors + **rules lane** (env + mount, api *and* worker)
- [x] `apps/api/Dockerfile`: rules corpus dirs + `CORPUS_RULES`/`SEED_CORPUS_RULES`
- [x] `northflank.template.json`: `CORPUS_RULES` on both `crx-api` and `crx-worker`

**Result: 12 files, −195 / +209. Code LOC 83,110 → 83,120 (+10).**
pytest **436** · gate ordinance **12 ✅** acts **80 ✅** rules ❌ · ruff clean ·
`docker compose config` VALID, rules env+mount on both services

Net LOC is flat, which is the honest number: ~90 lines of duplicated resolvers came out,
and the registry gained three documented methods plus the self-check coverage for them.
The win here is defect removal, not line count.

### Defects fixed (all were live)

- **`Corpus.path()` was CWD-relative.** Demonstrated: with `CORPUS_ACTS=./data/corpora/acts`
  it returned the bare relative `data/corpora/acts`, so the API and worker — which run from
  different working directories — could resolve the same variable to different places. Now
  always absolute and repo-anchored.
- **`source_path()` hardcoded `Acts/`.** The rules corpus keeps its PDFs under `Rules/`, so
  `sync_acts` never found them directly and only worked because its fallback recursive scan
  happened to reach them. Now `<title>/`-else-root, so it is right by construction.
- **The rules lane could not mount in Docker or production.** `docker-compose.yml`,
  `apps/api/Dockerfile` and `northflank.template.json` all declared two lanes.
- **`corpus_paths.CORPUS_ENV` had two entries**, so `$CORPUS_RULES` was silently ignored by
  every tool importing it, regardless of configuration.

### Plan correction

`corpus_sync.default_{ordinance,acts,rules}_path` were reported as having zero callers. They
did not — `tools/sync_corpus.py` imported all three. Caught by ruff/import failure immediately
after deleting them. Resolved by generating the CLI's per-lane flags from `CORPORA`, which
removes both the aliases and the six hand-written flags; `--help` output verified byte-identical
against `main`.

`run_corpus_sync`'s `ordinance=` / `acts=` / `rules=` / `*_only=` keyword signature is
deliberately untouched — its docstring records that the CLI, the API request body and the
worker payload all speak it, so it is a public contract, not a hardcode to remove.

## Phase 3 — One lane-parameterised suite · not started
- [ ] `tools/suite/{checks,loader,runner}.py` — one copy (was 3x md5-identical)
- [ ] `tools/suite/cases/{acts,rules,ordinance}.json`
- [ ] `invariants/common.py` + thin per-lane modules (acts vs rules differ by 179 of ~2,100 lines)
- [ ] `tools/run_suite.py <lane>` replaces 3x `run_tests.py`
- [ ] One suite README (was 3 near-copies, all citing the dead `scripts/` layout)
- Result: −___ LOC · gate ___

## Phase 4 — Unify acts+rules behind a profile · not started
- [ ] 4a: share the 6 docstring-only-diff modules verbatim (~5,036 LOC)
- [ ] 4b: `profiles.py` with `ACTS` / `RULES`
- [ ] 4c: adopt the cross-corpus fixes unconditionally (`SCHEDULE_TOC_RE`, dash-run terminator,
      `_precedes_first_chapter_in_toc`, real `calibrate._demo`, `CHAPTER_RE` bracket, `folio_value`)
- [ ] 4d: fix `is_code_like` / `_CODE_PARTS_RE` ordering wart
- [ ] Keep `acts_ingest` / `rules_ingest` `__init__.py` shims so the public API is untouched
- Result: −___ LOC · acts ___/80 · ordinance ___/12 · self-checks ___ · acts output moved? ___

## Phase 5 — Collapse converter CLIs · not started
- [ ] One `tools/convert.py <lane> <pdf>` replacing 3x `convert_*.py` + 3x `*_pdf_to_json.py`
- [ ] Makefile `convert-*` become thin wrappers (command surface unchanged)
- [ ] `convert_all.py` path bootstrap reads `CORPORA` (keep the orchestrator itself)
- Result: −___ LOC · all three `make convert-*` produce suite-valid JSON ___

## Phase 6 — Fix the red rules suite · not started
- [ ] `section_codes_ordered` (largest cluster — suspect 4-digit CODE / `code_sort_key`)
- [ ] `no_jammed_words`
- [ ] `no_split_ordinals`
- [ ] `no_orphan_marker_li`
- [ ] Each fix carries a `_demo()` assertion so the gate covers it corpus-free
- Result: rules ___/11 editions · acts still ___/80

## Phase 7 — Backend consolidation · not started
- [ ] `_now()` — 7 copies / 3 formats → one source, per-call-site wire format preserved
- [ ] Byte-identical twins: `_norm_text`, `_html_shape`, `usable`/`_usable_path`
- [ ] 14 `hashlib.sha256` sites → existing `blob_store.sha256_*`
- [ ] 6 JSON-column guards → one `as_json_dict()`
- [ ] 7 "document exists" 404s → one dep (keep each message string verbatim)
- [ ] Family-key: 3 implementations + a 4-deep fallback ladder → `services/editions.py`
- [ ] Split `apply_parsed_document` (427), `parse_json_document` (253), `export_qa_report` (205),
      `worker._execute` (95)
- [ ] Delete verified-dead symbols + dead params
- [ ] Merge 2 duplicated tests; drop ~60 redundant `@pytest.mark.asyncio`
- Result: −___ LOC · pytest ___ · smoke ___

## Phase 8 — Frontend consolidation · not started
- [ ] Fix latent `TypeError`: `TriagePage.jsx:69` `setReviewer` (delete obsolete block `:165-179`)
- [ ] Fix `confirmOnly` ignored by `promptDialog` (stray input on sign-out)
- [ ] Delete dead: `CopyButton` (via adopting it in `HtmlPanel`), `REVIEW_STATUS_*`,
      combined `usePdfRenderer`, `onUserChange` no-op, `getRole` re-export
- [ ] Delete unreachable retry branch `utils/api.js:112-115`
- [ ] Extract: `ProgressBar` (5 copies), `isTypingTarget` (4 divergent), `DocumentListItem`,
      metrics row, PDF page canvas, diff classifier, `setStatus`, corpus sync, `useDebounce`
- [ ] Split `TriagePage` 800 / `DashboardPage` 686 / `ReviewPage` 582 / `Sidebar` 510
- [ ] **State convergence** (own commit): react-query owns server state, Zustand owns UI only
- [ ] CSS: dead rules, `.spin` dup, one chip system, trim inline styles
- [ ] Delete unused assets; set `index.html` title
- [ ] Enable `react-hooks/exhaustive-deps` last; report findings
- Result: −___ LOC · web ___ · smoke ___

## Phase 9 — Docs, config, CI · not started
- [ ] `docs/pipeline-readme.md` (350 lines describing a repo layout that no longer exists)
- [ ] `docs/architecture.md` (no rules lane)
- [ ] `README.md` (layout, 10-of-27 Make targets, broken `import_qa_report`, non-goals)
- [ ] `AGENTS.md` (stale package list, "121 tests" → 439, ruff claims)
- [ ] `.env.example` `SEED_CORPUS_RULES`; `pyproject.toml` `testpaths`; `Makefile check`/`.PHONY`
- [ ] `ci.yml` duplicated postgres service block
- [ ] `.gitignore`: `prod-review-snapshot.json/`, `prod-verify.json/`
- [ ] Northflank naming drift
- Result: −___ LOC · `actionlint` ___

---

## Deferred

- **The `data/seed/` bake-into-image path now has no deploy consumer.** `apps/api/Dockerfile`
  implements it and `docker-compose.yml` sets `SEED_CORPUS_ORDINANCE`/`_ACTS`, but
  `northflank.template.json` sets no `SEED_CORPUS_*` at all — and Northflank is the only live
  deploy target now that CodeRun is gone. So the mechanism works and nothing uses it. Kept rather
  than removed (see Phase 1 corrections); worth a decision: wire it into the Northflank template,
  or drop `seed-archive` + the Dockerfile `COPY` + the compose env together. Raised with the user.
- **`tools/acts/{add_test_case,ocr_review,why_unbuilt,audit_all,audit_completeness}.py` and
  `convert_all.py` are acts-only.** The rules and ordinance lanes have no equivalents. Not creating
  siblings in this refactor; noted so the asymmetry is a decision rather than an oversight.
