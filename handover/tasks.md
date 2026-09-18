# The execution ledger

**This file is updated as work happens, never after.** If a box is ticked, the thing is
merged on `main`.

**State:** the register is **0** — **all three lanes are closed**, verified 2026-09-14 after
**round 37** against a live three-lane run on a corpus re-converted under this tree (77 of
103 at `0139b858daac`, 9 ordinance at `dbcab2f79b78`; the other 17 are image-backed and
cannot follow while OCR is out of scope). acts 0, rules 0, ordinance 0, delta zero, no lane
skipped. **The board has carried no register-bearing row since round 36** — work now comes
off the unresolved-marker census, **3,265 across 81 documents**, and rows 13 and 14 below
are the measured next two. **Nine of the thirteen hits were
closed by exemption and four by code** — see the closed-rows table below before treating a
zero as a clean corpus. Reasoning for every row is in [`plan.md`](plan.md); state is in
[`README.md`](README.md); the traps are in [`working-rules.md`](working-rules.md).

Written 2026-09-04 on `main` after PR #83 (round 17); updated after PR #84 (round 18),
PR #85 (round 19), PR #86 (round 20), and **2026-09-10 after PR #89 (rounds 21-28)**.
Artifact: [`wip/phase3-round21-28-customs-qa.md`](../wip/phase3-round21-28-customs-qa.md).

