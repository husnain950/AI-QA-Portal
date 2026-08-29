# Phase 0 — structure discovery, then the anomaly remediation it reframes

## Why this replaced the previous plan

The previous `wip/plan.md` opened a 157-hit anomaly register and a five-phase
remediation for it. That work is still real and is preserved below as Phase 1. What
changed is the order, and the reason is a measurement.

The pipeline chose its parsing behaviour from **the directory a PDF sat in**:

```
tools/convert.py <lane> <pdf>
  → corpus_registry.CORPORA
  → acts_ingest.run  = partial(legal_ingest.pipeline.run, profile=ACTS)
    rules_ingest.run = partial(legal_ingest.pipeline.run, profile=RULES)
    fbr_ingest.run   = a separate ~3,500-line fork, no Profile at all
```

Three caps, one per folder. Measured over all 190 staged documents, that is wrong on
four independent axes — and several of the register's open hits are symptoms of it,
not defects to patch. Fixing them under the old model would have hard-coded the
model.

`packages/legal_ingest/discover.py`, despite the name, was never schema discovery:
it is a body-driven fallback for editions that print no table of contents.

## What the corpus actually says

Source of truth: `FBR_Document_Inventory.xlsx`, 183 rows, every one present on disk.
Staged corpus after `tools/stage_corpus.py`: **190 documents** (the extra 7 are files
the lanes already held that the inventory does not list).

| Finding | Evidence |
|---|---|
| **Two unrelated instrument kinds shared a lane.** | **36 documents are amending instruments** — 25 in `acts`, 11 in `ordinance`. Their leaves are directives quoting a *different* law. `The Tax Laws (Amendment) Act, 2024` shipped a chapter with `code="PART I"` and heading `"Acts, Ordinances, President's Orders and Regulations"` — the Gazette masthead, parsed as a chapter. |
| **The `ordinance` lane had only ever seen one law.** | 26 of its 42 inventory documents were not staged at all. The 9 flat, TOC-less ICT (Tax on Services) Ordinance editions route to `fbr_ingest`, which has no body-driven fallback and **refuses them outright**: `RuntimeError: TOC parse left 3 section(s) without a chapter container`. Through `legal_ingest` with `--profile auto` the same file converts. The bug was the routing. |
| **Container shape varies inside a lane, and is stable across editions.** | Measured `container_order`: `CPD`/`PCD` (Income Tax Ordinance and Rules), `C` (Customs, Sales Tax, Federal Excise), `CP` (Sales Tax Rules, Customs Rules), flat (ICT Ordinance, the PSW instruments). Customs Act holds CH≈42 / PT=14 / DV=0 across **20 editions, 2007→2025**. |
| **But eras break inside a group.** | Income Tax Ordinance 2001: every edition up to 04.05.2024 measures **25** chapter lines; 30.06.2024 measures **499** and 31.07.2025 / 20.02.2026 measure **513**. The publisher re-typeset it, and the `producer` string at the break is the corrupted `Microsoft® Word 20190㘮`. |

And one negative finding worth as much: **"Finance Acts" is a filing folder, not a
document group.** Twenty files, four container shapes. Grouping by folder name would
have manufactured a family out of a filing convention.

## What shipped

Five families explain all 190 documents, **0 unexplained**:

| # | family | required | n | profile |
|---|---|---|---|---|
| 1 | `unconvertible` | legacy `.doc`/`.docx` | 3 | refused |
| 2 | `urdu` | any Arabic codepoint | 4 | refused (no RTL support) |
| 3 | `no_text_layer` | < 300 chars/page, group cannot supply a family | 30 | refused |
| 4 | `amending` | density ≥ 2.0 **or** ≥ 1 directive heading | 36 | `AMENDING` (new) |
| 5 | `consolidated` | ≥ 2 leaf lines | 117 | `ACTS` \| `RULES` |

Order is significant and is the documented tie-break. What *looks* like a family and
is not: `container_order` and TOC presence are **fields**, because
`calibrate.detect_toc_pages` already returns 0 for a TOC-less document and
`discover.discover_structure` already rebuilds containers from the body. A "flat"
family would have forked a path that works.

`Family` (what the document IS) holds a `Profile` (what its printer does). Those were
conflated; composition separates them in one field.

### Three things deliberately not built

- **A stratified sampler.** A full census over all 190 documents measures **~26 s**.
  A sampler to avoid 26 seconds is more code than it saves, and it would hide exactly
  the edition drift the report exists to show.
- **A clustering algorithm.** 190 points on 20 hand-picked features needs numpy (not
  installed), is threshold-sensitive, and the clusters get hand-labelled anyway.
  Replaced by a `Counter` group-by — 14 keys over this corpus — plus five ordered
  predicates. The group-by is the evidence a human reads; the predicates are what
  code runs.
