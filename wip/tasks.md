# Remediation tasks

Executable checklist for [`wip/plan.md`](./plan.md). Dependency order — do not start a
phase until the one above it passes its gate.

Baseline: `main` at `942db87` (PR #45). Every count below was measured on 2026-08-29
with `python tools/run_suite.py <lane>` and `python tools/discover_corpus.py` against
the corpus staged on this machine — the Phase 3 register **after** the Phase 2 run.

Rules of engagement, unchanged:
- Never commit to `main`. One branch and one PR per phase.
- Every parser fix ships with its locking case or invariant **in the same PR**.
- An anomaly is closed only when it is **fixed** or **exempted with traced evidence**.
  There is no third state; "tracked and deferred" without an exemption entry is a red gate.
- Re-measure after every phase. Numbers here are a snapshot, not a promise.

---

## Phase 0 — structure discovery — **DONE**
Branch: `feat/phase0-structure-discovery`

- [x] Stage the full inventory — `tools/stage_corpus.py --from "<FBR repo root>"`
      — 33 documents copied, **190 staged**, 26 of them the Ordinance documents that
        had never been staged at all
- [x] `packages/legal_ingest/signature.py` — text-only structural measurement, 20 fields
- [x] `packages/legal_ingest/families.py` — 5 ordered families, confidence, group inheritance
- [x] `packages/legal_ingest/profiles.py` — `AMENDING`, and the docstring claiming Acts
      and Rules are "the same family of document" corrected
- [x] `packages/legal_ingest/discover.py` — `_front_matter_container`; profile-supplied
      `is_amendment`
- [x] `packages/legal_ingest/pipeline.py` — `profile=None` → classify; `metadata.family`
      / `family_confidence` / `amends`; `type` + `node_key` on every node
- [x] `tools/convert.py --profile auto`
- [x] `tools/discovery/{signatures.json, report.md, unexplained.json}` committed
- [x] `tools/run_tests_smoke.py` runs `discover_corpus --check` (SKIP with no corpus)

**Gate — all met:**
`discover_corpus --assert` → 190 documents, 0 problems ·
`--check` → no drift ·
`--reconcile` → every inventory document is staged ·
13 package self-checks pass ·
`ruff check tools/ apps/api packages/legal_ingest/{signature,families,pipeline,profiles,discover}.py` clean ·
all three lane suites measure **exactly** their `HEAD` numbers (verified by stashing the diff)

### What discovery found

| family | n | parseable |
|---|---|---|
| consolidated | 117 | yes |
| amending | 36 | yes — **new** |
| no_text_layer | 30 | no |
| urdu | 4 | no |
| unconvertible | 3 | no |
| **unexplained** | **0** | — |

- 58 document groups; **5 span more than one family**
- 9 scans placed by group inheritance (only where every measured edition agrees)
- 29 parseable documents flagged low-confidence — they parse, and they are listed
- **73 of 190 documents route differently** under `--profile auto`: 36 amending
  (25 acts + 11 ordinance), 37 refused rather than mis-parsed

---

## Phase 1 — rebuild the toolchain — **DONE**
Branch: `fix/local-stack-and-toolchain`

- [x] Rebuild `.venv` on the pinned interpreter — **3.14.7 → 3.12.13**
      (`/opt/homebrew/bin/python3.12`), the version `pyproject.toml` pins and
      CI and the container already run
- [x] Install pipeline + OCR extras — 58 packages
      — **every OCR pin resolved unchanged on cp312**: `numpy 2.5.1`,
        `onnxruntime 1.28.0`, `rapidocr-onnxruntime 1.2.3`, `opencv-python 5.0.0.93`,
        `pyclipper 1.4.0`, `shapely 2.1.2`. Nothing had to move, so no re-pin and no
        `ocr_review.py` run was owed
- [x] `packages/legal_ingest/requirements-ocr.txt` header corrected — the pins said
      they were measured on Python 3.13; they are now measured on the 3.12 that
      everything else runs
- [x] `tools/convert_all.py --profile {lane,auto}` — see *What Phase 1 also had to fix*
- [ ] Rebuild api/worker images — **not attempted, and not needed this round.** The
      Docker daemon is down on this host; nothing in Phase 1 or Phase 2 needs the
      containers. Left for whenever the portal side resumes.

**Gate:**
`.venv/bin/python --version` → **3.12.13** ·
`import numpy, onnxruntime, rapidocr_onnxruntime` clean ·
`tesseract --version` still **5.5.2 / leptonica 1.87.0**, `pdftotext 26.08.0` ·
`tools/discover_corpus.py --check` → **no drift** across the interpreter change ·
all three lane suites re-measured at **exactly** their pre-rebuild numbers —
acts **148**, rules **90**, ordinance **5** ·
`ruff check apps/api tools` clean ·
`pytest tools/tests` → **48 passed** (46 + the 2 new)

**Two things the gate could not clear, both pre-existing and both recorded rather
than papered over:**

- `make test-api` cannot run here: the Docker daemon is down, so all 445 errors are
  the same `connection to server at "127.0.0.1", port 5432 ... Connection refused`.
  Not a rebuild regression — no test failed for a code reason.
- `tools/tests/test_heading_leak_class.py::test_scan_heading_leaks_skips_without_corpus`
  asserts `main(["acts"]) == 0`, which is only true **where the corpus is absent**.
  With the corpus staged, `scan_heading_leaks` correctly finds 144 hits across 80
  files and returns non-zero, so the test fails. It is green on CI and red on any
  developer machine that actually has the corpus — the exact inversion this project
  already knows about. Fixing it is not Phase 1's job; it is logged here so the next
  person does not read it as a rebuild break.

### What Phase 1 also had to fix

Phase 2 was unrunnable as written, and one of the two reasons could have destroyed
data.

- **`tools/convert_all.py` had no `--profile`.** It hardcoded the child command
  (`convert.py <lane> <pdf> -o <dest>`), and it is the only practical way to convert
  168 source files. `--profile auto` existed on `tools/convert.py` only, which
  converts one PDF. **Fixed:** the flag is threaded through `convert()` the same way
  `--admit-below-floor` already was.
- **`--profile auto` on the `ordinance` lane would have emptied it.** That lane maps
  to `fbr_ingest`, whose `run` takes no profile, so `convert.py` exits 2 on each of
  its 45 files. That is not an `_is_env_failure`, so `_quarantine` would have moved
  **all 12 existing ordinance JSONs** out of `output/` — a flag typo costing a lane.
  **Fixed:** one guard in `main()`, before any file is touched, asking the pipeline
  the same question `convert.py` asks. Locked by
  `tools/tests/test_convert_all_profile.py`, which fails if either half is removed.

Nothing was converted this round, by decision. `data/corpora/` is byte-identical.

---

## Phase 2 — re-convert the lanes that can take a profile — **DONE for the text-layer half**
Branch: `fix/phase2-reconvert-text-layer`

Run and findings: [`wip/phase2-run.md`](./phase2-run.md).

**Scope taken, by instruction: every document that needs no OCR, in all three lanes.**
The 61 scanned documents (2,456 pages, `data/ocr_cache` still 0 B) were skipped with
`convert_all.py --skip-scanned`, which uses the exact per-page census rather than the
8-page sample. The corpus is therefore at **two** parser revisions and the register
below is a mixed-revision measurement.

- [x] **Fix `--profile auto` before paying for any OCR.** `families.py` hardcoded
      `consolidated → ACTS`; the family's profile is now an OVERRIDE and only
      `amending` names one, so the lane's binding survives. Refusal moved to
      `Family.parseable`, which is what `profile=None` had been doubling as. Locked by
      `tools/tests/test_profile_auto_resolves_the_lane.py`, which asserts the
      resolution over every record in the committed `signatures.json` — no corpus
      needed, so it runs on CI.
- [x] **Widen `do_verify_lanes`** — compares the RESOLVED profile now. With the
      hardcode restored it reports 34 rules + 22 ordinance documents routing
      differently; fixed, 73 of 190, unchanged from Phase 0.
- [x] **Back up the JSON, not the database.** 103 files snapshotted to
      `output/_pre_phase2/` on all three lanes before anything ran.
- [x] **Rules** — `convert_all.py rules --profile auto --skip-scanned`. 11 converted,
      1 refused (the Urdu edition, for a family reason). Zero new documents: the 36
      the numpy fix unblocked are exactly the scans this run skips. All 11 changed —
      Customs Rules 2001 went 1 → 15 chapters — and none of it is the profile:
      `--profile lane` at this revision is byte-identical bar the two family keys.
- [x] **Acts** — `convert_all.py acts --profile auto --skip-scanned`. 64 converted,
      4 refused, 80 → **78**. Seven amending instruments now carry
      `instrument_kind="amending"`; 18 more are behind OCR, two of them behind a
      single page each.
- [x] **Ordinance, best-effort** at the lane profile (it takes no profile at all).
      9 converted, 10 refused — 9 of those the ICT editions with the exact refusal
      Phase 0 measured. No new documents. The 9 hand-named duplicates the run created
      were retired against `metadata.filename` after the run, never before.
- [x] `discover_corpus.py --write` not needed: `--check` reports **no drift**, which
      is what finding 3 predicted (OCR never writes back into a PDF, and no OCR ran).
- [x] Re-measured all three suites; the register below is rewritten from that run.

**Gate — met:** `--profile auto` resolves RULES for a rules document, locked by a test ·
every source document either converts or is refused with a reason, and **no refusal
reason is an `ImportError`** · `signatures.json` diff empty · `--check` clean ·
`data/ocr_cache` 0 B.

**Not met, and named rather than hidden:** the acts lane lost two documents. Not the
80 → 78 finding 2 predicted — those two `no_text_layer` documents are scans and were
never attempted — but `Sales Tax Act,1990 as amended up to 30.06.2020` and
`The Sales Tax Act, 1990 (as amended up to 31st December, 2019)`, which the CURRENT
parser refuses (`TOC parse left 2 section(s) without a chapter container`) and an older
one converted. Controlled: `--profile lane` raises the identical error, so this is
parser drift, not the profile. Phase 3 item.

### What Phase 2 still owes — the OCR half

- [ ] **61 scanned documents, 2,456 OCR pages.** There is a cheap tail worth deciding
      on rather than inheriting: **35 documents need ≤ 10 pages each, 172 pages
      total** (~15 min at the measured 0.2 pg/s), including Finance Act 2022 and 2023
      at **one page each**. At ≤ 30 pages it is 50 documents / 504 pages. The
      remainder is the marathon: Finance Act 2017-18 (683), 2025 (290), 2015 (236),
      2016-17 (215), 2014 (148), 2020 (140).
- [ ] **Rebuild the 9 provisional acts documents** with `--admit-below-floor`. All are
      scans; the pass means nothing until OCR runs.
- [ ] The **ordinance lane's other 10 text-layer documents** need the Phase 4
      `fbr_ingest` decision, not a re-run.

---

## Phase 3 — the anomaly register
Branch: one per invariant class

**50 hits across 103 converted editions**, re-measured 2026-08-30 after round 8.
210 → 193 → 148 → 92 → 78 → 75 → 70 → 64 → 50. Documents held: acts 80, rules 11,
ordinance 12.

Round 1: [`wip/phase3-chapter-numerals.md`](./phase3-chapter-numerals.md) — chapter
numerals, read the same way in the body scan, the tree and the invariant.
Round 2: [`wip/phase3-legal-reference.md`](./phase3-legal-reference.md) — the apparatus
caption, which was never in a body at all.
Round 3: [`wip/phase3-omissions-and-compilations.md`](./phase3-omissions-and-compilations.md)
— an unreadable glyph, and two documents that are not one instrument each.
Round 4: [`wip/phase3-split-codes.md`](./phase3-split-codes.md) — the text layer splits a
code, and a measured note that had gone out of date.
Round 5: [`wip/phase3-toc-furniture.md`](./phase3-toc-furniture.md) — the contents page's
own running title, read as a chapter.
Round 6: [`wip/phase3-chapter-order.md`](./phase3-chapter-order.md) — a part is not a
chapter, and a suffix is not a sum.
Round 7: [`wip/phase3-parenting-and-marker-runs.md`](./phase3-parenting-and-marker-runs.md)
— parented by where its code is printed, not by where it is.
Interlude: [`wip/phase3-gate-the-register.md`](./phase3-gate-the-register.md) — the register
is now committed and gated, and `make check` lints what CI lints.
Round 8: [`wip/phase3-omission-mirror.md`](./phase3-omission-mirror.md) — a repealed section
has nothing left to steal.

**Picking this up cold?** [`wip/HANDOVER.md`](./HANDOVER.md) has the full state: what
landed, the 16 open items with their traced leads, and the working rules learned the hard
way (never edit `packages/` mid-conversion; measure invariant and parser separately).

| Invariant | acts | rules | ordinance | total | was |
|---|---|---|---|---|---|
| `section_carries_its_body` | 15 (8) | 17 (4) | 5 (4) | 37 | 37 |
| `no_foreign_section_start_in_body` | 2 (2) | 3 (1) | — | **5** | 19 |
| `section_codes_ordered` | 4 (3) | — | — | 4 | 4 |
| `no_chapter_caption_in_section_heading` | 3 (3) | — | — | 3 | 3 |
| `clause_codes_plausible` | 1 (1) | — | — | 1 | 1 |
| `structure_counts` | — | — | — | **0** | 0 |
| `no_footnote_text_in_body` | — | — | — | **0** | 0 |
| `body_chapters_in_tree` | — | — | — | **0** | 0 |
| **per lane** | **25** | **20** | **5** | **50** | 64 |

`no_chapter_caption_in_section_heading` gains one because round 4 made it visible: with
rule 150ZQZA finally binding, its heading is readable, and it is a FALSE positive — the
source prints that section's own title in capitals. Round 5 fixes the invariant.

48 of the `section_carries_its_body` drop is two compilations moved to
`tools/suite/exemptions/rules.json` on evidence already accepted for sibling invariants;
8 is the invariant learning to read `Omitte(cid:2)d`. The exemptions still run and still
print their hit counts — an exemption documents a failure, it does not hide its size.

Still a mixed-revision measurement: 61 scanned documents keep whatever revision last
wrote them, and the rules column is measured over 11 of that lane's 48 documents.

- [x] **Two Sales Tax Act editions the parser refused** — the 30.06.2020 and 31.12.2019
      editions print their first chapter as `4 [Chapter-I`, a footnote marker in front of
      the amendment bracket, so `CHAPTER_RE` missed it while `Chapter-II`…`Chapter-X`
      matched. Sections 1 and 2 were parentless and the document refused outright.
      `body_chapter_entries` now reads its line through `_STRUCT_DECOR_RE`, the same
      stripper `is_structural_boundary` — called three lines below it — already uses.
      **acts 78 → 80.**
- [x] **`body_chapters_in_tree` (21) — both causes closed.**
      *Acts (19):* the Customs Act 1969 prints `CHAPTER 1` in Arabic on page 23 and roman
      elsewhere, so `insert_missing_body_chapters` inserted a second, EMPTY chapter beside
      the real one — and reported 23 chapters against a contents page saying 22. Numerals
      now match across the notation gap only; `XIVA` and `XIV-A` stay two chapters, with a
      case that fails if that guard is removed. **Every Customs edition now reads 22.**
      *Rules (2):* `_tree_chapter_numeral` and `_norm_body_numeral` normalised the two
      sides of one comparison differently. Replaced by a single `_numeral_key`, −27 lines.
      Measured on identical JSON, that alone is 210 → 189.
- [x] **`section_carries_its_body` — the traced half. 111 → 55, no parser change.**
      `(cid:N)` is a glyph whose font subset has no ToUnicode entry, and it is
      **unrecoverable**: the Sales Tax Act 2014 producer emitted dozens of LinuxLibertine
      subsets whose glyph `<02>` maps to a different character in each (`r`, `8`, `4`,
      `l`), and the ones that print `(cid:2)` are exactly those missing that entry.
      `_is_omission` now drops it before matching, so `Omitte(cid:2)d` reads as the
      omission it is — **111 → 103**. Two further widenings were measured and rejected: a
      dot-run marker buys **zero** (those leaves are already caught by their heading), and
      intra-word spacing buys **one**, for a regex whose job is precision.
      48 more are two compilations — Customs Rules 2001 (44 index rows) and Federal Excise
      Rules 2005 (4 rows of a second instrument starting at PDF page 75) — exempted on the
      evidence their sibling invariants already carry.
      Adding those entries made the runner re-check the rest and report **two existing
      exemptions as stale** (`no_orphan_marker_li`, and Federal Excise's own
      `section_codes_ordered`); both deleted. All three lanes now report **0 stale**.
- [x] **The split code — 14 hits, and a measured note that had expired.** The text layer
      prints `150 ZQR.` for `150ZQR`, so `_candidate_code` returned `None` for an entire
      18-rule chapter. `_DOTSUFFIX_RE` already reads a split suffix but is bracket-gated,
      with a `ponytail:` note saying all 146 unbracketed instances were tariff rows —
      *"widen only if that changes"*. Re-measured over 186,984 lines: **it has changed.**
      Dropping the gate outright still gains 392 tariff rows, so the gate stays and a
      second, narrower unbracketed branch is added beside it: mandatory trailing dot,
      hyphen-or-space separator but never a dot, and 2–4 letters but never a lone capital.
      **48 gained, 0 lost**, each narrowing locked by a case that fails without it.
      Honest caveat: the acts lane did **not** move. 32 of the 48 gained lines were
      hyphenated Customs sections already binding by another route — lines newly matched
      is not the same measurement as sections newly bound.
- [ ] **`section_carries_its_body` — the remaining 37.** ~24 real zoning misses scattered
      1–2 per edition; 3 a TOC row bound as body; 5 ordinance (`fbr_ingest`, sequenced
      after the Phase 4 decision on that fork); the rest untriaged.
- [x] **`no_footnote_text_in_body` (45) — closed, and none of it was in a body.**
      All 45 hits were the string `LEGAL REFERENCE` inside a citation tooltip's `title=`
      attribute; the invariant searched raw markup, so an attribute counted as body text.
      Zero appeared in rendered text. Stripping tags first is **193 → 148 on identical
      JSON**.
      Behind the false positive, a real defect it was not measuring: `build_page_model`
      moved the apparatus caption out of the body into `footnote_lines`, where it lands
      *before* the first marker — and a pre-marker line is by definition a continuation,
      so it came back as `^cont` and was spliced onto the previous page's last note.
      **473 footnote texts across 20 Customs editions.** The caption belongs in neither
      zone and is now dropped from both (`_drop_apparatus_captions`).
      The first version of the fix guarded `parse_footnotes` instead and left the caption
      in `footnote_lines`; `audit_completeness.py` compares that against the output's
      footnote texts and correctly read it as **48 lost words per edition**. Dropping one
      layer earlier keeps conservation at 100.000% on both sides.
      Also deleted a hardcoded `known_gaps` skip inside the check (Income Tax Ordinance
      11.03.2019, Division XXI) — re-measured as **stale**, matching no branch of the
      invariant before or after. A skip buried in a function cannot report itself stale;
      an `exemptions/` entry does.
- [x] **`no_foreign_section_start_in_body` 19 → 5 — the pair disagreed with itself.**
      Ten hits had a victim that is a REPEALED section: Customs s.20 reads
      `15[20. 112[Omitted]` in seven editions while s.2 prints the amendment marker in
      `such other 20[officers of Customs as may be notified by the Board;]`, plus Sales Tax
      s.3A, s.42 and Sales Tax Rules 14A. `section_carries_its_body` has skipped omissions
      since it was written; its documented mirror never asked, so one half of the pair
      reported what the other half had already dismissed. One guard, reusing the same
      `_is_omission` predicate — **64 → 54 on identical JSON, no re-conversion.**
      Four more were the mirror of an exemption that was never written down: the same two
      compilations round 3 exempted for `section_carries_its_body`, firing here from the
      same index rows (`'7. Jurisdiction ______'`, `'15.06.2002.'`, and Federal Excise's
      page-75 second instrument). Same traced evidence, same Phase 5 deletion condition —
      **54 → 50.**
      The amending hypothesis stays falsified for every document we can measure; it may
      still hold for the 18 amending instruments behind OCR.
      The five survivors are all real: Sales Tax 15.9.2021 s.3B (the cursor cascade), Sales
      Tax 30.06.2021 s.30 (a TOC row bound as a body) and three in Sales Tax Rules
      01-01-2025 (footnote text read as a section start).
- [x] **`register.json` has a generator.** Seven rounds hand-copied the `FAIL (n)` counts.
      `test_register_snapshot.py` already had `_measure()`; the generator is the test read
      backwards — `python tools/tests/test_register_snapshot.py --write`.
- [x] **`structure_counts` (5 → 0) — two fixes, and only the second moved the number.**
      *A part is not a chapter.* `PART_RE` required the numeral to end the line, so
      `PART-II ATTACHMENT AND SALE OF MOVABLE PROPERTY ..... 73` fell through to the caption
      branch and opened a chapter, lifting 64 rules out of CHAPTER XI. Two measured
      narrowings: the caption group needs `(?-i:…)` (unscoped it matches
      `Part 1 of Second China Overseas Ports` and 47 schedule rows), and a caption is only
      accepted when leaders or a folio follow (without it, Income Tax Rules 2002's running
      header `PART-I   SECOND SCHEDULE` on 457 pages takes `part_lines` 43 → **595**).
      **13 gained, 0 lost.** Sales Tax Rules: 43 → 41 chapters, 2 spurious containers → 4
      real part nodes, 339 sections held — **and the register did not move.**
      *A suffix is not a sum.* `insert_missing_body_chapters` sorted chapters by
      `_roman_value`, which folds a suffix into two decimals by SUMMING its letters:
      `XIV-AA` and `XIV-B` both 14.02, `XIV-AB`/`XIV-BA`/`XIV-C` all 14.03. Ordering on
      `(base numeral, suffix letters)` reproduces the contents page exactly.
      `_roman_value` itself is unchanged — round 1's Arabic/roman guard depends on it. The
      `ch.code` tiebreak had to come out: `XIVA` and `XIV-A` share a key and a string
      compare orders them by punctuation, not by the contents page. `list.sort` is stable,
      so equal keys keep the TOC's order. Both facts locked.
      `signatures.json` moved deliberately: 11 documents, `part_lines` plus
      `container_order` `CP → PC`, **0 family changes**.
- [x] **`section_codes_ordered` 6 → 4 — a definition clause is not a section.**
      `discover_structure` returns **0 chapters and 126 parentless sections** on a TOC-less
      edition, so `insert_missing_body_chapters` builds the whole tree and assigns sections
      by which codes are *printed* in each chapter's span. The Sales Tax Act defines
      "supply chain" as clause `[(33A)` inside section 2, so `33A` is in CHAPTER I's span;
      CHAPTER I claims it and CHAPTER VII, 55 pages later, finds the parent already set.
      An entry carrying an `anchor` is now placed by **position**, never by code
      membership; TOC entries have no anchor and keep the old behaviour.
      The lock needed strengthening first: with only two chapters the second pass
      reassigns 33A anyway, so the fixture passed with the fix removed. A third chapter
      reproduces the real document's shape.
      Remaining 4: Customs 2025 `'9' after '119'`, Sales Tax 2021 `'3' after '65'`, and
      Sales Tax 2014 `'3' after '32AA'` + `'22' after '75'` — different documents, not yet
      traced.
- [x] **`202B` — the marker run round 4 was right to refuse.** Round 4 measured the naive
      `MARKER_PREFIX` widening at **1 fix : 17 false positives**. The narrow form admits a
      whitespace-separated run **only** behind a lookahead for `[CODE. Capital`, which over
      186,971 lines matches exactly one. **acts `section_carries_its_body` 19 → 15.**
      A methodological correction came with it: every gained/lost measurement in this phase
      has used `output/*.json` plain_text, and that is **not** what the parser sees — the
      parser's line is `42 53 [202B.` while the rendering collapses it to `42 53[202B.`.
      The first lookahead anchored hard on `[`, matched the JSON and missed the PDF.
- [x] **The contents page's own title, read as a chapter — and the invariant's proxy.**
      Two fixes, measured separately.
      *Parser:* `82A out of order after 224` was a chapter-parsing problem, not an ordering
      one. A TOC page break landing inside a wrapped section row leaves the running title
      `THE CUSTOMS ACT,1969` on its own line; it is ALL-CAPS, so `is_foreign_caption`
      accepts it and `_open_caption_chapter` opens a chapter for it. `_page_furniture`
      exists for exactly that line — its docstring even names s.82A — but the two call
      sites order the tests differently, and the one reached on a wrapped row tested
      furniture *after* the caption branch had already fired. Customs 2008: **24 → 22
      chapters** (its contents lists 22), 82A back in CHAPTER IX, 167–192 in CHAPTER XVIII,
      **0 anonymous containers**, 297 sections preserved, 5 hits → 2.
      *Invariant:* `no_chapter_caption_in_section_heading` fired on any run of 3+ capitalised
      words. It now asks what its name asks — is the run a caption that appears on a chapter
      of this document? The three real leaks all match a chapter in their own tree;
      `150ZQZA`/`RESPONSIBILITIES OF THE VENDOR` does not, because the source sets that
      rule's own title in capitals. Alone: rules **2 → 0**, acts holds at 3.
      The locking fixture had to change with it — it pinned a leak in a document containing
      no chapter with that caption, which cannot happen (`_open_caption_chapter` opens a
      node even when the contents omit the `CHAPTER N` row). It now contains the chapter,
      and still fails if that chapter is removed.
- [ ] **`section_codes_ordered` (4) — untraced.** Round 5 closed
      only the Customs 2008 hit. The five Sales Tax hits are `CHAPTER I PRELIMINARY`
      holding `['1', '2', '33A']` across pages 2–75: section 33A (page 75) is parented to
      CHAPTER I instead of CHAPTER VII.
- [ ] `clause_codes_plausible` (1, Finance Act 2024). The jump `7->8517` is an HS tariff
      heading read from a **table row**; the check excludes schedules but not table-derived
      codes (ledger P06).
- [ ] Re-examine the 29 low-confidence documents in `tools/discovery/report.md` §5
      against their re-converted output. Low confidence is not a defect; it is a list
      of the documents whose output deserves a human read.
      **§5 was listing 2, not 29** — round 7 fixed the generator. Its filter tested
      `BY_LABEL[family].profile`, but Phase 2 made the profile an *override* (`None` for
      `consolidated`), so 27 rows had been dropped since PR #45. `report.md` had not been
      regenerated since Phase 0, so it kept printing the old 29 while its generator
      produced 2. `.profile` → `.parseable`, the field Phase 2 added for this question.

- [x] **Gate the register itself.** `data/corpora/*/output/` is gitignored, so
      `run_tests_smoke.py` SKIPs all three lane suites on CI and seven rounds of
      210 → 64 were enforced by prose and a human reading it.
      `tools/suite/register.json` now holds the measurement and
      `tools/tests/test_register_snapshot.py` replays it — skip with no corpus, compare
      with one, fail in **either** direction. An improvement failing it is the point: the
      number then moves in the same PR that moved it. Verified by perturbing the snapshot
      and by clearing the corpus paths.
- [x] **`make check` now lints what CI lints.** It ran `ruff check apps/api tools`; CI runs
      it bare, and `pyproject`'s `src` makes the bare form cover `packages/` too. Planting
      a violation in `packages/legal_ingest/` proved it: the Makefile's form reported
      "All checks passed", CI's found it.

**Gate:** every remaining hit is fixed, or has an entry in
`tools/suite/exemptions/<lane>.json` whose reason is traced to the source PDF

---

## Phase 4 — flip the default, and close the pipeline→portal loop
Branch: `feat/profile-auto-default`, then `fix/pipeline-to-portal`

- [ ] Make `--profile auto` the default once Phase 3 is at zero-or-exempted, and
      collapse the lane→package mapping to family→profile. Phase 2 removed the reason
      not to: the family now overrides the lane's profile rather than replacing it, so
      the default flip no longer silently re-parses a lane.
- [ ] Decide `fbr_ingest` on the evidence now committed in `signatures.json`: the 9 ICT
      Ordinance editions are `consolidated`/flat and structurally identical to the
      Acts-lane PSW and VDDA instruments, and nothing like the 13 Income Tax Ordinance
      editions they share a lane with. Merging the fork is still a v1 non-goal
      (`README.md:283`); this phase only decides it with numbers instead of guesses.
      **This is now also what gates the ordinance lane, and Phase 2 measured the
      cost.** Run best-effort at the lane profile, the lane converts 9 of its 19
      text-layer documents; the other 10 refuse, nine of them the ICT editions with the
      exact error Phase 0 recorded (`TOC parse left 3 section(s) without a chapter
      container`) and the tenth an amending Ordinance this pipeline cannot express.
      `--profile auto` is still not expressible here — `fbr_ingest.run` takes no
      profile, and Phase 1's guard refuses the run rather than letting 46 children fail
      and quarantine the lane.
- [ ] The transport work from the previous plan, unchanged: `make sync` after
      re-conversion, a mounted corpus volume in production, and an HTTP path that
      writes `version_metrics` so the portal can show pipeline health at all

**Gate:** a parser fix merged to `main` is visible in the portal without a manual step

---

## Phase 5 — the instrument tree level

Deferred here by decision: Phase 3 exempts around it, Phase 4 ships first, then this.

A compilation is not one instrument. Customs Rules 2001 binds 44 separately-notified
S.R.O. rule sets behind one index; Federal Excise Rules 2005 starts a second instrument at
PDF page 75 with its own contents page. The tree has no level above chapter, so those
documents' index rows become section leaves with no body, and their codes cannot ascend
document-wide.

- [ ] A level above chapter, so a compilation parses as N instruments
- [ ] The six walkers that hardcode `chapter/part/division/section` as the child keys
- [ ] The portal renderer
- [ ] Re-convert the compilations

**Gate: the deletion of the five `tools/suite/exemptions/rules.json` entries that name
this phase** — `section_carries_its_body`, `section_codes_ordered` and
`no_foreign_section_start_in_body` on Customs Rules 2001, and `section_carries_its_body`
and `no_foreign_section_start_in_body` on Federal Excise Rules 2005. (It said "four" and
then listed three; round 8 added the two mirror entries and counted them.) That is the
honest test that it worked, and the suite will report them stale on its own once it has.
