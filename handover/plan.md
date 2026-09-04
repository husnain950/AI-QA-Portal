# What is left: the architecture, and the phases that close it

**Status:** the plan for the work that remains. `tasks.md` beside it is the execution
ledger and is the file to trust for *what is done*; this file is the reasoning a task row
links back to. **It is not a historical record** — when a measurement disproves something
here, this file changes. (The frozen record is `wip/`, per [README §5](README.md#5-where-the-history-is).)

Written **2026-09-04**, on `main` after PR #81 (round 15). Every number below was measured
on this machine at that commit; §7 gives the command for each. Nothing is carried forward
from `wip/`, which is wrong on nearly every number it states.

State: [`README.md`](README.md) · Ranked work: [`open-work.md`](open-work.md) ·
Method: [`working-rules.md`](working-rules.md)

---

## 1. Context

`crx` is two systems joined by a directory glob. A pipeline (`packages/legal_ingest`,
`packages/fbr_ingest`, `tools/`) converts FBR statutory PDFs into JSON under
`data/corpora/<lane>/output/*.json`; a QA portal (`apps/api` FastAPI + Postgres,
`apps/web` React) flattens that JSON into rows reviewers annotate and approve.

Two tracks have finished. The **integration seam** closed as PRs #59–#76 — every problem
in `wip/integration/plan.md` §3, and the corpus-wide identity hole went from 5,047 leaves
(30%) to 89 (0.5%). The **anomaly register** went 210 → 29 over fifteen rounds, and is
now committed and gated (`tools/suite/register.json`).

What remains is the residue of both, and it is **harder per hit than what came before.**
Rounds 1–7 each found *one cause explaining many hits*: the cursor cascade, the header
band, the chapter numerals. What is left is mostly 1–2 hits per document with unrelated
causes. There are exactly two remaining one-cause-many-hits items — [§4 P3-4](#p3-4--the-container-code-guard)
and [§4 P3-5](#p3-5--the-chapter-letter-suffix--57-hits-24-documents-all-real) — and that
is the reason they rank where they do in `tasks.md`. **Expect a lower hits-per-round rate
from here.** A round that closes two hits is not a bad round now.

---

## 2. The register

Transcribed from `tools/suite/register.json` (`total` at `:16`, `lanes` at `:18-31`), and
re-measured live at this commit. Shape:
`{_comment: [str], total: int, lanes: {lane: {invariant: count}}}` — an integer count per
lane per invariant, no document attribution.

| invariant | acts | rules | ordinance | total | implementation |
|---|---|---|---|---|---|
| `section_carries_its_body` | 8 | 8 | 5 | **21** | `tools/suite/invariants/_common.py:1267` |
| `no_chapter_caption_in_section_heading` | 4 | — | — | **4** | `_common.py:2151` |
| `preamble_carries_no_toc_tail` | 2 | — | — | **2** | `_common.py:1086` |
| `no_foreign_section_start_in_body` | — | 1 | — | **1** | `_common.py:1371` |
| `clause_codes_plausible` | 1 | — | — | **1** | `_common.py:1874` |
| **per lane** | **15** | **9** | **5** | **29** | |

These five are shared in `_common.py`, bound by name via `all_invariants`
(`_common.py:2558-2570`), where a lane module's `inv_<name>` overrides `_common`'s.

**Six invariant classes are closed:** `body_chapters_in_tree`, `no_footnote_text_in_body`,
`structure_counts`, `no_code_fragment_in_section_heading` (round 12, was 31),
`no_structural_heading_in_body` (round 13, was 175), and **`section_codes_ordered`
(round 15, was 3)**. Note that last one still has **no shared implementation** — it is
three independent per-lane functions, `invariants/acts.py:121`, `rules.py:167` and
`ordinance.py:213` (the last importing `fbr_ingest.discover.code_sort_key` at `:223`) — so
a future regression can appear in one lane and not the others.

**The governing rule: fixed, or exempted with evidence traced to the source PDF. There is
no third state.** "Tracked and deferred" without an entry in
`tools/suite/exemptions/<lane>.json` is a red gate, not a decision.

---

## 3. What the register is a measurement *of*

**Read the last column before the first.** 103 documents converted, against the
source-file counts on the right.

| lane | hits | editions affected | converted | of source files |
|---|---|---|---|---|
| acts | 15 | 11 | 80 | 93 |
| rules | 9 | 4 | 11 | **48** |
| ordinance | 5 | 4 | 12 | 46 |

The rules lane converts **11 of 48** — the other 36 are scans and one is Urdu, and every
scan was skipped by instruction. It is also still a **mixed-revision** corpus: each round
re-converts only the documents its fix touches, so 61 scanned documents keep whatever
revision last wrote them. That is a property of the measurement, not a defect to fix.

---

## 4. The problems

Each carries the evidence, the measurement already taken, and — for the three that have
one — **the approach already known to be wrong.** Read that part before proposing a fix;
it is there because someone already spent a round on it.

### Phase 3 — the register's 29

#### P3-1 — `section_carries_its_body` (21) — four unrelated causes, not one

The largest class, and no longer a single defect. Invariant: `_common.py:1267`. Split so
the causes can be worked separately:

| cause | hits | lane | state |
|---|---|---|---|
| **a.** Omission spellings the invariant cannot read | 2 | acts | open |
| **b.** The STSP 58U/58V pair | 4 | rules | open, one cause / two editions |
| **c.** The round-10 residue — printed defects | 3 | rules | traced, each individually |
| **d.** The ordinance five | 5 | ordinance | **blocked on [P4-2](#p4-2--decide-the-fbr_ingest-fork--a-routing-problem)** |
| **e.** Single-document remainder | 7 | acts/rules | open |

**a.** Customs 30.06.2024 s.196K prints `to Omitted 96u`; 30.06.2025 s.79 prints
`A O mitted` — an intra-word space that round 3 measured and refused to admit into a regex
whose job is precision. Worth re-measuring now the count is small enough to trace
individually.

**c.** Sales Tax Rules 01-01-2025, each already traced to a printed defect: 44A opens with
a left double quote, 150ZQZI is printed `150ZQZl` (lowercase L for capital i), and 150W's
code appears only in a footnote. These are candidates for **exemption with evidence**, not
for parser work — the source is wrong, not the parser.

**e.** The Pakistan Single Window Act's ministry list read as sections 27/28, PFMA 2019
s.26, and Sales Tax 2014 s.10 (`R(cid:2)fund` — a font-encoding artifact).

#### P3-2 — the heading-terminator scan that walks through a boundary (3, acts)

`_find_heading_split` (`packages/legal_ingest/builder.py:2245`, called at `:2911` from
`_build_one` `:2827`) looks up to four lines ahead for a heading terminator and stops at a
grid table but **not** at a structural heading. So an omitted section borrows the *next*
section's terminator and its heading comes out
`*** Chapter-VII OFFENCES AND PENALTIES 33. Offences and penalties`. This is the whole
32AA cluster of `no_chapter_caption_in_section_heading` (`_common.py:2151`), across three
Sales Tax editions.

> **Do not add the obvious guard.** Round 13 measured it as **losing section 32AA
> outright** (127 leaves → 126): an omitted section has no terminator of its own, so
> refusing the borrowed one leaves nothing to open it with. This needs an **omission-aware
> fallback**, not a guard. Trace: `wip/phase3-round13-chapter-hyphen.md`.

#### P3-3 — `preamble_carries_no_toc_tail` (2, acts)

Invariant: `_common.py:1086`. Round 14 closed eight of the ten documents that had this.
The two survivors are the same shape and are only now *visible*: Customs 30.06.2008 and
Sales Tax 30.06.2023 each have a contents tail page carrying **2** schedule rows against
`detect_toc_pages`'s floor of **3**. 2008's source prints the typo `THE SECOND SHCEUDLE`,
which `grammar.SCHEDULE_TOC_RE` (`packages/legal_ingest/grammar.py:445`) rightly refuses.

Anchors: `detect_toc_pages` at `packages/legal_ingest/calibrate.py:253`; the dense-page
rule at `:279`; the floor loop at `:298-300`, reading
`profile.toc_tail_density_floor` (`profiles.py:89`; RULES `0.20` at `:128`, ACTS `None` at
`:161`).

> **Do not lower the floor.** `calibrate.py:288-297` records, in its own comment, a lower
> one swallowing the Income Tax Rules' body title page — 3 of 38 lines matched, and
> `first_body_page = toc_pages + 1` started the body a page late. **A fix needs a signal
> other than row density.**

#### P3-4 — the container-code guard

A `PART-N` line should be a boundary **only where the enclosing chapter actually holds a
part with that code.** Zero hits of its own; it is an *enabler*, and two independent
measurements now argue for it:

- it is what makes the PART separator widening safe — 14 real boundaries against 6
  annexure FORM losses, where the losses are an item counter running 8–11 *across* the
  parts (the measurement is in the comment at `builder.py:2085-2103`);
- it is what would have kept round 13 from dropping four chapter captions in Customs Rules
  2001 (conservation 74.101% → 74.087%), whose tree holds 41 of ~44 chapters and cannot
  express them.

Needs `build_sections` (`builder.py:1682`) to pass per-chapter container codes into
`_build_one` (`builder.py:2827`). That signature change is the whole task; the guard
itself is small.

#### P3-5 — the CHAPTER letter suffix — 57 hits, 24 documents, all real

`_STRUCTURAL_RE` (`packages/legal_ingest/builder.py:2104-2106`): the **CHAPTER branch is
`CHAPTER[\s\-]+[IVXLC0-9]+` with no letter-suffix class, where PART and Division beside it
both carry `[A-Z]{0,2}`.** So `CHAPTER XVI-A` sits in section 155's body across twenty
Customs editions.

Measured at **57 further hits across 24 documents, zero false**. Held out of round 13
because it doubles re-conversion from 21 to 44 documents, twenty of them the Customs
chapter tree that rounds 1 and 6 rebuilt. These 57 are **not in the register's 29** — the
register counts what the invariants currently see.

> **A test asserts the current *wrong* answer on purpose.**
> `tools/tests/test_structural_boundary_agrees_with_grammar.py:90-96`
> (`test_the_letter_suffixed_chapter_gap_is_still_open`), over
> `KNOWN_GAP_SUFFIXED_CHAPTERS` at `:63-65` — `["CHAPTER XVI-A", "1[CHAPTER XIX-A",
> "248[CHAPTER XIVA", "[CHAPTER - VIAB"]`. **Do not repair it. Its failure is the signal
> the widening landed** — the assertion message itself tells you to move the lines into
> `BOUNDARIES` (`:35-39`) and re-measure.

Note `XIVA` and `XIV-A` are two *different* chapters of Sales Tax Rules 2006. Matching
numerals by value collapses them.

#### P3-6 — `section_codes_ordered` — **CLOSED, round 15**

Was 3: Customs 2025 `'9' after '119'`; Sales Tax 2014 `'3' after '32AA'` and
`'22' after '75'`. Now **0**.

> **This entry said "the code was misread". That was wrong, and the pages disprove it.**
> Not one section code was misread. All three hits were a **chapter** wearing the wrong
> numeral, and the invariant could only see the consequence — sections walking backwards
> because their container sorts somewhere else. Both fixes are therefore in the *chapter*
> path, not the code path:
>
> 1. `toc.py`'s CHAPTER branch did not reset `pending_page`, so a contents row that
>    printed **no folio** stayed open across a chapter boundary and the next chapter's
>    caption opened a second, numeral-less node — `CHAPTER III` emitted **twice**.
> 2. `pipeline.py`'s `insert_missing_body_chapters` paired leftover numeral-less nodes
>    with leftover body numerals by **list position** (`zip(empties, unused)`), which is
>    correct only where the two lists correspond one-to-one. Now paired by which body span
>    actually prints the node's own sections.
>
> Full trace: `wip/phase3-round15-chapter-numeral-pairing.md`.

**The lesson that generalises to the rows still open:** this class was ranked "cheapest,
3 pages to read", and the reading is what disproved its own premise. Two of the remaining
rows carry a *predicted* cause in the same voice — [P3-1c](#p3-1--section_carries_its_body-21--four-unrelated-causes-not-one)
("each already traced to a printed defect") and [P3-1a](#p3-1--section_carries_its_body-21--four-unrelated-causes-not-one).
Neither prediction has been checked against a page since it was written.

#### P3-7 — `clause_codes_plausible` (1, Finance Act 2024)

Invariant: `_common.py:1874`. The jump `7->8517` is an HS tariff heading read from a
**table row**; the check excludes schedules but not table-derived codes (ledger P06).

> **Do not weaken it to clear its one hit.**

Two routes were suggested: bound the clause cursor by the measured gap, or reuse
`_QUOTE_CUE` (`_common.py:463-468`, already used at `:570`, `:1414` and
`invariants/ordinance.py:136`). Note the parser has a *separate* quote cue —
`pagemodel.py:585` `_OPEN_QUOTE_CUE_RE` — different regex, different owner. Do not
conflate them.

#### P3-8 — no invariant can see a document that lost 93% of its sections

Round 11's document gained 118 sections while the register moved 3. What would catch that
is a **cross-edition** fact, and invariants run per document: `runner.run` is handed one
`doc` with no lane, no path and no siblings.

The join exists — `signatures.json`'s `group` key matches `metadata.filename` on 80/80
acts documents. `group` is the first component of the corpus-relative path, i.e. the
containing folder (`packages/legal_ingest/signature.py:284`, rationale `:125-127`: the
folder *is* the document group, holding for 183/183 inventory rows). But its counts are
**PDF-regex measurements, not tree counts**, so a real parse-quality comparison needs a
new per-group index over `output/*.json`. That index is the task; the invariant is easy
once it exists.

### Phase 4 — 2 items

#### P4-1 — flip `--profile auto` to the default

So a family override *refines* the lane's profile rather than replacing it. Flags today:
`tools/convert.py:51` and `tools/convert_all.py:433`, both `--profile {lane,auto}`
defaulting to `lane`; `convert_all.py:486` refuses `auto` on ordinance up front.

**Gated on Phase 3 reaching zero-or-exempted** — flipping it re-parses everything, and
doing that while the register is non-zero destroys the ability to attribute a change.

#### P4-2 — decide the `fbr_ingest` fork — a routing problem

Decide on the evidence now committed in `signatures.json`. Both forks parse the same three
sections of an ICT Ordinance edition; **the only difference is that `legal_ingest` has a
flat-act fallback that gives them a container.** So this is a **routing** problem, not a
parsing one. Route by family, not by lane. Routing today:
`apps/api/backend/services/corpus_registry.py:98` (ordinance → `fbr_ingest`, asserted at
`:170`).

**Merging the fork stays the v1 non-goal it already is** (`README.md:283`). Follow-through
unblocks 9 documents, and with them [P3-1d](#p3-1--section_carries_its_body-21--four-unrelated-causes-not-one).

The fork also carries **two dormant copies of round 13's fixes**, measured at *zero*
additional hits across all 12 ordinance documents, so leaving them was correct — but they
are live landmines the moment routing changes:

| fork site | vs. fixed version |
|---|---|
| `packages/fbr_ingest/discover.py:221-244` — inline `core.split()`, the pre-round-1 spelling; an unreadable keyword still falls through to the nameless-Division branch at `:236` | `packages/legal_ingest/discover.py:429-452` — extracted `_split_container_heading`, `re.split(r"[\s\-]+", …, maxsplit=1)` at `:451` |
| `packages/fbr_ingest/builder.py:1395-1397` — `_STRUCTURAL_RE` still on `CHAPTER\s+`; round 13's hyphen widening was never ported | `packages/legal_ingest/builder.py:2104-2106` |

Only `legal_ingest`'s version is covered by
`tools/tests/test_structural_boundary_agrees_with_grammar.py`.

### Phase 5 — the instrument tree level, 4 limbs, not started

A level *above* chapter, so a compilation parses as N instruments rather than one document
whose index rows become section leaves.

1. **The level itself.**
2. **The tree walkers that hardcode the child keys.**
3. **The portal renderer.**
4. **Re-convert the compilations.**

> **Limb 2 is bigger than the record says.** `grammar.py:419` states "six tree walkers
> hardcode the child keys `("parts", "divisions", "sections")`, so a new `Node.kind` would
> be dropped **silently**" — and `toc.py:920` repeats it. That six is scoped to the parser
> package as it was then. A repo-wide grep at this commit finds **23 sites across 11
> files**: 7 in `legal_ingest` (`builder.py:2481,2676`, `schedules.py:147,604,631,817`,
> `pipeline.py:985`), 7 in the `fbr_ingest` fork
> (`pipeline.py:303`, `builder.py:1623,1818`, `schedules.py:118,367,394,580`), 4 in the
> suite (`loader.py:38`, `_common.py:1035,2509,2512`), 4 in the audit tools
> (`tools/acts/audit_completeness.py:258,262`, `tools/ordinance/audit_completeness.py:119,123`),
> and 1 in the API (`apps/api/backend/services/overlays.py:32` `_LEAF_SEGMENTS`).
> **A silent drop is the failure mode**, so limb 2 is where the risk lives, not limb 1.

**Its gate is the deletion of the 4 exemption entries that name it**, all in
`tools/suite/exemptions/rules.json:47-66` — two for Customs Rules 2001
(`:47-51` `section_carries_its_body`, `:52-56` `no_foreign_section_start_in_body`) and two
for Federal Excise Rules 2005 (`:57-61`, `:62-66`), each a pair on the same evidence, each
naming `wip/tasks.md` Phase 5 as its expiry condition. **That deletion is the honest test
that it worked**, and the suite reports the entries stale on its own once it does.

(`wip/HANDOVER.md` says this gate is *two* entries; `wip/tasks.md` says *five*. It is
**four** — verified by reading the file at this commit. The file holds 10 entries in
total; the other 6 are `no_jammed_words` / `no_split_ordinals` / one `section_codes_ordered`
naming Phase 6 option (a), and are not this gate.)

### Phase 2 — the OCR half: a decision, not work

**Out of scope by instruction, and it stays out until someone decides otherwise.**
`data/ocr_cache` is 0 B and must stay 0 B.

The shape of the decision, so it can be made rather than rediscovered: 61 scanned
documents, 2,456 OCR pages. There is a **cheap tail** — 35 documents need ≤ 10 pages each,
**172 pages in total**, roughly 15 minutes at the measured 0.2 pages/sec, and Finance Acts
2022 and 2023 are **one page each**. At ≤ 30 pages it is 50 documents / 504 pages. The
marathon tail is Finance Act 2017-18 (683 pages), 2025 (290), 2015 (236), 2016-17 (215),
2014 (148), 2020 (140).

> **Taking OCR in scope has consequences beyond time**, and this is the chain that makes
> it a deliberate decision rather than a cheap win:
> `data/ocr_cache` stops being 0 B → the fidelity-floor invariants wake up → a sub-floor
> scan routes to `_provisional/` (`tools/convert.py:60` `--admit-below-floor`, which
> stamps `metadata.ocr.provisional=true`) → and under the withdrawal shipped in the
> integration track, **that removes the document from the portal.**

Waiting on the same decision: the `--admit-below-floor` rebuild of the 9 provisional acts
documents, and the ordinance lane's other 10 text-layer documents (which actually depend
on [P4-2](#p4-2--decide-the-fbr_ingest-fork--a-routing-problem), not on OCR).

---

## 5. Sequencing — what blocks what

Short list, not a chart. Everything not named here is independent and can be picked up in
any order.

```
P3-1d (ordinance 5) ──── blocked on ── P4-2  (fbr_ingest routing)
P4-1 (--profile auto) ── blocked on ── Phase 3 at zero-or-exempted
P5-1 completion ──────── DEFINED BY ── deleting exemptions/rules.json:47-66
P3-4 (container guard) ─ enables ───── the PART separator widening
P3-5 (CHAPTER suffix) ── breaks ────── test_..._gap_is_still_open (by design)
delete _legacy_section_key ─ blocked on ─ 14 stale acts docs ─ blocked on ─ OCR decision
```

Two things that look like dependencies and are not: **P3-2 and P3-5 both touch
`builder.py` but not the same function** (`_find_heading_split:2245` vs
`_STRUCTURAL_RE:2104`), so they can be separate rounds. And **P3-1's five sub-causes are
independent** — a round may close b alone.

---

## 6. Acceptance criteria

Falsifiable, per phase. The governing rule applies to every row: **fixed, or exempted with
evidence traced to the source PDF; there is no third state.**

**Phase 3 is done when** `tools/suite/register.json` reads `total: 0`, or every remaining
hit has an entry in `tools/suite/exemptions/<lane>.json` carrying evidence traced to a
source PDF page — and `.venv/bin/python tools/run_tests_smoke.py` exits **zero**, which it
cannot do while the register is non-zero. That exit code is the phase's own gate.

**Phase 4 is done when** `--profile auto` is the default in both `convert.py` and
`convert_all.py`, a family override refines rather than replaces the lane profile, the
`fbr_ingest` routing decision is recorded with its evidence, and the 9 blocked documents
are converted.

**Phase 5 is done when** the 4 exemption entries at `exemptions/rules.json:47-66` are
**deleted** and all three lane suites stay green — not when the level exists. If deleting
them turns the suite red, the level did not work.

**Phase 2 is done when** someone records the decision. Doing nothing is a valid outcome;
leaving it unrecorded is not.

---

## 7. Verification

Every command below was run at this commit and produced exactly the output shown.

```sh
.venv/bin/python tools/run_suite.py acts        # 15 hits
.venv/bin/python tools/run_suite.py rules       #  9 hits
.venv/bin/python tools/run_suite.py ordinance   #  5 hits
.venv/bin/python -m pytest tools/tests -q       # 86 passed, 1 skipped in ~37s
.venv/bin/python tools/run_tests_smoke.py       # package self-checks + lane suites
.venv/bin/python tools/discover_corpus.py --check   # "no drift"
.venv/bin/ruff check                            # "All checks passed!"  -- BARE
du -sh data/ocr_cache                           # 0B
```

`run_suite.py` takes `lane` plus an optional `json_path`, `--pdf` and `--json <report>`.
**It has no `--check` and no `-o`** — `--check` exists only on `discover_corpus.py`, which
takes a *required* mode flag (`--write`/`--check`/`--assert`/`--reconcile`/`--verify-lanes`).
`run_tests_smoke.py` takes **no arguments at all**. There is **no `suite` Make target**.

Two outputs that are correct and look wrong:

- **The 1 skipped is intentional** —
  `test_heading_leak_class.py::test_scan_heading_leaks_skips_without_corpus`, whose skip
  reason is *"acts corpus is staged — the scan reports its hits, as it should"*.
- **`run_tests_smoke.py` exits non-zero while the register is non-zero.** Expected and
  pre-existing. It clears when Phase 3 reaches zero-or-exempted — see §6.

### CI does not gate any of this

`data/corpora/*/output/` is gitignored, so all three lane suites **SKIP** on CI. Green
checks on a PR are **not** evidence the ingest is right. The real gate is
`tools/tests/test_register_snapshot.py`, and only on a machine with the corpus staged:

| test | asserts |
|---|---|
| `:90-101` `test_register_matches_the_committed_snapshot` | live `{lane: {inv: n}}` equals the snapshot exactly; skips unless all three lanes are staged (`:86-87`) |
| `:104-122` `test_no_active_regression_case_fails` | zero `[FAIL] <case_id>` lines |
| `:125-135` `test_snapshot_total_agrees_with_its_own_lanes` | `total == sum of lanes`; **runs corpus-free**, so CI does check this much |
| `:138-145` `test_snapshot_names_only_real_invariants` | every key is in `runner.invariants_for(lane).ALL_INVARIANTS` |

It works by scraping suite stdout (`_FAIL` at `:34`, matching the format emitted by
`tools/suite/runner.py:110`), so **changing that print format breaks the gate silently.**

### Per round

Snapshot `output/_pre_<round>/` before re-converting, re-measure all three lanes, and
regenerate the register **in the same PR**:

```sh
.venv/bin/python tools/tests/test_register_snapshot.py --write
```

That is the only way to regenerate it — **no Make target, no pytest flag.** It exits 2 if
the corpus is not staged or if `--write` is absent, and it preserves the `_comment` block.
A round that *improves* the register **fails** `test_register_snapshot.py` until this is
run — that is the point: the number moves deliberately, in the PR that moved it.

Step-by-step: [`tasks.md` → How a round runs](tasks.md#how-a-round-runs--worked-for-round-15).
