# Phase 3, interlude — gate the register, and lint what CI lints

Follows [`wip/phase3-parenting-and-marker-runs.md`](./phase3-parenting-and-marker-runs.md)
(PR #52). No parser change, no re-conversion, no register movement. Two holes in the
checks themselves, both demonstrated rather than argued.

## 1. `make check` and CI lint different trees

`ci.yml` runs `ruff check` bare. The Makefile named paths — `ruff check apps/api tools` —
which looks equivalent and is not: `pyproject.toml` sets
`src = ["apps/api", "packages", "tools"]`, so the bare form also covers `packages/`.

Planting a two-line violation in `packages/legal_ingest/` shows it:

| invocation | result |
|---|---|
| `ruff check apps/api tools` (the Makefile's) | **All checks passed** |
| `ruff check` (CI's) | **Found 2 errors** |

So a lint break in the parser passed locally and failed the PR — which is the wrong way
round for a target whose comment says *"what CI gates on"*. The Makefile now runs it bare.

## 2. The register was gated by nothing at all

`data/corpora/*/output/` is gitignored, so `run_tests_smoke.py` SKIPs all three lane suites
on CI. Seven rounds have moved the register **210 → 64**, and every one of those numbers
was enforced by prose in `wip/tasks.md` and a human reading it. A silent regression would
have passed every check this project runs.

`tools/suite/register.json` now holds the measurement, and
`tools/tests/test_register_snapshot.py` replays it — the same trick
`test_profile_auto_resolves_the_lane.py` already uses to get a corpus-dependent fact onto
CI:

```json
{"acts":      {"section_carries_its_body": 15, "no_foreign_section_start_in_body": 10,
               "section_codes_ordered": 4, "no_chapter_caption_in_section_heading": 3,
               "clause_codes_plausible": 1},
 "rules":     {"section_carries_its_body": 17, "no_foreign_section_start_in_body": 9},
 "ordinance": {"section_carries_its_body": 5}}
```

- **corpus absent** → skip, exactly as the lane suites already do, so CI stays green
- **corpus staged** → compare, and fail on any difference **in either direction**

An improvement failing this test is the point. The number then moves deliberately, in the
same PR that moved it, which is the discipline `wip/tasks.md` asks for in prose today.

Two smaller checks come with it, because a snapshot can rot in ways the comparison cannot
see:

- `total` must equal the sum of its own lanes — the write-ups quote the headline, the test
  compares the detail, and nothing else would notice a hand edit moving one and not the
  other.
- every invariant named must exist in that lane's `ALL_INVARIANTS` — a typo would silently
  under-gate, which is the failure `test_suite_exemptions.py` already guards for
  exemptions.

### Verified both ways

Passing is not evidence a gate works. Perturbing the snapshot
(`section_carries_its_body: 15 → 99`) fails the comparison, and clearing the corpus paths
makes it skip while the two structural checks still run — the exact CI shape.

## Why this round exists

Three times in this phase an artifact has failed to report that its source was broken:

| round | artifact | silent for |
|---|---|---|
| 2 | a `known_gaps` skip **inside a check function** | unknown; found by re-measuring |
| 3 | two `exemptions/` entries | until an unrelated change made the runner re-check |
| 7 | `report.md` §5, not regenerated since Phase 0 | **PR #45 → PR #51** |

Round 3's is the instructive one: it is the only artifact of the three that *told us* it
was stale, and the format did that unprompted. This round gives the register the same
property.

## Gates

| gate | result |
|---|---|
| `ruff check` (bare) | clean |
| `pytest tools/tests` | **56 passed, 1 skipped** (was 53) |
| register test, corpus staged | passes |
| register test, corpus absent | skips; the two structural checks still run |
| register test, snapshot perturbed | **fails**, as it must |
| parser changed | no — `packages/` untouched |
| register | 64, unmoved |
