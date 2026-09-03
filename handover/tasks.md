# The execution ledger

**This file is updated as work happens, never after.** If a box is ticked, the thing is
merged on `main`.

**State:** the register is **32**. **21 of 66** checklist items are open, plus 3 optional
leftovers from the finished integration track. There is no next PR in sequence — pick a
row from the table below. Reasoning for every row is in [`plan.md`](plan.md); state is in
[`README.md`](README.md); the traps are in [`working-rules.md`](working-rules.md).

Written 2026-09-03 on `main` at `d0d591d`. **Next round is 15; next PR is #80.**

---

## Start here — pick one

Ranked by value against cost, each with the ONE thing that actually blocks it. An agent
with no other context can take row 1 and start.

| # | pick this up | hits | the single blocker | plan.md |
|---|---|---|---|---|
| 1 | **trace `section_codes_ordered`** — read 3 source PDF pages | 3 | nothing. Untraced only because nobody read the pages. **Cheapest row on the board.** | [P3-6](plan.md#p3-6--section_codes_ordered-3--untraced) |
| 2 | **the CHAPTER letter suffix** | **57** ¹ | doubles re-conversion to 44 documents, 20 of them the Customs chapter tree. Nothing else. Highest-value row. | [P3-5](plan.md#p3-5--the-chapter-letter-suffix--57-hits-24-documents-all-real) |
| 3 | **the container-code guard** | 0 ² | `build_sections` must pass per-chapter container codes into `_build_one` — a signature change. | [P3-4](plan.md#p3-4--the-container-code-guard) |
| 4 | **the STSP 58U/58V pair** | 4 | nothing. One cause, two editions — the best remaining hits-per-round ratio. | [P3-1b](plan.md#p3-1--section_carries_its_body-21--four-unrelated-causes-not-one) |
| 5 | **the round-10 rules residue** | 3 | a judgement call, not code: all three are *printed* defects, so this is an **exemption-with-evidence** row. | [P3-1c](plan.md#p3-1--section_carries_its_body-21--four-unrelated-causes-not-one) |
| 6 | **the heading-terminator scan** | 3 | needs an **omission-aware fallback**; the obvious guard was measured losing section 32AA outright. | [P3-2](plan.md#p3-2--the-heading-terminator-scan-that-walks-through-a-boundary-3-acts) |
| 7 | **the omission spellings** | 2 | `A O mitted` needs an intra-word-space tolerance a precision regex refused in round 3. Re-measure now the count is traceable. | [P3-1a](plan.md#p3-1--section_carries_its_body-21--four-unrelated-causes-not-one) |
| 8 | **`preamble_carries_no_toc_tail`** | 2 | needs **a signal other than row density** — the `rows >= 3` floor is load-bearing and may not be lowered. | [P3-3](plan.md#p3-3--preamble_carries_no_toc_tail-2-acts) |
| 9 | **the single-document remainder** | 7 | nothing shared — PSW ministry list, PFMA s.26, `R(cid:2)fund`. Three unrelated traces. | [P3-1e](plan.md#p3-1--section_carries_its_body-21--four-unrelated-causes-not-one) |
| 10 | **`clause_codes_plausible`** | 1 | **do not weaken the check.** Two routes suggested, neither measured. | [P3-7](plan.md#p3-7--clause_codes_plausible-1-finance-act-2024) |
| 11 | **decide the `fbr_ingest` fork** | 5 ³ | **a decision, on evidence already committed.** Route by family, not by lane. Merging stays the v1 non-goal. | [P4-2](plan.md#p4-2--decide-the-fbr_ingest-fork--a-routing-problem) |
| 12 | **the cross-edition index** | 0 ⁴ | needs a new per-group index over `output/*.json`; `signatures.json`'s counts are PDF-regex, not tree counts. | [P3-8](plan.md#p3-8--no-invariant-can-see-a-document-that-lost-93-of-its-sections) |
| 13 | **the instrument tree level** (4 limbs) | 0 ⁵ | limb 2 is **23 walker sites across 11 files** and a new `Node.kind` is dropped *silently*. | [Phase 5](plan.md#phase-5--the-instrument-tree-level-4-limbs-not-started) |
| 14 | flip `--profile auto` to default | — | **BLOCKED: Phase 3 must reach zero-or-exempted first.** Flipping it re-parses everything and destroys attribution. | [P4-1](plan.md#p4-1--flip---profile-auto-to-the-default) |
| 15 | the OCR decision | — | **BLOCKED: needs a human decision.** Not work. See the consequence chain before deciding. | [Phase 2](plan.md#phase-2--the-ocr-half-a-decision-not-work) |
| 16 | delete `_legacy_section_key` | — | **BLOCKED on row 15** — 6 documents / 89 leaves still rely on it. And the query that would confirm this **does not exist yet**; writing it is step 1. | [Deferred](#deferred-with-reasons) |
| 17 | the `ReviewToolbar` approval gate | — | **a product decision, then one line.** Cheapest row here once someone decides. | [Deferred](#deferred-with-reasons) |
| 18 | delete the Zustand mirror | — | 8 consumer modules, and **no data-hooks layer exists to move onto** — it must be written. Architecture, not a defect. | [Deferred](#deferred-with-reasons) |

¹ Not in the register's 32 — the invariants cannot currently see them. Closing this row
*adds* hits before it removes them; see the task below.
² An enabler: it unblocks the PART separator widening and prevents round 13's
chapter-caption losses.
³ Unblocks the ordinance five in `section_carries_its_body`, and 9 documents.
⁴ A new instrument, not a fix. Round 11 lost 93% of a document's sections and the register
moved 3.
⁵ Measured by the *deletion* of 4 exemption entries, not by hits.

**Before touching any of them, read [Rules of engagement](#rules-of-engagement).** Every
rule there was paid for, and three of them have drawn blood twice.

### How this reconciles to "21 of 66"

The 21 unchecked boxes in `wip/tasks.md` map onto the rows above exactly. Verified by
`grep -c '^\s*- \[ \]' wip/tasks.md` → 21, and `- [x]` → 45.

| `wip/tasks.md` line | row above |
|---|---|
| `:664` `section_codes_ordered` | 1 — note it says **4** hits; the register says **3**. `wip/` is stale, the register is truth |
| `:418` CHAPTER letter suffix | 2 |
| `:401` container-code guard | 3 |
| `:436` `section_carries_its_body` — the remaining 21 | 4, 5, 7, 9 (one box, four causes) |
| `:388` heading-terminator scan | 6 |
| `:379` `preamble_carries_no_toc_tail` | 8 |
| `:668` `clause_codes_plausible` | 10 |
| `:712` decide `fbr_ingest` · `:430` its dormant copies | 11 (two boxes) |
| `:503` no invariant sees a 93% loss | 12 |
| `:741` `:742` `:743` `:744` the four Phase 5 limbs | 13 (four boxes) |
| `:701` `--profile auto` default | 14 |
| `:184` OCR · `:190` the 9 provisional · `:192` the ordinance 10 | 15 (three boxes) |
| `:536` `convert_all.py` cannot resume · `:671` the 29 low-confidence documents · `:79` rebuild api/worker images | [Deferred](#deferred-with-reasons) (three boxes) |

Rows 16–18 are **not** among the 21 — they come from `wip/integration/tasks.md`'s own
ledger. So: **21 checklist items + 3 integration leftovers = 24 open things**, which is
the honest total.

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
- **Two source files have no `.pdf` extension** — Customs Rules 2001 and The Finance
  (Supplementary) Act 2022 — so a `**/*.pdf` glob misses them **silently**. Any
  re-conversion loop must handle them.
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

## How a round runs — worked for round 15

Copy this. Do not invent a variation.

```sh
# 1. Branch. Use a worktree -- the tree is shared with peer sessions.
git worktree add .worktrees/r15 -b fix/phase3-round15-<slug> main
cd .worktrees/r15

# 2. Baseline, before touching anything. The corpus lives in the MAIN tree
#    (data/corpora is gitignored, so a worktree has no copy) -- run suites from there.
cd /Users/muhammad.husnain/Downloads/code/crx
for L in acts rules ordinance; do .venv/bin/python tools/run_suite.py $L > /tmp/pre-$L.txt; done

# 3. Snapshot the outputs you are about to overwrite.
cp -r data/corpora/acts/output data/corpora/acts/output/_pre_15   # per lane you touch

# 4. Write the failing test FIRST, then the fix. Confirm the test fails without it.
.venv/bin/python -m pytest tools/tests/<the new test> -q      # must be RED

# 5. Re-convert ONLY the affected documents, per file, explicit -o. Never convert-all.
make convert-acts PDF="data/corpora/acts/<...>" OUT="data/corpora/acts/output/<...>.json"
#    Do not edit packages/ while this runs. Mind the two files with no .pdf extension.

# 6. Re-measure ALL THREE lanes -- a fix in one lane can move another.
for L in acts rules ordinance; do .venv/bin/python tools/run_suite.py $L; done

# 7. Regenerate the register IN THIS PR. No Make target, no pytest flag.
.venv/bin/python tools/tests/test_register_snapshot.py --write

# 8. Full gate.
.venv/bin/python -m pytest tools/tests -q     # baseline: 86 passed, 1 skipped
.venv/bin/ruff check                          # BARE
du -sh data/ocr_cache                         # must still be 0B
cd apps/web && npm run test                   # only if you touched the portal; 17-failed baseline
```

Then: write the round artifact as `wip/phase3-round15-<slug>.md`
— **a new file; do not edit existing `wip/` files** — following the shape of
`wip/phase3-round14-preamble-front-matter.md`: what was measured, what moved, what moved
by **zero**, and what was rejected and why. Open **PR #80** with the before/after
artifact linked in the body.

**If the register improved, `test_register_snapshot.py` fails until step 7 is done.** That
is the design, not a bug.

---

## The tasks

Each carries: what it closes · **Steps** · **Definition of done** · **Do not** ·
**Result** (empty until it lands).

### 1. Trace `section_codes_ordered` — 3 hits, acts

Three hits, nobody has read the source pages. Invariant is acts-only:
`tools/suite/invariants/acts.py:121`.

**Steps**
1. Get the three failures with their documents:
   `.venv/bin/python tools/run_suite.py acts | grep -A3 section_codes_ordered`
2. The three are Customs 2025 `'9' after '119'`; Sales Tax 2014 `'3' after '32AA'` and
   `'22' after '75'`. Find the printed page for each code in the source PDF.
3. Decide per hit, and only from the page: **parser defect** (the code was misread) or
   **printed defect** (the source really prints them out of order).
4. Parser defect → fix + failing test. Printed defect → an entry in
   `tools/suite/exemptions/acts.json` quoting the page. **Note that file does not exist
   yet** — only `rules.json` does (`tools/suite/runner.py:30-32`: a missing file means no
   exemptions, which is not an error).

**Definition of done** — register total **32 → 29**; `run_suite.py acts` → 15 hits; each
of the three either fixed or carrying an exemption entry with a page citation.

**Do not** — do not infer the answer from the JSON. `'3' after '32AA'` is exactly the shape
a cursor cascade produces *and* the shape a genuine printing error produces; only the page
distinguishes them.

**Result** — _(empty)_

---

### 2. The CHAPTER letter suffix — 57 hits, 24 documents

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

**Result** — _(empty)_

---

### 3. The container-code guard — 0 hits, an enabler

A `PART-N` line should be a boundary **only where the enclosing chapter actually holds a
part with that code.**

**Steps**
1. `build_sections` (`packages/legal_ingest/builder.py:1682`) must pass per-chapter
   container codes into `_build_one` (`:2827`). That signature change is the task.
2. Add the guard at the PART branch of the boundary test.
3. Re-measure the PART separator widening with the guard in place: it previously scored
   14 real boundaries against 6 annexure FORM losses, the losses being an item counter
   running 8–11 *across* the parts.
4. Confirm against Customs Rules 2001 — round 13 dropped four chapter captions there
   (conservation 74.101% → 74.087%) because its tree holds 41 of ~44 chapters and cannot
   express them.

**Definition of done** — the guard exists; the PART widening measures 14 gained / **0**
lost; Customs Rules 2001's conservation does not fall; a test asserts a `PART-N` line is
*not* a boundary in a chapter that lacks that code, and fails without the guard.

**Do not** — do not ship the widening without the guard. That pairing is the whole point of
the row.

**Result** — _(empty)_

---

### 4. The STSP 58U/58V pair — 4 hits, rules

The same two rules in both Sales Tax Special Procedures Rules 2007 editions — **one cause,
two editions.** Best remaining hits-per-round ratio.

**Steps**
1. `.venv/bin/python tools/run_suite.py rules` → find the 58U/58V failures and their two
   documents.
2. Read 58U and 58V on the source pages of **both** editions. One cause across two
   editions means the fix is at the parser, not per document.
3. Fix + a test that fails without it. Re-convert both editions per file.

**Definition of done** — register total **−4**; `run_suite.py rules` → 5 hits; both
editions re-converted at one revision.

**Do not** — do not fix one edition and assume the other follows. Confirm both, because
"same shape, two editions" is exactly what round 9's cursor cascade looked like before it
turned out to be one cause.

**Result** — _(empty)_

---

### 5. The round-10 rules residue — 3 hits, an exemption row

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

**Result** — _(empty)_

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

**Do not** — **do not add a guard that stops the scan at a structural heading.** Measured,
round 13: an omitted section has no terminator of its own, so refusing the borrowed one
leaves nothing to open it with, and the section vanishes.

**Result** — _(empty)_

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

**Result** — _(empty)_

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

**Result** — _(empty)_

---

### 9. The single-document remainder — 7 hits

Three unrelated traces, no shared cause: the Pakistan Single Window Act's ministry list read
as sections 27/28; PFMA 2019 s.26; Sales Tax 2014 s.10 printing `R(cid:2)fund` (a
font-encoding artifact).

**Steps** — one at a time, each: read the source page → classify parser vs printed →
fix-with-test or exempt-with-evidence. `R(cid:2)fund` is a `(cid:N)` glyph fallback and may
belong to a broader font-encoding class worth grepping the corpus for before fixing it
locally.

**Definition of done** — register **−7** across however many PRs it takes; each hit closed
individually with its own evidence.

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

**Result** — _(empty)_

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

**Result** — _(empty)_

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

**Result** — _(empty)_

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

**Result** — _(empty)_

---

### 14. `--profile auto` as the default — BLOCKED

**Blocked: Phase 3 must reach zero-or-exempted first.** Flipping it re-parses everything,
and doing that while the register is non-zero destroys the ability to attribute any change.

When unblocked: `tools/convert.py:51` and `tools/convert_all.py:433`, both
`--profile {lane,auto}` defaulting to `lane`. A family override must **refine** the lane's
profile, not replace it. `convert_all.py:486` refuses `auto` on ordinance — that refusal
interacts with [task 11](#11-decide-the-fbr_ingest-fork--unblocks-5-hits-and-9-documents)
and must be revisited with it.

**Result** — _(empty)_

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

Nothing in `wip/` was changed to write this file. `wip/` is the historical record and
shipping code cites it. Note that **every file under `wip/integration/` states the register
as 34** and `wip/HANDOVER.md` states it as **64**; it is **32**. `wip/tasks.md:664` states
`section_codes_ordered` as **4**; it is **3**. When those disagree with this folder, this
folder is right — and `tools/suite/register.json` is right about the register over
everything, including this file.
