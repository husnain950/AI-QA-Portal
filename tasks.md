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

## Phase 3 — One lane-parameterised suite · **done (invariants split deferred)**
- [x] `tools/suite/{checks,loader,runner,__init__}.py` — one copy each (was 3× md5-identical)
- [x] `tools/suite/cases/{acts,rules,ordinance}.json`
- [x] `tools/suite/invariants/{acts,rules,ordinance}.py` (moved; **not yet split** — see below)
- [x] `tools/run_suite.py <lane>` replaces 3× `run_tests.py` (differed by 4 lines)
- [x] One `tools/suite/README.md`; deleted `tools/ordinance/README.md` (4th copy) and the
      two duplicate suite READMEs
- [x] Repaired `tools/add_test_case.py` and `tools/import_qa_report.py` — both were dead
- [x] `run_tests_smoke.py` invokes `run_suite.py <lane>`

**Result: 31 files, −2,550 / +189. Code LOC 83,120 → 81,247 (−1,873).**
pytest **436** · gate ordinance **12 ✅** acts **80 ✅** rules ❌ · ruff clean

**Rules failure set verified byte-identical to baseline** — same 8 lines, same counts
(`section_codes_ordered` 32 + 5, `no_jammed_words` 1 + 3 + 1, `no_split_ordinals` 1 + 1,
`no_orphan_marker_li` 1). The consolidation changed no behaviour.

### Two tools repaired rather than deleted

`add_test_case.py` said `from tests import checks, loader` and `import_qa_report.py` pointed
`CASES` at a `tests/cases.json` that has never existed in this repo — neither could start.
They are how a regression case gets added, which is the workflow the suite README documents,
so they were worth fixing rather than dropping. Both now resolve against `tools/suite/`, and
`add_test_case.py` takes the lane as an argument instead of hardcoding acts.

### Deferred: the invariants split (~2,000 lines still duplicated)

Measured precisely before deciding:

| | count |
|---|---|
| functions identical across all three lanes | 32 |
| identical acts↔rules only | 20 |
| differing acts↔rules | 11 (+1 rules-only) |
| module constants identical across all three | 39 |
| module constants differing acts↔rules | **1** (`_SPLIT_ORDINAL`) |

So the split is well-defined — but a dependency check showed the 32 "common" functions call
lane-specific `_ref_key` and `_SPLIT_ORDINAL`, and `ALL_INVARIANTS` fixes every invariant's
signature to `fn(doc)`, so there is nowhere to pass a lane in. Injecting it needs exactly the
per-corpus profile Phase 4 introduces. Splitting now would mean inventing a second, parallel
injection mechanism and then unpicking it — so this moves to **Phase 6b**, immediately after
the packages are unified. The files are already in their destination directory, so that step
is purely a content split.

## Phase 4 — Unify acts+rules behind a profile · **done**
- [x] `packages/legal_ingest/` — one pipeline, 12 modules (was 2 × 12 forks)
- [x] `packages/legal_ingest/profiles.py` — `Profile` dataclass, `ACTS` / `RULES`
- [x] Profile threaded explicitly (no global state): `run` → `calibrate` → `Calibration.profile`
      → `build_page_model`; `parse_toc(lines, profile)`
- [x] Adopted unconditionally: `SCHEDULE_TOC_RE`, dash-run heading terminator,
      `_precedes_first_chapter_in_toc`, real `calibrate._demo`, `CHAPTER_RE` insertion
      bracket, 4-digit `CODE` + `is_code_like` year guard, `page_offset_samples`
- [x] Gated per corpus: ordinal gap/dtop bounds, `_reattach_raised_ordinals`, folio
      parenthesised + running-title forms, subchapter TOC rows, hyphen leaders,
      codeless TOC rows, TOC-tail density floor, `instrument_kind`, notifying S.R.O.
- [x] `acts_ingest` / `rules_ingest` reduced to profile-binding shims — `from
      <lane>_ingest import run` unchanged
- [x] Submodule importers repointed to `legal_ingest` (backend provenance, 4 acts
      tools, both invariants modules, `apps/api/Dockerfile`)
- [x] `is_code_like` / `_CODE_PARTS_RE` ordering wart fixed by taking the clean base

