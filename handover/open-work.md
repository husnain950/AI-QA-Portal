# What is left

20 open items. Ranked by value, each with the one thing that actually blocks it.
State and verification are in [`README.md`](README.md); method is in
[`working-rules.md`](working-rules.md); the executable ledger — **the file to work
from** — is [`tasks.md`](tasks.md).

> **This file, `tasks.md` and `plan.md` §4 each carry the same ranked list.** Three copies
> of one fact is the very shape `working-rules.md` warns about under *"a cached artifact
> cannot tell you its generator is wrong"*. Until they are consolidated, **`tasks.md` is
> the authority** and every round must update all three. Flagged 2026-09-04, round 15;
> still true after round 16, which had to touch all three again.

Expect a lower hits-per-round rate from here than the early rounds got. Rounds 1–7 each
found *one cause explaining many hits*. What is left is mostly 1–2 hits per document with
different causes — with two exceptions, items 4 and 5, which are still one-cause-many-hits
and are the reason they rank where they do. Round 16 spent the last of the cheap
one-cause-many-hits rows.

---

## Phase 3 — the register's 25

### 1. `section_carries_its_body` (17) — four unrelated causes, one of them closed

The largest class, and no longer a single defect:

- **Omission spellings the invariant cannot read (2, acts).** Customs 30.06.2024 s.196K
  prints `to Omitted 96u`; 30.06.2025 s.79 prints `A O mitted` — an intra-word space that
  round 3 measured and refused to admit into a regex whose job is precision. Worth
  re-measuring now the count is small enough to trace individually.
