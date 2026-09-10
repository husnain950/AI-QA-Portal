# The execution ledger

**This file is updated as work happens, never after.** If a box is ticked, the thing is
merged on `main`.

**State:** the register is **13**, regenerated in PR #89 and **verified against a live
three-lane run** on a corpus converted at one revision — acts 6, rules 2, ordinance 5, delta
zero, no lane skipped. Reasoning for every row is in [`plan.md`](plan.md); state is in
[`README.md`](README.md); the traps are in [`working-rules.md`](working-rules.md).

Written 2026-09-04 on `main` after PR #83 (round 17); updated after PR #84 (round 18),
PR #85 (round 19), PR #86 (round 20), and **2026-09-10 after PR #89 (rounds 21-28)**.
Artifact: [`wip/phase3-round21-28-customs-qa.md`](../wip/phase3-round21-28-customs-qa.md).

**Nine invariant classes are closed.** Round 15 closed `section_codes_ordered` — see
[task 1's Result](#1-trace-section_codes_ordered--3-hits-acts--closed-round-15). Round 16
closed one of `section_carries_its_body`'s causes, taking that class 21 → 17 — see
[task 2's Result](#2-the-stsp-58u58v-pair--4-hits-rules--closed-round-16).

**Rounds 21-28 (PR #89) closed three more and took the register 22 → 13.** Eight rounds
against one Customs Act edition, closing 21 reviewer-logged defects; the acts lane went
**15 → 6**. `no_chapter_caption_in_section_heading`, `preamble_carries_no_toc_tail` and
`clause_codes_plausible` are all **0**, and so are the two omission spellings. Those were
rows 1, 2, 3 and 5 of the board below — see each row's Result.

**Read this before believing any Result below that credits round 20.** Round 20 shipped
working code for rows 1, 2, 3 and 5 and could not move the register, because the private
editions carrying the hits were absent from that host. The rounds 21-28 re-conversion is
what turned those into zeroes. **Shipped and measured are two different states**, and this
ledger carried four rows as open for a full round because it conflated them. When a Result
says "code shipped, register not moved", the row is *not* closed — it is unmeasured.

**Round 17 closed the container-code guard** and shipped the PART separator widening it
enables: 14 gained, 0 lost, register unchanged at 25 — see
[task 4's Result](#4-the-container-code-guard--0-hits-an-enabler--closed-round-17).

**Round 18 closed the CHAPTER letter suffix** — the row that had been top of the board:
**80 swallowed boundary lines across 24 documents went to 0**, register **unchanged at 25**
(rise +57 on the invariant, fall −57 on the parser) — see
[task 3's Result](#3-the-chapter-letter-suffix--57-hits-24-documents--closed-round-18). It
also **located a second gap on the same line of code** and left it open on evidence: the
**en-dash separator**, 42 lines across 21 documents, closed by round 20.

**Round 19 closed the round-10 rules residue** — **25 → 22**, by *exemption with evidence*:
all three are printing errors traced to PDF pages 66, 109 and 151. **Two of the three traces
this file carried were wrong** — see
[task 5's Result](#5-the-round-10-rules-residue--3-hits-an-exemption-row).

### Decisions on record (2026-09-04)

Taken by the repository owner, so they are not rediscovered:

| decision | consequence |
|---|---|
| **Scope: everything**, through Phase 5 | the ranked table below is worked top to bottom, not sampled |
| **OCR (row 13) stays out of scope**, recorded as a deliberate "no" | `data/ocr_cache` stays 0 B; row 14 stays blocked, but *honestly* blocked |
| **`ReviewToolbar` gates on CRITICAL flags only** (row 15) | switch to `hasCriticalQualityFlags`, matching the backend's `CRITICAL_FLAGS` |
| Context is cleared between PRs | **this folder is the only memory that survives; updating it is part of the PR** |

**Execution order** no longer differs from the value ranking. It did for one round: the
container-code guard was worked before the CHAPTER letter suffix so that row 1's twenty
Customs editions would be re-converted once rather than twice. **Round 17 landed the
guard**, so row 1 is now simply the top row.

One thing that reordering was *also* justified by turned out to be false, and round 17
measured it: the guard would **not** have kept round 13 from dropping four chapter captions
in Customs Rules 2001. See [task 4's Result](#4-the-container-code-guard--0-hits-an-enabler--closed-round-17).

---

## Start here — pick one

Ranked by value against cost, each with the ONE thing that actually blocks it. An agent
with no other context can take a row and start.

**This board was rebuilt on 2026-09-10 from a live three-lane run, not from the previous
board.** Rounds 21-28 closed four of its rows, and the register they close against is
**13**, not 22. Every hit count below is the live one.

| # | pick this up | hits | the single blocker | plan.md |
|---|---|---|---|---|
| 1 | **letter-suffixed citation markers** | 0 ¹ | **nothing.** 22 marker-size words carrying an UPPERCASE suffix (`59&59A`, `66A`, `27/27A`, `2/2A`, `18/18A`) render as literal body text and build no footnote record, because `grammar.MARKER` (`:132`) allows `[a-z]` only. One cause, 9 sections, 6 chapters | *(new — see the row below)* |
| 2 | **the ordinance five** | 5 | all in `fbr_ingest` on ITO editions (233AA, 214E ×2, 122C ×2). **No longer blocked on a decision** — round 20 decided routing, and ITO stays on `fbr_ingest`. It is a parser round in the fork | [P4-2](plan.md#p4-2--decide-the-fbr_ingest-fork--a-routing-problem) |
| 3 | **the single-document remainder** | 4 | nothing shared — PSW ministry list (ss.27/28), PFMA s.26, Sales Tax 2014 s.10 `R(cid:2)fund`. Three unrelated traces | [P3-1e](plan.md#p3-1--section_carries_its_body-17--four-unrelated-causes-one-of-them-closed) |
| 4 | **Customs 2008 ss.181 / 189** | 2 | **newly visible, and nobody has read those pages.** Two heading-only leaves in one edition — the only shared-cause candidate left in acts | *(none yet)* |
| 5 | **the two rules hits** | 2 | Sales Tax Rules 30-06-2025 rule 150 is the `150ZQ*` family again; 01-01-2025 rule 13 carries the start of 44A under `no_foreign_section_start_in_body`, which the round-19 exemption does **not** cover — that entry names `section_carries_its_body` | [P3-1e](plan.md#p3-1--section_carries_its_body-17--four-unrelated-causes-one-of-them-closed) |
| 6 | delete `_legacy_section_key` | — | **BLOCKED on row 12**, decided as *no OCR* — so the 14 stale acts documents stay stale. The query that would confirm the 6 documents / 89 leaves **does not exist yet**; writing it is step 1 | [Deferred](#deferred-with-reasons) |
| 7 | the `ReviewToolbar` approval gate | — | **DECIDED 2026-09-04: gate on CRITICAL flags only.** Switch to `hasCriticalQualityFlags`, already tested and unused. One line plus the test. Cheapest row on the board | [Deferred](#deferred-with-reasons) |
| 8 | delete the Zustand mirror | — | 8 consumer modules, and **no data-hooks layer exists to move onto** — it must be written. Architecture, not a defect | [Deferred](#deferred-with-reasons) |
| 12 | the OCR decision | — | **DECIDED 2026-09-04: out of scope, deliberately.** `data/ocr_cache` stays 0 B. Not work — the decision is the deliverable, and it is recorded | [Phase 2](plan.md#phase-2--the-ocr-half-a-decision-not-work) |

¹ **Zero in the register, and that is the point.** The invariants share the parser's marker
grammar, so `inv_leading_marker_cited`, `inv_citation_refs_resolve` and
`inv_footnote_on_citing_leaf` are all as blind to an uppercase suffix as the builder is.
This is the exact shape row 5 of the old board had before round 18 closed it: **expect the
register to rise when the invariant is widened and fall when the parser is.** Measure the
two halves separately. `inv_footnotes_in_numeric_order` sees ordering only, so a *missing*
note is invisible to it in any case.

### Closed by rounds 21-28 (PR #89) — kept so they are not re-picked

| old row | was | now |
|---|---|---|
| the heading-terminator scan | 3 | **0** — `no_chapter_caption_in_section_heading` is gone from the register |
| the omission spellings | 2 | **0** — neither Customs 30.06.2024 s.196K nor 30.06.2025 s.79 is a hit |
| `preamble_carries_no_toc_tail` | 2 | **0** — the class is closed |
| `clause_codes_plausible` | 1 | **0** — closed by round 20's code, measured by round 21-28's re-conversion |

Rows 7-12 of the old board (the schedule PART reader, the CHAPTER en-dash, the cross-edition
index, the instrument tree, `--profile auto`) were closed by round 20 and are dropped from
the ranking rather than carried as zeroes. Their Results are still below.

### Traced but not taken — evidence recorded, no row opened

Found on 2026-09-10 while tracing the rounds 21-28 leftovers. Each is a **different cause**
from row 1, and this file forbids batching unrelated causes into one round:

- **s.156's `69.` and `81,`** — the two cells the rounds 21-28 handoff called "penalty-table
  marker cells". Its named cause was wrong: `pagemodel._true_table_marker` is never reached
  (that table is not grid-extracted; its `<tbody>` is empty). `69.` dies on the trailing-dot
  guard (`pagemodel.py:152`), `81,` because `_MARKER_RUN_SEP_RE` splits `"81,"` into
  `['81','']` and the empty tail fails `MARKER_RE` (`grammar.py:257`). The printed run is
  `81, 89` with a space, so the comma dangles. `grammar.MARKER_PREFIX` already tolerates
  this shape — but only for the section-heading prefix.
- **`1b[(7)` in s.185A** — the genuine part-marker/part-text token. `_render_words`
  (`builder.py:240-259`) treats a word as all-marker or all-text; there is no partial-consume
  path. The handoff ascribed this to s.2, whose cross-reference **renders correctly today**.
- **`pagemodel.CITE_SENT_RE_TEXT` is dead code.** Nothing consumes it; the live pattern is
  the hand-duplicated `builder.py:726` `_CITE_SENT_RE`, with a third looser copy at `:845`.
  Any widening has to touch the copies that run.
- **Chapter V footnotes 42 and 66** — source defects (66 is never printed, the block runs
  65 → 67; 42 is printed indented under 41's quotation). **They cannot be exempted**: an
  exemption keys on `applies_to` + `invariant`, and no invariant reports a missing footnote.
  Recorded here because "fixed, or exempted with evidence" has no third state for a defect
  no instrument can see — which makes this an argument for an instrument, not for a waiver.
- **s.29's mid-title bracket** — `Restriction on amendment of [goods declaration`. Round 21's
  strip (`builder.py:3114`) is anchored `^[\s\[(]+`, so a mid-string bracket never reaches
  its count test. Cosmetic.

**Before touching any of them, read [Rules of engagement](#rules-of-engagement).** Every
rule there was paid for, and three of them have drawn blood twice.

### How this reconciles to `wip/tasks.md`

The unchecked boxes in `wip/tasks.md` map onto the rows above exactly. `wip/` is frozen,
so its box for `section_codes_ordered` (`:664`) is still unticked there — **round 15
closed it**, and this file is the authority on that, not `wip/`.

| `wip/tasks.md` line | row above |
|---|---|
| `:664` `section_codes_ordered` | **CLOSED, round 15.** It said **4** hits, the register said **3**, and it is now **0** |
| `:401` container-code guard | **CLOSED, round 17.** 14 gained, 0 lost, register unchanged |
| `:418` CHAPTER letter suffix | **CLOSED, round 18.** 80 lines over 24 documents to 0; register unchanged |
| `:436` `section_carries_its_body` — now **12** | rows 2, 3, 5 (one box; round 16 closed one cause, round 19 exempted the round-10 residue, rounds 21-28 closed the omission spellings) |
| `:388` heading-terminator scan | **CLOSED, rounds 21-28.** The class is 0 |
| `:379` `preamble_carries_no_toc_tail` | **CLOSED, rounds 21-28.** The class is 0 |
| `:668` `clause_codes_plausible` | **CLOSED, round 20, measured rounds 21-28.** The class is 0 |
| `:712` decide `fbr_ingest` · `:430` its dormant copies | 8 (two boxes) |
| `:503` no invariant sees a 93% loss | 10 |
| `:741` `:742` `:743` `:744` the four Phase 5 limbs | 11 (four boxes) |
| `:701` `--profile auto` default | 12 |
| `:184` OCR · `:190` the 9 provisional · `:192` the ordinance 10 | 13 (three boxes) |
| `:536` `convert_all.py` cannot resume · `:671` the 29 low-confidence documents · `:79` rebuild api/worker images | [Deferred](#deferred-with-reasons) (three boxes) |

The schedule PART reader and the CHAPTER en-dash separator had no box in `wip/` at all —
round 17 and round 18 located them as new work, and round 20 closed both. The three
integration leftovers (rows 6-8 above) come from `wip/integration/tasks.md`'s own ledger,
not from `wip/tasks.md`.

Recounted 2026-09-10: **5 register-bearing rows + 3 integration leftovers + the OCR decision
= 9 open things**, down from 22. Four of the register rows are 1-2 hits each on unrelated
single documents, which is the shape `open-work.md` predicted for the tail.

---

## Rules of engagement

The full set, because this is the file an agent actually opens. Long-form reasoning:
[`working-rules.md`](working-rules.md).

### Never

- **Never commit to `main`.** One branch and one PR per unit of work.
- **Never edit `packages/` while a conversion runs.** `convert_all.py` spawns a fresh child
  per document, so each imports the parser *when it starts*; an edit mid-run gives early
  documents the old code and later ones the new. **A mixed-revision corpus looks
  completely normal.** Done twice in one session, ~30 minutes each. Kill and restart.
- **Never run `make convert-all` to "re-convert the lane".** It converts the whole **lane**,
  not the corpus: `LANE=ordinance` targets all 46 ordinance PDFs where only 12 are in the
  corpus — quadrupling it and pushing 34 new documents at the portal. **The same gap exists
  on acts (80 of 93).** Convert **per file with an explicit `-o`**:
  ```sh
  make convert-acts PDF="data/corpora/acts/<...>.pdf" OUT="data/corpora/acts/output/<...>.json"
  ```
  (`Makefile:51-53`; `OUT=` becomes `-o`. `convert-all` is `Makefile:58-60`.)
- **Never weaken `clause_codes_plausible`** to clear its one hit.
- **Never lower `detect_toc_pages`'s `rows >= 3` floor** — its own comment
  (`calibrate.py:288-297`) records a lower one swallowing the Income Tax Rules' body title
  page.
- **Never "repair" `test_the_letter_suffixed_chapter_gap_is_still_open`.** It asserts the
  current *wrong* answer on purpose; its failure is the signal the widening landed.
- **Never let `data/ocr_cache` grow** until OCR is deliberately taken in scope.
- **Never edit `wip/`.** It is the historical record, and shipping code cites it —
  `tools/convert.py:88`, `tools/discover_corpus.py:423`,
  `packages/legal_ingest/families.py:98,183`, `_common.py:1098,2163`, and 4 exemption
  entries name `wip/tasks.md` as their expiry condition.

### Conversion

- **`convert_all.py` cannot resume.** Two runs killed mid-flight left 49 of 80 acts
  documents at the new revision — the mixed-revision hazard above. **`--skip-existing` does
  not help**: after a re-conversion every output exists. What worked was converting only
  outputs older than the parser's mtime.
- **Nineteen source files have no `.pdf` extension**, not two. This rule used to name
  only Customs Rules 2001 and The Finance (Supplementary) Act 2022; a round-16 walk of the
  three lanes counts **6 in acts, 12 in rules, 1 in ordinance**, including five Customs Act
  editions and four Sales Tax Rules 2006 editions. A `**/*.pdf` glob misses every one of
  them **silently** — and so does the obvious repair `name.endswith(".pdf") or "." not in
  name`, because these names carry a dot in their *date* (`Customs Act, 1969 as amended up
  to 30.06.2021`). Sniff the file, or list the directory; do not pattern-match the name.
- **`make convert-*` from a worktree runs the WRONG interpreter.** The Makefile sets
  `PYTHON := $(ROOT)/.venv/bin/python` only `ifneq (,$(wildcard $(ROOT)/.venv/bin/python))`
  and `ROOT` is the *worktree*, which has no `.venv` — so it silently falls back to
  `python3` and dies on `ModuleNotFoundError: No module named 'pdfplumber'`. Pass the main
  tree's interpreter explicitly:
  ```sh
  make convert-rules PYTHON=/Users/muhammad.husnain/Downloads/code/crx/.venv/bin/python \
    PDF="…" OUT="…"
  ```
  It still imports `packages/` from the worktree — that part is right, and it is the whole
  point of converting from there.
- **A worktree has no corpus, and `tools/*.py` resolve everything from `__file__`.**
  `data/corpora/*` is gitignored, so a fresh worktree holds only its README — and because
  both the import root and the corpus root come from `__file__`, running a tool from the
  main tree measures **main's** parser while running it from the worktree finds **no
  documents**. Symlink the lanes in once, with **absolute** targets:
  ```sh
  for L in acts rules ordinance; do ln -sfn "$PWD/data/corpora/$L" .worktrees/rN/data/corpora/$L; done
  ```
  (A relative `../../../` from `.worktrees/rN/data/corpora/` lands in `.worktrees/`.)
- **The Bash tool's cwd resets between calls — use absolute paths in every edit.** In
  round 15 a heredoc with a relative path patched `packages/` in the **main tree**; half
  the change landed on the wrong branch and the measurement silently used unfixed code.
  `git status` in **both** trees before trusting a number.
- **Clear `__pycache__` after any mutate-and-restore verification.** Patching a module,
  re-importing and restoring leaves stale bytecode: the source is right while the module in
  memory is the version you rejected. Caught by pytest only *after* a re-conversion had
  already run against it.
- `--profile auto` is **refused on ordinance** up front (`convert_all.py:486`).

### Measuring

- **Measure the invariant fix and the parser fix separately**, on identical JSON for the
  first. Nearly every class is part wrong-invariant, part real defect, and a single total
  hides both. `no_footnote_text_in_body` was 45 hits that were *all* a `title=` attribute —
  concealing a 473-footnote defect underneath.
- **Measure candidate widenings as gained/lost — and know which corpus you are measuring.**
  A naive `MARKER_PREFIX` widening scored **1 fix : 17 false positives**; the narrowed form
  scored **1 : 0**. But every measurement here runs over `output/*.json` `plain_text`, and
  **that is not what the parser sees**: the parser's line is `42 53 [202B.` where the
  rendering collapses it to `42 53[202B.`. A lookahead anchored on `[` matched the JSON and
  missed the PDF.
- **Verify a lock by removing the fix.** A parenting lock passed with the fix stubbed out —
  its two-chapter fixture let a later pass repair the damage; three chapters reproduced the
  real document. **A gate that cannot be made to fail on purpose is not a gate.**
- **Report changes that moved a number by zero.** Round 4's acts lane and round 6's PART fix
  were both correct and both scored nothing; folding them into a total would have
  misattributed the rounds that did move it.
- **A cached artifact cannot tell you its generator is wrong.** Three instances in one
  phase. Only the `exemptions/` format reported itself stale, unprompted. That is the
  argument for the register snapshot.
- **Read the comments before generalising.** `_DOTSUFFIX_RE` (`builder.py:1424-1430`)
  carried a measurement saying its bracket gate was safe; re-running it showed the
  measurement had expired — but it was still right about the danger.
- **The obvious generalisation is often wrong.** `XIVA` and `XIV-A` are two *different*
  chapters of Sales Tax Rules 2006; matching numerals by value collapses them.

### The seam to the portal

- **A parse-only change does not travel.** `create_version` gates on `source_hash` — the
  JSON *bytes* — so editing `json_parser` / `parse_quality` / `html_sanitizer` reaches no
  existing row on re-sync, **`--force` included**. Measure it as two fresh first-ingests
  into a scratch database (`wip/integration/measure/p5_seam.py`, scratch DB
  `pdf_qa_p5scratch`), never as a re-sync of an existing one.
- **The local dev database is many rounds stale.** An acts document never re-converted and
  never re-synced has **304 of 309** stored leaves differing from a fresh parse. Any
  carryover or approval-loss number measured against it is an artefact of its age.
- **Run the whole web suite, against its baseline.** From `apps/web`: `npm run test` (or
  `npx vitest run`) is **17 failed here, always**, in `libraryFavorites` and `libraryPage`
  (Node 26 wants `--localstorage-file`; CI pins 22). Diff against that baseline — do not
  skip the suite, and **do not run only the files you touched**: that misses the ones that
  *consume* them, which is how #75 shipped a red build.
- **The Northflank deploy is outward-facing and gated on green CI on `main`.** Confirm
  before triggering it.

### Gates and lint

- **CI does not gate the pipeline.** `data/corpora/*/output/` is gitignored, so all three
  lane suites SKIP on CI. Seven rounds moved the register 210 → 64 with nothing enforcing
  those numbers but prose. **Green checks on a PR are not evidence about ingest.**
- **`tools/tests/test_register_snapshot.py` is the real gate**, and only where the corpus is
  staged. It scrapes suite stdout (`:34`), so **changing `tools/suite/runner.py:110`'s print
  format breaks it silently.**
- **Run `ruff check` bare.** `pyproject.toml`'s `src = ["apps/api", "packages", "tools"]` is
  what pulls `packages/` in; `ruff check apps/api tools` silently misses it. `Makefile:80-92`
  and `ci.yml` both run it bare — match them.
- **A regression case should assert the property it names, not the markup.** Two cases were
  pinned to an attribute-free `<p>` that the current parser classes; `re.search` made the
  fix two characters each.
- **Every behaviour change ships with the test that fails without it, in the same PR.**

### And the one that governs all of it

**Fixed, or exempted with evidence traced to the source PDF. There is no third state.**
"Tracked and deferred" without an entry in `tools/suite/exemptions/<lane>.json` is a red
gate, not a decision.

---

## How a round runs — worked for round 18

Copy this. Do not invent a variation.

```sh
# 1. Branch. Use a worktree -- the tree is shared with peer sessions.
git worktree add .worktrees/r18 -b fix/phase3-round18-<slug> main
cd .worktrees/r18

# 2. Baseline, before touching anything. The corpus lives in the MAIN tree
#    (data/corpora is gitignored, so a worktree has no copy) -- run suites from there.
cd /Users/muhammad.husnain/Downloads/code/crx
for L in acts rules ordinance; do .venv/bin/python tools/run_suite.py $L > /tmp/pre-$L.txt; done   # 6 / 2 / 5 today

# 3. Snapshot the outputs you are about to overwrite.
mkdir -p data/corpora/acts/output/_pre_18 \
  && cp data/corpora/acts/output/*.json data/corpora/acts/output/_pre_18/

# 4. Write the failing test FIRST, then the fix. Confirm the test fails without it.
.venv/bin/python -m pytest tools/tests/<the new test> -q      # must be RED

# 5. Re-convert ONLY the affected documents, per file, explicit -o. Never convert-all.
#    PYTHON= is REQUIRED from a worktree -- see the Conversion rules.
make convert-acts PYTHON=/Users/muhammad.husnain/Downloads/code/crx/.venv/bin/python \
  PDF="data/corpora/acts/<...>" OUT="data/corpora/acts/output/<...>.json"
#    Do not edit packages/ while this runs. Mind the 19 files with no .pdf extension.

# 6. Re-measure ALL THREE lanes -- a fix in one lane can move another.
for L in acts rules ordinance; do .venv/bin/python tools/run_suite.py $L; done   # 6 / 2 / 5

# 7. Regenerate the register IN THIS PR. No Make target, no pytest flag.
.venv/bin/python tools/tests/test_register_snapshot.py --write

# 8. Full gate.
.venv/bin/python -m pytest tools/tests -q     # baseline: 231 passed, 1 skipped
.venv/bin/ruff check                          # BARE
du -sh data/ocr_cache                         # must still be 0B
cd apps/web && npm run test                   # only if you touched the portal; 17-failed baseline
```

Then: write the round artifact as `wip/phase3-round18-<slug>.md`
— **a new file; do not edit existing `wip/` files** — following the shape of
`wip/phase3-round17-container-code-guard.md`: what was measured, what moved, what moved
by **zero**, and what was rejected and why. Open **PR #84** with the before/after
artifact linked in the body.

**If the register improved, `test_register_snapshot.py` fails until step 7 is done.** That
is the design, not a bug.

---

## The tasks

Each carries: what it closes · **Steps** · **Definition of done** · **Do not** ·
**Result** (empty until it lands).

**The numbers here are stable anchors, not the ranking.** Sections are never renumbered —
three of them are closed rounds that other files cite — so they drift from the *Start
here* table as rows close. Current mapping:

| Start here row | section below |
|---|---|
| 1 letter-suffixed citation markers | *none yet* — traced 2026-09-10; the trace is in the Start here table above |
| 2 the ordinance five | [11](#11-decide-the-fbr_ingest-fork--unblocks-5-hits-and-9-documents) |
| 3 the single-document remainder | [9](#9-the-single-document-remainder--7-hits) |
| 4 Customs 2008 ss.181 / 189 | *none yet* — newly visible on the live run |
| 5 the two rules hits | *none yet* |
| 12 the OCR decision | [15](#15-the-ocr-decision--blocked-needs-a-human) |

Closed: section [1](#1-trace-section_codes_ordered--3-hits-acts--closed-round-15) (round
15), [2](#2-the-stsp-58u58v-pair--4-hits-rules--closed-round-16) (round 16),
[4](#4-the-container-code-guard--0-hits-an-enabler--closed-round-17) (round 17),
[3](#3-the-chapter-letter-suffix--57-hits-24-documents--closed-round-18) (round 18),
[5](#5-the-round-10-rules-residue--3-hits-an-exemption-row) (round 19),
[12](#12-the-cross-edition-index--a-new-instrument), [13](#13-the-instrument-tree-level--phase-5-4-limbs),
[14](#14---profile-auto-as-the-default--blocked) (round 20), and
[6](#6-the-heading-terminator-scan--3-hits-acts), [7](#7-the-omission-spellings--2-hits-acts),
[8](#8-preamble_carries_no_toc_tail--2-hits-acts), [10](#10-clause_codes_plausible--1-hit-finance-act-2024)
(**rounds 21-28** — code from round 20, measured by the round-27 re-conversion).

### 1. Trace `section_codes_ordered` — 3 hits, acts — **CLOSED, round 15**

**Closed by PR #81 (round 15).** Artifact:
`wip/phase3-round15-chapter-numeral-pairing.md`. Kept here because what it found
contradicts what this row predicted, and the next rows inherit that.

**Result** — register **32 → 29**; `run_suite.py acts` **18 → 15**; the invariant is
**0 — the class is closed**, the sixth to close. rules and ordinance moved by **zero**.

**No hit was what this row assumed.** The row said *"decide per hit: parser defect (the
code was misread) or printed defect"*, and expected `tools/suite/exemptions/acts.json` to
be created. **All three source pages are correct, no code was misread, and that file
still does not exist.** Not one section code was wrong — three *chapters* were mislabelled,
and the invariant could only see the consequence: sections walking backwards because
their container sorts elsewhere.

| document | hit | the page says | was parsed as |
|---|---|---|---|
| Customs 1969 30.06.2025 | `'9' after '119'` | contents p3: ss.9-11 under `CHAPTER III` | `CHAPTER XI` / WAREHOUSING |
| Sales Tax 1990 01.07.2014 | `'3' after '32AA'` | body p51: `Chapter-VI` | `CHAPTER I` / PRELIMINARY |
| Sales Tax 1990 01.07.2014 | `'22' after '75'` | body p81: `Chapter-IX` | `CHAPTER III` / REGISTRATION |

**Two causes, one shared endpoint.**

1. **`toc.py`, the CHAPTER branch of `parse_toc`.** A chapter row did not close a section
   row that printed **no folio at all**. Customs' contents print `3F Hiring of technology
   specialists…` with no page number; `SECTION_NOPAGE_RE` parks it in `pending_page` for
   its wrapped title and nothing cleared it, so `CHAPTER III`'s caption was offered to
   s.3F, correctly judged foreign to it, and opened as a chapter of its own. **`CHAPTER
   III` came out twice** — a coded shell beside a numeral-less node holding III's caption
   and its sections. `_open_caption_chapter` resets all three state variables; this branch
   reset two. **The fix is the third.**
2. **`pipeline.py`, `insert_missing_body_chapters`.** `zip(empties, unused)` paired
   leftover numeral-less nodes with leftover body numerals **by list position**, which is
   right only if the two lists correspond one-to-one. They need not. Replaced with pairing
   by **which body span actually prints that node's own sections**, reusing
   `_codes_in_span`, already defined in that function.

**Leaf counts unchanged** — 325 and 116. Sections changed container; none was gained or
lost. That is the check round 13 failed (127 → 126).

**Scope was measured, not guessed.** Each acts/rules document's contents were parsed twice
at the same commit, fix on and fix off, and compared: **8 documents change, 7 more carry a
code-less chapter (cause 2's only reach), 76 are provably untouchable.** Those 15 were
re-converted; **0 failures, 0 refusals**. 10 of the 15 moved by **zero** and are reported
as such. **The ordinance lane cannot be reached by either fix — it runs `fbr_ingest`,
which has its own `toc.py` and its own `insert_missing_body_chapters`.**

**What was rejected:** an exemption (no printed defect exists); widening
`_captions_match`'s 3-word floor to 2 (a 2-word coincidence would bind chapters across 103
documents — the floor is untouched, the fallback beneath it was the defect); reparenting by
page order (tree-walk and page order legitimately disagree on 21 of 103 documents, which
is P5's reading-order limb); porting either fix into the `fbr_ingest` fork (row 9's call).

---

### 2. The STSP 58U/58V pair — 4 hits, rules — **CLOSED, round 16**

**Closed by PR #82 (round 16).** Artifact: `wip/phase3-round16-bracketed-code-dot.md`.
Kept here because the row's prediction was right about the cause and wrong about its reach,
and rows 1–7 inherit both halves of that.

**Result** — register **29 → 25**; `run_suite.py rules` **9 → 5**; both editions
**ALL PASS**. acts and ordinance moved by **zero**. `section_carries_its_body` is
**21 → 17** (acts 8, rules 4, ordinance 5) — one of its four causes closed, the class is not.

**The row said "one cause, two editions", and that was right.** S.R.O. 188(I)/2015
*renamed* rules 59 and 60, so both editions print the code inside the amendment bracket
with the dot outside it:

```
111[58U]. Application:--The provisions of this Chapter shall apply to
112[58V]. Conditions and limitations for availing zero-rating facility:--(1)
```

**It was a misread, not a miss.** `_BRACKETED_DOTLESS_RE` — the last pattern
`builder._candidate_code_raw` tries — backtracks `CODE` to its digits and reads the suffix
letter as the title's first capital, so `111[58U].` returned the code **`58`**, a real rule
of Chapter IX forty pages earlier. 58U and 58V bound to nothing and their 5,534 characters
were carried onto 58W, which pushed 58W's own text onto 58X. One new pattern,
`_BRACKETED_CODE_DOT_RE` (`builder.py:1383`), tried before the one that reads the shape
wrongly.

**Leaf counts unchanged** — 92 and 88. The only text delta is 83 characters per edition,
and it is the *deletion* of the two placeholder headings the empty leaves carried. Nothing
moved in or out. Conservation is 100.000% / 0 missing on both documents **before and
after** — a multiset audit cannot see a placement error, which is worth knowing before
trusting one again.

**What the row did not predict: the same shape is in a third document.** Rules 19D–19G of
**Income Tax Rules 2002 print it in all six editions** and all four currently read as rule
`19`. This fix repairs them. **None was converted** — that document has no
`output/*.json`, and converting it would push six new documents into the corpus and at the
portal. They score zero here and are the row-1 lesson in miniature: *the fix's reach and
the corpus's reach are different numbers.*

**Scope was measured over the source, not the output.** 290,982 distinct text lines from
every PDF in the three lanes, scored against `main`'s `_candidate_code`: the shipped form
**gains 0 and changes 12, all 12 correct.** Read with a bare `CODE` instead of
`CODE_SUFFIXED` it also gains a penalty **table row serial** — Sales Tax 01.07.2014's
`2[21].Where any person repeats an offence`, inside s.33's table, forty pages past s.21.
The letter suffix is the guard.

---

### 3. The CHAPTER letter suffix — 57 hits, 24 documents — **CLOSED, round 18**

`_STRUCTURAL_RE` (`packages/legal_ingest/builder.py:2104-2106`) has a CHAPTER branch of
`CHAPTER[\s\-]+[IVXLC0-9]+` — **no letter-suffix class, where PART and Division beside it
both carry `[A-Z]{0,2}`.** Measured at 57 hits / 24 documents / **zero false**.

**Steps**
1. Widen the CHAPTER branch's numeral to carry the same suffix class as PART and Division.
   Read the measured comment at `:2085-2103` first — it explains why PART and Division stay
   on `\s+`.
2. Run `tools/tests/test_structural_boundary_agrees_with_grammar.py`. **It will fail at
   `:90-96`. That is the signal.** Move the four lines from `KNOWN_GAP_SUFFIXED_CHAPTERS`
   (`:63-65`) into `BOUNDARIES` (`:35-39`), as the assertion message itself instructs.
3. Check `test_a_boundary_the_split_cannot_read_would_become_a_nameless_division`
   (`:112-123`) still passes — every `BOUNDARIES` line must split to a keyword plus a
   non-empty numeral, or it silently becomes a nameless Division.
4. **Re-convert 44 documents**, per file, explicit `-o`, 20 of them Customs editions.
   Budget for this; it is the reason the row was deferred.
5. Re-measure all three lanes. **Expect the register to rise before it falls** — these 57
   were invisible to the invariants, so making the boundary readable exposes them.

**Definition of done** — the four gap lines are in `BOUNDARIES`; the whole
`test_structural_boundary_agrees_with_grammar.py` is green; all 44 documents are at one
revision; the register is regenerated and the *net* movement is written down with the rise
and the fall reported separately.

**Do not** — do not port this to `packages/fbr_ingest/builder.py:1395-1397` in the same PR.
That fork is gated on [P4-2](plan.md#p4-2--decide-the-fbr_ingest-fork--a-routing-problem)
and measured at zero additional hits. Do not match numerals by value: `XIVA` and `XIV-A`
are two different chapters of Sales Tax Rules 2006.

**Result** — **CLOSED, round 18** (PR #84). Artifact:
`wip/phase3-round18-chapter-letter-suffix.md`. 80 swallowed boundary lines across
24 documents to 0; register unchanged at 25. Round 20 later closed the en-dash
gap on the same line.

**Closed by PR #83 (round 17).** Artifact:
`wip/phase3-round17-container-code-guard.md`. Kept here because half of what this row
gave as its justification turned out to be false, and because the *other* half reproduced
round 13's number exactly.

**Result** — the guard exists, the PART separator widening shipped behind it, and it
measures **14 gained / 0 lost** — round 13's number, four rounds later. The register is
**unchanged at 25** (15 / 5 / 5), which is what "0 hits, an enabler" predicted, so
`register.json` needed no regeneration. Five rules-lane documents re-converted.
Conservation is identical off vs on on all five, Customs Rules 2001's output
**byte-identical** but for its timestamp.

`is_structural_boundary` takes an optional `container_codes`; `_part_codes_in_scope`
resolves them per entry from the container tree, including **ancestors** — the caption a
missing cut swallows belongs to the part the *next* section opens, so rule 87's own
container `PART I` is not enough and the walk has to reach CHAPTER XI. Three callers
(`discover`, `preamble_refs`, `pipeline`) deliberately pass nothing and keep the
pre-round-17 answer; `discover` especially, because vouching a line with a container built
from that same line would be circular.

**What separated the two populations was never the spelling of the line.** Sales Tax Rules
2006 (01-01-2025) prints both — five real `PART-N` captions under CHAPTER XI, which holds
those parts, and form STR-11's two inside rule 165 under CHAPTER XVIII, which holds none.
One document, so neither an exemption nor a per-document rule could have told them apart,
and **a document-wide set of part codes would have vouched for the form.** Per-chapter was
load-bearing, not tidiness.

| document | candidates | cut | kept |
|---|---|---|---|
| Sales Tax Rules 2006 (01-01-2025) | 7 | **4** | 2 × STR-11, 1 × en dash |
| Sales Tax Rules 2006 (30-06-2025) | 5 | **4** | 1 × en dash |
| Customs Rules 2001 (30.06.2023) | 5 | **0** | rule 34's form, 0 parts in tree |
| STSP Rules 2007 × 2 editions | 3 + 3 | **6** | — |

> **Step 4 of this row was wrong, and so is `plan.md` P3-4's second bullet.** The guard
> would **not** have kept round 13 from dropping Customs Rules 2001's four chapter
> captions. Extending it to the CHAPTER branch moves conservation 74.087% → 74.099%, and
> **all 28 of those tokens are a duplication**: `preamble_refs` passes no codes, so the
> preamble's `CHAPTER I` line stops being a boundary, the preamble no longer ends there,
> and it swallows the caption *plus rule 1's opening text, which rule 1 still holds*. Not
> one leaf changed. The multiset audit only checks presence, so it scored the second copy
> as a recovery. Round 13's preamble leak, re-created and reported as a success.
>
> Even with the preamble side fixed it would be a bad trade: three of Customs Rules 2001's
> 44 chapters have no node, and putting their heading lines back into bodies raises
> `no_structural_heading_in_body` from **0** to buy 32 words on the one document already
> carrying four Phase-5 exemption entries. **Those captions are Phase 5, not this guard.**

Also rejected, measured: **widening the class to en/em dashes gains zero.** `PART – IV`
appears in both Sales Tax Rules 2006 editions and is why the count is 14 and not 16 — but
neither edition's CHAPTER XI holds a `PART IV` node, so the guard refuses both anyway.

**Locked by** `tools/tests/test_hyphenated_part_needs_a_container.py` — 3 cases, all
through `build_sections` on byte-identical body lines where only the container tree
differs. Each of the three ways to break it fails a different case, **including the
wiring**: hand `_build_one` a `frozenset()` and every unit test of the predicate alone
still passes while the gain is silently zero. That is why the test does not call the
predicate.

---

### 5. The round-10 rules residue — 3 hits, an exemption row — **CLOSED, round 19**

Sales Tax Rules 01-01-2025, each already traced to a **printed** defect: 44A opens with a
left double quote; 150ZQZI is printed `150ZQZl` (lowercase L for capital i); 150W's code
appears only in a footnote.

**Steps**
1. Re-confirm each against the source page — the traces exist but the pages are the
   authority.
2. Write three entries in `tools/suite/exemptions/rules.json` (10 entries today), each
   quoting the page and its printed text. Follow the shape of `:17-21`.
3. Give each an **expiry condition** where one exists. `150ZQZl` is an OCR-class defect and
   may expire on the OCR decision; the other two are permanent printing errors.

**Definition of done** — register total **−3** by exemption; `tools/tests/test_suite_exemptions.py`
green; each entry names the page it was traced to.

**Do not** — do not widen the parser to accept a left double quote as a code prefix, and do
not "fix" `150ZQZl` by collapsing `l`→`I`. Both make the parser wrong about correct
documents to be right about a broken one.

**Result** — **closed by PR #85 (round 19).** Register **25 → 22**, one exemption entry
covering all three hits (the format keys on `applies_to` + `invariant`, so three separate
entries for one pair is not a shape it has). `register.json` regenerated in the PR.

All three re-confirmed against the source pages, and **two of the three traces above were
wrong**:

| hit | this file said | the page says |
|---|---|---|
| 44A | opens with a left double quote | **correct** — p.66 prints `“44A. -Selection and conduct of audit.-(1)` |
| 150W | "code appears only in a footnote" | **wrong** — p.109 prints `228[50W. Audit.--`, the leading digit **dropped**, while its contents row on p.10 reads `150W. Audit` |
| 150ZQZI | printed `150ZQZl`, an **OCR-class** defect that "may expire on the OCR decision" | spelling **correct** (p.151), expiry **wrong** — `source_kind` is `native-digital`, so this document is never OCR'd and the defect **can never expire on that decision** |

The 150ZQZI trace also gained the argument that makes it un-fixable rather than merely
awkward: **p.152 carries a genuinely different rule, `150ZQZL. Right granted to the
licensee`**, so collapsing `l`→`I` would collide two real rules. (Its contents row on p.13
also prints the typo `liceensing`, which is where the leaf's heading comes from.)

Entered with **no expiry**, and the three hits are **enumerated in the reason on purpose**: a
fourth hit on this document would be a new defect the entry does not describe.

---

### 6. The heading-terminator scan — 3 hits, acts

`_find_heading_split` (`builder.py:2245`, called `:2911` from `_build_one` `:2827`) looks
four lines ahead for a terminator and stops at a grid table but **not** at a structural
heading, so an omitted section borrows the next section's terminator.

**Steps**
1. Read `wip/phase3-round13-chapter-hyphen.md` first. It contains the measurement that
   kills the obvious fix.
2. Reproduce: the heading comes out
   `*** Chapter-VII OFFENCES AND PENALTIES 33. Offences and penalties` across three Sales
   Tax editions — the whole 32AA cluster of `no_chapter_caption_in_section_heading`.
3. Design an **omission-aware fallback**: when the borrowed terminator is refused *and* the
   section is an omission, open the section on the omission itself.
4. Verify by leaf count, not just by the register: round 13's guard took a document 127
   leaves → **126**, losing section 32AA outright.

**Definition of done** — register **−3**; the 32AA cluster gone from
`no_chapter_caption_in_section_heading` (4 → 1); **leaf count unchanged or higher** on all
three editions; a test that fails without the fallback.

**Result** — **CLOSED, rounds 21-28** (PR #89). The parser shipped in round 20: an
omission-aware fallback, so when the borrowed terminator is a structural boundary / next
code / TABLE caption and the current line is an omission, the leaf opens on that line.
Locked by `tools/tests/test_omitted_heading_stops_at_boundary.py`. **Round 20 could not
measure it** — the three Sales Tax editions were not on that host. The round-27
re-conversion put them at one revision and the class went to **0**:
`no_chapter_caption_in_section_heading` is gone from the register entirely (was 4).

---

### 7. The omission spellings — 2 hits, acts

Customs 30.06.2024 s.196K prints `to Omitted 96u`; 30.06.2025 s.79 prints `A O mitted` —
an intra-word space round 3 measured and refused to admit into a regex whose job is
precision.

**Steps**
1. Re-measure the tolerance now the count is 2 and each can be traced individually — round
   3's refusal was correct *at 37 hits*, where a false positive was expensive.
2. If a bounded intra-word-space tolerance still measures false positives, this is an
   exemption row instead. Either outcome is a valid close.

**Definition of done** — register **−2**, by fix or by exemption-with-evidence; if by fix,
a gained/lost measurement showing 2 gained / 0 lost.

**Do not** — do not admit a general `\s*` between every character of `Omitted`. That is the
form round 3 measured and rejected.

**Result** — **CLOSED, rounds 21-28** (PR #89). The invariant widened in round 20:
`_is_omission` accepts only the whole-string forms `"to Omitted 96u"` and `"A O mitted"`,
with no general `\s*` between letters — the form round 3 measured and rejected. Round 20
could not measure it because neither Customs edition was staged. Both are now converted at
one revision and **neither is a hit**. Note this row's own instruction — "if a bounded
tolerance still measures false positives, this is an exemption row instead" — was never
needed: the whole-string form cost nothing.

---

### 8. `preamble_carries_no_toc_tail` — 2 hits, acts

Customs 30.06.2008 and Sales Tax 30.06.2023 each have a contents tail page carrying **2**
schedule rows against `detect_toc_pages`'s floor of **3**. 2008's source prints the typo
`THE SECOND SHCEUDLE`, which `grammar.SCHEDULE_TOC_RE` (`grammar.py:445`) rightly refuses.

**Steps**
1. Read `calibrate.py:288-297` — the comment recording why the floor exists.
2. Find **a signal other than row density**: a schedule-name run, the page's position
   relative to `first_body_page`, or the absence of body text. The floor stays at 3.
3. Verify the Income Tax Rules' body title page is still *not* swallowed — that is the
   regression the floor was put there to prevent.

**Definition of done** — register **−2**; the Income Tax Rules' `first_body_page` unchanged;
a test covering both the two tails and the title page that must not be swallowed.

**Do not** — **do not lower the floor**, and do not widen `SCHEDULE_TOC_RE` to match
`SHCEUDLE`. A typo tolerance in a schedule-heading regex is a false-positive generator
across 103 documents.

**Result** — **CLOSED, rounds 21-28** (PR #89). The extra signal shipped in round 20 — the
floor stayed at 3 and `SHCEUDLE` is still refused, both of which this row insisted on. Round
20 measured 0 on the *public* editions and left the register's 2 standing on the private
ones. Those are now converted, and the class is **0**: `preamble_carries_no_toc_tail` is
gone from the register.

---

### 9. The single-document remainder — 4 hits

Three unrelated traces, no shared cause: the Pakistan Single Window Act's ministry list read
as sections 27/28; PFMA 2019 s.26; Sales Tax 2014 s.10 printing `R(cid:2)fund` (a
font-encoding artifact).

**Steps** — one at a time, each: read the source page → classify parser vs printed →
fix-with-test or exempt-with-evidence. `R(cid:2)fund` is a `(cid:N)` glyph fallback and may
belong to a broader font-encoding class worth grepping the corpus for before fixing it
locally.

**Definition of done** — register **−4** across however many PRs it takes; each hit closed
individually with its own evidence. (This row said **7** until 2026-09-10; the live run
counts **4** — PSW ss.27/28, PFMA s.26, Sales Tax 2014 s.10.)

**Do not** — do not batch these into one "misc" fix. Three unrelated causes in one PR is
what makes a round unattributable.

**Result** — _(empty)_

---

### 10. `clause_codes_plausible` — 1 hit, Finance Act 2024

The jump `7->8517` is an HS tariff heading read from a **table row**; the check
(`_common.py:1874`) excludes schedules but not table-derived codes (ledger P06).

**Steps**
1. Two routes were suggested, neither measured: **(a)** bound the clause cursor by the
   measured gap; **(b)** reuse `_QUOTE_CUE` (`_common.py:463-468`, already used at `:570`,
   `:1414`, `ordinance.py:136`).
2. Measure both as gained/lost across all three lanes before choosing.

**Definition of done** — register **−1**; the check still fires on a genuine implausible
clause jump (prove it with a fixture that must stay red).

**Do not** — **do not weaken the check.** And do not reach for the parser's
`pagemodel.py:585` `_OPEN_QUOTE_CUE_RE` thinking it is the same thing as
`_common._QUOTE_CUE` — different regex, different owner, different side of the fence.

**Result** — **CLOSED, round 20** (PR #86), **measured rounds 21-28** (PR #89).
`_DOTFORM_RE` uses `\.(?!\d)` so a quoted `8517.1430` is not a clause start. Public Finance
Act 2024 reconverted: clauses **1–12**. The fixture that must stay red still stays red, and
the check was not weakened — which this row and `working-rules.md` both forbid. The
register's last hit cleared with the round-27 re-conversion; the class is **0**.

---

### 11. Decide the `fbr_ingest` fork — unblocks 5 hits and 9 documents

**A decision on evidence already committed, not a code task.** Both forks parse the same
three sections of an ICT Ordinance edition; the only difference is that `legal_ingest` has a
flat-act fallback that gives them a container. **So this is routing, not parsing.**

**Steps**
1. Read the evidence in `tools/discovery/signatures.json` (`records[].assignment`) and
   `README.md:283` (the standing v1 non-goal).
2. Decide: route by **family**, not by lane. Routing today is
   `apps/api/backend/services/corpus_registry.py:98`, asserted at `:170`.
3. Record the decision with its evidence — in this file's **Result**, and as the artifact
   for its PR.
4. Only then: the ordinance five in `section_carries_its_body`, and the 9 documents.
5. If routing changes, the fork's **two dormant copies** stop being dormant:
   `fbr_ingest/discover.py:221-244` (pre-round-1 `core.split()`) and
   `fbr_ingest/builder.py:1395-1397` (`CHAPTER\s+`, no hyphen). Both measured at **zero**
   additional hits across all 12 ordinance documents today.

**Definition of done** — the decision is written down with its evidence; if it routes by
family, the 9 documents convert and the ordinance five are closed or exempted.

**Do not** — **do not merge the fork.** That is the v1 non-goal (`README.md:283`) and it is
not what the evidence asks for. Do not port round 13's fixes into the fork "while you are
there" — that is a separate, measured, zero-value change today.

**Result** — **CLOSED as routing, round 20** (PR #86). Convert CLIs and
`corpus_registry` route by family; `--profile auto` is the default. Flat ICT
(empty `container_order`) uses `legal_ingest` + Acts profile; Income Tax
Ordinance stays on `fbr_ingest`. Forks not merged. Nine public ICT PDFs
convert to a synthetic root with three sections. The ordinance five still
need ITO editions on `fbr_ingest` — public ICT files are a different family.

---

### 12. The cross-edition index — a new instrument

No invariant can see a document that lost 93% of its sections: round 11's document gained
118 sections while the register moved 3. Invariants run per document — `runner.run` gets one
`doc` with no lane, no path, no siblings.

**Steps**
1. Build a per-group index over `output/*.json` — **tree counts**, not the PDF-regex counts
   `signatures.json` holds.
2. Join on `signatures.json`'s `group` (`packages/legal_ingest/signature.py:284` — the first
   component of the corpus-relative path, i.e. the containing folder; rationale `:125-127`,
   holding for 183/183 inventory rows). It matches `metadata.filename` on 80/80 acts
   documents.
3. Add the invariant on top of that index, not inside `runner.run`.

**Definition of done** — a check that would have caught round 11's document, demonstrated
by running it against `output/_pre_11/` if that snapshot survives, or a synthetic pair if
not. **A gate that cannot be made to fail on purpose is not a gate.**

**Do not** — do not compare against `signatures.json`'s counts directly. They are PDF-regex
measurements; comparing a tree count to a regex count produces noise on every document.

**Result** — **CLOSED, round 20** (PR #86). `tools/check_cross_edition_quality.py`
indexes tree counts, joins `signatures.json` groups, flags a >50% collapse vs
five or more siblings near the median. Wired into `tools/run_tests_smoke.py`.
Skips without corpus; unit tests lock the fail-on-purpose gate.

---

### 13. The instrument tree level — Phase 5, 4 limbs

A level above chapter, so a compilation parses as N instruments rather than one document
whose index rows become section leaves.

**Steps**
1. **The level itself.**
2. **The walkers.** `grammar.py:419` says "six tree walkers hardcode the child keys
   `("parts", "divisions", "sections")`, so a new `Node.kind` would be dropped
   **silently**". A grep at this commit finds **23 sites across 11 files** — 7 in
   `legal_ingest` (`builder.py:2481,2676`, `schedules.py:147,604,631,817`,
   `pipeline.py:985`), 7 in the `fbr_ingest` fork (`pipeline.py:303`,
   `builder.py:1623,1818`, `schedules.py:118,367,394,580`), 4 in the suite
   (`loader.py:38`, `_common.py:1035,2509,2512`), 4 in the audit tools
   (`tools/acts/audit_completeness.py:258,262`,
   `tools/ordinance/audit_completeness.py:119,123`), 1 in the API
   (`apps/api/backend/services/overlays.py:32`). **Silent drop is the failure mode — this
   limb is where the risk is.**
3. **The portal renderer.**
4. **Re-convert the compilations.**
5. **Delete the 4 exemption entries** at `tools/suite/exemptions/rules.json:47-66`.

**Definition of done** — **the 4 entries are deleted and all three lane suites stay green.**
Not "the level exists". If deleting them turns the suite red, the level did not work. The
suite reports them stale on its own once it does.

**Do not** — do not add a `Node.kind` before auditing all 23 walker sites. A dropped node is
silent, and a silent drop in limb 1 will be diagnosed as a limb 3 rendering bug.

**Result** — **CLOSED, round 20** (PR #86). Optional `instruments[]`, `type=instrument`,
`inst:` keys in `legal_contract`; walkers updated; Alembic `0006_section_instrument_context.py`;
portal breadcrumbs/sidebar/upload. Compilation exemptions for Customs Rules 2001
and Federal Excise Rules 2005 **deleted**. Public FE 2015: two instruments,
suite 60/60. Public Customs Rules 2001: body discovery, compilation case PASS.
Remaining rules exemptions are jammed-tokens, split-ordinals, and the round-19
STR printing errors.

---

### 14. `--profile auto` as the default — SHIPPED, round 20

**Shipped in PR #86** on `tools/convert.py` and `tools/convert_all.py`, both
`--profile {lane,auto}` defaulting to `auto`. A family override refines the
lane's profile. `lane` preserves the historical route.

This was gated on Phase 3 reaching zero-or-exempted so a full reparse could be
attributed, and that full reparse has still **not** been run. What rounds 21-28 did run is
narrower and worth not confusing with it: **77 documents** (the acts and rules lanes) at one
revision, which is what took the register to 13. The 14 skipped acts documents and the whole
12-document ordinance lane are untouched. Do not `make convert-all` — it converts the whole
*lane*, not the corpus. Explicit `--profile lane` is still the escape hatch.

**Result** — default is `auto`. Full-corpus attribution remains blocked until the ordinance
lane and the 14 skipped acts documents are converted at the same revision as the other 77.

---

### 15. The OCR decision — BLOCKED, needs a human

**Not work. A decision.** `data/ocr_cache` is 0 B and stays 0 B until someone decides
otherwise. The shape of the decision, the cheap tail, and the consequence chain are in
[`plan.md` Phase 2](plan.md#phase-2--the-ocr-half-a-decision-not-work).

Read the consequence chain before recommending the "cheap" 15-minute tail: it ends with
documents **disappearing from the portal**.

**Result** — _(empty)_

---

## Deferred, with reasons

Real, but not open. Each carries the reason it is not being done, rather than a note that
it isn't.

| row | why it is not open |
|---|---|
| **delete `_legacy_section_key` + the `source_key` bridge** | Blocked on the 14 stale acts documents (→ the OCR decision): 6 documents / 89 leaves still rely on it. Definition at `apps/api/backend/services/document_store.py:61`, the only call site `:257`, reached only after `by_node_key` **and** `by_source_key` both miss (the 3-tier ladder is `:245-258`). **The ledger says "confirm with a query, not a guess" in five places and that query does not exist** — `wip/integration/measure/census.py` counts the JSON corpus, not the database; the only `node_key IS NULL` in the repo is a partial index (`alembic/versions/0004_section_node_key.py:43`). **Writing the query is step 1.** |
| **the `ReviewToolbar` approval gate** | **A product decision, then one line.** `apps/web/src/components/review/ReviewToolbar.jsx:46-47` calls `hasAnyQualityFlags` (`utils/qualityFlags.js:82`) while `qualityFlags.js:17` claims to mirror the *narrower* backend `CRITICAL_FLAGS` (`apps/api/backend/services/parse_quality.py:14-21`: `missing_table`, `footnote_glue`, `wall_of_text`, `heading_body_bleed`). `hasCriticalQualityFlags` (`qualityFlags.js:87-88`) exists and is **tested** (`test/qualityFlags.test.js:40`) but unused by the toolbar — so the helper is verified and the gate is not. Cheapest row on the board once someone decides which behaviour is wanted. |
| **delete the Zustand mirror in `documentStore`** | Architecture, not a defect — the bug it caused is fixed and tested. **Bigger than the record says:** `open-work.md:183` calls it "five pages"; it is **8 consumer modules** — `ReviewPage.jsx:20,62`, `DashboardPage.jsx:15,71`, `Sidebar.jsx:5,44`, `ReviewToolbar.jsx:4,31`, `PdfPanel.jsx:6,107`, `AiFixPanel.jsx:14,227`, `CommandPalette.jsx:9,32-33`, and `stores/reviewStore.js:3,57,109,124-128,150`. **And there is no data-hooks layer to move onto:** `apps/web/src/hooks/` holds only `useKeyboardNav`/`usePdfRenderer`/`useTextSelection`, and app code contains **zero** `useQuery`/`useMutation` calls — everything routes through `documentStore`'s `fetchQuery` wrapper (`documentStore.js:8-12`). It must be written first. |
| **an explicit `order` field** | Needs the **source pages**: tree-walk and page-sort order disagree on **21 of 103** documents and the JSON cannot settle which is right. P5's reading-order limb — measured and deferred, not open. |
| **delete `normalize_heading`** | A **parser** task hiding in the integration ledger. A parser round must first stop emitting a leading `]` and the truncated `[...`. Then it is one deletion. Note it lives API-side: `apps/api/backend/services/json_parser.py:82`. |
| **`convert_all.py` cannot resume** (`wip/tasks.md:536`) | Known, with a workaround that works: convert only outputs older than the parser's mtime. Worth fixing when a round needs a full-lane re-conversion; no round does today. |
| **re-examine the 29 low-confidence documents** (`wip/tasks.md:671`) | `tools/discovery/report.md` §5 was wrong from PR #45 to #51 because it had not been regenerated since Phase 0. The generator is fixed; the list has not been re-read since. Cheap, and may dissolve on its own. |
| **rebuild api/worker images** (`wip/tasks.md:79`) | Explicitly "not attempted, and not needed this round". A deploy concern, and the deploy is gated on green CI on `main` and is outward-facing — confirm before triggering. |
| **the `fbr_ingest` dormant copies** | Measured at **zero** additional hits across all 12 ordinance documents, so leaving them was correct. Gated on [task 11](#11-decide-the-fbr_ingest-fork--unblocks-5-hits-and-9-documents); they become live the moment routing changes. |

---

## Where this stands

Nothing in `wip/` is edited to keep this file current — each round only *adds* its own
write-up there. `wip/` is the historical record and shipping code cites it. Note that
**every file under `wip/integration/` states the register as 34** and `wip/HANDOVER.md`
states it as **64**; it is **13**. `wip/tasks.md:664` states `section_codes_ordered` as
**4**; the class is **closed**. When those disagree with this folder, this folder is
right — and `tools/suite/register.json` is right about the register over everything,
including this file.