**Result: 41 files, −12,090 / +393. Code LOC 81,247 → 69,577 (−11,670).**
`packages/` Python: 31,029 → 19,322. pytest **436** · web **134 ✅** build ✅ ·
gate ordinance **12 ✅** acts **80 ✅** rules ❌ (identical failure set) ·
ruff repo-wide **27 → 17** · self-checks **9** (acts had 7; it gains `calibrate`,
`pipeline` and `profiles` coverage it never had)

### Acts output: measured, not assumed

A byte-compare against the committed `output/*.json` showed three differences — but the
control was wrong: **the corpus JSON on disk is stale relative to `main`**. It predates
`metadata.source_kind` and the semantic preamble markup, both of which are in *both*
pre-merge forks. So the golden files are not a baseline for this change.

The correct control is the same PDF converted by pre-change `main` and by the unified
package. Run on three Acts editions, the entire difference is:

```
only in unified: ['.metadata.calibration.page_offset_samples']
differing values: 0
```

One additive metadata field, zero content changes. That is deliberate behaviour change
#4 from the plan and nothing else — the Acts reading is otherwise byte-identical.

### Design notes

`Calibration` carries the profile. `build_page_model` already receives a `Calibration`
at every call site, so this avoided threading a second argument through the page model
and kept the change to signatures small.

Two things the plan expected to be profile knobs turned out not to need to be. The
4-digit `CODE` widening feeds nine *import-time* compiled regexes, so making it vary per
corpus would have meant a lazy per-profile regex layer; instead the widening is adopted
for both with the year guard that accompanies it, which is exactly how the Rules
pipeline already ran — and the 80-edition Acts suite plus the byte-compare above confirm
it changes nothing. Conversely the folio reader needed **two** flags, not one: its "bare"
pattern also accepted `(104)`, and a centred subsection marker in a footer band is
printed the same way, which is why the Acts reader had required `str.isdigit()`.

## Phase 5 — Collapse converter CLIs · **done**
- [x] `tools/convert.py <lane> <pdf>` replaces 6 files:
      `convert_{acts,rules,ordinance}.py` (18 lines each, differed in 3) and
      `{acts/acts,rules/rules,ordinance/fbr}_pdf_to_json.py` (86/86/68; the first two
      differed by one import line)
- [x] Dropped the `importlib.util.spec_from_file_location` indirection — the shims
      loaded a sibling script *by path* to call its `main()`
- [x] Makefile `convert-{ordinance,acts,rules}` collapse to one pattern recipe; the
      documented command surface is unchanged (`make -n` verified for all three)
- [x] `convert_all.py` invokes the unified CLI

**Result: 8 files, −238 / +42. Code LOC 69,577 → 69,388 (−189).**
pytest **436** · gate ordinance **12 ✅** acts **80 ✅** rules ❌ · ruff clean

End-to-end: one real PDF per lane converted through the new CLI —
acts 2 sections/1 page, rules 8 sections/6 pages, ordinance **431 sections/784 pages**.

`--admit-below-floor` applies only to lanes with an OCR stage. Rather than record that
as another per-lane fact, the CLI asks the pipeline (`inspect.signature`), so a lane
that grows an OCR stage starts accepting the flag with no edit here, and one that has
none gets a clear error instead of a `TypeError`.

Noted, not a regression: the ordinance pipeline raises `IndexError` on a stray one-page
notification PDF sitting in the corpus directory (it indexes past the end looking for a
TOC). `packages/fbr_ingest` has **zero files changed** since the baseline commit, so
this predates the refactor entirely. Filed under Deferred.

## Phase 6 — Fix the red rules suite · **diagnosed, needs your call**

Investigated all four failure classes down to the source PDFs. **None is a refactor
regression, and none is a small parser bug.** Two need an ingest feature, one is not
deterministically fixable, and one is a trade-off the pipeline already makes on purpose.

| invariant | hits | root cause | fixable here? |
|---|---|---|---|
| `section_codes_ordered` | 37 | compilation embeds separately-notified instruments | **feature** |
| `no_orphan_marker_li` | 1 | same document, same cause | **feature** |
| `no_jammed_words` | 5 | source PDF emits one 75-char token, no space glyphs | **no** |
| `no_split_ordinals` | 2 | source prints `21 st`; parser refuses on purpose | **no — by design** |

### 1 + 2. Compilations that embed other instruments (38 of 42 hits)