- **A families JSON schema and loader.** A family carries a `Profile`, and a
  `Profile` is behaviour; this repo's format for behaviour is a frozen dataclass.
  Split on the line the repo already draws: **families in code, measurements in
  JSON** — because the measurements are what must diff on a rerun.

### The two amending-profile changes

`AMENDING` sets `instrument_kind="amending"` and `suppress_front_matter_containers`,
both off for `ACTS`/`RULES` so no existing document changes.
`discover._quoted_container` already rejected containers printed *after* the first
clause; its own docstring named the masthead as the front-matter case it did not
cover. `_front_matter_container` is that case.

`discover_structure` now also takes the profile, because `amending_density` is a good
measure and a poor gate: it is diluted by anything the instrument reproduces at
length, so Finance Act 2022 measures 1.23 against a 2.0 threshold and ledger P14
records Finance Act 2025 at 0.21. `families.classify` reads the whole document and
does not have that blind spot.

### Additive, for the diff/resync work this phase exists not to foreclose

- `metadata.family`, `family_confidence`, and `metadata.amends` — the laws an amending
  instrument changes, read off clause headings that already parse.
- `type` and `node_key` on every container and leaf. `toc.Node.kind` always computed
  the first and `_node_to_dict` always threw it away, so the output used one dict
  shape for a chapter, a schedule part and a section leaf. `node_key` is the ancestor
  chain **by code** (`ch:vii/pt:i/s:114`), sitting beside the positional `source_key`
  that `json_parser._stable_id` mints — so a node inserted above a leaf no longer
  forces every id below it to be re-minted.

### Verified

- All three lane suites measure **exactly** what they measure at `HEAD` — 148 acts,
  90 rules, 5 ordinance — confirmed by stashing the diff and re-running.
- `--profile auto` on Federal Excise Act 2005 (01.07.2017) is identical to lane
  routing once the new keys are removed.
- `discover_corpus.py --check` is byte-stable across reruns and is wired into
  `tools/run_tests_smoke.py`; a missing corpus is a SKIP, as the lane suites already are.
- 13 package self-checks pass, `ruff` clean across `tools/`, `apps/api` and the
  touched `packages/legal_ingest` modules.

---

# Phase 1 — the anomaly register, re-measured

The previous plan's register is **not** discarded. It is re-measured here against the
JSON currently on disk, which is what the numbers below describe.

**243 invariant hits across 37 of 103 converted editions** — higher than the 157 the
old register recorded, because PR #41 landed `no_chapter_caption_in_section_heading`
and tightened `no_footnote_text_in_body`, and because the on-disk JSON predates
several parser fixes.

| Lane | hits | editions affected | converted |
|---|---|---|---|
| acts | 148 | 27 | 80 |
| rules | 90 | 6 | 11 |
| ordinance | 5 | 4 | 12 |

| Invariant | acts | rules | ordinance |
|---|---|---|---|
| `no_footnote_text_in_body` | 109 (20 docs) | — | — |
| `section_carries_its_body` | 26 (9) | 78 (6) | 5 (4) |
| `no_foreign_section_start_in_body` | 9 (9) | 10 (4) | — |
| `no_chapter_caption_in_section_heading` | 3 (3) | 2 (2) | — |
| `clause_codes_plausible` | 1 (1) | — | — |

**Read `no_foreign_section_start_in_body` in the light of Phase 0.** "A leaf contains
the START of another section in its body" is the literal signature of an amending
instrument parsed as a consolidated one: the other section is the one being quoted.
Those 19 hits should be **re-measured after re-conversion under the family profiles**,
not patched.

Phase 1 order:

1. **Rebuild the toolchain.** `.venv` is Python **3.14.7** against a `>=3.12` pin, and
   `numpy` / `rapidocr-onnxruntime` are absent, so no OCR runs. This blocks
   re-converting 30 `no_text_layer` documents *and* several amending ones — Finance
   Act 2023 and The Tax Laws (Amendment) Act 2020 both refuse today with
   `OCR failed on page N: No module named 'numpy'`.
2. **Re-convert all three lanes at one parser revision, with `--profile auto`.**
   Only then are the register's numbers a property of the parser rather than of when
   each file was last converted.
3. **Re-measure**, then classify every surviving hit as fixed or exempted with traced
   evidence (`tools/suite/README.md`). There is no third state.
4. The pipeline→portal transport work from the previous plan — sync, seeding,
   `version_metrics` — is unchanged and follows.

Nothing in Phase 1 needs the discovery stage to change again. That is the point of
running it first.
