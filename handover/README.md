# Handover — start here

Written **2026-09-04**, on `main` after PR #82 (round 16). Every number below was
measured on this machine at that commit, not carried forward; §4 says which command
produces each one.

**One-line state:** the anomaly register is **25**, down from 210. It is committed and
gated on CI. **20 of 66** checklist items remain open — the residue of Phase 3, all of
Phase 4 and Phase 5, and the OCR work, which is now **deliberately** out of scope
(decided 2026-09-04; the decision and its consequences are in
[`tasks.md`](tasks.md#decisions-on-record-2026-09-04)).

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
| `section_carries_its_body` | 8 | 4 | 5 | **17** |
| `no_chapter_caption_in_section_heading` | 4 | — | — | **4** |
| `preamble_carries_no_toc_tail` | 2 | — | — | **2** |
| `no_foreign_section_start_in_body` | — | 1 | — | **1** |
| `clause_codes_plausible` | 1 | — | — | **1** |
| **per lane** | **15** | **5** | **5** | **25** |

Trajectory: `210 → 193 → 148 → 92 → 78 → 75 → 70 → 64 → 50 → 44 → 33 → 30 → 30 → 34 → 34 → 32 → 29 → 25`.
The rise to 34 is not a regression — round 12 added `preamble_carries_no_toc_tail`, a new
instrument that made four existing defects visible for the first time.

**Six invariant classes are closed:** `body_chapters_in_tree`, `no_footnote_text_in_body`,
`structure_counts`, `no_code_fragment_in_section_heading` (round 12, was 31),
`no_structural_heading_in_body` (round 13, was 175), and **`section_codes_ordered`
(round 15, was 3)** — which turned out to be three mislabelled *chapters*, not three
misread section codes.

`section_carries_its_body` is **not** among them, and its 21 → 17 in round 16 is why the
distinction matters: that class has four unrelated causes and round 16 closed one of them
(the STSP 58U/58V pair). Three remain, plus the ordinance five behind the `fbr_ingest`
decision.

**The rule has not changed: fixed, or exempted with evidence traced to the source PDF.
There is no third state.** "Tracked and deferred" without an exemption entry is a red gate.

## 2. What the register is a measurement *of*

**Read the last column before the first.**

| lane | hits | editions affected | converted | of source files |
|---|---|---|---|---|
| acts | 15 | 11 | **80** | 93 |
| rules | 5 | 2 | **11** | **48** |
| ordinance | 5 | 4 | 12 | 46 |

103 documents converted, against the source-file counts in the last column. The rules lane converts **11 of 48** — the other 36
are scans and one is Urdu, and every scan in the corpus was skipped by instruction. Acts
has the same shape smaller: 25 editions carrying 2,065 image-backed pages.

It is also still a **mixed-revision** corpus. Each round re-converts only the documents its
fix touches, so 61 scanned documents keep whatever revision last wrote them. At this commit:

| documents | `pipeline_revision` |
|---|---|
| 39 | `7cc5d34…-dirty` |
| 15 | `6824850…-dirty` (round 15) |
| 14 | *(none recorded)* |
| 13 | `8e01b27…` (round 13) |
| 12 | `4827840…` (round 12) |
| 8 | `06d8bfb…` (round 14) |
| 2 | `88f5d14…-dirty` (round 16) |

Round 15 re-converted 15 documents, chosen by measurement rather than by guess: each
acts/rules document's contents were parsed twice at the same commit, with the fix on and
off, and **76 were shown untouchable**. The ordinance lane cannot be reached by that
round's fixes at all — it runs `packages/fbr_ingest`, a separate parser.

Round 16 re-converted **2**, and its scope was measured the same way — over the source
rather than the output: 290,982 distinct text lines from all 187 PDFs in the three lanes,
scored against the unfixed parser. The fix changes **12 lines and gains none**. Four are
the two documents it re-converted; the other eight are **Income Tax Rules 2002**, which has
no `output/*.json` and was deliberately left alone rather than pushed into the corpus.

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
.venv/bin/python tools/run_suite.py acts        # and rules, ordinance -> 15 / 5 / 5
.venv/bin/python -m pytest tools/tests -q       # 92 passed, 1 skipped
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
| register **64** | **25** |
| **16 of 48** items open | **20 of 66** |
| after eight merged PRs (#46–#53) | #54–#81 have merged since |
| **three** invariant classes closed | **six** |
| its whole §2 register table | wrong on every row — `no_foreign_section_start_in_body` 19 → 1, `section_carries_its_body` 37 → 17 |
| "`section_carries_its_body` and `no_foreign_section_start_in_body` move together — fix start detection and both move" | superseded; the second is down to 1 and the first is now four unrelated causes |
| Sales Tax 15.9.2021 — "the pages *interleave*. Read those source pages before theorising" | **disproved.** They do not interleave; it was the cursor cascade, closed in round 9 |
| Phase 5's gate is "the deletion of the **two** Round 3 exemptions" | **4 entries**, across 2 documents. (`wip/tasks.md` says *five*; that is also wrong — verified by grep at this commit) |
| "4c — transport and deploy … Docker is down on this host" | done, as the `wip/integration/` track, #59–#76 |
| an exported transcript "is **not gitignored**" | resolved — `.gitignore:80` |
| `pytest tools/tests` → 56 passed | 92 passed, 1 skipped |

One more, not in HANDOVER: every file under `wip/integration/` still states the register as
**34**. Round 14 took it to 32, round 15 to 29 and round 16 to **25**. `wip/tasks.md:664`
also states `section_codes_ordered` as **4** open hits; the class is **closed**.