`Customs Rules, 2001` is 563 pages and parses to **one chapter and 62 leaves**. Its TOC
is not a chapter/section contents at all but a *compilation index* of 44 separately
notified rule sets (`17. Duty and Tax Remission (DTRE) for Export S.R.O.185(I)/2020`),
and the literal first line of page 1 is a stray `CHAPTER VII` — which is where the one
chapter's name comes from. TOC detection itself is correct: pages 1-5 score 54-86% and
page 6 drops to 2%.

`Federal Excise Rules 2005` shows the same thing in miniature and is worth reading,
because it makes the shape unambiguous. PDF page 75 is:

```
The
ELECTRONIC FILING OF FEDERAL EXCISE RETURN
RULES, 2005
CONTENTS
1. Short title, application and commencement.
2. Definitions.
...
```

A whole second instrument, with its own contents page, inside the body — so rules 1-5
land after rule 86 inside `CHAPTER XVI`. The invariant is right; the document tree has
no level above chapter for "instrument", and six tree walkers hardcode
chapter/part/division/section as the child keys. `toc.py`'s own `SUBCHAPTER_TOC_RE`
comment already declined a smaller version of this change as "a much larger change than
the defect warrants".

I tried the cheap fix first — refusing a body line whose heading ends in a leader run —
and **reverted it**, because the diagnosis showed those rows do not come through
`_candidate_code` at all, and shipping a guard that fixes nothing measurable is exactly
the speculative complexity this refactor is removing.

### 3. Jammed words (5 hits)

Not a spacing heuristic to tune. pdfplumber reports the run as **one 75-character
token** — `whetherthemonthlyreturnsfurnishedbytheregisteredpersoncorrectlyreflect` — so
there is no positional information inside it to split on. Recovering the spaces needs
dictionary or language-model word splitting, which is non-deterministic and against
both the pipeline's determinism and the README's "no LLM/vision in the conversion path".

### 4. Split ordinals (2 hits)

Footnote 54.104 reads `dated 21 st June, 2006`. The parser refuses to merge it
**deliberately**, and `pagemodel` says why: the discriminators are a size drop and the
absence of a space glyph, and this one is equal size (8.04pt), dtop 0.00, with a real
space — indistinguishable from a genuine `21 st` typo in the source. Merging it would
mean merging real typos too. The invariant does not know the parser made that choice.

### The decision

Making this suite green needs one of:

- **(a)** an `instrument` level in the document tree + a body-side contents-block
  suppressor — a real ingest feature touching the tree, six walkers, the JSON schema
  and the portal's leaf labelling;
- **(b)** a per-document invariant exemption mechanism (the suite has `known_gap` for
  *cases* but invariant failures are unconditionally hard), recording these four with
  their reasons so the suite gates everything else;
- **(c)** leave it red and keep the baseline documented, as it was before this work.

I have not chosen for you: (a) is a feature, (b) changes the suite's contract, and (c)
is the status quo. **Raised with the user.** The failure set is byte-identical to the
pre-refactor baseline either way, verified after every phase.

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

- **`fbr_ingest` crashes on a non-edition PDF.** `data/corpora/ordinance/Income Tax
  Ordinance, 2001/` contains a one-page notification alongside the real editions;
  converting it raises `IndexError` from `_toc_lines` indexing past the last page.
  Pre-existing (fbr_ingest is untouched), and it does not affect the suite because the
  corpus is defined by `output/*.json`, not by the PDFs present. A `len(pdf.pages)`
  guard would fix it.

- **The `data/seed/` bake-into-image path now has no deploy consumer.** `apps/api/Dockerfile`
  implements it and `docker-compose.yml` sets `SEED_CORPUS_ORDINANCE`/`_ACTS`, but
  `northflank.template.json` sets no `SEED_CORPUS_*` at all — and Northflank is the only live
  deploy target now that CodeRun is gone. So the mechanism works and nothing uses it. Kept rather
  than removed (see Phase 1 corrections); worth a decision: wire it into the Northflank template,
  or drop `seed-archive` + the Dockerfile `COPY` + the compose env together. Raised with the user.
- **`tools/acts/{add_test_case,ocr_review,why_unbuilt,audit_all,audit_completeness}.py` and
  `convert_all.py` are acts-only.** The rules and ordinance lanes have no equivalents. Not creating
  siblings in this refactor; noted so the asymmetry is a decision rather than an oversight.
