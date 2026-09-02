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

**34 invariant hits across 103 converted editions**, measured 2026-09-02 after round 13.
210 → 193 → 148 → 92 → 78 → 75 → 70 → 64 → 50 → 44 → 33 → 30 → 30 → **34** → 34. The acts
lane holds 80 documents.

The +4 is not a regression. PR #74 added `preamble_carries_no_toc_tail`, a NEW question
about a defect that was already there: four Customs Act editions print the tail of their
Contents page in front of the enacting formula. It is counted here because the pipeline
owns the cause; the portal's half of it (`is_junk_leaf` dropping the whole leaf) closed
separately in #75.

Rounds 12 and 13 each moved the register by **zero, deliberately**, and each closed a
defect class no invariant could see:

- Round 12 — 31 headings carrying their own code tail, 15 documents, 2 lanes. The
  heading stripper never read the `code` argument it was handed.
  `wip/phase3-round12-body-heading-code.md`.
- Round 13 — 175 chapter headings swallowed into the preceding section's body, 21
  documents, 2 lanes. `grammar.CHAPTER_RE` spells the keyword/numeral separator
  `[\s\-]+`; `builder._STRUCTURAL_RE` and the suite's `_STRUCT_LINE` both spelled it
  `\s+`, so `Chapter-II` was not a boundary and the invariant written to catch exactly
  that was blind for the same reason. `wip/phase3-round13-chapter-hyphen.md`.

In both, the invariant that can see the class ships closed at 0 in the same PR.

| Lane | hits | editions affected | converted | of source files |
|---|---|---|---|---|
| acts | 20 | 16 | **80** | 93 |
| rules | 9 | 4 | **11** | **48** |
| ordinance | 5 | 4 | 12 | 46 |

**Read the last column before the first.** The rules lane still converts 11 of 48
documents — the other 36 are scans and one is Urdu, and this round of work skipped every
scan in the corpus by instruction. The acts lane has the same shape at smaller scale: 25
editions carrying 2,065 image-backed pages.

| Invariant | acts | rules | ordinance | total |
|---|---|---|---|---|
| `section_carries_its_body` | 8 (6) | 8 (4) | 5 (4) | **21** |
| `no_chapter_caption_in_section_heading` | 4 (4) | — | — | **4** |
| `preamble_carries_no_toc_tail` | 4 (4) | — | — | **4** |
| `section_codes_ordered` | 3 (2) | — | — | **3** |
| `no_foreign_section_start_in_body` | — | 1 (1) | — | **1** |
| `clause_codes_plausible` | 1 (1) | — | — | 1 |
| `structure_counts` | — | — | — | **0** |
| `no_footnote_text_in_body` | — | — | — | **0** |
| `no_code_fragment_in_section_heading` | 0 (was 14) | 0 (was 17) | — | **0** |
| `no_structural_heading_in_body` | 0 (was 171) | 0 (was 4) | 0 | **0** |

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

Re-derived from the live register after round 13, not carried forward. The counts
below are hits; the parenthesised number is documents.

1. **`section_carries_its_body` (21)** — still the largest class, and it is now four
   unrelated causes rather than one:
   - **omission spellings the invariant cannot read (2, acts).** Customs 30.06.2024
     s.196K prints `to Omitted 96u`, and 30.06.2025 s.79 prints `A O mitted` — an
     intra-word space round 3 measured and refused to admit for a regex whose job is
     precision. Worth re-measuring now the count is small enough to trace individually.
   - **the STSP 58U/58V pair (4, rules).** The same two rules in both Sales Tax Special
     Procedures Rules 2007 editions — one cause, two editions.
   - **the round-10 residue (3, rules).** Sales Tax Rules 01-01-2025, each already
     traced to a printed defect: 44A opens with a left double quote, 150ZQZI is printed
     `150ZQZl`, and 150W's code appears only in a footnote.
   - **the ordinance five**, which live in the `fbr_ingest` fork and are sequenced after
     the Phase 4 decision on it.
   The remainder are single documents: the Pakistan Single Window Act's ministry list
   read as sections 27/28, PFMA 2019 s.26, Sales Tax 2014 s.10 (`R(cid:2)fund`).
