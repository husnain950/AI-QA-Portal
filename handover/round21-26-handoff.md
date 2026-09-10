# Handoff — rounds 21-27, the Customs Act QA pass

Written **2026-09-10**. Branch **`fix/phase3-round21-fused-citation-markers`**, ten
commits, working tree clean. **PR #89 is open**
(<https://github.com/husnain950/AI-QA-Portal/pull/89>) and **the portal has been
re-pushed** — everything in §4 below is done. What is left is review of the PR and
the small follow-ups in §8.

> Read [`README.md`](README.md) for standing state and
> [`working-rules.md`](working-rules.md) for method. `wip/` is the frozen historical
> record — do not edit it, and do not read it for current state.

---

## 1. What this was

A reviewer logged 21 defects against `Customs Act, 1969 as amended up to 30th June, 2025`
(portal document `c58ffb0e-669a-4305-9bff-dec375605ce6`) in
`~/Downloads/Customs Sheet Audit.xlsx`. The task was to verify each one, separate real
defects from false positives, write the findings back into that workbook, and fix
everything fixable.

**All 21 rows are closed.** 16 by code, 3 by re-pushing the portal, 1 by design, 1 was
half a false positive whose real half is fixed. The workbook is updated in place —
`Bug Report` columns Q-W, a new `Root Causes` sheet, and outcome blocks in `Summary`,
`Chapter Status` and `Verified Non-Issues`. A copy of the original is at
`<scratchpad>/Customs Sheet Audit.ORIGINAL.xlsx`.

## 2. The single most important fact

**The portal is serving a parse uploaded 2026-08-23.** Three of the reported defects
(BUG-007, 008, 019) were already fixed by rounds 18 and 20 and only looked open because
of that. Always establish which of the three code states you are looking at before
believing a bug report against this portal:

| state | what it is |
|---|---|
| portal | parse uploaded 2026-08-23, pre-round-17 |
| corpus JSON | whatever revision each file last got — **mixed** |
| HEAD | the parser you are editing |

## 3. The six commits, and what each is measured at

Every round was measured by converting the one PDF before and after and diffing leaf by
leaf. Numbers are for the 30.06.2025 edition.

| round | commit | change | measured |
|---|---|---|---|
| 21 | `9929a09` | `grammar.marker_run` reads a marker token the text layer fused with punctuation (`11[`, `7,45[`, `5&7[`, `1/2[`); `builder._render_marker_token` emits one `<sup>` per marker. Plus the unbalanced-bracket strip in `_body_heading_title`, the API footnote `ORDER BY`, and the `FootnotePanel` empty state | unrendered marker sites 55 → 3, footnotes 707 → 794, `plain_text` byte-identical |
| 22 | `95b8d08` | `_zone_swallows_heading` no longer lets a footnote-SIZED heading veto the footnote zone — a quotation that opened on the previous page was reading as a live heading | s.34 3,223 → 685 chars, s.196J 9,356 → 268, Chapter V 110 → 135 of 137 notes |
| 23 | `2c388ee` | `insert_missing_body_sections` adopts a body section code the contents page never lists | 325 → 340 sections, 5 existing bodies changed, all correct splits |
| 24 | `3dfa0ec` | contents-row repairs: rejoin a split code suffix (`79` `A` → `79A`); a row ending in a page number is not a schedule's title | duplicate codes 1 → 0, all five schedule headings cleared |
| 25 | `cec6be8` | `reparent_sections_to_body_chapters` — membership follows the body spine, not the contents page | 4 sections moved: VI 35-41, VII 42-59, VIII 60-72A |
| 26 | `7bafd10` | `_accept_marker` refuses a quoted section heading as a footnote definition | 795 → 794 records, one section's list changed |
| 27 | `e40badd` | **two guards rounds 23 and 25 needed** — found by running the lane suites over a fully re-converted corpus, not by the single-document measurement | Customs Rules 2001 1011/41/66 hits → **0/0/0**; Customs Act unchanged at 339 |

**Round 27 is the one to read first if you are short of time.** Rounds 23 and 25 were each
measured on one document, looked clean, and were both wrong in the rules lane: round 23
inserted rule 27 into a chapter holding rules 1-2 (the contents page jumps 2 → 39, so it
"sorted between neighbours") and collapsed 860 of 1,102 rules to stubs; round 25 re-parented
98 sections, some 34 chapters away. A round measured on one document is measured on one
document.

Aggregate, before (HEAD) → after: sections **325 → 339**, duplicate codes **1 → 0**,
footnote records **707 → 794**, unparsed marker sites **55 → 3**, Chapter V footnotes
**110 → 135 of 137**, body characters 427,056 → 415,401 (the fall is 11,655 characters of
footnote block and chapter heading that were sitting inside section bodies — no legal text
was lost).

**14 sections recovered:** 19B, 27A, 32C, 79A, 196L-196U, 208, less the phantom duplicate
79 that round 24 removed. Eleven are in Chapters XIX-A and XX, which the QA pass never
reached.

## 4. Done since this was first written

All of the following completed on 2026-09-10:

- Corpus re-converted at `f3a37e0` — 77 text-layer acts and rules documents at one
  revision, 0 failures, `data/ocr_cache` still 0 B.
- **Register regenerated: 22 → 13** with `tools/tests/test_register_snapshot.py --write`.
  acts 15 → 6 (three classes closed outright), ordinance 5 → 5, rules 2 → 2. No lane
  worse. Committed in `0be9068`.
- `tools/tests`: **231 passed, 1 skipped** — up from 2 failed / 229 passed. Both former
  failures predate this work and are now fixed (see §5).
- Artifact written: `wip/phase3-round21-28-customs-qa.md`, generated from two
  conversions of the same PDF.
- **PR #89 opened.**
- **Portal re-pushed** — `POST /api/documents/{id}/replace-json` with `If-Match` on the
  active version, HTTP 200. Verified on the live API: Chapter III correct, Chapter XI
  present, VI 35-41 / VII 42-59 / VIII 60-72A, Chapter XIX-A 196K-196U, **0 duplicate
  section codes**, schedule headings clean, s.2's footnote tail in order
  (9.45 … 9.50), s.3A has its 2 footnotes, s.55 no longer shows the bogus "footnote 43",
  s.34 at 685 characters. 345 rows, 784 footnotes.
- **Review-state cost of the re-push, as warned:** 331 → 345 sections, reviewed
  327 → 226, approved **204 → 163**, has_issues 123 → 63. About 41 approvals no longer
  count, because their `node_key` changed — chiefly Chapter XI's 36 sections, which the
  old parse had under Chapter X (`ch:x/s:84` → `ch:xi/s:84`), plus the four sections that
  moved chapter and the fourteen new ones. Every one of them is recoverable for reference
  from `data/backups/review-snapshot-20260910-070706.json`. The has_issues drop is the
  good half: 60 sections were flagged for defects that are now fixed.

## 4b. The original next-steps list, kept for the record

1. **Wait for the corpus re-conversion to finish.** Restarted 2026-09-10 ~13:55 at round
   27 — the earlier run produced the bad round-26 output for the rules lane and must not be
   measured. Runs from
   `<scratchpad>/reconvert.py`, log at `<scratchpad>/reconvert.log`, 77 text-layer
   documents in the acts and rules lanes, roughly one a minute. It resumes by comparing
   each output's mtime against the newest `packages/legal_ingest/*.py`, so if it dies you
   can simply run it again and it picks up. **14 documents are deliberately skipped** —
   8 OCR-backed (out of scope, `data/ocr_cache` must stay at 0 B) and 6 with no
   `source_kind` recorded (five Finance Acts, Benami, Income Tax Third Amendment). Those
   stay at their old revision and the corpus stays mixed to that extent.
2. **Run the three lane suites and regenerate `tools/suite/register.json` in this PR.**
   A round that improves the register fails `test_register_snapshot.py` until the file is
   updated; that is the point.
3. **Read §5 before you trust the register.**
4. **Open the PR** on `fix/phase3-round21-fused-citation-markers`. Six commits, one unit
   of work each. They are stacked in one PR on purpose: the corpus can only be converted
   once, so measuring each round against its own parent is impossible on shared corpus
   files — say so in the PR body. Link a before/after artifact per
   [`pr-review-artifact.md`](../.claude/../handover/README.md) convention.
5. **Re-push this one document to the portal**, which closes BUG-007, 008 and 019.
   Reviewer state is already backed up:
   `data/backups/review-snapshot-20260910-070706.json` (111 documents, this document's
   204 approvals and 123 has_issues included; 4 unrelated Income Tax Ordinance documents
   failed with server truncation, a known transient).
   - `push_corpus` pushes **everything** from the **local DB**, which is rounds stale —
     do not use it.
   - Use `POST /api/documents/{id}/replace-json`, multipart `json_file`, with an
     `If-Match` header naming the active version id from
     `GET /api/documents/{id}/versions`. API base is
     `https://p01--crx-web--m4hljdfnbvqq.code.run/api`; sign in at `/api/auth/login`
     with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`.
   - Tell QA first: reviewer state carries across by `node_key`, but the 14 new sections
     arrive as new rows and any annotation anchored into s.34's or s.41's swallowed tail
     will re-anchor or orphan.

## 5. The trap that will cost you an hour if you skip it

**The corpus on this disk measures 133 register hits against the committed 22, and that is
not from this work.** Verified by stashing every change and re-running: baseline is
acts 49 / ordinance 5 / rules 79. It is mixed-revision drift — output files written by
several different parser revisions, exactly what `working-rules.md` warns about.

Consequences:

- `test_register_snapshot.py` fails on this machine **before** you change anything, and
  so does the regression case `customs_2001_is_a_compilation` in the rules lane.
- **Do not commit 133 as the new snapshot.** Regenerate the register only from a corpus
  converted at one revision. The re-conversion in §4.1 gets acts and rules there; the
  ordinance lane runs `packages/fbr_ingest`, which none of this touched.
- Isolate your own delta the way this work did: stash, measure, unstash, measure. The
  invariant half and the parser half must be measured separately — round 21's widening of
  `inv_leading_marker_cited` alone took that class from 0 to 61 across 17 Customs
  editions, with the parser untouched.

## 6. Verification state as of this handoff

| check | result |
|---|---|
| module self-checks (grammar, pagemodel, builder, toc, pipeline) | all pass |
| `apps/api` suite | **540 passed**, 0 failed |
| web suite (`vitest`) | 17 failed / 206 passed — this repo's standing baseline, unchanged |
| `ruff check` (bare) | clean |
| `tools/tests` | **2 failed, 229 passed, 1 skipped** — both failures are `test_register_snapshot.py`, and both fail at baseline too (see §5). Note the suite is 229 tests now; `README.md` still says 98. |
| three lane suites + register | **not yet run at rounds 21-26** — needs §4.1 first |

## 7. Judgement calls made, so you can overrule them knowingly

- **A shape guard against splitting a grouped number was written and removed.** Refusing a
  run whose head is shorter than its three-digit tail rejects `100,000` but also rejects
  `35,106`, `91,118`, `79,104`, `8,137` and `7&110` — five genuine runs in this edition.
  No shape separates them; type size does, and the caller already measures it.
  `0101.9000,` is a 12pt body word and never reaches the token grammar.
- **`is_table` alone is not enough to reject a false section start.** Admitting s.156's
  flattened penalty-table rows destroyed the monotonic cursor: 202 sections moved, s.9 ran
  to 60,500 characters, s.156 collapsed to 28. The heading dash over a two-line window is
  the load-bearing guard. Two lines because a title wraps.
- **`reparent_sections_to_body_chapters` declines unless the body prints a line for every
  chapter in the tree.** Partial evidence would reorganise a document on the strength of
  the few headings that happened to parse.
- **Uncited footnotes stay attached to the covering leaf.** QA asked for an "unattached"
  state. Dropping them loses 184 notes' legal text on this edition, and a label needs a
  column, a model field and a UI badge. Left alone; recorded in the workbook.
- **s.79A's heading is left as `O mitted`.** That is the contents page's own kerning, not
  something the portal invented — `pdftotext` rejoins it silently, the text layer does
  not. The QA report's own "Verified Non-Issues" sheet sets the rule: source typos are
  preserved. Only the code was repaired.

## 8. Known-open, and why

- **Chapter V footnotes 42 and 66** — source defects. 66 is never printed (the block runs
  65, 67); 42 is printed indented under 41's quotation, so it nests in 41 the way sub-note
  1a nests in 1. Exemption candidates if you want the class at zero.
- **Two penalty-table marker cells** in s.156 — same family as round 21 but a different
  code path: `pagemodel._true_table_marker` refuses letter suffixes and anything ≥ 100,
  and `CITE_SENT_RE_TEXT` has no `[a-z]` group. Not attempted.
- **s.29's mid-title bracket** — `Restriction on amendment of [goods declaration`. The
  marker is gone; the amendment bracket remains mid-title. Cosmetic.
- **One legal cross-reference** left unrendered in s.2: `sections 79, 104[,121], 131`.
  The token carries both a marker and ordinary text.

## 9. Where the evidence is

The scratchpad for this session holds every conversion used as evidence —
`head_customs2025.json` (HEAD, before), `r21d`/`r22`/`r23d`/`r24`/`r25b`/`r26_customs2025.json`
(after each round), `prod_customs2025.json` (the portal's own export),
`customs2025.txt` (the full `pdftotext -layout` dump, page-indexed), and
`Customs Sheet Audit.ORIGINAL.xlsx`. Scratchpads are session-local — if you need any of
it, re-derive with `tools/convert.py acts "<pdf>" -o <path>`.
