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

# Phase 3 — the anomaly register, in progress

*(Numbered to match `wip/tasks.md`, which is the executable checklist. Round 1 is written
up in `wip/phase3-chapter-numerals.md`; the Phase 2 run that produced the baseline is in
`wip/phase2-run.md`.)*

**30 invariant hits across 103 converted editions**, measured 2026-08-30 after round 11.
210 → 193 → 148 → 92 → 78 → 75 → 70 → 64 → 50 → 44 → 33 → 30. The acts lane holds 80
documents.

| Lane | hits | editions affected | converted | of source files |
|---|---|---|---|---|
| acts | 16 | 12 | **80** | 93 |
| rules | 9 | 4 | **11** | **48** |
| ordinance | 5 | 4 | 12 | 46 |

**Read the last column before the first.** The rules lane still converts 11 of 48
documents — the other 36 are scans and one is Urdu, and this round of work skipped every
scan in the corpus by instruction. The acts lane has the same shape at smaller scale: 25
editions carrying 2,065 image-backed pages.

| Invariant | acts | rules | ordinance | total |
|---|---|---|---|---|
| `section_carries_its_body` | 8 (6) | 8 (4) | 5 (4) | **21** |
| `no_foreign_section_start_in_body` | — | 1 (1) | — | **1** |
| `section_codes_ordered` | 4 (3) | — | — | **4** |
| `structure_counts` | — | — | — | **0** |
| `no_chapter_caption_in_section_heading` | 3 (3) | — | — | **3** |
| `clause_codes_plausible` | 1 (1) | — | — | 1 |
| `no_footnote_text_in_body` | — | — | — | **0** |

## What round 1 closed, and what it taught

`body_chapters_in_tree` is gone — 21 hits, two causes, one class. **The body scan, the
tree and the invariant were each reading a chapter numeral differently**, and the three
symptoms looked unrelated until they were traced:

- A heading printed `4 [Chapter-I` — footnote marker in front of the amendment bracket —
  was invisible to the body scan, so two Sales Tax Act editions had parentless sections
  and **refused to convert at all**. The fix reads the line through the stripper that
  `is_structural_boundary`, called three lines below in the same function, already used.
- `CHAPTER 1` (Arabic, page 23 of the Customs Act) matched no roman `I`, so a second,
  empty PRELIMINARY chapter was inserted in 19 editions — the reason they all read 23
  chapters against a contents page saying 22.
- The invariant's own two normalisers disagreed with each other.

Two lessons worth carrying into the remaining classes:

1. **Measure the invariant fix and the parser fix separately.** On identical JSON the
   invariant fix alone is 210 → 189; the parser fix then reads 189 → 193, and every one
   of those four is either a document that did not exist before (the two restored
   editions, 2 hits each) or a defect newly *visible* (`CHAPTER XIV-AC`). A single total
   would have hidden all of that.
2. **The obvious generalisation was wrong.** Matching numerals by value collapses `XIVA`
   and `XIV-A`, which are two different chapters of Sales Tax Rules 2006 — a fact
   `structure_counts` already had a comment about. The corpus, and the comments already
   in the code, are where a fix gets checked before it is measured.

## Order for what remains

1. **`section_carries_its_body` (111)** — the largest class. Round 2's triage
   decomposed it from measurement rather than assumption: **48** are the two compilations
   (Customs Rules 2001 and Federal Excise Rules 2005), whose cause is already traced and
   accepted for three sibling invariants; **14** are one printed defect — the text layer
   splits the code, `150 ZQR.` for `150ZQR`, so `_candidate_code` returns `None` for a
   whole 18-section run; **8** are omissions the invariant fails to recognise (an
   ellipsis `2[15. ... ]`, and `(cid:N)` corruption); the remaining ~41 are real zoning
   misses and one untriaged group.
2. **`no_foreign_section_start_in_body` (20)** — the mirror of class 1: the invariant only
   fires when the victim leaf is itself heading-only, so these move with the start-detection
   fixes rather than separately.
3. ~~`no_footnote_text_in_body`~~ — **closed in round 2.**
4. ~~`structure_counts`~~ — **closed in round 6.** The parser sorted chapters by a numeral
   value that sums a suffix's letters, so `XIV-AB`, `XIV-BA` and `XIV-C` all collided at
   14.03. A suffix is alphabetical, not additive.
5. **`section_codes_ordered` (7)** and **`no_chapter_caption_in_section_heading` (5)** —
   one cause: an omitted-section placeholder lands at a tree position matching neither its
   code nor its page, and its segment then runs on into the next chapter heading.
5. `no_chapter_caption_in_section_heading` (4), `clause_codes_plausible` (1).

Every hit ends **fixed** or **exempted with traced evidence** in
`tools/suite/exemptions/<lane>.json` (`tools/suite/README.md`). There is no third state.

## And what Phase 2 still owes, unchanged

61 scanned documents, 2,456 OCR pages — of which **35 documents need ≤ 10 pages each**,
172 pages in total. Finance Acts 2022 and 2023 are one page each. The
`--admit-below-floor` rebuild of the 9 provisional acts documents waits on the same
thing, and the ordinance lane's other 10 text-layer documents wait on the Phase 4
`fbr_ingest` decision.

**Phase 4 —** flip `--profile auto` to the default, decide `fbr_ingest`, and the
pipeline→portal transport work — sync, seeding, `version_metrics` — unchanged.

Nothing in Phases 3–4 needs the discovery stage to change again. That is the point of
running it first.
