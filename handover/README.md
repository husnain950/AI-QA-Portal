# Handover — start here

Written **2026-09-04**, on `main` after PR #83 (round 17); updated after PR #84
(round 18), PR #85 (round 19), round 20 (PR #86), and **2026-09-10 after PR #89
(rounds 21-28)**. `register.json` reads **13**, regenerated in PR #89 from a
corpus converted at one revision.

**One-line state:** the anomaly register is **13**, down from 210. It is committed, gated
on CI, and **matches a live three-lane run on this machine** — acts 6, rules 2, ordinance 5,
delta zero, no lane skipped. Rounds 21-28 closed the Customs Act QA pass and took the acts
lane **15 → 6**, closing three invariant classes outright. What remains of Phase 3 is
thirteen hits across ten documents plus OCR, which is still **deliberately** out of scope
(decided 2026-09-04; the decision and its consequences are in
[`tasks.md`](tasks.md#decisions-on-record-2026-09-04)). Artifact:
[`wip/phase3-round21-28-customs-qa.md`](../wip/phase3-round21-28-customs-qa.md).

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
| `section_carries_its_body` | 6 | 1 | 5 | **12** |
| `no_foreign_section_start_in_body` | — | 1 | — | **1** |
| **per lane** | **6** | **2** | **5** | **13** |

Trajectory: `210 → 193 → 148 → 92 → 78 → 75 → 70 → 64 → 50 → 44 → 33 → 30 → 30 → 34 → 34 → 32 → 29 → 25 → 25 → 25 → 22 → 13`.
The rise to 34 is not a regression — round 12 added `preamble_carries_no_toc_tail`, a new
instrument that made four existing defects visible for the first time.

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
| acts | 6 | 4 | **80** | 93 |
| rules | 2 | 2 | **11** | **48** |
| ordinance | 5 | 4 | 12 | 46 |

103 documents converted, against the source-file counts in the last column. The rules lane
converts **11 of 48** — the other 36 are scans and one is Urdu, and every scan in the corpus
was skipped by instruction. Acts has the same shape smaller: 25 editions carrying 2,065
image-backed pages.

**The acts and rules lanes are now at ONE revision.** This is new, and it is the single
biggest change to how much any measurement here can be trusted. Recounted at this commit:

| documents | `pipeline_revision` |
|---|---|
| **77** (66 acts + 11 rules) | **`f3a37e0…` (round 27)** |
| 14 | *(none recorded)* — the acts documents rounds 21-28 deliberately skipped |
| 12 | `4827840…` (round 12) — the whole ordinance lane, which runs `fbr_ingest` |

The 14 skipped are 8 OCR-backed (out of scope; `data/ocr_cache` must stay at 0 B) and 6 with
no `source_kind` recorded (five Finance Acts, Benami, Income Tax Third Amendment). They stay
at their old revision, and the corpus stays mixed to exactly that extent.

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
.venv/bin/python tools/run_suite.py acts        # and rules, ordinance -> 6 / 2 / 5
.venv/bin/python -m pytest tools/tests -q       # 231 passed, 1 skipped
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
| `pytest tools/tests` → 56 passed | **231 passed, 1 skipped** |

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
