# Round 46 — one clean re-conversion, and the two documents it found

**2026-09-18.** No parser change. `packages/` is byte-identical to `main` at
`34f0453fd498`; the only tracked files this round adds are this artifact, the handover
update, and one gate.

The job was provenance: **21 acts outputs carried `a8a0dffe4bf9-dirty`**, stamped by round
38 from a tree with uncommitted edits, so their stamp records the commit *before* whatever
was being tested and answers nothing. `handover/README.md` had recorded the fix — one clean
77-document re-conversion — and recorded that nothing depended on it. That second half was
wrong, and the run is what proved it.

## What ran

One worktree at `34f0453fd498`, clean (`pipeline_revision()` printed
`34f0453fd498`, no `-dirty`, **before** the first child spawned), corpora bound in by
`CORPUS_ACTS` / `CORPUS_RULES` rather than symlinks, and
`data/corpora/_reconvert/run.py` — the staged-set harness, unchanged except
`max_workers` 4 → 2 for the OOM rule in `working-rules.md`.

| | |
|---|---|
| rules | `staged 11  scanned-skip 0  todo 11` |
| acts | `staged 80  scanned-skip 14  todo 66` |
| total | **77 converted, 0 failures**, 1,162s wall (19m 22s), 975s of child time |

Baseline snapshotted into `output/_pre_46/` for both lanes **before** the first conversion,
91 files, and never written to again.

## The stamps

| lane | before | after |
|---|---|---|
| acts | 29 `a8a0dffe4bf9`, **21 `a8a0dffe4bf9-dirty`**, 15 `d6512faa9a02`, 1 `974029e3c0bf`, 14 none | **66 `34f0453fd498`**, 14 none |
| rules | 9 `a8a0dffe4bf9`, 1 `e6a0bc8059e0`, 1 `fea1cc5bac2c` | **11 `34f0453fd498`** |
| ordinance | 9 `dbcab2f79b78`, 3 `4827840c191f` | unchanged — not in scope |

**`-dirty` is now 0 across all three lanes.** What is still mixed is mixed *for a reason that
is recorded*: the 14 image-backed acts editions and the 3 image-backed ITO editions cannot be
re-converted at all under the standing no-OCR decision, and the 9 ordinance documents run
`fbr_ingest`, which no round since #93-#99 has touched.

## The finding: two Federal Excise editions were never installed

Of the 77, **75 are byte-identical to their baseline** once `pipeline_revision` and
`converted_at` are normalised. Two are not:

| document | `<table>` | `<tr>` | `<p>` | unresolved `<sup class="marker">` |
|---|---|---|---|---|
| The Federal Excise Act, 2005 (As amended up to 11th March 2019 ) | 2 → **5** | 5 → **132** | 704 → 689 | 43 → **6** |
| The Federal Excise Act, 2005 (as amended up to 31st December, 2019) | 3 → **6** | 11 → **92** | 780 → 721 | unchanged |

Leaves, footnote records and bound citations are **unchanged on both** — `class="cite"` is
303 before and 303 after on the 11-March edition, so not one bound citation was lost; the 37
markers that disappeared are the false ones, tariff-cell serials read as citations, exactly
the FS-03 class round 39 measured.

Both were stamped `a8a0dffe4bf9` — **round 38**. The corpus stages **17** Federal Excise
editions; the 2026-09-18 install re-converted **15** (`_pre_45` holds exactly 15 files). So
round 39's tariff-table fix reached 15 of the 17 documents its own census had named, and two
kept serving round 38's prose rendering for the tables. The round-45 note in
`handover/README.md` says "the fifteen staged editions" and never says fifteen of what.

**The claim this round disproves is in the handover's own words:** *"Every staged document's
CONTENT matches `main`, which is why the register snapshot and the pipeline gate both pass."*
The second clause is true and the first did not follow from it. Nothing that reads content
could see this — the two documents were internally consistent, the register was 0, all three
lane suites were green, and both stayed green afterwards (acts 65/65, rules 65/65, ordinance
47/47 + 18 cases). **A re-conversion for provenance is also the only audit of installation the
project has.**

## The gate

`tools/tests/test_corpus_provenance_is_clean.py` — one assertion: no staged output may carry
a `-dirty` revision, in any lane. It skips with no corpus, like the lane suites and
`test_register_snapshot.py`, so CI will skip it too.

It is deliberately **not** "the corpus is at one revision", which can never be true while the
17 image-backed documents exist. Stale is attributable; `-dirty` never is.

Mutation-tested against the real defect rather than a synthetic one — pointed at
`_pre_46/` through `CORPUS_ACTS`, it fails and names all 21; against the corpus as it now
stands it passes:

```
CORPUS_ACTS=<tmp dir whose output/ links to _pre_46>  pytest …test_corpus_provenance_is_clean.py
    1 failed  -- "21 of 80 staged documents were converted from a dirty tree", all 21 named
pytest …test_corpus_provenance_is_clean.py                      (corpus as it now stands)
    1 passed
```

(The `80` is the baseline acts lane alone: run from a worktree, the other two lanes resolve
to the worktree's own empty `data/corpora/`, which is also why this test SKIPS there and
measures only from the tree that holds the corpus.)

## Verification, at this commit

```
run_suite.py acts        ALL PASS | invariants 65/65 | exempt 0 (0 hits)
run_suite.py rules       ALL PASS | invariants 65/65 | exempt 0 (0 hits)
run_suite.py ordinance   ALL PASS | invariants 47/47 | cases 18/18
pytest tools/tests -q    322 passed, 1 skipped
discover_corpus.py --check   no drift
ruff check               All checks passed!
run_tests_smoke.py       Pipeline gate passed (exit 0)
du -sh data/ocr_cache    0B
```

`tools/suite/register.json` is unchanged and needs no update: the register was 0 before and
is 0 after, and neither changed document moved an invariant.

## For the next round

- **`convert_all.py`'s staged-set harness is the only thing that re-converts a whole lane
  correctly, and it is gitignored.** `data/corpora/_reconvert/run.py` has now been the right
  tool three times (rounds 35, 45, 46) and it lives in the corpus, where a fresh clone does
  not get it. Worth promoting into `tools/` the next time someone needs it.
- **Count the population, not the batch.** Round 45 converted "the fifteen staged editions"
  against a census of 17. Whatever a round's census names, install that number and print both.
