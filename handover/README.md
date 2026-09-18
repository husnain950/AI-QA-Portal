# Handover — start here

Written **2026-09-04**, on `main` after PR #83 (round 17); updated after PR #84
(round 18), PR #85 (round 19), round 20 (PR #86), and **2026-09-10 after PR #89
(rounds 21-28)**, and **2026-09-14 after the acts-lane exemptions**.
`register.json` reads **8**, regenerated in that PR from a
corpus converted at one revision.

**One-line state:** the anomaly register is **0**, down from 210. **All three lanes are at
zero**, measured on a corpus re-converted under this tree — acts 0, rules 0, ordinance 0,
delta zero, no lane skipped. Rounds 29-34 (PRs #93-#99) took it **13 → 0**.

**Round 38 (2026-09-17) came from an external QA cycle, not the board.** 19 rows against
`Federal Excise Act, 2005 as amended upto 30-06-2025`: **18 real, 1 not**, collapsing to
9 root causes. Sixteen closed by seven fixes, one closed as not-a-defect with a pin, two
tariff-table rows held for a second PR. Each cause fired far beyond the one document —
the orphaned heading terminator was **412 leaves across 30 documents**, the missing
schedule title **237 across 34**. Corpus after: unresolved markers **2,813 → 2,427**,
bare-`[See …]` leaves **201 → 7**, orphaned dashes **412 → 2**, leaves **+2** (two
omitted s.31 recovered). Register still **0**. See
[`tasks.md`](tasks.md#closed-by-round-38--a-qa-cycle-not-a-board-row).

**Round 39 (2026-09-18) closed the two rows round 38 held.** FS-02 and FS-07, the
Federal Excise tariff tables that reached the portal as `<p>` prose. The ledger's
one-line prescription (widen `_NUM_TOKEN`) is **not** a fix: alone it renders 125 `<tr>`
for a 69-row table and reprints the page header nine times as data. **Five defects**, four
in the column model and one — `no_split_ordinals`, `30 th June` — raised by the round
itself, because the table path has always joined words with `" ".join`. Measured over 119
convertible sources converted twice: **17 changed, 102 byte-identical**, and the 17 are
exactly the census population (162 `Col.(N)` rows / 17 documents, all Federal Excise).
Tables **+51**, `<tr>` **+1,933**, `<p>` **−607**, leaves **+0**, footnote records **+0**;
unresolved markers **−181**, all of them false. Register still **0**. **FS-07 is only half
closed** — THIRD SCHEDULE Table-I prints no numbering row at all, which is
[row q4](tasks.md#closed-by-round-38--a-qa-cycle-not-a-board-row). See
[`tasks.md`](tasks.md#closed-by-round-38--a-qa-cycle-not-a-board-row).

**Every gate is green as of round 40.** `tools/discover_corpus.py --check` had reported
`signatures.json` stale over 27 documents since **PR #86 (round 20)**; round 40 regenerated
the artifacts and attributed the whole drift to one character — the CHAPTER en-dash added to
`grammar.CHAPTER_RE`'s separator class, which `signature.measure` counts into
`chapter_lines`. No family moved and no parser code changed. **The lesson generalises:** a
widening of any pattern `signature.measure` reads (`CHAPTER_RE`, `PART_RE`, `DIVISION_RE`,
`SCHEDULE_RE`, `TABLE_RE`, the TOC rows) moves a discovery signature silently, because the
only thing watching it is a gate CI skips. Rerun `--write` in the same round. Artifact:
[`wip/phase3-round40-discovery-signatures.md`](../wip/phase3-round40-discovery-signatures.md).

**Round 41 closed row 13, the top of the board.** Sales Tax Rules 2006 (01-01-2025) went
from **761 unresolved markers and 0 footnote records to 367 records, 321 bound citations and
57 unresolved**. `calibrate` had paired its 12.0pt body with the 11.0pt of two whole pages —
*another regime's body*, not the page folio the ledger named — failed the `SIZE_GAP_MIN` test
and gave the document up. The gap test was consulted in the wrong place: it now skips that
candidate rather than the document, gated by a mass floor and by the requirement that a
footnote zone actually sit at the foot of the page. **Exactly one document in the corpus
changes.** The row's rider did **not** fire. Artifact:
[`wip/phase3-round41-second-body-calibration.md`](../wip/phase3-round41-second-body-calibration.md).

**Round 42 closed row 14, the last ranked row.** Customs Rules 2001 goes from **41 chapters
to 43**, with rule **89** recovered. `builder._STRUCT_DECOR_RE` knew only whitespace between
stacked amendment markers, so `41&46 [CHAPTER VIII` and `2&30 [CHAPTER XIV` were never
boundaries; the grammar's own `MARKER_PREFIX` has known `,` and `&` for rounds. **CHAPTER XX
is deliberately not recovered** — it wears an opening quote, and that glyph opens quoted
repealed text far more often than a substituted caption. Artifact:
[`wip/phase3-round42-marker-run-decoration.md`](../wip/phase3-round42-marker-run-decoration.md).

**The board has had no register-bearing work since round 36.** Work is picked from the
**unmeasured surface** instead — the unresolved `<sup class="marker">` census, which no
invariant watches. It stands at **3,265 across 81 documents** after round 37 (acts 1,900 /
rules 934 / ordinance 431), down from 3,930/82. The ranked table in
[`tasks.md`](tasks.md#start-here--pick-one) carries the next two rows, both measured.

**Read that number with its qualifier.** **Nine of those thirteen were closed by exemption
with evidence, four by code.** An exemption silences a whole invariant for a whole document,
and the runner still prints those hits under its `EXEMPT INVARIANTS` banner — so "register 0"
means *nothing un-excused is failing*, not that the corpus is clean. The split is in
[`tasks.md`](tasks.md#closed-by-rounds-29-34-prs-93-99--kept-so-they-are-not-re-picked) and
the round is in
[`wip/phase3-rounds-29-34-merge.md`](../wip/phase3-rounds-29-34-merge.md). OCR is still
**deliberately** out of scope (decided 2026-09-04; consequences in
[`tasks.md`](tasks.md#decisions-on-record-2026-09-04)).

**Rounds 21-28 were measured on one document and then corrected by the lane suites.**
Eight rounds against `Customs Act, 1969 … 30th June, 2025`, closing 21 reviewer-logged
defects: fused citation markers, a footnote zone vetoed by a footnote-sized heading, body
sections the contents page never lists, contents-row repairs, chapter membership following
the body spine, and a quoted heading refused as a footnote definition. Sections **325 → 339**,
footnote records **707 → 794**, unrendered marker sites **55 → 3**, duplicate codes **1 → 0**.

**Round 27 is the one to read first.** Rounds 23 and 25 were each measured on one document,
looked clean, and were both wrong in the rules lane — round 23 collapsed 860 of 1,102 rules
to stubs, round 25 re-parented 98 sections. Both were caught only by running the lane suites
over a fully re-converted corpus. **A round measured on one document is measured on one
document.**

**Three acts classes closed in that pass**, which is where 15 → 6 comes from:
`no_chapter_caption_in_section_heading` (was 4), `preamble_carries_no_toc_tail` (was 2) and
`clause_codes_plausible` (was 1) are all **0**, as are the two omission spellings inside
`section_carries_its_body`. Every one of those was a row on the ranked board; see
[`tasks.md`](tasks.md).

**Rounds 17 and 18 both moved the register by zero, on purpose.** Round 17 shipped the
container-code guard and the PART separator widening it enables (**14 gained, 0 lost**).
Round 18 closed the **CHAPTER letter suffix**: **80 swallowed boundary lines across 24
documents went to 0**, with 0 leaves and 0 chapter nodes gained or lost — the register rose
**+57** when the invariant was widened and fell **-57** when the parser was, netting zero.
A round that moves the register by zero and says so is working as designed; see §3's last
rule.

**Round 19 took the register to 22** — by **exemption with evidence**, not by a fix: the
three heading-only leaves of Sales Tax Rules 2006 (01-01-2025) are each a printing error in
the source, traced to PDF pages 66, 109 and 151. Two of the three traces the ledger carried
for them were **wrong**; see
[`tasks.md` task 5](tasks.md#5-the-round-10-rules-residue--3-hits-an-exemption-row).

> **This folder supersedes `wip/HANDOVER.md`.** That file was written 2026-08-30 at
> register 64 and is now wrong on nearly every number it states. `wip/` is deliberately
> untouched — it is the historical record, and code still cites it (see §5) — but do not
> read it for current state. §6 lists exactly what it gets wrong.

| | |
|---|---|
| [`open-work.md`](open-work.md) | what is left, ranked, with the blocker for each |
| [`working-rules.md`](working-rules.md) | how to work on this, and the traps that drew blood |
| [`plan.md`](plan.md) | the architecture: every remaining problem numbered, with the fix already known to be wrong |
| [`tasks.md`](tasks.md) | **the execution ledger — start here to do work.** Pick a row, follow the steps, record the result |

---

## 1. The register

`tools/suite/register.json` is the committed truth and CI compares against it. This table
is transcribed from that file, which `tools/tests/test_register_snapshot.py` verified
against a live three-lane run at this commit.

| invariant | acts | rules | ordinance | total |
|---|---|---|---|---|
| `section_carries_its_body` | — | — | — | **0** |
| **per lane** | **0** | **0** | **0** | **0** |

Trajectory: `210 → 193 → 148 → 92 → 78 → 75 → 70 → 64 → 50 → 44 → 33 → 30 → 30 → 34 → 34 → 32 → 29 → 25 → 25 → 25 → 22 → 13 → 12 → 10 → 9 → 6 → 1 → 0`.
The rise to 34 is not a regression — round 12 added `preamble_carries_no_toc_tail`, a new
instrument that made four existing defects visible for the first time.

**2026-09-14 — round 37 is the first round taken off the UNMEASURED surface, and it is the
first in four rounds where an invariant had something to say.** The board had no
register-bearing work left, so the round came off the unresolved-marker census instead.
Customs Rules 2001 (30.06.2023) carried **665** unresolved `<sup class="marker">` and **zero**
footnote records — and the source turned out to print its whole apparatus, once, at the end:
`As Amended:-` on p561 and **158 numbered S.R.O. entries** to p563, at BODY size. Three gates
in `footnotes.py` each refuse a body-sized apparatus, so the lot read as body and rule **1122
(*Audit*)** swallowed 157 notification lines. Read as its own shape: **665 unresolved → 0, 672
citations bound, 421 footnote records on 229 leaves, 0 leaves gained or lost**, one leaf's text
changed (1122, −796 words). **Then the register moved 0 → 1** and that hit was real: a
document with no footnote records passes every footnote invariant, so
`footnote_on_citing_leaf` had never had anything to look at. It was a gridless table span
swallowing the CHAPTER XIV caption on p102; fixed in the same PR. Corpus-wide the unresolved
population goes **3,930 → 3,265**. **76 of the 77 re-converted documents are byte-identical.**
Artifact: [`wip/phase3-round37-terminal-amendment-list.md`](../wip/phase3-round37-terminal-amendment-list.md).

**2026-09-14 — board row 1 is CLOSED, and the register moved by zero on purpose.** `MARKER_NOTE_RE` read one trailing dot where the Customs source prints six note heads with two, so each opened no note and its line was folded into the previous note's body. Widened to `\.{0,2}` (uppercase branch `\.{1,2}`, its dot still mandatory). Across 20 Customs editions: **+120 footnote records, +254 citations bound, −254 unresolved markers, 0 notes lost**, leaf counts and body words unchanged, footnote zone unmoved, and the rules control byte-identical in its body. **The register is 0 before and 0 after** — no invariant here can see a marker-grammar change in either direction, which is why the proof is the output diff. The board's nine-heads/seven-real count was wrong: it is **six and six**. Artifact: [`wip/phase3-round36-double-dot-note-head.md`](../wip/phase3-round36-double-dot-note-head.md).

**2026-09-14 — `no_foreign_section_start_in_body` is CLOSED (was 1), and it was an INVARIANT bug.** `_table_cell_lines` collected per-`<td>` text, but the renderer flattens a short table row into ONE `plain_text` line joined by spaces, which equals no cell. Sales Tax Rules 2006 (01-01-2025) rule 13's Schedule row `44A | Steel ingots / bala | M. Tons` was read as the start of rule 44A. No parser change, no re-conversion. **Ten classes are now closed.** Artifact: [`wip/phase3-table-row-join.md`](../wip/phase3-table-row-join.md).

**2026-09-14 — the ordinance five turned out to be TWO causes, and 214E's is fixed.** The 11.03.2019 and 30.06.2019 ITO editions print s.214E as `4[“214E.` with the opening quote GLUED into the bracket token, which `fbr_ingest._DOTFORM_RE` cannot cross — so 214E's whole body sat in 214C. **The U+2500 box-drawing dash this folder blamed was not the cause**; the working 30.06.2020 control prints the identical `audit.─` terminator. Ordinance **5 → 3**. Artifact: [`wip/phase3-fbr-quote-prefixed-section-start.md`](../wip/phase3-fbr-quote-prefixed-section-start.md).

**2026-09-14 — five acts hits closed by exemption with evidence.** `tools/suite/exemptions/acts.json` was created (it had never existed) with three entries: Customs 1969 30.06.2008 ss.181/189, where the source misprints the body code (`35.` for `181.`, `37.` for `189.`, both at body size) and **the same misprint hits s.185D as `36.` where no invariant sees it**; and PFMA 2019 s.26 plus PSW 2021 ss.27/28, both `scanned-ocr` with `pipeline_revision: null` — two of the 14 documents round 27 skipped, so neither can be re-measured without making `data/ocr_cache` non-zero. Both carry the OCR decision as their expiry. PSW's two are not sections at all: they are rows of the Act's `[SCHEDULE]`, whose `S. No.` column reads as section codes. Artifact: [`wip/phase3-acts-exemptions.md`](../wip/phase3-acts-exemptions.md).

**Nine invariant classes are closed:** `body_chapters_in_tree`, `no_footnote_text_in_body`,
`structure_counts`, `no_code_fragment_in_section_heading` (round 12, was 31),
`no_structural_heading_in_body` (round 13, was 175), `section_codes_ordered` (round 15,
was 3) — which turned out to be three mislabelled *chapters*, not three misread section
codes — and **three more in rounds 21-28**: `no_chapter_caption_in_section_heading`
(was 4), `preamble_carries_no_toc_tail` (was 2) and `clause_codes_plausible` (was 1).

Those last three are worth a second look, because **none of them was closed by a round
aimed at it.** Round 20 had shipped the code for all three against public PDFs and could not
move the register, because the private editions carrying the hits were not on that host. The
rounds 21-28 re-conversion put them at one revision and the hits went with them. A fix that
is shipped and a fix that is *measured* are two different states, and the board carried them
as open for a full round in between.

`no_structural_heading_in_body` is closed **more strongly** since round 18: its own pattern
carried the same narrow CHAPTER branch as the parser, so it was blind to 57 hits it should
have reported. Both were widened together, and it is back to 0 with an instrument as wide as
the defect. A closed class whose instrument is narrower than the bug is not closed -- it is
unmeasured.

`section_carries_its_body` is **not** among them, and its 21 → 17 → 14 → **12** across rounds
16, 19 and 21-28 is why the distinction matters: that class has several unrelated causes.
Round 16 closed one (the STSP 58U/58V pair), round 19 **exempted** another with evidence (the
round-10 rules residue), and rounds 21-28 closed the two omission spellings. What is left is
six single-document traces plus the ordinance five behind the `fbr_ingest` decision.

**The rule has not changed: fixed, or exempted with evidence traced to the source PDF.
There is no third state.** "Tracked and deferred" without an exemption entry is a red gate.

## 2. What the register is a measurement *of*

**Read the last column before the first.**

| lane | hits | editions affected | converted | of source files |
|---|---|---|---|---|
| acts | 0 | 0 | **80** | 93 |
| rules | 0 | 0 | **11** | **48** |
| ordinance | 0 | 0 | 12 | 46 |

103 documents converted, against the source-file counts in the last column. The rules lane
converts **11 of 48** — the other 36 are scans and one is Urdu, and every scan in the corpus
was skipped by instruction. Acts has the same shape smaller: 25 editions carrying 2,065
image-backed pages.

**All three lanes are at ONE revision, as far as the OCR decision allows.** Re-measured
2026-09-14 after **round 37**, converting every staged document from a **clean** tree — 77 of
77, 0 failures, 953s. The 21/56 split rounds 35-36 left in acts and rules is **gone**:

| documents | `pipeline_revision` |
|---|---|
| **77** (66 acts + 11 rules) | **`0139b858daac`** — round 37. Every text-layer document in both lanes |
| **9** (ordinance) | `dbcab2f79b78` — PRs #93-#99. Rounds 35-37 are all `legal_ingest`; the ordinance lane runs `fbr_ingest` and does not import it, so it is current |
| 14 | *(none recorded)* — the image-backed acts documents, see below |
| 3 | `4827840…` (round 12) — the image-backed ITO editions (20.02.2026, 30.06.2024, 31.07.2025) |

**The ordinance lane moved twenty-two rounds in one step**, from round 12, and nine of its
twelve documents are now current. The other three are image-backed and cannot follow.

**Convert from a clean tree.** `pipeline_revision` appends `-dirty` and records the tree's
HEAD, not the change being tested. Round 35 converted all 77 from a worktree with its edits
uncommitted and stamped them `8032b142c72f-dirty` — the commit *before* the fix, marked
unanswerable — which cost a second 16-minute run to correct. The rule is in
[`working-rules.md`](working-rules.md).

**Re-convert the staged set, never the lane.** `convert_all.py <lane>` targets every PDF in
the lane — 46 + 93 + 48 = **187** against 103 staged outputs — so a bare run adds 84
documents and the register stops measuring the same document set. Three ordinance outputs
also carry a legacy filename (`Income Tax Ordinance 2001 - amended upto 30.06.2024.json`
against today's `Income Tax Ordinance, 2001 Amended upto 30.06.2024.json`), so converting
them under `out_path` leaves the old file beside the new one and the lane holds 15 documents,
three of them duplicates. Both traps are live for the next re-convert:
[`wip/phase3-rounds-29-34-merge.md`](../wip/phase3-rounds-29-34-merge.md).

**All 14 are image-backed — corrected 2026-09-14.** This block used to split them into 8
OCR-backed (out of scope; `data/ocr_cache` must stay at 0 B) and 6 with no `source_kind`
recorded, which reads as six documents that are merely unlabelled. `convert_all.scan_page_count`
is an exact per-page census, not a sample, and it reports image-backed pages on every one of
the 14. A file with even one such page cannot convert without the OCR extras, so under the
standing no-OCR decision **all 14 stay at their old revision permanently**, and the corpus
stays mixed to exactly that extent. Board row 6 is blocked for as long as that decision
stands — not pending a census.

**The consequence: the standing "mixed-revision drift" warning is spent for acts and rules.**
It used to be that `test_register_snapshot.py` failed on this machine *before* you changed
anything, and so did the rules-lane regression case `customs_2001_is_a_compilation`. Both
are green now. Do not carry that warning forward as if it still applied — but do not extend
the all-clear to the ordinance lane either, which nothing in rounds 21-28 touched.

Round 15 re-converted 15 documents, chosen by measurement rather than by guess: each
acts/rules document's contents were parsed twice at the same commit, with the fix on and
off, and **76 were shown untouchable**. The ordinance lane cannot be reached by that
round's fixes at all — it runs `packages/fbr_ingest`, a separate parser.

Round 16 re-converted **2**, and its scope was measured the same way — over the source
rather than the output: 290,982 distinct text lines from all 187 PDFs in the three lanes,
scored against the unfixed parser. The fix changes **12 lines and gains none**. Four are
the two documents it re-converted; the other eight are **Income Tax Rules 2002**, which has
no `output/*.json` and was deliberately left alone rather than pushed into the corpus.

Round 17 re-converted **5**, all rules-lane, and its scope was measured by parsing each
candidate document **twice at the same commit** with the fix on and off — the only way to
attribute a change on a mixed-revision corpus. Its round-16 predecessor's two documents and
three of round 15's fifteen are among the five, which is why those rows fell.

Round 18 re-converted **24** -- 20 Customs Act editions and 4 rules editions -- and its
scope was measured the same way, over which body lines flip answer between the old pattern
and the new. **The ledger's standing estimate of 44 was stale**: it dated from before round
13 shipped. The flipped-line set and the invariant-hit set were the same 24 documents, which
is the cross-check that the scope was right.

## 3. Ground rules

- **Never commit to `main`.** One branch and one PR per unit of work.
- **Every behaviour change ships with the test that fails without it, in the same PR.**
- **A gate that cannot fail is a no-op.** If a new check cannot be made to fail on purpose,
  it does not count as a gate.
- **Measure the invariant fix and the parser fix separately**, on identical JSON for the
  first. Nearly every class is part wrong-invariant, part real defect, and a single total
  hides both.
- **Report changes that moved a number by zero.** Folding them into a total misattributes
  the rounds that did move it.

## 4. Verification

```sh
.venv/bin/python tools/run_suite.py acts        # and rules, ordinance -> 1 / 2 / 5
.venv/bin/python -m pytest tools/tests -q       # 245 passed, 1 skipped
.venv/bin/python tools/run_tests_smoke.py       # package self-checks + lane suites
.venv/bin/python tools/discover_corpus.py --check
.venv/bin/ruff check                            # BARE -- matches ci.yml
du -sh data/ocr_cache                           # must stay 0 B
```

Two things about that output that are correct and look wrong:

- **The 1 skipped is intentional.** It is
  `test_heading_leak_class.py::test_scan_heading_leaks_skips_without_corpus`, which skips
  with the reason *"acts corpus is staged — the scan reports its hits, as it should"*.
  (`wip/tasks.md:99` still logs this as a test that is green on CI and **red** with a
  corpus. That was fixed; it now skips cleanly. Verified at this commit.)
- **`run_tests_smoke.py` exits non-zero while the register is non-zero.** Expected and
  pre-existing. It clears when Phase 3 reaches zero-or-exempted.

**CI does not gate any of this.** `data/corpora/*/output/` is gitignored, so all three lane
suites SKIP on CI. Green checks on a PR are not evidence the ingest is right — the register
snapshot test is, and only on a machine with the corpus staged. Run it before merging a
parser change.

Per round: snapshot `output/_pre_<round>/` before re-converting, re-measure all three lanes,
and regenerate `tools/suite/register.json` **in the same PR**. A round that *improves* the
register fails `test_register_snapshot.py` until that file is updated — that is the point.

## 5. Where the history is

`wip/` holds the full record: 45 files, one write-up per round (`wip/phase3-*.md`), the
Phase 0/1/2 findings, and the finished `wip/integration/` track. **Nothing there was changed
when this folder was written**, and it must not be deleted wholesale — shipping code cites
it as its source of record:

| cited file | cited from |
|---|---|
| `wip/phase2-findings.md` | `tools/convert.py:88`, `tools/discover_corpus.py:423`, `packages/legal_ingest/families.py:98,183`, `tools/tests/test_profile_auto_resolves_the_lane.py:3` |
| `wip/tasks.md` | `tools/suite/exemptions/rules.json` (4 entries name it as their **expiry condition**), `tools/suite/register.json`, `tools/suite/invariants/_common.py:2163`, two tests |
| `wip/integration/plan.md` | `tools/suite/invariants/_common.py:1054` |

`wip/integration/measure/*.py` are also linted by `make check` and by CI.

## 6. What `wip/HANDOVER.md` gets wrong

Kept for the record, because someone will open it. Its **§4 working rules are still the
best part of it** and are carried into [`working-rules.md`](working-rules.md); everything
factual below it has moved.

| it says | actually |
|---|---|
| register **64** | **13** |
| **16 of 48** items open | **17 of 66**, plus two located since |
| after eight merged PRs (#46–#53) | #54–#85 have merged since |
| **three** invariant classes closed | **six** |
| its whole §2 register table | wrong on every row — `no_foreign_section_start_in_body` 19 → 1, `section_carries_its_body` 37 → 14 |
| "`section_carries_its_body` and `no_foreign_section_start_in_body` move together — fix start detection and both move" | superseded; the second is down to 1 and the first is now four unrelated causes |
| Sales Tax 15.9.2021 — "the pages *interleave*. Read those source pages before theorising" | **disproved.** They do not interleave; it was the cursor cascade, closed in round 9 |
| Phase 5's gate is "the deletion of the **two** Round 3 exemptions" | **4 entries**, across 2 documents. (`wip/tasks.md` says *five*; that is also wrong — verified by grep at this commit) |
| "4c — transport and deploy … Docker is down on this host" | done, as the `wip/integration/` track, #59–#76 |
| an exported transcript "is **not gitignored**" | resolved — `.gitignore:80` |
| `pytest tools/tests` → 56 passed | **245 passed, 1 skipped** |

One more, not in HANDOVER: every file under `wip/integration/` still states the register as
**34**. Round 14 took it to 32, round 15 to 29, round 16 to 25, where rounds 17 and 18 left it,
and round 19 to 22, and rounds 21-28 to **13**. `wip/tasks.md:664` also states `section_codes_ordered` as **4** open hits; the class is
**closed**. And `wip/tasks.md:401`'s container-code guard box is unticked there; **round 17
closed it**, and this folder is the authority on that.

`handover/` itself was wrong about one thing until round 17 measured it: `plan.md` P3-4,
`open-work.md` item 4 and `tasks.md` task 4 all claimed the container-code guard "would
have kept round 13 from dropping four chapter captions in Customs Rules 2001". It would
not. All three now say so, and the reason it took a round to notice is the three-copy
problem `open-work.md` flags at the top of itself.
