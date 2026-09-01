# PR-J — The ordinance lane onto the contract, and the preamble TOC tail gated

Review page: <https://claude.ai/code/artifact/3e33c896-83dc-486e-a926-40384063e1f0>

Closes the largest row in `tasks.md`'s Deferred table, and the pipeline half of **P5**.

Measured on this host, 2026-09-01, from `main` at `4827840` (round 12, #73).

---

## 1. What the ledger said, and what measuring said

| Deferred said | measured |
|---|---|
| "multi-hour, freezes parser work" | **4m41s** for the whole lane (12 documents, 4 workers). The acts lane had converted in 3 minutes on 08-31. Only OCR is slow, and the ordinance pipeline has no OCR stage. |
| "14 stale acts docs, ordinance lane" | the 14 acts documents share **one** blocker, `RuntimeError: OCR failed … No module named 'numpy'`, all dated 2026-08-27. numpy 2.5.1 is installed now. Left out of scope by decision; their own PR. |
| the corpus is `main`'s output | **it was not.** See §2. |

## 2. `main` was one parser round behind its own data — again

All 77 contract-stamped documents on disk carried:

```
pipeline_revision: 7cc5d3431337-dirty      <- HEAD's sha, from a DIRTY tree
converted_at:      2026-08-31T14:xx UTC    (19:xx PKT)
```

and one acts run-log in this tree named `.worktrees/r12/…` as its output path. Round 12
committed at 19:50 PKT and was **PR #73, still open**. The corpus was round-12 output;
`main` was not.

This is P11 repeating, and it is the second time. **#73 was merged first** — it was
`MERGEABLE` / `CLEAN` with four green checks — so the conversion below ran on a tree that
matches the corpus. The ordinance lane now records `pipeline_revision: 4827840c191f`,
with no `-dirty`.

The point worth keeping: nothing but `pipeline_revision` could have told anyone this.
That key exists because of P11, and it earned its place the first time it was read.

## 3. What the conversion did

12 documents, converted with an explicit `-o` at each existing corpus path. `convert-all`
was **not** used: it targets all 46 ordinance PDFs, and 34 of them are not in the corpus —
running it would have added 34 documents to the portal under cover of a re-conversion.

| | before | after |
|---|---|---|
| `contract_version` | 0 / 12 | **12 / 12** |
| `pipeline_revision` | none | **`4827840c191f`**, all 12 |
| nodes with `type` | 0 | **6,941 / 6,941** |
| nodes with `node_key` | 0 | **6,941 / 6,941** |
| leaves with `node_key` | 0 | **4,958 / 4,958** |
| duplicate `node_key` | — | **0** |

`plan.md` §7 named ordinance `node_key` collisions as unmeasured on 11 of 12 documents.
They are measured now: **zero**, across all 6,941 keys.

**Corpus-wide, the identity hole closes from 5,047 leaves (30%) to 89 (0.5%)** — the 89 are
in the 6 pre-Phase-0 acts documents that OCR blocks, which is why the `source_key` bridge
stays load-bearing and stays.

Churn, re-measured on the larger corpus: one inserted leaf per document, across **96
documents / 16,460 leaves** (was 84 / 11,502) — `source_key` reports **422** leaves falsely
"changed", `node_key` reports **0**.

## 4. Nine documents were purely additive. Three were stale output.

The check `plan.md` demanded: strip `type`, `node_key` and the four contract metadata keys
from each new file and compare against the pre-conversion snapshot.

**Nine of twelve are byte-identical.** The conversion adds; it does not parse differently.

**Three are not**, and they are exactly the three whose JSON name never matched its PDF
stem (`Income Tax Ordinance 2001 - amended upto {20.02.2026, 30.06.2024, 31.07.2025}`).
Same structure counts, identical `plain_text` on every leaf and in the preamble; the
difference is `html` on 23 of 528 leaves:

```
-<p><strong>AN</strong></p>                     +<p class="act-title"><strong>AN</strong></p>
-<p>WHEREAS … ; WHEREAS …</p>                   +<p class="recital">WHEREAS …;</p>
                                                +<p class="recital">WHEREAS …</p>
-<sup class="cite" title="">35.3</sup>          +<sup class="marker" data-ref="35.3">3</sup>
```

Those are two **already-merged** fixes these three documents had never received:
`7bb3b71` (gazette preamble HTML) and `700157b` (an empty-title cite is a marker, and
carries `data-ref`). The five classes are `fbr_ingest.GAZETTE_KINDS` — the same five PR-F
found the backend sanitizer was silently discarding at 965 occurrences.

So the corpus held three documents several fixes behind the rest, and **nothing on disk
could have said so** until `pipeline_revision` and `converted_at` existed. That is the
mixed-revision hazard, caught on its first real use, in the lane nobody had looked at.

## 5. Two regression cases were pinned to markup, not to the property they name

Bringing those three documents onto the current parser failed two ordinance cases:

```
qa_preamble_an_standalone        arg: "<p><strong>AN</strong></p>"
qa_preamble_recitals_separate    arg: "<p>WHEREAS"
```

Their descriptions are about structure — *"'AN' renders as its own centred title
paragraph"*, *"the WHEREAS recitals begin their own paragraph"* — but the patterns pin a
`<p>` with no attributes, and the current parser classes those paragraphs. `preamble_matches`
is `re.search`, so both now read `<p[^>]*>`: the paragraph boundary each case actually
asserts, without the attribute neither case mentions. A recital collapsing back into the
long-title paragraph still fails them.

This is a de-pinning, not a weakening. Two lines.

## 6. The new invariant

`inv_preamble_carries_no_toc_tail`, bound in all three lanes.

When the Contents parse overruns, the last rows of the contents listing are glued in front
of the enacting formula, so one node holds both. The portal's answer to this today is worse
than the defect: `json_parser.is_junk_leaf` matches the same column header and **drops the
whole leaf**, so the preamble *and* the enacting formula of four Customs Act editions never
reach a reviewer at all — invisibly to the register, the conservation audits and the
reviewer.

**4 hits: Customs Act 1969, the 2013, 2014, 2015 and 2016 editions. 0 in rules, 0 in
ordinance, and 0 on any non-preamble leaf.**

Made to fail on purpose (`tools/tests/test_preamble_toc_tail.py`, 5 tests): the Customs
shape fires, an html-only header fires, a clean preamble passes, a document with no
preamble passes, and — the one that matters — an addressable `code=Contents` leaf holding a
real contents listing does **not** fire. The invariant is about the preamble, not about the
marker.

The API-side deletion is P5's other half and is a separate PR. **Those four preambles are
still dropped from the reviewer's screen today**; this PR makes the cause countable, not
the symptom fixed.

## 7. The register: 30 → 34, and which half moved it

Reported separately, because a single total misattributes them:

| | acts | rules | ordinance | total |
|---|---|---|---|---|
| committed before | 16 | 9 | 5 | **30** |
| after re-conversion, before the invariant | 16 | 9 | 5 | **30** |
| after the invariant | 20 | 9 | 5 | **34** |

**The re-conversion moved the register by zero.** Twelve documents changed identity
representation and three changed HTML, and not one invariant hit moved — including
`contract_complete`, which stopped early-returning on all 12 and now holds them to the
whole contract. The +4 is the new question being asked, all of it in acts.

Regenerated with `tools/tests/test_register_snapshot.py --write`, the file's own generator,
rather than hand-copied.

## 8. Through the real sync

`sync_corpus.py --only ordinance` — PR-B's migration path running on the lane it was built
for, for the first time:

```
ordinance: validated=12  added=0  updated=12  skipped=0  failed=0  withdrawn=0  problems=[]
```

| | result |
|---|---|
| section ids | **5,951 kept, 0 retired, 0 newly minted** |
| `node_key` backfilled onto existing rows | **5,939 / 5,951** |
| the 12 without one | the synthesised preamble leaf, which has no node in the tree — by design |
| versions per document | 1 → **2**, exactly one new version each |
| documents added | **0** — nothing duplicated |

### The approval resets are the local database, not this change

200 approvals were seeded on ordinance leaves before the sync; 195 survived, **5 reset**,
in 5 different documents — four of them in documents whose JSON was byte-identical. That
looked like a contradiction, so it was tested rather than explained away.

Take an acts document that was **not** re-converted and **not** re-synced, parse its JSON
fresh and compare against its stored rows: **304 of 309 leaves already differ.** This local
development database predates several merged rounds, so *any* re-sync of *any* lane resets
approvals on it. The re-conversion is exonerated; §4's byte-check stands.

Worth carrying: **carryover measured against this database overstates the cost of a sync.**
Production was pushed current at #71 and is the only place that measurement means anything.

## 9. Verification

```
tools/tests            76 passed, 1 skipped
apps/api/backend/tests  519 passed
ruff check              All checks passed        (bare, matches ci.yml)
run_suite acts/rules/ordinance   register 34, matching register.json
data/ocr_cache          0 B                      (unchanged — no OCR in this lane)
```

## 10. What this deliberately did not do

- **The 14 OCR-blocked acts documents.** numpy is installed and they would probably convert,
  but that takes OCR in scope, moves `data/ocr_cache` off 0 B, and can route a sub-floor
  scan into `_provisional/` — which under PR-C's withdrawal removes it from the portal. Own
  PR, with the cache and the fidelity floor measured on purpose.
- **Deleting the `source_key` bridge.** 89 leaves in 6 documents still have no `node_key`.
  It stays load-bearing until those 14 convert.
- **`is_junk_leaf` / `normalize_heading`.** P5's API half. Separate PR; §6 is its
  pipeline-side gate.
- **Production.** Not deployed. `make backup-remote` → `push_corpus --dry-run` → read the
  diff → push is PR-D's order of operations and needs a decision, not an assumption.
