# What is left

Rounds 21-28 (PR #89) closed the Customs Act QA pass and took the register **22 → 13**,
regenerated from a corpus converted at one revision. Round 20 (PR #86) had shipped Phase 4
routing, Phase 5 instruments, the Finance Act 2024 clause cursor, the CHAPTER en-dash and
the schedule PART reader. OCR stays out.

**Four of this file's ranked items are now zero** — the heading-terminator scan, the
omission spellings, `preamble_carries_no_toc_tail` and `clause_codes_plausible`. Three of
them had working code since round 20 and were only ever waiting on a corpus at one revision.

What is left is **13 hits across ten documents**, plus the three optional integration
leftovers. Ranked by value, each with the one thing that actually blocks it.
State and verification are in [`README.md`](README.md); method is in
[`working-rules.md`](working-rules.md); the executable ledger — **the file to work
from** — is [`tasks.md`](tasks.md). Artifact:
[`wip/phase3-round21-28-customs-qa.md`](../wip/phase3-round21-28-customs-qa.md).

> **This file, `tasks.md` and `plan.md` §4 each carry the same ranked list.** Three copies
> of one fact is the very shape `working-rules.md` warns about under *"a cached artifact
> cannot tell you its generator is wrong"*. Until they are consolidated, **`tasks.md` is
> the authority** and every round must update all three. Flagged 2026-09-04, round 15;
> still true after rounds 16, 17 and 18, each of which had to touch all three again — and
> round 17 found this file and `plan.md` **both** asserting something the measurement
> disproved (item 4 below), which is exactly the cost the warning predicts. **Rounds 18 and
> 19 both paid it again** — round 19 found *two of the three* traces for its row wrong at the
> source pages. **PR #89 paid it worst: it updated none of the three**, so all four files
> described a register of 22 for a day while the committed one read 13, and this file's item
> 9 was duplicated — once as open, once as closed. Reconciled 2026-09-10 from a live run. **Round 18 paid it**, from `tasks.md` itself: its prescribed fix for item 5 (`[A-Z]{0,2}`, "the same
> suffix class as PART and Division") cannot cross a hyphen and finds 9 of the 57 hits the
> same row quotes. The measurement was right and the instruction derived from it was wrong.

Expect a lower hits-per-round rate from here than the early rounds got. Rounds 1–7 each
found *one cause explaining many hits*. What is left is mostly 1–2 hits per document with
different causes. **Round 18 spent the last one-cause-many-hits row** (item 5, at 57).
Rounds 16, 17 and 18 took the three cheapest rows on the board; what is left needs a trace
before it needs code, and the top row is now a judgement call rather than a fix.

---

## Phase 3 — the register's 13

### 1. `section_carries_its_body` (12) — several unrelated causes, three of them closed

The largest class, and no longer a single defect:

- ~~**Omission spellings the invariant cannot read (2, acts).**~~ **CLOSED, rounds 21-28**
  (PR #89). Round 20 widened `_is_omission` to the whole-string forms `to Omitted 96u` and
  `A O mitted` — no general `\s*` between letters, which is the form round 3 measured and
  rejected — and could not measure it, because neither Customs edition was staged on that
  host. Both are converted now and neither is a hit.
- ~~**The STSP 58U/58V pair (4, rules).**~~ **CLOSED, round 16** (PR #82). Both editions
  print `111[58U].` — S.R.O. 188(I)/2015 renamed rules 59/60, so the amendment bracket
  wraps the code and the dot prints after the `]`. `_BRACKETED_DOTLESS_RE` read that as
  rule **58**. One new pattern in `builder._candidate_code_raw`; artifact
  `wip/phase3-round16-bracketed-code-dot.md`.
- ~~**The round-10 residue (3, rules).**~~ **CLOSED, round 19** (PR #85), by *exemption with
  evidence* — all three are printing errors in a `native-digital` source, so no parser change
  can read them: 44A prints `“44A.` with a left double quote (p.66); **150W prints `228[50W.`
  with its leading digit dropped** (p.109) — *not* "only in a footnote", which is what this
  file used to say; and 150ZQZI prints `150ZQZl` with a lowercase L (p.151) while **p.152
  carries a genuinely different rule `150ZQZL`**, so the two cannot be folded. Entered with
  **no expiry**: this document is never OCR'd, so the earlier "OCR-class, may expire on the
  OCR decision" note was wrong on both counts.
- **The ordinance five (5)** — ITO 2001 editions, ss.233AA, 214E ×2, 122C ×2, all in the
  `fbr_ingest` fork. **No longer blocked on a decision**: round 20 decided routing and ITO
  stays on `fbr_ingest`. This is now a parser round in the fork, and it is the largest single
  block left.
- **Customs 1969 (30.06.2008) ss.181 and 189 (2)** — two heading-only leaves in one edition,
  newly the only shared-cause candidate in the acts lane. Nobody has read those pages.
- **Sales Tax Rules 2006 (30-06-2025) rule 150 (1)** — the `150ZQ*` family again, a different
  edition from the one round 19 exempted.

The remainder are single documents: the Pakistan Single Window Act's ministry list read as
sections 27/28, PFMA 2019 s.26, and Sales Tax 2014 s.10 (`R(cid:2)fund`).

**One hit is not in this class at all**: Sales Tax Rules 2006 (01-01-2025) rule 13 carries
the start of 44A under `no_foreign_section_start_in_body`. Round 19's exemption for that
document names `section_carries_its_body`, so it does **not** cover this one — the entry is
scoped to three enumerated hits on purpose.

### 2. The heading-terminator scan — **CLOSED, rounds 21-28**

`builder._find_heading_split` looks up to four lines ahead for a heading terminator and
stops at a grid table but **not** at a structural heading, so an omitted section borrows the
next section's terminator and its heading comes out
`*** Chapter-VII OFFENCES AND PENALTIES 33. Offences and penalties`. This is the whole 32AA
cluster of `no_chapter_caption_in_section_heading`, across three Sales Tax editions.

**The obvious guard is already known to be wrong.** Round 13 measured it as **losing section
32AA outright** (127 leaves → 126): an omitted section has no terminator of its own, so
refusing the borrowed one leaves nothing to open it with. This needs an omission-aware
fallback, not a guard. Trace: `wip/phase3-round13-chapter-hyphen.md`.

**Closed.** Round 20 shipped exactly that fallback and could not measure it — the three
Sales Tax editions were not on that host. The rounds 21-28 re-conversion put them at one
revision and `no_chapter_caption_in_section_heading` went to **0**.

### 3. `preamble_carries_no_toc_tail` — **CLOSED, rounds 21-28**

Round 14 closed eight of the ten documents that had this. The two survivors are the same
shape and both are now *visible*, which they were not before that round: Customs 30.06.2008
and Sales Tax 30.06.2023 each have a contents tail page carrying **2** schedule rows against
`detect_toc_pages`'s floor of **3**. 2008's source prints the typo `THE SECOND SHCEUDLE`,
which `grammar.SCHEDULE_TOC_RE` rightly refuses.

**The floor is load-bearing** — that function's own comment records a lower one swallowing
the Income Tax Rules' body title page and starting the body a page late. A fix needs a
signal other than row density.

**Closed.** Round 20 added the extra signal, left the floor at 3 and kept refusing
`SHCEUDLE`, then measured 0 on the *public* editions only. Both private editions are now
converted and the class is **0**.

### 4. The container-code guard — **CLOSED, round 17**

A `PART-N` line is a boundary only where the enclosing chapter actually holds a part with
that code. Shipped with the PART separator widening it enables: **14 gained, 0 lost**,
register **unchanged at 25**. Artifact `wip/phase3-round17-container-code-guard.md`.

This file listed **two** measurements arguing for it. The first held and reproduced
exactly. **The second was false, and round 17 disproved it:** the guard would *not* have
kept round 13 from dropping Customs Rules 2001's four chapter captions. Extending it to the
CHAPTER branch moves conservation 74.087% → 74.099% and all 28 of those tokens are a
**duplication** — `preamble_refs` passes no codes, so the preamble's own `CHAPTER I` line
stops being a boundary, the preamble no longer ends there and swallows rule 1's opening
text, which rule 1 still holds. Not one leaf changed. **Those four captions are Phase 5.**

The discriminator had to be per-chapter, not per-document: Sales Tax Rules 2006
(01-01-2025) prints five real `PART-N` captions under CHAPTER XI *and* form STR-11's two
under CHAPTER XVIII in the same document.

### 5. The CHAPTER letter suffix — **CLOSED, round 18**

**80 swallowed boundary lines across 24 documents went to 0**, register **unchanged at 25**
(rise +57 on the invariant, fall -57 on the parser). **0 leaves and 0 chapter nodes gained
or lost**: every one of these chapters was already in the tree off the contents page, so the
fix **un-duplicates** a caption the body was printing twice. Artifact
`wip/phase3-round18-chapter-letter-suffix.md`.

Three things this entry had wrong, all measured:

- **The prescribed class was wrong.** `[A-Z]{0,2}` — "the same suffix class as PART and
  Division" — cannot cross a hyphen, and the separator usually *is* one (`CHAPTER XVI-A`).
  It finds **9** hits, not 57. The shipped class is `(?:-?[A-Z]{1,2})?`: no spaced form,
  because `grammar.ROMAN`'s spaced branch under `IGNORECASE` eats *of / or / for*.
- **Two regexes were narrow, not one.** The suite's own `_STRUCT_LINE` carried the identical
  narrow CHAPTER branch, which is *why* the register rises before it falls — the instrument
  for this defect was as narrow as the defect.
- **44 documents was a round-13-era estimate.** Measured at this commit: **24**.

**A second gap on the same line was located and left open** — see item 9 below.

### 6. `section_codes_ordered` — **CLOSED, round 15**

Was 3, now **0**, and **not for the reason this file predicted**: no section code was
misread. All three were a *chapter* mislabelled — `toc.py` emitting `CHAPTER III` twice
because a folio-less contents row stayed open across the chapter boundary, and
`insert_missing_body_chapters` then pairing leftover nodes to leftover numerals by list
position. See `wip/phase3-round15-chapter-numeral-pairing.md`.

The hits were: Customs 2025 `'9' after '119'`; Sales Tax 2014 `'3' after '32AA'` and `'22' after '75'`.
Nobody has read the source pages for these.

### 7. `clause_codes_plausible` — **CLOSED, round 20, measured rounds 21-28**

The jump `7->8517` is an HS tariff heading read from a **table row**; the check excludes
schedules but not table-derived codes (ledger P06). **Do not weaken it.**

**Closed.** Round 20 took neither suggested route: `_DOTFORM_RE` uses `\.(?!\d)`, so a
quoted `8517.1430` is not a clause start. The check was not weakened and its
must-stay-red fixture still stays red. Measured to **0** by the rounds 21-28 re-conversion.

### 8. No invariant can see a document that lost 93% of its sections — **CLOSED, round 20**

Round 11's document gained 118 sections while the register moved 3. What would catch that is
a **cross-edition** fact, and invariants run per document: `runner.run` is handed one `doc`
with no lane, no path and no siblings. The join exists — `signatures.json`'s `group` key
matches `metadata.filename` on 80/80 acts documents — but its counts are PDF-regex
measurements, not tree counts, so a real parse-quality comparison needs a new per-group index
over `output/*.json`.

### 9. The CHAPTER en-dash separator — **CLOSED, round 20**

`CHAPTER – VI` is a real boundary. Grammar, builder, discover, and `_STRUCT_LINE`
now agree. The known-gap test is a `BOUNDARIES` case.

### 10. The schedule PART reader — **CLOSED, round 20** (public gazette PDFs)

Cause on the public Finance Act 2021/2019 PDFs was **not** the 8.5pt gate: the
page model emits `P ART -I` (glyph-split keyword). `_PART_RE` now uses
`grammar.spaced('PART')`. Live reconvert: FA2021 Fifth Schedule `PART I`–`VIII`;
FA2019 `PART I`–`VII`. Arabic `Part-1`/`Part-11` accepted; `l`→`I` still refused.
Public FA2025 has no PART headings; public FA2014 has no text layer.

### 11. Letter-suffixed citation markers — 22 sites, 1 document — **new, 2026-09-10**

`grammar.MARKER` (`:132`) is `(?:\d{1,4}[a-z]?|\*)` — a **lowercase-only** suffix. Customs
1969 (30.06.2025) prints 22 citation markers with an **uppercase** suffix at marker size
(8.04pt against a 12.0pt dominant): `59&59A`, `59/59A`, `66A`, `66B`, `30A`, `36/36A`,
`27/27A` ×3, `2/2A` ×3, `2A` ×2, `14/14A`, `18/18A`, across 9 sections in 6 chapters. Every
one renders as literal body text and builds no footnote record. The same document prints
**90** lowercase-suffixed markers that parse correctly, so this is a case inconsistency in
the source's own marker printing, not a size or layout problem.

**Not in the register, and that is the shape to recognise.** The invariants share the
parser's marker grammar, so `inv_leading_marker_cited`, `inv_citation_refs_resolve` and
`inv_footnote_on_citing_leaf` are as blind to an uppercase suffix as the builder is — the
same shape item 5 had before round 18 closed it. **Expect the register to rise when the
invariant is widened and fall when the parser is**, and measure the two halves separately.

**The blocker is a source question, not a code one.** p62 prints `55&55a` and p64 prints
`66A`. If the *note* for `66A` is printed `66a.`, the fix is a case-fold on the citation
join and a wider class would mint a marker resolving to no note. The affected body pages
carry no footnote block of their own, so the definitions are on other pages: find them first.

**Do not widen `MARKER` globally.** `79A` is a real section code in this document — round 24
shipped a repair to rejoin its split `79` `A` — and `155A`…`155R`, `32A`, `26B`, `129A` all
print at body size as codes.

### Also open in Phase 3, off the ranked list

- **`fbr_ingest` carries both of round 13's narrow copies, dormant.** Its `discover.py` has
  the identical broken keyword/numeral split and the same `\s+` separator. Measured at
  **zero** additional hits across all 12 ordinance documents, so it was correctly left
  alone — but it is a live landmine gated on the Phase 4b fork decision.
- **`convert_all.py` cannot resume a re-conversion** — see [`working-rules.md`](working-rules.md).
- **Re-examine the 29 low-confidence documents** in `tools/discovery/report.md` §5, now that
  the generator that hid them is fixed.

---

## Phase 2 — the OCR half, 3 items

61 scanned documents, 2,456 OCR pages. **There is a cheap tail worth deciding on:
35 documents need ≤ 10 pages each, 172 pages in total** — roughly 15 minutes at the measured
0.2 pages/sec. Finance Acts 2022 and 2023 are **one page each**. At ≤ 30 pages it is 50
documents / 504 pages. The marathon tail is Finance Act 2017-18 (683 pages), 2025 (290),
2015 (236), 2016-17 (215), 2014 (148), 2020 (140).

Also waiting on the same decision: the `--admit-below-floor` rebuild of the 9 provisional
acts documents, and the ordinance lane's other 10 text-layer documents (which actually
depend on Phase 4b, not on OCR).

**Taking OCR in scope has consequences beyond time.** `data/ocr_cache` stops being 0 B, the
fidelity-floor invariants wake up, and a sub-floor scan routes to `_provisional/` — which,
under the withdrawal shipped in the integration track, *removes that document from the
portal*. Decide deliberately.

## Phase 4 — shipped, round 20

- **`--profile auto` is the convert default.** A family override refines the
  lane's profile. The full-corpus reparse that the original gate asked for was
  **not** run: no private corpus on the round-20 host. Rounds 21-28 converted 77 of the
  103 documents at one revision, which is what moved the register to 13 — but the ordinance
  lane and 14 skipped acts documents are still at older revisions, so full-corpus
  attribution stays blocked.
- **`fbr_ingest` is a routing decision, not a merge.** Flat ICT → `legal_ingest`;
  Income Tax Ordinance stays on `fbr_ingest`. The ordinance five still need ITO
  editions.

The transport-and-deploy limb of Phase 4 is **closed** — it ran as its own track in
`wip/integration/`, PRs #59–#76.

## Phase 5 — shipped, round 20

The **instrument tree level** exists: `instruments[]`, walker sites, portal
renderer. Gate met: the 4 compilation exemption entries for Customs Rules 2001
and Federal Excise Rules 2005 are **deleted**. Remaining rules exemptions are
jammed-tokens, split-ordinals, and the round-19 STR printing errors.

---

## The integration track — finished, with 3 optional leftovers

Every problem in `wip/integration/plan.md` §3 is **closed**: the output contract, positional
leaf identity, withdrawal, the two ingest paths, the sanitizer, stale review state, and the
CI gate at the corpus interface. PRs #59–#76. The corpus-wide identity hole went from 5,047
leaves (30%) to **89 (0.5%)**.

There is no next PR in sequence. Three boxes remain unticked, none blocking:

| pick up | the single blocker |
|---|---|
| delete `_legacy_section_key` + the `source_key` bridge | blocked on the 14 stale acts documents only — 6 documents / 89 leaves still rely on it. Confirm with a query, not a guess. |
| reconcile `ReviewToolbar`'s approval gate | **a product decision, then one line.** It gates on *any* quality flag while claiming to mirror the narrower `CRITICAL_FLAGS`. Cheapest row on the board once someone decides. |
| delete the Zustand mirror in `documentStore` | means rewriting five pages onto React Query hooks. The bug it caused is already fixed and tested, so this is architecture, not a defect. |

Two more from that track's ranked list are worth knowing because they are **not** integration
work:

- **An explicit `order` field** needs the *source pages*: tree-walk and page-sort order
  disagree on 21 of 103 documents and the JSON cannot settle which is right. This is P5's
  reading-order limb, measured and deferred rather than open.
- **Deleting `normalize_heading`** is a *parser* task hiding in the integration ledger — a
  parser round must first stop emitting a leading `]` and the truncated `[...`. Then it is
  one deletion.

> Every file under `wip/integration/` still states the register as **34**. It is **13**.