- ~~**The STSP 58U/58V pair (4, rules).**~~ **CLOSED, round 16** (PR #82). Both editions
  print `111[58U].` — S.R.O. 188(I)/2015 renamed rules 59/60, so the amendment bracket
  wraps the code and the dot prints after the `]`. `_BRACKETED_DOTLESS_RE` read that as
  rule **58**. One new pattern in `builder._candidate_code_raw`; artifact
  `wip/phase3-round16-bracketed-code-dot.md`.
- **The round-10 residue (3, rules).** Sales Tax Rules 01-01-2025, each already traced to a
  printed defect: 44A opens with a left double quote, 150ZQZI is printed `150ZQZl`, and
  150W's code appears only in a footnote.
- **The ordinance five**, which live in the `fbr_ingest` fork and are sequenced behind the
  Phase 4 decision on it.

The remainder are single documents: the Pakistan Single Window Act's ministry list read as
sections 27/28, PFMA 2019 s.26, and Sales Tax 2014 s.10 (`R(cid:2)fund`).

### 2. The heading-terminator scan that walks through a boundary (3, acts)

`builder._find_heading_split` looks up to four lines ahead for a heading terminator and
stops at a grid table but **not** at a structural heading, so an omitted section borrows the
next section's terminator and its heading comes out
`*** Chapter-VII OFFENCES AND PENALTIES 33. Offences and penalties`. This is the whole 32AA
cluster of `no_chapter_caption_in_section_heading`, across three Sales Tax editions.

**The obvious guard is already known to be wrong.** Round 13 measured it as **losing section
32AA outright** (127 leaves → 126): an omitted section has no terminator of its own, so
refusing the borrowed one leaves nothing to open it with. This needs an omission-aware
fallback, not a guard. Trace: `wip/phase3-round13-chapter-hyphen.md`.

### 3. `preamble_carries_no_toc_tail` (2, acts)

Round 14 closed eight of the ten documents that had this. The two survivors are the same
shape and both are now *visible*, which they were not before that round: Customs 30.06.2008
and Sales Tax 30.06.2023 each have a contents tail page carrying **2** schedule rows against
`detect_toc_pages`'s floor of **3**. 2008's source prints the typo `THE SECOND SHCEUDLE`,
which `grammar.SCHEDULE_TOC_RE` rightly refuses.

**The floor is load-bearing** — that function's own comment records a lower one swallowing
the Income Tax Rules' body title page and starting the body a page late. A fix needs a
signal other than row density.

### 4. The container-code guard

A `PART-N` line should be a boundary only where the enclosing chapter actually holds a part
with that code. **Two independent measurements now argue for it:**

- it is what makes the PART separator widening safe (14 real boundaries against 6 annexure
  FORM losses, where the losses are an item counter running 8–11 *across* the parts);
- it is what would have kept round 13 from dropping four chapter captions in Customs Rules
  2001 (conservation 74.101% → 74.087%), whose tree holds 41 of ~44 chapters and cannot
  express them.

Needs `build_sections` to pass per-chapter container codes into `_build_one`.

### 5. The CHAPTER letter suffix — 57 hits, 24 documents, all real

`_STRUCTURAL_RE`'s CHAPTER branch has no suffix class where PART and Division beside it both
do, so `CHAPTER XVI-A` sits in section 155's body across twenty Customs editions. Measured
and held out of round 13 because it doubles re-conversion to 44 documents, twenty of them
the Customs chapter tree that rounds 1 and 6 rebuilt.

**Pinned by a test that asserts the current *wrong* answer** and fails the moment the
widening lands:
`test_structural_boundary_agrees_with_grammar.py::test_the_letter_suffixed_chapter_gap_is_still_open`.

Do not "fix" that test — its failure is the signal.

### 6. `section_codes_ordered` — **CLOSED, round 15**

Was 3, now **0**, and **not for the reason this file predicted**: no section code was
misread. All three were a *chapter* mislabelled — `toc.py` emitting `CHAPTER III` twice
because a folio-less contents row stayed open across the chapter boundary, and
`insert_missing_body_chapters` then pairing leftover nodes to leftover numerals by list
position. See `wip/phase3-round15-chapter-numeral-pairing.md`.

The hits were: Customs 2025 `'9' after '119'`; Sales Tax 2014 `'3' after '32AA'` and `'22' after '75'`.
Nobody has read the source pages for these.

### 7. `clause_codes_plausible` (1, Finance Act 2024)

The jump `7->8517` is an HS tariff heading read from a **table row**; the check excludes
schedules but not table-derived codes (ledger P06). **Do not weaken it.** Two routes were
suggested: bound the clause cursor by the measured gap, or reuse `_common._QUOTE_CUE`.

### 8. No invariant can see a document that lost 93% of its sections

Round 11's document gained 118 sections while the register moved 3. What would catch that is
a **cross-edition** fact, and invariants run per document: `runner.run` is handed one `doc`
with no lane, no path and no siblings. The join exists — `signatures.json`'s `group` key
matches `metadata.filename` on 80/80 acts documents — but its counts are PDF-regex
measurements, not tree counts, so a real parse-quality comparison needs a new per-group index
over `output/*.json`.

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

## Phase 4 — 2 items

- **Flip `--profile auto` to the default** once Phase 3 is at zero-or-exempted, so a family
  override *refines* the lane's profile rather than replacing it.
- **Decide `fbr_ingest`** on the evidence now committed in `signatures.json`. Both forks
  parse the same three sections of an ICT Ordinance edition; the only difference is that
  `legal_ingest` has a flat-act fallback that gives them a container, so this is a
  **routing** problem, not a parsing one. Route by family, not by lane. Merging the fork
  stays the v1 non-goal it already is (`README.md:283`). Follow-through unblocks 9 documents.

The transport-and-deploy limb of Phase 4 is **closed** — it ran as its own track in
`wip/integration/`, PRs #59–#76. Any bullet in `wip/tasks.md` describing it as open predates
that.

## Phase 5 — 4 items, not started

The **instrument tree level**: a level above chapter, so a compilation parses as N
instruments rather than one document whose index rows become section leaves.

1. The level itself
2. The six walkers that hardcode `chapter/part/division/section` as the child keys
3. The portal renderer
4. Re-convert the compilations

**Its gate is the deletion of the 4 exemption entries that name it**, all in
`tools/suite/exemptions/rules.json` — two for Customs Rules 2001 and two for Federal Excise
Rules 2005, each a `section_carries_its_body` / `no_foreign_section_start_in_body` pair on
the same evidence. That deletion is the honest test that it worked, and the suite reports
them stale on its own once it does.

(`wip/HANDOVER.md` says this gate is *two* entries and `wip/tasks.md` says *five*. It is
four — verified at this commit.)

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

> Every file under `wip/integration/` still states the register as **34**. It is **25**.