**Nine invariant classes are closed.** Round 15 closed `section_codes_ordered` — see
[task 1's Result](#1-trace-section_codes_ordered--3-hits-acts--closed-round-15). Round 16
closed one of `section_carries_its_body`'s causes, taking that class 21 → 17 — see
[task 2's Result](#2-the-stsp-58u58v-pair--4-hits-rules--closed-round-16).

**Rounds 21-28 (PR #89) closed three more and took the register 22 → 13.** Eight rounds
against one Customs Act edition, closing 21 reviewer-logged defects; the acts lane went
**15 → 6**. `no_chapter_caption_in_section_heading`, `preamble_carries_no_toc_tail` and
`clause_codes_plausible` are all **0**, and so are the two omission spellings. Those were
rows 1, 2, 3 and 5 of the board below — see each row's Result.

**Read this before believing any Result below that credits round 20.** Round 20 shipped
working code for rows 1, 2, 3 and 5 and could not move the register, because the private
editions carrying the hits were absent from that host. The rounds 21-28 re-conversion is
what turned those into zeroes. **Shipped and measured are two different states**, and this
ledger carried four rows as open for a full round because it conflated them. When a Result
says "code shipped, register not moved", the row is *not* closed — it is unmeasured.

**Round 17 closed the container-code guard** and shipped the PART separator widening it
enables: 14 gained, 0 lost, register unchanged at 25 — see
[task 4's Result](#4-the-container-code-guard--0-hits-an-enabler--closed-round-17).

**Round 18 closed the CHAPTER letter suffix** — the row that had been top of the board:
**80 swallowed boundary lines across 24 documents went to 0**, register **unchanged at 25**
(rise +57 on the invariant, fall −57 on the parser) — see
[task 3's Result](#3-the-chapter-letter-suffix--57-hits-24-documents--closed-round-18). It
also **located a second gap on the same line of code** and left it open on evidence: the
**en-dash separator**, 42 lines across 21 documents, closed by round 20.

**Round 19 closed the round-10 rules residue** — **25 → 22**, by *exemption with evidence*:
all three are printing errors traced to PDF pages 66, 109 and 151. **Two of the three traces
this file carried were wrong** — see
[task 5's Result](#5-the-round-10-rules-residue--3-hits-an-exemption-row).

### Decisions on record (2026-09-04)

Taken by the repository owner, so they are not rediscovered:

| decision | consequence |
|---|---|
| **Scope: everything**, through Phase 5 | the ranked table below is worked top to bottom, not sampled |
| **OCR (row 13) stays out of scope**, recorded as a deliberate "no" | `data/ocr_cache` stays 0 B; row 14 stays blocked, but *honestly* blocked |
| **`ReviewToolbar` gates on CRITICAL flags only** (row 15) | switch to `hasCriticalQualityFlags`, matching the backend's `CRITICAL_FLAGS` |
| Context is cleared between PRs | **this folder is the only memory that survives; updating it is part of the PR** |

**Execution order** no longer differs from the value ranking. It did for one round: the
container-code guard was worked before the CHAPTER letter suffix so that row 1's twenty
Customs editions would be re-converted once rather than twice. **Round 17 landed the
guard**, so row 1 is now simply the top row.

One thing that reordering was *also* justified by turned out to be false, and round 17
measured it: the guard would **not** have kept round 13 from dropping four chapter captions
in Customs Rules 2001. See [task 4's Result](#4-the-container-code-guard--0-hits-an-enabler--closed-round-17).

---

## Start here — pick one

Ranked by value against cost, each with the ONE thing that actually blocks it. An agent
with no other context can take a row and start.

**This board was rebuilt on 2026-09-10 from a live three-lane run, not from the previous
board.** Rounds 21-28 closed four of its rows; rounds 29-34 (PRs #93-#99) closed five more
and took the register to **0**. Those five are in their own table below the open rows, not
in the ranking — a struck row in the ranking is a row that gets re-picked.

**Since round 36 the board has carried no register-bearing row, so rows 13 and 14 come off
the UNMEASURED surface** — the unresolved-marker census, which no invariant watches. It is
**3,265 across 81 documents** after round 37 (acts 1,900 / rules 934 / ordinance 431). Both
rows below were traced to their source pages during round 37 and neither is a hypothesis.

| # | pick this up | hits | the single blocker | plan.md |
|---|---|---|---|---|
| 13 | **Sales Tax Rules 2006 (01-01-2025): 869 unresolved markers, 0 notes** | **869** — 27% of the whole unmeasured population, the largest single block left | **The document DOES print per-page footnotes, and the board's old guess that it has "no footnote zone" is about calibration, not about the source.** PDF page 60 sets body **12.0pt**, note prose **9.0pt**, note heads **6.0pt at x0 36.0**, inline markers 8.04pt — a textbook zone, six notes (164-169) with edit verbs. Calibration records `body_size 12.0, footnote_size 11.0, footnote_text_max 0.0, footnote_marker_max_size 0.0, zone_mode "none"`: **11.04pt is the page FOLIO**, not footnote prose. The cause is that the document has **TWO size regimes** — the rules body at 12.0/9.0 and the annexed STR forms at 9.96/8.04 (pp.237, 240, where the notes read `393 Form STR-28 … added by Notification No. S.R.O. 918(I)/2019`) — so a 36-page sample mixes them and the pair the fit returns is not a body/footnote pair. Fix the **sampling**, not the thresholds. ⚠ **READ THIS BEFORE TOUCHING ITS CALIBRATION:** round 35's `Word.upper_ok` gate (`pagemodel.py:113`) reads `footnote_marker_max > 0.0` as *"this document has no footnote zone, so every uppercase token in it is a section code"*, and **this is the document that condition was built against**. Give it a zone and the gate opens: the 56 section cross-references round 35 measured being lifted into `<sup>` (`72A` ×30) come back. Re-measure this document's html against `main` **in the same round**, or do not touch it | *(none yet)* |
| 14 | **Customs Rules 2001: three CHAPTER captions missing from the tree** | — (register-invisible; 41 chapters where the source prints 44) | **Two of the three are traced to the page, and they are two different decorations.** (1) **CHAPTER XIV** — p102 prints `2&30 [CHAPTER XIV`, a marker **RUN** glued to the bracket. `builder._STRUCT_DECOR_RE` (`:2331`) is `^(?:[\d*]{1,3}\s*\|\[+\s*)+`, which reads ONE marker and stops at the `&`, so the line is never a boundary and rules 326-340 are parented under CHAPTER XIII. (2) **CHAPTER XX** — p163 prints `“Chapter XX` with a LEFT DOUBLE QUOTATION MARK and in mixed case; the `34[CHAPTER XXI` on the same page IS recognised, which is the control. Same shape as the ordinance `4[“214E.` defect closed by PR #96, on a different code path. (3) **CHAPTER VIII** — not traced; no caption is printed between CHAPTER VII (p21) and CHAPTER IX (p34) and rules 127-132 are absent from the body, so it may be an omission in the source. **This is a boundary widening**: it re-parents sections, and rounds 13, 18 and 27 are all on record about what that costs when it is batched into another round. Measure it as gained/lost over all 187 sources first | *(none yet)* |
| 6 | delete `_legacy_section_key` | — | **BLOCKED on row 12**, decided as *no OCR* — and **permanently**, not pending a census: all 14 stale acts documents are image-backed (measured 2026-09-14, exact per-page), so none of them can ever be re-converted while that decision stands. The query that would confirm the 6 documents / 89 leaves **does not exist yet**; writing it will confirm the block, not lift it. It has **two** call sites, not one: `document_store.py:224` builds the index for every row on every sync, `:257` is the lookup | [Deferred](#deferred-with-reasons) |
| 8 | delete the Zustand mirror | — | 8 consumer modules, and **no data-hooks layer exists to move onto** — it must be written. Architecture, not a defect | [Deferred](#deferred-with-reasons) |
| 12 | the OCR decision | — | **DECIDED 2026-09-04: out of scope, deliberately.** `data/ocr_cache` stays 0 B. Not work — the decision is the deliverable, and it is recorded | [Phase 2](plan.md#phase-2--the-ocr-half-a-decision-not-work) |

### Closed by round 38 — a QA cycle, not a board row

Not a board row and not off the census: an external QA cycle logged **19 rows** against
the review portal's rendering of `Federal Excise Act, 2005 as amended upto 30-06-2025`.
Every row was re-checked against the source PDF's glyph geometry before any code moved.
**18 real, 1 not** — and they collapse to **9 root causes**, each firing far beyond the
one document the reviewer opened.

| # | pick this up | result | what it was | artifact |
|---|---|---|---|---|
| ~~q1~~ (r38) | ~~**QA Cycle 1 — 19 rows, Federal Excise 30-06-2025**~~ | **16 closed by code, 1 closed as not-a-defect, 2 held for PR 2** | **CLOSED 2026-09-17 (round 38).** Seven fixes. The reviewer found **one instance each of corpus-wide classes**: the orphaned heading terminator was **412 leaves / 30 documents** (and prints in TWO spellings — fused `documents.--`, and as a separate token in Sales Tax 1990, which alone held 50); the missing schedule title **237 leaves / 34 documents**, where `_finish_leaf` promoted a `[See …]` line into the `<h4>` slot and shipped leaves with no heading element at all; the per-document marker size gate turned ordinary numerals into citations wherever a schedule is set below body size (**515 → 412 markers on the reviewer's document, 103 lost and 0 gained, every one false**). Corpus: leaves **13,103 → 13,105** (+2, both s.31 *Omitted* recovered — the CH5-03 class in two older Excise editions), unresolved markers **2,813 → 2,427**, bare-`[See …]` leaves **201 → 7**, orphaned dashes **412 → 2**, gazette-title-mid-sentence **15 → 0**. All residue is in five image-backed documents that cannot be re-converted under the OCR decision — five exemptions, each saying so. | [artifact](../wip/phase3-round38-qa-cycle1-excise.md) |
| ~~q1b~~ (r38) | ~~CH4-01 — s.27's marker resolving to s.26's note~~ | **not a defect; pinned** | PDF p.41 prints a real superscript `1` at x0 197.6, 8.04pt, before `[or beverages]`, and page 41's footnote 1 **is** that note. Footnote numbering in these compilations restarts **per page, not per section**. Doing what the row asked would unresolve every legitimately reused marker in the corpus (`43.2` twice in s.29, `83.2` twice in Table-II). Pinned by `tools/tests/test_page_scoped_footnote_reuse_is_faithful.py` so a later round does not "fix" it | same artifact |
| ~~q2~~ (r39) | ~~**FIRST/THIRD SCHEDULE tariff tables render as prose**~~ | **FS-02 closed; FS-07 half closed** | **CLOSED 2026-09-17 (round 39) for the FIRST SCHEDULE.** The ledger's diagnosis was right and its prescription was not a fix. Widening `_NUM_TOKEN` alone renders **125 `<tr>` for a 69-row table**, shreds serial 6 across five of them and reprints the page header nine times as data — worse than the prose it replaces. **Four defects, not one:** (1) `_NUM_TOKEN` matched only the bare `(N)`; (2) `_boundaries` took the midpoint between the numbering labels' **centres**, which holds only when a label is centred over its own column — `Col.(1)` is wider than the serial column it names, so the boundary landed 19pt inside a description column starting at x0 174.1 — and the white-gutter refinement that would have corrected it **cannot fire on a table this long**: over Table-I's 221 rows the minimum occupancy in the three gutters is **4, 4 and 5 rows**, about 2%, never zero; (3) the header block is reprinted on every page and only the first is the thead; (4) `_assign` ordered a column's words by `top`, which restarts per page, so a row crossing a page break read its continuation first. Census: **162 `Col.(N)` rows / 17 documents, all Federal Excise, acts lane only** — 0 in rules, 0 in ordinance. **Measured** over 119 convertible sources converted twice: **17 changed, 102 byte-identical**, and the changed set is exactly the census population. Tables **+51**, `<tr>` **+1,933**, `<p>` **−607**, leaves **+0**, footnote records **+0**. Citations **−36** are the *reprinted* header's marker on Table-II continuation pages — **no distinct cite id disappeared anywhere in the corpus**; unresolved markers **−181** were *false* markers (serials in a tariff cell read as citations, the FS-03 class). `plain_text` moved on 9 and is identical once whitespace is removed on all 9. Acts suite **67/68 clean on BOTH trees**, the single failure byte-identical and outside the changed set. **A fifth defect surfaced during the round**: `no_split_ordinals` 65→64 on `30 th June`, because the table path builds text with `" ".join` — fixed in both places it occurs (`builder._render_line_run` for `plain_text`, `tables._assign` for the cell) by reusing `footnotes.words_are_glued` | [artifact](../wip/phase3-round39-tariff-table-columns.md) |

| ~~q3~~ (r40) | ~~`tools/discover_corpus.py --check` is stale — 27 documents~~ | **CLOSED 2026-09-18 (round 40). The pipeline gate is green.** | **It was one character, and it was round 20's.** All 27 records differed in **exactly one field**, `signature.chapter_lines`; zero `NEW`, zero `GONE`, zero `MOVED`, so **no family assignment moved**. `signatures.json` was last written at `f7269d8` (round 6, PR #51); `grammar.CHAPTER_RE` last moved at `2d6fa52` (PR #86, round 20), which added the **en-dash** to its separator class (`[\s\-]+` → `[\s\-–]+`) — the second gap round 18 located on that line. `signature.measure` counts `CHAPTER_RE` matches into `chapter_lines`, so the parser widening moved a discovery signature that no round regenerated. **Proved by restoring the pre-#86 regex in-process: the census then reproduces the committed `signatures.json` byte-identically**, so nothing else has drifted since round 6. Two delta shapes, every gained line read: **+2 on 24 documents** (20 Customs Act, 2 Income Tax Rules, 1 Sales Tax Rules) and **+15/+15/+15/+8 on four Income Tax Rules 2002 editions**, where 18-10-2016 gains `CHAPTER – IV` once and `CHAPTER – XV` **fourteen times** — a running page head, not fourteen chapters. That is correct for this metric: `chapter_lines` counts *lines* and `families.py` reads it as a floor (`chapter_lines=40`) meaning "prints chapter structure", which is why no family moved. **No parser change; `packages/` is byte-identical to `main` and nothing was re-converted** — a signature is measured from the source PDF, not from `output/`. No new gate: `run_tests_smoke.py:125` already runs `--check`, and the pre-round tree fails it while the post-round tree prints "no drift" | [artifact](../wip/phase3-round40-discovery-signatures.md) |

| q4 | **THIRD SCHEDULE Table-I still renders as prose** | open — the other half of FS-07 | **Not the `Col.(N)` defect and not closed by round 39.** Its header (p.90) is `S.No. Description of Goods Heading/ sub-heading Number` with **no numbering row at all**; the next line is data, `(1) Crude vegetable oil, …`, where `(1)` is a serial and not a column label. `find_table_spans` requires a numbering row because that is what makes the column count recoverable, so there is nothing to widen. Needs boundaries inferred with no numbering row — from the header's own word positions, or the data's left-edge clusters — which makes `find_table_spans` accept spans it rejects **everywhere** in the corpus today. **Size the blast radius before writing any of it** | — |
| q5 | port round 39's defects 2-4 to the `fbr_ingest` fork | open, low | `packages/fbr_ingest/tables.py` is the same file minus round 37's caption guard; the two forks have been drifting one round at a time. The `Col.(N)` spelling is measured **absent** from every document that fork parses (0 of 45 ordinance sources), so **defect 1 is deliberately not ported**. Defects 2-4 — the valley gutter, the reprinted header block, the page-crossing word order — are general to any multi-page gridless table and are the part worth porting. Unmeasured on that lane: census the ordinance sources for multi-page gridless tables first, or it is a no-op round | — |

### Closed by round 37 — the first row off the UNMEASURED surface

Not a board row: the board had none left. Round 37 came off the unresolved-marker census,
and it is the **first round in four where an invariant had something to say** — because a
document with zero footnote records passes every footnote invariant in the suite.

| # | pick this up | result | what it was | artifact |
|---|---|---|---|---|
| ~~u1~~ (r37) | ~~**Customs Rules 2001 — 665 unresolved markers, 0 notes**~~ | **665 → 0; 672 citations bound, 421 records** | **CLOSED 2026-09-14 (round 37).** The document prints **no per-page footnotes at all**. Its apparatus is printed ONCE at the end — `As Amended:-` on p561 and **158 numbered S.R.O. entries** to p563 — at **body size**. Three gates in `footnotes.py` each refuse a body-sized apparatus (`_size_zone_top` separates by size; `_is_marker_word` caps the marker at `footnote_marker_max_size` 9.0; `_is_amendment_note` wants an edit verb, and `S.R.O.247(I)/2002, - dated 08.05.2002.` has none), so the whole block read as body and rule **1122 (*Audit*)** swallowed 157 notification lines. Read as its own shape rather than by loosening three measured gates. **All 107 distinct cited markers are plain numbers inside 1..157 — nothing on this document was unresolvable.** The caption alone is not the gate: "as amended:-" is ordinary prose, so the cut also requires that ~every line below it is a numbered S.R.O. entry. **1 of 77 re-converted documents changed; the other 76 are byte-identical** | [artifact](../wip/phase3-round37-terminal-amendment-list.md) |
| ~~u1b~~ (r37) | ~~`footnote_on_citing_leaf` **0 → 1**, revealed by the above~~ | **back to 0, by code** | **The hit was real and it was NOT caused by the reader — it was revealed by it.** `tables.find_table_spans` extends a gridless table span on a **margin** test, and a *centred* CHAPTER caption sits to the RIGHT of the table's first column, so the test never fires. p102 folded `2&30 [CHAPTER XIV` and `TRANSSHIPMENT` into rule 325's last repeal row (`<td>S.R.O. 1319(I)/1996 2&30</td><td>24.11.1996 [CHAPTER XIV TRANSSHIPMENT</td>`); the caption's markers were registered as citations of leaf 325 while rendering as literal cell text, so the notes were attached to a leaf whose html shows no `<sup>`. `pagemodel` already guards the GRID path against exactly this; the gridless fallback now does too. **NOT fixed by it: `2&30 [CHAPTER XIV` is still not a structural boundary** — that is [row 14](#start-here--pick-one) | same artifact |

### Closed by round 36 — the last register-bearing row

Closed by **code**, and the register moved by **zero** — as it must: no invariant here can
see a marker-grammar change in either direction. The evidence is the output diff and the
control document, not the register.

| # | pick this up | result | what it was | artifact |
|---|---|---|---|---|
| ~~1~~ (r36) | ~~**note heads printed with a DOUBLE dot**~~ | **0 -> 254 citations bound** | **CLOSED 2026-09-14 (round 36).** `MARKER_NOTE_RE` read one trailing dot; the Customs source prints six note heads with two, so `parse_footnotes` opened no note and `footnotes.py:1242` folded each line into the PREVIOUS note's body -- the real note had no record, its neighbour carried prose that was never its own. Widened to `\.{0,2}`, and the uppercase branch to `\.{1,2}` with its dot still MANDATORY. **The board's own numbers here were wrong**: it said nine heads of which seven were real; the page says **six, all six real**. `130..`, `230..` and `2005..` x2 are mid-line `page NNN..` / `Act, 2005..` sentence-enders and can never reach a path that reads `words[0]` only, and **`39..` on p275 was missed entirely**. Mint measured over all 91 staged text-layer sources: 119 double-dot first words, 20 documents, all Customs, **0 false positives** | [artifact](../wip/phase3-round36-double-dot-note-head.md) |

### Closed by rounds 29-34 (PRs #93-#99) — kept so they are not re-picked

Five rows in one sitting, and **the register reached 0**. Read the middle column before
re-opening any of them, because the two halves are not the same claim:

| closed by | hits | where |
|---|---|---|
| **exemption with evidence** | **9** | ordinance stubs 3 (#97), acts 5 (#94), Sales Tax 2014 s.10 1 (#99) |
| **code** | **4** | ITO s.214E ×2 (#96, parser), rules 150 (#98, parser), rules 13 (#95, invariant) |

Nine of the thirteen are still *printed* — the runner reports them under its
`EXEMPT INVARIANTS` banner, and an exemption silences a whole invariant for a whole
document, so a fourth hit appearing on an exempted document is silent too. **"Register 0"
means nothing un-excused is failing. It does not mean the corpus is clean.**

| # | pick this up | hits | the single blocker | plan.md |
|---|---|---|---|---|
| ~~1~~ | ~~**letter-suffixed citation markers**~~ | **0 → 22 seen, 13 bound** | **CLOSED 2026-09-14 (round 35).** `grammar.MARKER` allowed `[a-z]` only, so 22 markers printed with an UPPERCASE suffix at 8.04pt rendered as literal body text and built no footnote record. Widened to `[A-Za-z]` on both sides of the join — the notes print `66A.` uppercase at 9pt, so no case-fold was needed. **Two classes:** `_MARKER_PARTS_RE` (`:139`) carried the same narrow class and feeds `marker_sort_key`, so widening `:132` alone would have left every uppercase note sorting to the end of the document. All 22 are now markers and 13 resolve; the 9 that do not are blocked by two source defects (the double-dot note head, row 1 above, and `36A`, which the source cites and never defines) | [artifact](../wip/phase3-uppercase-marker-suffix.md) |
| ~~2~~ | ~~**the ordinance five**~~ | **0** | **CLOSED 2026-09-14. The lane is at zero.** It was TWO causes: s.214E ×2 was a live parser bug (`4[“214E.`, quote glued into the bracket token), and ss.233AA + 122C ×2 are omitted sections with no printed body, exempted with evidence. The parser fix had to land FIRST — an exemption silences a whole invariant for a document, and the 30.06.2019 edition carried both | [P4-2](plan.md#p4-2--decide-the-fbr_ingest-fork--a-routing-problem) |
| ~~3~~ | ~~**Sales Tax 2014 s.10**~~ | **0** | **CLOSED 2026-09-14 by exemption. The acts lane is at zero.** It was NOT simply a live parser defect: the body prints `1[(10)`, a bare parenthesised code in an amendment bracket, and `_BRACKETPAREN_RE` refuses those for a **measured** reason (bare `CODE` once blocked THIRTY sections into stubs). A dash-gated widening was measured and would mint **83 phantom sections** inside s.2's definition clauses. The contents page cannot break the tie either — it has no ToUnicode mapping for `e` | [P3-1e](plan.md#p3-1--section_carries_its_body-17--four-unrelated-causes-one-of-them-closed) |
| ~~4~~ | ~~**Customs 2008 ss.181 / 189**~~ | 0 | **CLOSED 2026-09-14 by exemption.** The pages were read: the source misprints the code, `35.` for `181.` and `37.` for `189.`, at body size. **The same misprint hits s.185D as `36.` and no invariant sees it** | *(none yet)* |
| ~~5~~ | ~~the two rules hits~~ | **0** | **CLOSED 2026-09-14, and they were two different kinds of defect.** 30-06-2025 rule 150 was a *parser* defect — page xii prints `150 ZQR.`, a three-letter suffix that kept its dot, so the document shipped two leaves coded 150. 01-01-2025 rule 13 was an *invariant* bug — `_table_cell_lines` could not see a flattened table ROW, so a Schedule serial cell read as a section start. The rules lane is at zero | [P3-1e](plan.md#p3-1--section_carries_its_body-17--four-unrelated-causes-one-of-them-closed) |
| ~~7~~ | ~~the `ReviewToolbar` approval gate~~ | — | **CLOSED 2026-09-14.** Gate switched to `hasCriticalQualityFlags`, mirroring the backend's `CRITICAL_FLAGS`. One line plus two tests — see [the Result below](#the-reviewtoolbar-approval-gate--closed-2026-09-14) | [Deferred](#deferred-with-reasons) |

¹ **The rise-then-fall prediction this footnote used to make was WRONG, and round 35
measured it.** It said: the invariants share the parser's marker grammar, so expect the
register to rise when the invariant is widened and fall when the parser is. Widening
`_LEADING_AMEND_MARKER` to either case against the un-re-converted corpus moved the register
by **zero** — `inv_leading_marker_cited` fires only on a leaf that *opens* with an amendment
marker and renders no `<sup>` at all, and all 22 were inline, in leaves that already carried
citations. Round 21's 0 → 61 came from the **run form**, which does appear leading. The shape
is a property of that class, not of every marker-grammar class. Widen the instrument anyway —
one narrower than the defect cannot measure a future regression in it — but do not predict the
number from a different round's.

### Closed by rounds 21-28 (PR #89) — kept so they are not re-picked

| old row | was | now |
|---|---|---|
| the heading-terminator scan | 3 | **0** — `no_chapter_caption_in_section_heading` is gone from the register |
| the omission spellings | 2 | **0** — neither Customs 30.06.2024 s.196K nor 30.06.2025 s.79 is a hit |
| `preamble_carries_no_toc_tail` | 2 | **0** — the class is closed |
| `clause_codes_plausible` | 1 | **0** — closed by round 20's code, measured by round 21-28's re-conversion |

Rows 7-12 of the old board (the schedule PART reader, the CHAPTER en-dash, the cross-edition
index, the instrument tree, `--profile auto`) were closed by round 20 and are dropped from
the ranking rather than carried as zeroes. Their Results are still below.

### Traced but not taken — evidence recorded, no row opened

Found on 2026-09-10 while tracing the rounds 21-28 leftovers. Each is a **different cause**
from row 1, and this file forbids batching unrelated causes into one round:

- **s.156's `69.` and `81,`** — the two cells the rounds 21-28 handoff called "penalty-table
  marker cells". Its named cause was wrong: `pagemodel._true_table_marker` is never reached
  (that table is not grid-extracted; its `<tbody>` is empty). `69.` dies on the trailing-dot
  guard (`pagemodel.py:152`), `81,` because `_MARKER_RUN_SEP_RE` splits `"81,"` into
  `['81','']` and the empty tail fails `MARKER_RE` (`grammar.py:257`). The printed run is
  `81, 89` with a space, so the comma dangles. `grammar.MARKER_PREFIX` already tolerates
  this shape — but only for the section-heading prefix.
- **`1b[(7)` in s.185A** — the genuine part-marker/part-text token. `_render_words`
  (`builder.py:240-259`) treats a word as all-marker or all-text; there is no partial-consume
  path. The handoff ascribed this to s.2, whose cross-reference **renders correctly today**.
- **`pagemodel.CITE_SENT_RE_TEXT` is dead code.** Nothing consumes it; the live pattern is
  the hand-duplicated `builder.py:726` `_CITE_SENT_RE`, with a third looser copy at `:845`.
  Any widening has to touch the copies that run.
- **Chapter V footnotes 42 and 66** — source defects (66 is never printed, the block runs
  65 → 67; 42 is printed indented under 41's quotation). **They cannot be exempted**: an
  exemption keys on `applies_to` + `invariant`, and no invariant reports a missing footnote.
  Recorded here because "fixed, or exempted with evidence" has no third state for a defect
  no instrument can see — which makes this an argument for an instrument, not for a waiver.
- **s.29's mid-title bracket** — `Restriction on amendment of [goods declaration`. Round 21's
  strip (`builder.py:3114`) is anchored `^[\s\[(]+`, so a mid-string bracket never reaches
  its count test. Cosmetic.

Added 2026-09-14 while tracing round 37. Both were read on the page; neither is batched into
that round, and the first is big enough to have its own row (14) on the board:

- **`builder._STRUCT_DECOR_RE` reads ONE marker, not a run.** `^(?:[\d*]{1,3}\s*|\[+\s*)+`
  (`builder.py:2331`) stops at the `&` in `2&30 [CHAPTER XIV` (Customs Rules 2001 p102), so
  that caption is not a structural boundary anywhere in the parser and CHAPTER XIV is absent
  from the tree. **Round 37 did NOT fix this** — it only stopped the caption being eaten by
  the repeal table above it. Widening the decor class is a **boundary** change across all 187
  sources; it is row 14, not a one-line patch.
- **A quoted, mixed-case chapter caption.** The same document prints `“Chapter XX` on p163 —
  left double quotation mark, and `Chapter` rather than `CHAPTER`. `34[CHAPTER XXI`, four
  lines below it, IS recognised, which is the control. Same shape as the ordinance
  `4[“214E.` defect PR #96 closed, on a different code path. Part of row 14.
- **`footnote_on_citing_leaf` cannot see a note attached to a leaf that displays no
  citation** *until* the document has notes at all. Not a defect in the invariant — it is the
  reason round 37's hit had been invisible since the corpus was staged. See
  [`working-rules.md`](working-rules.md#measuring).

**Before touching any of them, read [Rules of engagement](#rules-of-engagement).** Every
rule there was paid for, and three of them have drawn blood twice.

### How this reconciles to `wip/tasks.md`

The unchecked boxes in `wip/tasks.md` map onto the rows above exactly. `wip/` is frozen,
so its box for `section_codes_ordered` (`:664`) is still unticked there — **round 15
closed it**, and this file is the authority on that, not `wip/`.

| `wip/tasks.md` line | row above |
|---|---|
| `:664` `section_codes_ordered` | **CLOSED, round 15.** It said **4** hits, the register said **3**, and it is now **0** |
| `:401` container-code guard | **CLOSED, round 17.** 14 gained, 0 lost, register unchanged |
| `:418` CHAPTER letter suffix | **CLOSED, round 18.** 80 lines over 24 documents to 0; register unchanged |
| `:436` `section_carries_its_body` — now **12** | rows 2, 3, 5 (one box; round 16 closed one cause, round 19 exempted the round-10 residue, rounds 21-28 closed the omission spellings) |
| `:388` heading-terminator scan | **CLOSED, rounds 21-28.** The class is 0 |
| `:379` `preamble_carries_no_toc_tail` | **CLOSED, rounds 21-28.** The class is 0 |
| `:668` `clause_codes_plausible` | **CLOSED, round 20, measured rounds 21-28.** The class is 0 |
| `:712` decide `fbr_ingest` · `:430` its dormant copies | 8 (two boxes) |
| `:503` no invariant sees a 93% loss | 10 |
| `:741` `:742` `:743` `:744` the four Phase 5 limbs | 11 (four boxes) |
| `:701` `--profile auto` default | 12 |
| `:184` OCR · `:190` the 9 provisional · `:192` the ordinance 10 | 13 (three boxes) |
| `:536` `convert_all.py` cannot resume · `:671` the 29 low-confidence documents · `:79` rebuild api/worker images | [Deferred](#deferred-with-reasons) (three boxes) |

The schedule PART reader and the CHAPTER en-dash separator had no box in `wip/` at all —
round 17 and round 18 located them as new work, and round 20 closed both. The three
integration leftovers (rows 6-8 above) come from `wip/integration/tasks.md`'s own ledger,
not from `wip/tasks.md`.

Recounted 2026-09-10: **5 register-bearing rows + 3 integration leftovers + the OCR decision
= 9 open things**, down from 22. Four of the register rows are 1-2 hits each on unrelated
single documents, which is the shape `open-work.md` predicted for the tail.

---

## Rules of engagement

The full set, because this is the file an agent actually opens. Long-form reasoning:
[`working-rules.md`](working-rules.md).

### Never

- **Never commit to `main`.** One branch and one PR per unit of work.
- **Never edit `packages/` while a conversion runs.** `convert_all.py` spawns a fresh child
  per document, so each imports the parser *when it starts*; an edit mid-run gives early
  documents the old code and later ones the new. **A mixed-revision corpus looks
  completely normal.** Done twice in one session, ~30 minutes each. Kill and restart.
- **Never run `make convert-all` to "re-convert the lane".** It converts the whole **lane**,
  not the corpus: `LANE=ordinance` targets all 46 ordinance PDFs where only 12 are in the
  corpus — quadrupling it and pushing 34 new documents at the portal. **The same gap exists
  on acts (80 of 93).** Convert **per file with an explicit `-o`**:
  ```sh
  make convert-acts PDF="data/corpora/acts/<...>.pdf" OUT="data/corpora/acts/output/<...>.json"
  ```
  (`Makefile:51-53`; `OUT=` becomes `-o`. `convert-all` is `Makefile:58-60`.)
- **Never weaken `clause_codes_plausible`** to clear its one hit.
- **Never lower `detect_toc_pages`'s `rows >= 3` floor** — its own comment
  (`calibrate.py:288-297`) records a lower one swallowing the Income Tax Rules' body title
  page.
- **`test_the_letter_suffixed_chapter_gap_is_still_open` does not exist.** Round 18 spent it.
  The rule it carried — *a pin that asserts the current wrong answer is a signal, not a test
  to repair* — still holds, and the pins that carry it today are
  `tools/tests/test_structural_boundary_agrees_with_grammar.py` (`BOUNDARIES:36`,
  `NOT_BOUNDARIES:67`) and `tools/tests/test_suffixed_chapter_cuts_the_section.py`.
  `KNOWN_GAP_SUFFIXED_CHAPTERS` is gone too. Verified 2026-09-14: `grep` over `tools/` and
  `packages/` finds neither name.
- **Never let `data/ocr_cache` grow** until OCR is deliberately taken in scope.
- **Never edit `wip/`.** It is the historical record, and shipping code cites it —
  `tools/convert.py:88`, `tools/discover_corpus.py:423`,
  `packages/legal_ingest/families.py:98,183`, `_common.py:1098,2163`, and 4 exemption
  entries name `wip/tasks.md` as their expiry condition.

### Conversion

- **`convert_all.py` cannot resume.** Two runs killed mid-flight left 49 of 80 acts
  documents at the new revision — the mixed-revision hazard above. **`--skip-existing` does
  not help**: after a re-conversion every output exists. What worked was converting only
  outputs older than the parser's mtime.
- **Nineteen source files have no `.pdf` extension**, not two. This rule used to name
  only Customs Rules 2001 and The Finance (Supplementary) Act 2022; a round-16 walk of the
  three lanes counts **6 in acts, 12 in rules, 1 in ordinance**, including five Customs Act
  editions and four Sales Tax Rules 2006 editions. A `**/*.pdf` glob misses every one of
  them **silently** — and so does the obvious repair `name.endswith(".pdf") or "." not in
  name`, because these names carry a dot in their *date* (`Customs Act, 1969 as amended up
  to 30.06.2021`). Sniff the file, or list the directory; do not pattern-match the name.
- **`make convert-*` from a worktree runs the WRONG interpreter.** The Makefile sets
  `PYTHON := $(ROOT)/.venv/bin/python` only `ifneq (,$(wildcard $(ROOT)/.venv/bin/python))`
  and `ROOT` is the *worktree*, which has no `.venv` — so it silently falls back to
  `python3` and dies on `ModuleNotFoundError: No module named 'pdfplumber'`. Pass the main
  tree's interpreter explicitly:
  ```sh
  make convert-rules PYTHON=/Users/muhammad.husnain/Downloads/code/crx/.venv/bin/python \
    PDF="…" OUT="…"
  ```
  It still imports `packages/` from the worktree — that part is right, and it is the whole
  point of converting from there.
- **A worktree has no corpus, and `tools/*.py` resolve everything from `__file__`.**
  `data/corpora/*` is gitignored, so a fresh worktree holds only its README — and because
  both the import root and the corpus root come from `__file__`, running a tool from the
  main tree measures **main's** parser while running it from the worktree finds **no
  documents**. Symlink the lanes in once, with **absolute** targets:
  ```sh
  for L in acts rules ordinance; do ln -sfn "$PWD/data/corpora/$L" .worktrees/rN/data/corpora/$L; done
  ```
  (A relative `../../../` from `.worktrees/rN/data/corpora/` lands in `.worktrees/`.)
- **The Bash tool's cwd resets between calls — use absolute paths in every edit.** In
  round 15 a heredoc with a relative path patched `packages/` in the **main tree**; half
  the change landed on the wrong branch and the measurement silently used unfixed code.
  `git status` in **both** trees before trusting a number.
- **Clear `__pycache__` after any mutate-and-restore verification.** Patching a module,
  re-importing and restoring leaves stale bytecode: the source is right while the module in
  memory is the version you rejected. Caught by pytest only *after* a re-conversion had
  already run against it.
- `--profile auto` is **refused on ordinance** up front (`convert_all.py:486`).

### Measuring

- **Measure the invariant fix and the parser fix separately**, on identical JSON for the
  first. Nearly every class is part wrong-invariant, part real defect, and a single total
  hides both. `no_footnote_text_in_body` was 45 hits that were *all* a `title=` attribute —
  concealing a 473-footnote defect underneath.
- **Measure candidate widenings as gained/lost — and know which corpus you are measuring.**
  A naive `MARKER_PREFIX` widening scored **1 fix : 17 false positives**; the narrowed form
  scored **1 : 0**. But every measurement here runs over `output/*.json` `plain_text`, and
  **that is not what the parser sees**: the parser's line is `42 53 [202B.` where the
  rendering collapses it to `42 53[202B.`. A lookahead anchored on `[` matched the JSON and
  missed the PDF.
- **Verify a lock by removing the fix.** A parenting lock passed with the fix stubbed out —
  its two-chapter fixture let a later pass repair the damage; three chapters reproduced the
  real document. **A gate that cannot be made to fail on purpose is not a gate.**
- **Report changes that moved a number by zero.** Round 4's acts lane and round 6's PART fix
  were both correct and both scored nothing; folding them into a total would have
  misattributed the rounds that did move it.
- **A cached artifact cannot tell you its generator is wrong.** Three instances in one
  phase. Only the `exemptions/` format reported itself stale, unprompted. That is the
  argument for the register snapshot.
- **Read the comments before generalising.** `_DOTSUFFIX_RE` (`builder.py:1424-1430`)
  carried a measurement saying its bracket gate was safe; re-running it showed the
  measurement had expired — but it was still right about the danger.
- **The obvious generalisation is often wrong.** `XIVA` and `XIV-A` are two *different*
  chapters of Sales Tax Rules 2006; matching numerals by value collapses them.

### The seam to the portal

- **A parse-only change does not travel.** `create_version` gates on `source_hash` — the
  JSON *bytes* — so editing `json_parser` / `parse_quality` / `html_sanitizer` reaches no
  existing row on re-sync, **`--force` included**. Measure it as two fresh first-ingests
  into a scratch database (`wip/integration/measure/p5_seam.py`, scratch DB
  `pdf_qa_p5scratch`), never as a re-sync of an existing one.
- **The local dev database is many rounds stale.** An acts document never re-converted and
  never re-synced has **304 of 309** stored leaves differing from a fresh parse. Any
  carryover or approval-loss number measured against it is an artefact of its age.
- **Run the whole web suite, against its baseline.** From `apps/web`: `npm run test` (or
  `npx vitest run`) is **17 failed here, always**, in `libraryFavorites` and `libraryPage`
  (Node 26 wants `--localstorage-file`; CI pins 22). Diff against that baseline — do not
  skip the suite, and **do not run only the files you touched**: that misses the ones that
  *consume* them, which is how #75 shipped a red build.
- **The Northflank deploy is outward-facing and gated on green CI on `main`.** Confirm
  before triggering it.

### Gates and lint

- **CI does not gate the pipeline.** `data/corpora/*/output/` is gitignored, so all three
  lane suites SKIP on CI. Seven rounds moved the register 210 → 64 with nothing enforcing
  those numbers but prose. **Green checks on a PR are not evidence about ingest.**
- **`tools/tests/test_register_snapshot.py` is the real gate**, and only where the corpus is
  staged. It scrapes suite stdout (`:34`), so **changing `tools/suite/runner.py:110`'s print
  format breaks it silently.**
- **Run `ruff check` bare.** `pyproject.toml`'s `src = ["apps/api", "packages", "tools"]` is
  what pulls `packages/` in; `ruff check apps/api tools` silently misses it. `Makefile:80-92`
  and `ci.yml` both run it bare — match them.
- **A regression case should assert the property it names, not the markup.** Two cases were
  pinned to an attribute-free `<p>` that the current parser classes; `re.search` made the
  fix two characters each.
- **Every behaviour change ships with the test that fails without it, in the same PR.**

### And the one that governs all of it

**Fixed, or exempted with evidence traced to the source PDF. There is no third state.**
"Tracked and deferred" without an entry in `tools/suite/exemptions/<lane>.json` is a red
gate, not a decision.

---

## How a round runs — worked for round 18

Copy this. Do not invent a variation.

```sh
# 1. Branch. Use a worktree -- the tree is shared with peer sessions.
git worktree add .worktrees/r18 -b fix/phase3-round18-<slug> main
cd .worktrees/r18

# 2. Baseline, before touching anything. The corpus lives in the MAIN tree
#    (data/corpora is gitignored, so a worktree has no copy) -- run suites from there.
cd /Users/muhammad.husnain/Downloads/code/crx
for L in acts rules ordinance; do .venv/bin/python tools/run_suite.py $L > /tmp/pre-$L.txt; done   # 1 / 2 / 5 today

# 3. Snapshot the outputs you are about to overwrite.
mkdir -p data/corpora/acts/output/_pre_18 \
  && cp data/corpora/acts/output/*.json data/corpora/acts/output/_pre_18/

# 4. Write the failing test FIRST, then the fix. Confirm the test fails without it.
.venv/bin/python -m pytest tools/tests/<the new test> -q      # must be RED

# 5. Re-convert ONLY the affected documents, per file, explicit -o. Never convert-all.
#    PYTHON= is REQUIRED from a worktree -- see the Conversion rules.
make convert-acts PYTHON=/Users/muhammad.husnain/Downloads/code/crx/.venv/bin/python \
  PDF="data/corpora/acts/<...>" OUT="data/corpora/acts/output/<...>.json"
#    Do not edit packages/ while this runs. Mind the 19 files with no .pdf extension.

# 6. Re-measure ALL THREE lanes -- a fix in one lane can move another.
for L in acts rules ordinance; do .venv/bin/python tools/run_suite.py $L; done   # 1 / 2 / 5

# 7. Regenerate the register IN THIS PR. No Make target, no pytest flag.
.venv/bin/python tools/tests/test_register_snapshot.py --write

# 8. Full gate.
.venv/bin/python -m pytest tools/tests -q     # baseline: 231 passed, 1 skipped
.venv/bin/ruff check                          # BARE
du -sh data/ocr_cache                         # must still be 0B
cd apps/web && npm run test                   # only if you touched the portal; 17-failed baseline
```

Then: write the round artifact as `wip/phase3-round18-<slug>.md`
— **a new file; do not edit existing `wip/` files** — following the shape of
`wip/phase3-round17-container-code-guard.md`: what was measured, what moved, what moved
by **zero**, and what was rejected and why. Open **PR #84** with the before/after
artifact linked in the body.

**If the register improved, `test_register_snapshot.py` fails until step 7 is done.** That
is the design, not a bug.

---

## The tasks

Each carries: what it closes · **Steps** · **Definition of done** · **Do not** ·
**Result** (empty until it lands).

**The numbers here are stable anchors, not the ranking.** Sections are never renumbered —
three of them are closed rounds that other files cite — so they drift from the *Start
here* table as rows close. Current mapping:

| Start here row | section below |
|---|---|
| 1 letter-suffixed citation markers | *none yet* — closed by round 35; the double-dot row beneath it by **round 36** |
| 2 the ordinance five | [11](#11-decide-the-fbr_ingest-fork--unblocks-5-hits-and-9-documents) |
| 3 the single-document remainder | [9](#9-the-single-document-remainder--7-hits) |
| 4 Customs 2008 ss.181 / 189 | **CLOSED 2026-09-14** — see the acts-exemptions Result below |
| 5 the two rules hits | *none yet* |
| 12 the OCR decision | [15](#15-the-ocr-decision--blocked-needs-a-human) |

Closed: section [1](#1-trace-section_codes_ordered--3-hits-acts--closed-round-15) (round
15), [2](#2-the-stsp-58u58v-pair--4-hits-rules--closed-round-16) (round 16),
[4](#4-the-container-code-guard--0-hits-an-enabler--closed-round-17) (round 17),
[3](#3-the-chapter-letter-suffix--57-hits-24-documents--closed-round-18) (round 18),
[5](#5-the-round-10-rules-residue--3-hits-an-exemption-row) (round 19),
[12](#12-the-cross-edition-index--a-new-instrument), [13](#13-the-instrument-tree-level--phase-5-4-limbs),
[14](#14---profile-auto-as-the-default--blocked) (round 20), and
[6](#6-the-heading-terminator-scan--3-hits-acts), [7](#7-the-omission-spellings--2-hits-acts),
[8](#8-preamble_carries_no_toc_tail--2-hits-acts), [10](#10-clause_codes_plausible--1-hit-finance-act-2024)
(**rounds 21-28** — code from round 20, measured by the round-27 re-conversion).

### 1. Trace `section_codes_ordered` — 3 hits, acts — **CLOSED, round 15**

**Closed by PR #81 (round 15).** Artifact:
`wip/phase3-round15-chapter-numeral-pairing.md`. Kept here because what it found
contradicts what this row predicted, and the next rows inherit that.

**Result** — register **32 → 29**; `run_suite.py acts` **18 → 15**; the invariant is
**0 — the class is closed**, the sixth to close. rules and ordinance moved by **zero**.

**No hit was what this row assumed.** The row said *"decide per hit: parser defect (the
code was misread) or printed defect"*, and expected `tools/suite/exemptions/acts.json` to
be created. **All three source pages are correct, no code was misread, and that file
still does not exist.** Not one section code was wrong — three *chapters* were mislabelled,
and the invariant could only see the consequence: sections walking backwards because
their container sorts elsewhere.

| document | hit | the page says | was parsed as |
|---|---|---|---|
| Customs 1969 30.06.2025 | `'9' after '119'` | contents p3: ss.9-11 under `CHAPTER III` | `CHAPTER XI` / WAREHOUSING |
| Sales Tax 1990 01.07.2014 | `'3' after '32AA'` | body p51: `Chapter-VI` | `CHAPTER I` / PRELIMINARY |
| Sales Tax 1990 01.07.2014 | `'22' after '75'` | body p81: `Chapter-IX` | `CHAPTER III` / REGISTRATION |

**Two causes, one shared endpoint.**

1. **`toc.py`, the CHAPTER branch of `parse_toc`.** A chapter row did not close a section
   row that printed **no folio at all**. Customs' contents print `3F Hiring of technology
   specialists…` with no page number; `SECTION_NOPAGE_RE` parks it in `pending_page` for
   its wrapped title and nothing cleared it, so `CHAPTER III`'s caption was offered to
   s.3F, correctly judged foreign to it, and opened as a chapter of its own. **`CHAPTER
   III` came out twice** — a coded shell beside a numeral-less node holding III's caption
   and its sections. `_open_caption_chapter` resets all three state variables; this branch
   reset two. **The fix is the third.**
2. **`pipeline.py`, `insert_missing_body_chapters`.** `zip(empties, unused)` paired
   leftover numeral-less nodes with leftover body numerals **by list position**, which is
   right only if the two lists correspond one-to-one. They need not. Replaced with pairing
   by **which body span actually prints that node's own sections**, reusing
   `_codes_in_span`, already defined in that function.

**Leaf counts unchanged** — 325 and 116. Sections changed container; none was gained or
lost. That is the check round 13 failed (127 → 126).

**Scope was measured, not guessed.** Each acts/rules document's contents were parsed twice
at the same commit, fix on and fix off, and compared: **8 documents change, 7 more carry a
code-less chapter (cause 2's only reach), 76 are provably untouchable.** Those 15 were
re-converted; **0 failures, 0 refusals**. 10 of the 15 moved by **zero** and are reported
as such. **The ordinance lane cannot be reached by either fix — it runs `fbr_ingest`,
which has its own `toc.py` and its own `insert_missing_body_chapters`.**

**What was rejected:** an exemption (no printed defect exists); widening
`_captions_match`'s 3-word floor to 2 (a 2-word coincidence would bind chapters across 103
documents — the floor is untouched, the fallback beneath it was the defect); reparenting by
page order (tree-walk and page order legitimately disagree on 21 of 103 documents, which
is P5's reading-order limb); porting either fix into the `fbr_ingest` fork (row 9's call).

---

### 2. The STSP 58U/58V pair — 4 hits, rules — **CLOSED, round 16**

**Closed by PR #82 (round 16).** Artifact: `wip/phase3-round16-bracketed-code-dot.md`.
Kept here because the row's prediction was right about the cause and wrong about its reach,
and rows 1–7 inherit both halves of that.

**Result** — register **29 → 25**; `run_suite.py rules` **9 → 5**; both editions
**ALL PASS**. acts and ordinance moved by **zero**. `section_carries_its_body` is
**21 → 17** (acts 8, rules 4, ordinance 5) — one of its four causes closed, the class is not.

**The row said "one cause, two editions", and that was right.** S.R.O. 188(I)/2015
*renamed* rules 59 and 60, so both editions print the code inside the amendment bracket
with the dot outside it:

```
111[58U]. Application:--The provisions of this Chapter shall apply to
112[58V]. Conditions and limitations for availing zero-rating facility:--(1)
```

**It was a misread, not a miss.** `_BRACKETED_DOTLESS_RE` — the last pattern
`builder._candidate_code_raw` tries — backtracks `CODE` to its digits and reads the suffix
letter as the title's first capital, so `111[58U].` returned the code **`58`**, a real rule
of Chapter IX forty pages earlier. 58U and 58V bound to nothing and their 5,534 characters
were carried onto 58W, which pushed 58W's own text onto 58X. One new pattern,
`_BRACKETED_CODE_DOT_RE` (`builder.py:1383`), tried before the one that reads the shape
wrongly.

**Leaf counts unchanged** — 92 and 88. The only text delta is 83 characters per edition,
and it is the *deletion* of the two placeholder headings the empty leaves carried. Nothing
moved in or out. Conservation is 100.000% / 0 missing on both documents **before and
after** — a multiset audit cannot see a placement error, which is worth knowing before
trusting one again.

**What the row did not predict: the same shape is in a third document.** Rules 19D–19G of
**Income Tax Rules 2002 print it in all six editions** and all four currently read as rule
`19`. This fix repairs them. **None was converted** — that document has no
`output/*.json`, and converting it would push six new documents into the corpus and at the
portal. They score zero here and are the row-1 lesson in miniature: *the fix's reach and
the corpus's reach are different numbers.*

**Scope was measured over the source, not the output.** 290,982 distinct text lines from
every PDF in the three lanes, scored against `main`'s `_candidate_code`: the shipped form
**gains 0 and changes 12, all 12 correct.** Read with a bare `CODE` instead of
`CODE_SUFFIXED` it also gains a penalty **table row serial** — Sales Tax 01.07.2014's
`2[21].Where any person repeats an offence`, inside s.33's table, forty pages past s.21.
The letter suffix is the guard.

---

### 3. The CHAPTER letter suffix — 57 hits, 24 documents — **CLOSED, round 18**

`_STRUCTURAL_RE` (`packages/legal_ingest/builder.py:2104-2106`) has a CHAPTER branch of
`CHAPTER[\s\-]+[IVXLC0-9]+` — **no letter-suffix class, where PART and Division beside it
both carry `[A-Z]{0,2}`.** Measured at 57 hits / 24 documents / **zero false**.

**Steps**
1. Widen the CHAPTER branch's numeral to carry the same suffix class as PART and Division.
   Read the measured comment at `:2085-2103` first — it explains why PART and Division stay
   on `\s+`.
2. Run `tools/tests/test_structural_boundary_agrees_with_grammar.py`. **It will fail at
   `:90-96`. That is the signal.** Move the four lines from `KNOWN_GAP_SUFFIXED_CHAPTERS`
   (`:63-65`) into `BOUNDARIES` (`:35-39`), as the assertion message itself instructs.
3. Check `test_a_boundary_the_split_cannot_read_would_become_a_nameless_division`
   (`:112-123`) still passes — every `BOUNDARIES` line must split to a keyword plus a
   non-empty numeral, or it silently becomes a nameless Division.
4. **Re-convert 44 documents**, per file, explicit `-o`, 20 of them Customs editions.
   Budget for this; it is the reason the row was deferred.
5. Re-measure all three lanes. **Expect the register to rise before it falls** — these 57
   were invisible to the invariants, so making the boundary readable exposes them.

**Definition of done** — the four gap lines are in `BOUNDARIES`; the whole
`test_structural_boundary_agrees_with_grammar.py` is green; all 44 documents are at one
revision; the register is regenerated and the *net* movement is written down with the rise
and the fall reported separately.

**Do not** — do not port this to `packages/fbr_ingest/builder.py:1395-1397` in the same PR.
That fork is gated on [P4-2](plan.md#p4-2--decide-the-fbr_ingest-fork--a-routing-problem)
and measured at zero additional hits. Do not match numerals by value: `XIVA` and `XIV-A`
are two different chapters of Sales Tax Rules 2006.

**Result** — **CLOSED, round 18** (PR #84). Artifact:
`wip/phase3-round18-chapter-letter-suffix.md`. 80 swallowed boundary lines across
24 documents to 0; register unchanged at 25. Round 20 later closed the en-dash
gap on the same line.

**Closed by PR #83 (round 17).** Artifact:
`wip/phase3-round17-container-code-guard.md`. Kept here because half of what this row
gave as its justification turned out to be false, and because the *other* half reproduced
round 13's number exactly.

**Result** — the guard exists, the PART separator widening shipped behind it, and it
measures **14 gained / 0 lost** — round 13's number, four rounds later. The register is
**unchanged at 25** (15 / 5 / 5), which is what "0 hits, an enabler" predicted, so
`register.json` needed no regeneration. Five rules-lane documents re-converted.
Conservation is identical off vs on on all five, Customs Rules 2001's output
**byte-identical** but for its timestamp.

`is_structural_boundary` takes an optional `container_codes`; `_part_codes_in_scope`
resolves them per entry from the container tree, including **ancestors** — the caption a
missing cut swallows belongs to the part the *next* section opens, so rule 87's own
container `PART I` is not enough and the walk has to reach CHAPTER XI. Three callers
(`discover`, `preamble_refs`, `pipeline`) deliberately pass nothing and keep the
pre-round-17 answer; `discover` especially, because vouching a line with a container built
from that same line would be circular.

**What separated the two populations was never the spelling of the line.** Sales Tax Rules
2006 (01-01-2025) prints both — five real `PART-N` captions under CHAPTER XI, which holds
those parts, and form STR-11's two inside rule 165 under CHAPTER XVIII, which holds none.
One document, so neither an exemption nor a per-document rule could have told them apart,
and **a document-wide set of part codes would have vouched for the form.** Per-chapter was
load-bearing, not tidiness.

| document | candidates | cut | kept |
|---|---|---|---|
| Sales Tax Rules 2006 (01-01-2025) | 7 | **4** | 2 × STR-11, 1 × en dash |
| Sales Tax Rules 2006 (30-06-2025) | 5 | **4** | 1 × en dash |
| Customs Rules 2001 (30.06.2023) | 5 | **0** | rule 34's form, 0 parts in tree |
| STSP Rules 2007 × 2 editions | 3 + 3 | **6** | — |

> **Step 4 of this row was wrong, and so is `plan.md` P3-4's second bullet.** The guard
> would **not** have kept round 13 from dropping Customs Rules 2001's four chapter
> captions. Extending it to the CHAPTER branch moves conservation 74.087% → 74.099%, and
> **all 28 of those tokens are a duplication**: `preamble_refs` passes no codes, so the
> preamble's `CHAPTER I` line stops being a boundary, the preamble no longer ends there,
> and it swallows the caption *plus rule 1's opening text, which rule 1 still holds*. Not
> one leaf changed. The multiset audit only checks presence, so it scored the second copy
> as a recovery. Round 13's preamble leak, re-created and reported as a success.
>
> Even with the preamble side fixed it would be a bad trade: three of Customs Rules 2001's
> 44 chapters have no node, and putting their heading lines back into bodies raises
> `no_structural_heading_in_body` from **0** to buy 32 words on the one document already
> carrying four Phase-5 exemption entries. **Those captions are Phase 5, not this guard.**

Also rejected, measured: **widening the class to en/em dashes gains zero.** `PART – IV`
appears in both Sales Tax Rules 2006 editions and is why the count is 14 and not 16 — but
neither edition's CHAPTER XI holds a `PART IV` node, so the guard refuses both anyway.

**Locked by** `tools/tests/test_hyphenated_part_needs_a_container.py` — 3 cases, all
through `build_sections` on byte-identical body lines where only the container tree
differs. Each of the three ways to break it fails a different case, **including the
wiring**: hand `_build_one` a `frozenset()` and every unit test of the predicate alone
still passes while the gain is silently zero. That is why the test does not call the
predicate.

---

### 5. The round-10 rules residue — 3 hits, an exemption row — **CLOSED, round 19**

Sales Tax Rules 01-01-2025, each already traced to a **printed** defect: 44A opens with a
left double quote; 150ZQZI is printed `150ZQZl` (lowercase L for capital i); 150W's code
appears only in a footnote.

**Steps**
1. Re-confirm each against the source page — the traces exist but the pages are the
   authority.
2. Write three entries in `tools/suite/exemptions/rules.json` (10 entries today), each
   quoting the page and its printed text. Follow the shape of `:17-21`.
3. Give each an **expiry condition** where one exists. `150ZQZl` is an OCR-class defect and
   may expire on the OCR decision; the other two are permanent printing errors.

**Definition of done** — register total **−3** by exemption; `tools/tests/test_suite_exemptions.py`
green; each entry names the page it was traced to.

**Do not** — do not widen the parser to accept a left double quote as a code prefix, and do
not "fix" `150ZQZl` by collapsing `l`→`I`. Both make the parser wrong about correct
documents to be right about a broken one.

**Result** — **closed by PR #85 (round 19).** Register **25 → 22**, one exemption entry
covering all three hits (the format keys on `applies_to` + `invariant`, so three separate
entries for one pair is not a shape it has). `register.json` regenerated in the PR.

All three re-confirmed against the source pages, and **two of the three traces above were
wrong**:

| hit | this file said | the page says |
|---|---|---|
| 44A | opens with a left double quote | **correct** — p.66 prints `“44A. -Selection and conduct of audit.-(1)` |
| 150W | "code appears only in a footnote" | **wrong** — p.109 prints `228[50W. Audit.--`, the leading digit **dropped**, while its contents row on p.10 reads `150W. Audit` |
| 150ZQZI | printed `150ZQZl`, an **OCR-class** defect that "may expire on the OCR decision" | spelling **correct** (p.151), expiry **wrong** — `source_kind` is `native-digital`, so this document is never OCR'd and the defect **can never expire on that decision** |

The 150ZQZI trace also gained the argument that makes it un-fixable rather than merely
awkward: **p.152 carries a genuinely different rule, `150ZQZL. Right granted to the
licensee`**, so collapsing `l`→`I` would collide two real rules. (Its contents row on p.13
also prints the typo `liceensing`, which is where the leaf's heading comes from.)

Entered with **no expiry**, and the three hits are **enumerated in the reason on purpose**: a
fourth hit on this document would be a new defect the entry does not describe.

---

### 6. The heading-terminator scan — 3 hits, acts

`_find_heading_split` (`builder.py:2245`, called `:2911` from `_build_one` `:2827`) looks
four lines ahead for a terminator and stops at a grid table but **not** at a structural
heading, so an omitted section borrows the next section's terminator.

**Steps**
1. Read `wip/phase3-round13-chapter-hyphen.md` first. It contains the measurement that
   kills the obvious fix.
2. Reproduce: the heading comes out
   `*** Chapter-VII OFFENCES AND PENALTIES 33. Offences and penalties` across three Sales
   Tax editions — the whole 32AA cluster of `no_chapter_caption_in_section_heading`.
3. Design an **omission-aware fallback**: when the borrowed terminator is refused *and* the
   section is an omission, open the section on the omission itself.
4. Verify by leaf count, not just by the register: round 13's guard took a document 127
   leaves → **126**, losing section 32AA outright.

**Definition of done** — register **−3**; the 32AA cluster gone from
`no_chapter_caption_in_section_heading` (4 → 1); **leaf count unchanged or higher** on all
three editions; a test that fails without the fallback.

**Result** — **CLOSED, rounds 21-28** (PR #89). The parser shipped in round 20: an
omission-aware fallback, so when the borrowed terminator is a structural boundary / next
code / TABLE caption and the current line is an omission, the leaf opens on that line.
Locked by `tools/tests/test_omitted_heading_stops_at_boundary.py`. **Round 20 could not
measure it** — the three Sales Tax editions were not on that host. The round-27
re-conversion put them at one revision and the class went to **0**:
`no_chapter_caption_in_section_heading` is gone from the register entirely (was 4).

---

### 7. The omission spellings — 2 hits, acts

Customs 30.06.2024 s.196K prints `to Omitted 96u`; 30.06.2025 s.79 prints `A O mitted` —
an intra-word space round 3 measured and refused to admit into a regex whose job is
precision.

**Steps**
1. Re-measure the tolerance now the count is 2 and each can be traced individually — round
   3's refusal was correct *at 37 hits*, where a false positive was expensive.
2. If a bounded intra-word-space tolerance still measures false positives, this is an
   exemption row instead. Either outcome is a valid close.

**Definition of done** — register **−2**, by fix or by exemption-with-evidence; if by fix,
a gained/lost measurement showing 2 gained / 0 lost.

**Do not** — do not admit a general `\s*` between every character of `Omitted`. That is the
form round 3 measured and rejected.

**Result** — **CLOSED, rounds 21-28** (PR #89). The invariant widened in round 20:
`_is_omission` accepts only the whole-string forms `"to Omitted 96u"` and `"A O mitted"`,
with no general `\s*` between letters — the form round 3 measured and rejected. Round 20
could not measure it because neither Customs edition was staged. Both are now converted at
one revision and **neither is a hit**. Note this row's own instruction — "if a bounded
tolerance still measures false positives, this is an exemption row instead" — was never
needed: the whole-string form cost nothing.

---

### 8. `preamble_carries_no_toc_tail` — 2 hits, acts

Customs 30.06.2008 and Sales Tax 30.06.2023 each have a contents tail page carrying **2**
schedule rows against `detect_toc_pages`'s floor of **3**. 2008's source prints the typo
`THE SECOND SHCEUDLE`, which `grammar.SCHEDULE_TOC_RE` (`grammar.py:445`) rightly refuses.

**Steps**
1. Read `calibrate.py:288-297` — the comment recording why the floor exists.
2. Find **a signal other than row density**: a schedule-name run, the page's position
   relative to `first_body_page`, or the absence of body text. The floor stays at 3.
3. Verify the Income Tax Rules' body title page is still *not* swallowed — that is the
   regression the floor was put there to prevent.

**Definition of done** — register **−2**; the Income Tax Rules' `first_body_page` unchanged;
a test covering both the two tails and the title page that must not be swallowed.

**Do not** — **do not lower the floor**, and do not widen `SCHEDULE_TOC_RE` to match
`SHCEUDLE`. A typo tolerance in a schedule-heading regex is a false-positive generator
across 103 documents.

**Result** — **CLOSED, rounds 21-28** (PR #89). The extra signal shipped in round 20 — the
floor stayed at 3 and `SHCEUDLE` is still refused, both of which this row insisted on. Round
20 measured 0 on the *public* editions and left the register's 2 standing on the private
ones. Those are now converted, and the class is **0**: `preamble_carries_no_toc_tail` is
gone from the register.

---

### 9. The single-document remainder — 4 hits

Three unrelated traces, no shared cause: the Pakistan Single Window Act's ministry list read
as sections 27/28; PFMA 2019 s.26; Sales Tax 2014 s.10 printing `R(cid:2)fund` (a
font-encoding artifact).

**Steps** — one at a time, each: read the source page → classify parser vs printed →
fix-with-test or exempt-with-evidence. `R(cid:2)fund` is a `(cid:N)` glyph fallback and may
belong to a broader font-encoding class worth grepping the corpus for before fixing it
locally.

**Definition of done** — register **−4** across however many PRs it takes; each hit closed
individually with its own evidence. (This row said **7** until 2026-09-10; the live run
counts **4** — PSW ss.27/28, PFMA s.26, Sales Tax 2014 s.10.)

**Do not** — do not batch these into one "misc" fix. Three unrelated causes in one PR is
what makes a round unattributable.

**Result** — _(empty)_

---

### 10. `clause_codes_plausible` — 1 hit, Finance Act 2024

The jump `7->8517` is an HS tariff heading read from a **table row**; the check
(`_common.py:1874`) excludes schedules but not table-derived codes (ledger P06).

**Steps**
1. Two routes were suggested, neither measured: **(a)** bound the clause cursor by the
   measured gap; **(b)** reuse `_QUOTE_CUE` (`_common.py:463-468`, already used at `:570`,
   `:1414`, `ordinance.py:136`).
2. Measure both as gained/lost across all three lanes before choosing.

**Definition of done** — register **−1**; the check still fires on a genuine implausible
clause jump (prove it with a fixture that must stay red).

**Do not** — **do not weaken the check.** And do not reach for the parser's
`pagemodel.py:585` `_OPEN_QUOTE_CUE_RE` thinking it is the same thing as
`_common._QUOTE_CUE` — different regex, different owner, different side of the fence.

**Result** — **CLOSED, round 20** (PR #86), **measured rounds 21-28** (PR #89).
`_DOTFORM_RE` uses `\.(?!\d)` so a quoted `8517.1430` is not a clause start. Public Finance
Act 2024 reconverted: clauses **1–12**. The fixture that must stay red still stays red, and
the check was not weakened — which this row and `working-rules.md` both forbid. The
register's last hit cleared with the round-27 re-conversion; the class is **0**.

---

### 11. Decide the `fbr_ingest` fork — unblocks 5 hits and 9 documents

**A decision on evidence already committed, not a code task.** Both forks parse the same
three sections of an ICT Ordinance edition; the only difference is that `legal_ingest` has a
flat-act fallback that gives them a container. **So this is routing, not parsing.**

**Steps**
1. Read the evidence in `tools/discovery/signatures.json` (`records[].assignment`) and
   `README.md:283` (the standing v1 non-goal).
2. Decide: route by **family**, not by lane. Routing today is
   `apps/api/backend/services/corpus_registry.py:98`, asserted at `:170`.
3. Record the decision with its evidence — in this file's **Result**, and as the artifact
   for its PR.
4. Only then: the ordinance five in `section_carries_its_body`, and the 9 documents.
5. If routing changes, the fork's **two dormant copies** stop being dormant:
   `fbr_ingest/discover.py:221-244` (pre-round-1 `core.split()`) and
   `fbr_ingest/builder.py:1395-1397` (`CHAPTER\s+`, no hyphen). Both measured at **zero**
   additional hits across all 12 ordinance documents today.

**Definition of done** — the decision is written down with its evidence; if it routes by
family, the 9 documents convert and the ordinance five are closed or exempted.

**Do not** — **do not merge the fork.** That is the v1 non-goal (`README.md:283`) and it is
not what the evidence asks for. Do not port round 13's fixes into the fork "while you are
there" — that is a separate, measured, zero-value change today.

**Result** — **CLOSED as routing, round 20** (PR #86). Convert CLIs and
`corpus_registry` route by family; `--profile auto` is the default. Flat ICT
(empty `container_order`) uses `legal_ingest` + Acts profile; Income Tax
Ordinance stays on `fbr_ingest`. Forks not merged. Nine public ICT PDFs
convert to a synthetic root with three sections. The ordinance five still
need ITO editions on `fbr_ingest` — public ICT files are a different family.

---

### 12. The cross-edition index — a new instrument

No invariant can see a document that lost 93% of its sections: round 11's document gained
118 sections while the register moved 3. Invariants run per document — `runner.run` gets one
`doc` with no lane, no path, no siblings.

**Steps**
1. Build a per-group index over `output/*.json` — **tree counts**, not the PDF-regex counts
   `signatures.json` holds.
2. Join on `signatures.json`'s `group` (`packages/legal_ingest/signature.py:284` — the first
   component of the corpus-relative path, i.e. the containing folder; rationale `:125-127`,
   holding for 183/183 inventory rows). It matches `metadata.filename` on 80/80 acts
   documents.
3. Add the invariant on top of that index, not inside `runner.run`.

**Definition of done** — a check that would have caught round 11's document, demonstrated
by running it against `output/_pre_11/` if that snapshot survives, or a synthetic pair if
not. **A gate that cannot be made to fail on purpose is not a gate.**

**Do not** — do not compare against `signatures.json`'s counts directly. They are PDF-regex
measurements; comparing a tree count to a regex count produces noise on every document.

**Result** — **CLOSED, round 20** (PR #86). `tools/check_cross_edition_quality.py`
indexes tree counts, joins `signatures.json` groups, flags a >50% collapse vs
five or more siblings near the median. Wired into `tools/run_tests_smoke.py`.
Skips without corpus; unit tests lock the fail-on-purpose gate.

---

### 13. The instrument tree level — Phase 5, 4 limbs

A level above chapter, so a compilation parses as N instruments rather than one document
whose index rows become section leaves.

**Steps**
1. **The level itself.**
2. **The walkers.** `grammar.py:419` says "six tree walkers hardcode the child keys
   `("parts", "divisions", "sections")`, so a new `Node.kind` would be dropped
   **silently**". A grep at this commit finds **23 sites across 11 files** — 7 in
   `legal_ingest` (`builder.py:2481,2676`, `schedules.py:147,604,631,817`,
   `pipeline.py:985`), 7 in the `fbr_ingest` fork (`pipeline.py:303`,
   `builder.py:1623,1818`, `schedules.py:118,367,394,580`), 4 in the suite
   (`loader.py:38`, `_common.py:1035,2509,2512`), 4 in the audit tools
   (`tools/acts/audit_completeness.py:258,262`,
   `tools/ordinance/audit_completeness.py:119,123`), 1 in the API
   (`apps/api/backend/services/overlays.py:32`). **Silent drop is the failure mode — this
   limb is where the risk is.**
3. **The portal renderer.**
4. **Re-convert the compilations.**
5. **Delete the 4 exemption entries** at `tools/suite/exemptions/rules.json:47-66`.

**Definition of done** — **the 4 entries are deleted and all three lane suites stay green.**
Not "the level exists". If deleting them turns the suite red, the level did not work. The
suite reports them stale on its own once it does.

**Do not** — do not add a `Node.kind` before auditing all 23 walker sites. A dropped node is
silent, and a silent drop in limb 1 will be diagnosed as a limb 3 rendering bug.

**Result** — **CLOSED, round 20** (PR #86). Optional `instruments[]`, `type=instrument`,
`inst:` keys in `legal_contract`; walkers updated; Alembic `0006_section_instrument_context.py`;
portal breadcrumbs/sidebar/upload. Compilation exemptions for Customs Rules 2001
and Federal Excise Rules 2005 **deleted**. Public FE 2015: two instruments,
suite 60/60. Public Customs Rules 2001: body discovery, compilation case PASS.
Remaining rules exemptions are jammed-tokens, split-ordinals, and the round-19
STR printing errors.

---

### 14. `--profile auto` as the default — SHIPPED, round 20

**Shipped in PR #86** on `tools/convert.py` and `tools/convert_all.py`, both
`--profile {lane,auto}` defaulting to `auto`. A family override refines the
lane's profile. `lane` preserves the historical route.

This was gated on Phase 3 reaching zero-or-exempted so a full reparse could be
attributed, and that full reparse has still **not** been run. What rounds 21-28 did run is
narrower and worth not confusing with it: **77 documents** (the acts and rules lanes) at one
revision, which is what took the register to 13. The 14 skipped acts documents and the whole
12-document ordinance lane are untouched. Do not `make convert-all` — it converts the whole
*lane*, not the corpus. Explicit `--profile lane` is still the escape hatch.

**Result** — default is `auto`. Full-corpus attribution remains blocked until the ordinance
lane and the 14 skipped acts documents are converted at the same revision as the other 77.

---

### The `ReviewToolbar` approval gate — CLOSED 2026-09-14

**Closed by the `fix/review-toolbar-critical-gate` PR.** The decision on record (2026-09-04)
was "gate on CRITICAL flags only"; this is that decision shipped.

**Result** — `apps/web/src/components/review/ReviewToolbar.jsx:47` now calls
`hasCriticalQualityFlags` (`utils/qualityFlags.js:86-88`) instead of `hasAnyQualityFlags`.
The approve confirm now fires only for the four codes the backend itself treats as issues
(`parse_quality.py:14-21`: `missing_table`, `footnote_glue`, `wall_of_text`,
`heading_body_bleed`) — the same set that elevates a section `pending -> has_issues` on
ingest. Informational flags still render in the banner; they no longer block an approve.

**The row said "one line plus the test". It was one line plus TWO tests**, and the second
one is the one that matters:

- `test/approveGate.test.jsx`'s `'still confirms for non-critical flags like
  page_range_out_of_bounds'` asserted the OLD contract and had to invert. It is now
  `'approves silently when the only flags are non-critical (page_range_out_of_bounds)'`.
  Confirmed red against the new code before it was rewritten.
- A new case, `'still confirms when a critical flag rides along with a non-critical one'`
  (`['page_range_out_of_bounds', 'missing_table']`), pins the half the first test cannot
  see. Without it, a gate that had been weakened to *never* fire would still pass.

**No backend change.** `review_state.py:21`, `document_store.py:297` and
`json_parser.py:9,254` already route through `has_critical_flags`; the frontend was the
only side disagreeing.

**One thing this leaves behind:** `hasAnyQualityFlags` (`utils/qualityFlags.js:82`) now has
**no caller in app code** — only its own unit test. It is left in place deliberately rather
than deleted in a behaviour PR; deleting it is a separate, trivial cleanup.

**Verified:** whole web suite **17 failed / 215 passed**, the standing baseline failure set
(`libraryFavorites`, `libraryPage` — Node 26 wants `--localstorage-file`, CI pins 22),
unchanged by name. `npm run lint` (oxlint `--deny-warnings`) clean.

### The acts-lane exemptions — CLOSED 2026-09-14

**Closed by the `fix/phase3-acts-exemptions` PR.** Artifact:
[`wip/phase3-acts-exemptions.md`](../wip/phase3-acts-exemptions.md).

**Result** — register **13 → 8**; `run_suite.py acts` **6 → 1**. rules and ordinance moved
by **zero**, which is correct and worth stating: no parser code was touched and no PDF was
converted, so no other lane *could* move.

`tools/suite/exemptions/acts.json` **had never existed.** Round 15 predicted it would be
needed for `section_codes_ordered`, and it was not — that class was closed by a parser fix
instead. These are the first acts-lane exemptions.

**Two of the three rows were ranked as ordinary traces and were not.** Rows 3 and 4 of the
Start-here board treated PFMA s.26 and PSW ss.27/28 as pages someone simply had not read.
Both documents are **`source_kind: scanned-ocr` with `pipeline_revision: null`** — two of
the 14 documents the round-27 re-conversion deliberately skipped. **Three of the six acts
hits were OCR-blocked and the board did not say so.** Check `source_kind` before ranking a
row as a trace.

| document | hits | what the page says |
|---|---|---|
| Customs 1969 30.06.2008 | ss.181, 189 | the source misprints the body code: p185 prints `35.` where `181.` belongs, p191 prints `37.` where `189.` belongs, both 12.00pt at x0 93.6, against contents rows that read correctly. Neighbours 180/182/188/190 all print their own codes, so it is not an offset |
| PFMA 2019 | s.26 | p12 emits `system.—The` as ONE 9.00pt token, so the heading swallowed the body |
| PSW 2021 | ss.27, 28 | not sections — rows of the Act's `[SCHEDULE]`, an `S. No. \| Organization` table whose serial column reads as section codes |

**Three things worth carrying forward:**

- **The Customs misprint is three sections wide, not two.** s.185D prints `36.` on p189.
  **No invariant reports it**, because that leaf did pick up a body — so the register only
  ever saw two thirds of this defect. Do not infer the extent of a defect from its hit count.
- **PFMA's entry does not claim the parser is broken.** `builder.DASHES` already contains
  U+2014, so the hit may be nothing but stale-revision drift. It cannot be tested without
  re-running OCR. The entry says exactly that. It exists because "tracked and deferred" is
  not a state this suite allows.
- **PSW's parse shape is the evidence, not the two leaves.** It emits one chapter whose
  codes run `3..23` then jump to `27, 28, 29` — ss.24-26 absent — and **zero schedules**.
  Its serial column OCRs as `I.`, `I D.`, `1I.`, `1$.`, `23,`. If OCR is ever taken in
  scope, the fix is to recover the Schedule *as a schedule*, not to patch two leaves.

**What was rejected:** adopting the contents-page code whenever a body code breaks monotonic
order and the heading matches. That would read the Customs pair and s.185D — and it is
exactly the shape rounds 23 and 25 shipped and round 27 had to guard, after one of them
collapsed 860 of 1,102 rules to stubs in another lane. Two hits in one edition do not buy it.

**No new test was added, deliberately.** `tools/tests/test_suite_exemptions.py` is already
lane-generic: it loops all three lanes, skips a missing file, and asserts each entry names a
real invariant, carries a non-empty reason, and that `applies_to` matches **exactly one**
staged corpus document. Creating the file brought all three assertions to bear.

### 15. The OCR decision — BLOCKED, needs a human

**Not work. A decision.** `data/ocr_cache` is 0 B and stays 0 B until someone decides
otherwise. The shape of the decision, the cheap tail, and the consequence chain are in
[`plan.md` Phase 2](plan.md#phase-2--the-ocr-half-a-decision-not-work).

Read the consequence chain before recommending the "cheap" 15-minute tail: it ends with
documents **disappearing from the portal**.

**Result** — _(empty)_

---

## Deferred, with reasons

Real, but not open. Each carries the reason it is not being done, rather than a note that
it isn't.

| row | why it is not open |
|---|---|
| **delete `_legacy_section_key` + the `source_key` bridge** | Blocked on the 14 stale acts documents (→ the OCR decision): 6 documents / 89 leaves still rely on it. Definition at `apps/api/backend/services/document_store.py:61`, the only call site `:257`, reached only after `by_node_key` **and** `by_source_key` both miss (the 3-tier ladder is `:245-258`). **The ledger says "confirm with a query, not a guess" in five places and that query does not exist** — `wip/integration/measure/census.py` counts the JSON corpus, not the database; the only `node_key IS NULL` in the repo is a partial index (`alembic/versions/0004_section_node_key.py:43`). **Writing the query is step 1.** |
| **the `ReviewToolbar` approval gate** | **CLOSED 2026-09-14.** `ReviewToolbar.jsx:47` now calls `hasCriticalQualityFlags`; the approve confirm fires only for the backend's `CRITICAL_FLAGS` set. See the Result section below. |
| **delete the Zustand mirror in `documentStore`** | Architecture, not a defect — the bug it caused is fixed and tested. **Bigger than the record says:** `open-work.md:183` calls it "five pages"; it is **8 consumer modules** — `ReviewPage.jsx:20,62`, `DashboardPage.jsx:15,71`, `Sidebar.jsx:5,44`, `ReviewToolbar.jsx:4,31`, `PdfPanel.jsx:6,107`, `AiFixPanel.jsx:14,227`, `CommandPalette.jsx:9,32-33`, and `stores/reviewStore.js:3,57,109,124-128,150`. **And there is no data-hooks layer to move onto:** `apps/web/src/hooks/` holds only `useKeyboardNav`/`usePdfRenderer`/`useTextSelection`, and app code contains **zero** `useQuery`/`useMutation` calls — everything routes through `documentStore`'s `fetchQuery` wrapper (`documentStore.js:8-12`). It must be written first. |
| **an explicit `order` field** | Needs the **source pages**: tree-walk and page-sort order disagree on **21 of 103** documents and the JSON cannot settle which is right. P5's reading-order limb — measured and deferred, not open. |
| **delete `normalize_heading`** | A **parser** task hiding in the integration ledger. A parser round must first stop emitting a leading `]` and the truncated `[...`. Then it is one deletion. Note it lives API-side: `apps/api/backend/services/json_parser.py:82`. |
| **`convert_all.py` cannot resume** (`wip/tasks.md:536`) | Known, with a workaround that works: convert only outputs older than the parser's mtime. Worth fixing when a round needs a full-lane re-conversion; no round does today. |
| **re-examine the 29 low-confidence documents** (`wip/tasks.md:671`) | `tools/discovery/report.md` §5 was wrong from PR #45 to #51 because it had not been regenerated since Phase 0. The generator is fixed; the list has not been re-read since. Cheap, and may dissolve on its own. |
| **rebuild api/worker images** (`wip/tasks.md:79`) | Explicitly "not attempted, and not needed this round". A deploy concern, and the deploy is gated on green CI on `main` and is outward-facing — confirm before triggering. |
| **the `fbr_ingest` dormant copies** | Measured at **zero** additional hits across all 12 ordinance documents, so leaving them was correct. Gated on [task 11](#11-decide-the-fbr_ingest-fork--unblocks-5-hits-and-9-documents); they become live the moment routing changes. |

---

## Where this stands

Nothing in `wip/` is edited to keep this file current — each round only *adds* its own
write-up there. `wip/` is the historical record and shipping code cites it. Note that
**every file under `wip/integration/` states the register as 34** and `wip/HANDOVER.md`
states it as **64**; it is **13**. `wip/tasks.md:664` states `section_codes_ordered` as
**4**; the class is **closed**. When those disagree with this folder, this folder is
right — and `tools/suite/register.json` is right about the register over everything,
including this file.