2. **The heading-terminator scan that walks through a boundary (3 hits, acts).**
   `builder._find_heading_split` looks up to four lines ahead for a heading terminator
   and stops at a grid table but not at a structural heading, so an omitted section
   borrows the next section's terminator and its heading comes out
   `*** Chapter-VII OFFENCES AND PENALTIES 33. Offences and penalties`. This is the whole
   of `no_chapter_caption_in_section_heading`'s 32AA cluster across three Sales Tax
   editions. Round 13 traced it and measured the obvious guard as **losing section 32AA
   outright** (127 leaves → 126): an omitted section has no terminator of its own, so
   refusing the borrowed one leaves nothing to open it with. Needs an omission-aware
   fallback. `wip/phase3-round13-chapter-hyphen.md`.
3. **`preamble_carries_no_toc_tail` (4, acts)** — the preamble begins on the last
   Contents page. `pipeline.py`'s H5 comment already records the cost it accepted
   ("one extra front-matter page into the preamble on 9, repairs 4, loses nothing"), so
   the trim belongs where the front matter lands, not at the page boundary. **The
   invariant undercounts**: it keys on the column header `Section Page No.`, which is one
   spelling of the defect — 6 of the 20 Customs editions are affected, including 2008
   (contents rows, no column header) and 2007 (a bare roman folio `(xxii)`).
4. **The container-code guard**, which two independent measurements now argue for: a
   `PART-N` line should be a boundary only where the enclosing chapter actually holds a
   part with that code. It is what makes the PART separator widening safe (14 real
   boundaries against 6 annexure-form losses), and it is what would have kept round 13
   from dropping four chapter captions in Customs Rules 2001, whose tree cannot express
   them. Needs `build_sections` to pass per-chapter container codes into `_build_one`.
5. **The CHAPTER letter suffix (57 hits, 24 documents)** — `_STRUCTURAL_RE`'s CHAPTER
   branch has no suffix class where PART and Division beside it both do, so
   `CHAPTER XVI-A` sits in section 155's body in twenty Customs editions. Measured and
   held out of round 13 because twenty of the twenty-four are the Customs editions whose
   chapter tree rounds 1 and 6 rebuilt. Pinned by a test that fails when it lands.
6. **`section_codes_ordered` (3)** — Customs 2025 `'9' after '119'`, Sales Tax 2014
   `'3' after '32AA'` and `'22' after '75'`. Untraced.
7. **`clause_codes_plausible` (1, Finance Act 2024).** The jump `7->8517` is an HS tariff
   heading read from a **table row**; the check excludes schedules but not table-derived
   codes (ledger P06). Do not weaken it.
8. **No invariant can see a document that lost 93% of its sections.** Round 11's document
   gained 118 sections while the register moved 3. What would catch it is a CROSS-EDITION
   fact, and invariants run per document: `runner.run` is handed one `doc` with no lane,
   no path and no siblings. The join exists — `signatures.json`'s `group` key matches
   `metadata.filename` on 80/80 acts documents — but its counts are PDF-regex
   measurements, not tree counts, so a real parse-quality comparison needs a new
   per-group index over `output/*.json`.

Every hit ends **fixed** or **exempted with traced evidence** in
`tools/suite/exemptions/<lane>.json` (`tools/suite/README.md`). There is no third state.

## And what Phase 2 still owes, unchanged

61 scanned documents, 2,456 OCR pages — of which **35 documents need ≤ 10 pages each**,
172 pages in total. Finance Acts 2022 and 2023 are one page each. The
`--admit-below-floor` rebuild of the 9 provisional acts documents waits on the same
thing, and the ordinance lane's other 10 text-layer documents wait on the Phase 4
`fbr_ingest` decision.

**Phase 4 —** flip `--profile auto` to the default and decide `fbr_ingest`. The
pipeline→portal transport work is **no longer open**: it ran as its own track in
`wip/integration/` (PRs #59–#76), which closed every problem in that plan's §3 — the
output contract, positional leaf identity, withdrawal, the two ingest paths, the
sanitizer, stale review state, and the CI gate at the corpus interface. PR-J (#74) took
the ordinance lane onto the contract: 12/12 documents carrying `contract_version`, 6,941
nodes typed and keyed, and the corpus-wide identity hole 5,047 leaves (30%) → 89 (0.5%).
The Phase 4 bullet below describing that lane as blocked predates it.

Nothing in Phases 3–4 needs the discovery stage to change again. That is the point of
running it first.
