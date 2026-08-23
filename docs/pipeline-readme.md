# FBR PDF → JSON ingestion pipeline

A deterministic, dependency-light pipeline that converts an FBR legal-text PDF
(e.g. *Income Tax Ordinance, 2001*) into the structured JSON your website
ingests. Output matches the schema of
`_Income_Tax_Ordinance__2001_Amended_upto_20.02.2026.json`.

```
metadata        { filename, total_pages, toc_pages_scanned,
                  chapters_count, schedules_count, sections_count }
chapters[]      { code, heading, parts[], divisions[], sections[] }
schedules[]     { code, heading?, parts[], divisions[], sections[] }
  section       { code, heading, page_number, html, plain_text,
                  start_page, end_page, footnotes[] }
  footnote      { ref, marker, text, html }         # ref/marker = "{printedpage}.{n}"
```

**Footnote refs use the printed page number, starting at 1** (e.g. `1.*`, `1.1`),
not the physical PDF page. The same printed-page ref is used by the inline
`<sup class="cite">` citations in the body. Every footnote also carries an
`html` field: one `<p>` per line, and — when the footnote embeds a rate
`TABLE` — a `<div class="fn-table">` flex grid whose columns are recovered from
the footnote's word x-positions.

## Where things live

This document was written for the standalone ordinance repository, where the pipeline
sat beside its own `output/` and `tests/`. In this monorepo:

| Then | Now |
|---|---|
| `fbr_ingest/` | `packages/fbr_ingest/` — the Ordinance pipeline |
| — | `packages/legal_ingest/` — the Acts **and** Rules pipeline, one `Profile` per corpus |
| `scripts/fbr_pdf_to_json.py` | `tools/convert.py <lane> <PDF>` (or `make convert-<lane> PDF=…`) |
| `scripts/run_tests.py` | `tools/run_suite.py <lane>` |
| `tools/add_test_case.py` | `tools/add_test_case.py <lane>` |
| `tools/import_qa_report.py` | `tools/import_qa_report.py` |
| `tools/ordinance/audit_completeness.py` | `tools/<lane>/audit_completeness.py` |
| `tests/` | `tools/suite/` — `checks.py`/`loader.py`/`runner.py` shared, `invariants/<lane>.py` and `cases/<lane>.json` per lane |
| `output/` | `$CORPUS_<LANE>/output/` (gitignored; see `.env.example`) |

`python tools/run_tests_smoke.py` is the gate: package self-checks always, each lane's
regression suite when its corpus is staged.

The QA-issue catalogue below is the Ordinance pipeline's own history and still describes
`fbr_ingest` accurately. `legal_ingest` was forked from it and has since diverged; for
what differs per corpus there, read `packages/legal_ingest/profiles.py`.

## How it works (`fbr_ingest/`)

| Module | Responsibility |
|---|---|
| `toc.py` | Parses the Table of Contents into the Chapter→Part→Division→Section tree and an ordered section list with printed page numbers. |
| `pagemodel.py` | Per-page geometry. Splits every page into **header / body / footnote-block / footer page-number** zones and normalises glyphs. |
| `footnotes.py` | Reads each page's footnote block into ordered `{marker: text}` entries. |
| `builder.py` | Splits the running body into sections, resolves inline citation markers, and renders `html` + `plain_text` + `footnotes`. |
| `schedules.py` | Extracts the Schedules (First–Fifteenth), segmenting by Schedule/Part/Division headings and attaching rendered content to each terminal node. |
| `tables.py` | Detects tables in section/schedule *body* text and renders them as `<table class="fbr-table">` (thead = title + numbering row, tbody = data rows). |
| `pipeline.py` | Orchestrates: TOC → calibrate page offset → scan body + schedules → assemble → JSON. |
| `tools/convert.py` | CLI entry point (lane-dispatched; see the table above). |

The printed-to-PDF page mapping is auto-calibrated (a constant offset of 19 for
this document: printed page 1 = PDF page 20). Footer page numbers are then
**sanitized by local consensus** (`pipeline.sanitize_printed_pages`): the PDF
misprints 11 footers (e.g. PDF page 188 prints "189" between "168" and "170";
533 prints "517" between "513" and "515"), and every footnote ref derives from
the printed number, so each page's number is validated against its neighbours
and repaired when outvoted.

## The QA issues — and how each is fixed

The old model's defects all traced back to **not separating a page into its real
zones before reading text**. Fixes are structural, not band-aids:

1. **Page numbers bleeding into body text** (`"inheritance. 157"`, `"…196"`,
   `"…209"`, `31`, `166` …). The centred footer page-number is detected by
   position (bottom, centred, bare integer) and stripped. Body text no longer
   ends with a stray page number. *Verified: 0 occurrences across all 443
   sections.*
2. **Wrong asterisk glyph** (`U+F0D8` shown instead of `*`). Normalised in
   `pagemodel.normalize_text`. *Verified: 0 private-use glyphs remain.*
3. **Sections not merged across page breaks.** Sections are cut on *headings*,
   not page boundaries, so content flows across pages automatically.
4. **Structural headers swallowed into the previous section** (`"…in force. CHAPTER II CHARGE OF TAX"`).
   A section stops at the next standalone `CHAPTER` / `PART` / `Division` line.
5. **Amendment markers** (`1[…]`, `3[ ]`) mishandled. Inline superscript markers
   (font size ≈ 6.5) are detected by font size and turned into
   `<sup class="cite" title="…">{page}.{n}</sup>` linked to the right footnote.
6. **Footnotes split by their own quoted text.** Amendment text quoted inside a
   footnote carries nested superscript markers (`2[Provided…`, `1[(ii)…`) and
   even quoted years (`2020`) that start lines at the left margin. Evidence
   rules in `footnotes._accept_marker` (year values; bracketed repeats of an
   already-seen marker; bracketed markers inside a continuing quotation) fold
   those lines back into the owning footnote instead of starting a bogus one.
   *Verified: footnote word-token conservation vs the PDF is 100.000%.*
7. **Footnotes spanning page breaks.** A continuation is spliced onto its
   footnote and the merged footnote is re-rendered from its raw line records,
   so a rate table whose last row wraps onto the next page (e.g. footnote 505.2's
   "Pakistan Mercantile Exchange" row) comes out as one `fn-table`, followed by
   its provisos as paragraphs. The owning leaf's `end_page` extends to the last
   page the footnote's text physically reaches.
8. **Duplicate printed markers.** The PDF misprints the same footnote number
   twice on a few pages (two `5`s on printed page 92, two `3`s on 509). Dedup is
   by `(ref, text)`, so both legal texts survive.
9. **Heading-page span gaps.** A Division heading alone on a page (e.g.
   `1[DIVISION VII` on printed 506) used to leave that page in no leaf's span,
   silently dropping its footnotes (the whole Finance-Act-2024 substitution
   note). The heading page is now part of the new division's footnote span.
10. **Words split by mid-word font-subset switches and ordinal superscripts.**
   Passing `extra_attrs` makes pdfplumber split a word wherever the embedded
   font subset flips mid-word (`b|y`, `developmen|t` — ~2,500 pairs across 633
   pages), and the raised `st/nd/rd/th` of `30th` is emitted as its own tiny
   word whose top can drag it onto a neighbouring line (stray `<p>th</p>`
   paragraphs; `30 June` missing its suffix — 455 pairs on 222 pages).
   `pagemodel._merge_split_words` re-joins both classes before any line
   grouping, tracking the last glyph run's metrics so `31st day` doesn't chain
   into `31stday`; bare digit/`*` tokens never merge (they are citation
   markers). Heading-dash and subsection-marker splitting in `builder` handle
   the fused tokens (`—Any`, `enterprise.-(1)`, `[(4AB)`).
   *Verified: body word-token conservation rose from 99.973% to 99.995%;
   footnotes remain 100.000%.*
11. **Omitted sections' bracket lines swallowed by the previous section.** An
   omitted section survives in the body only as an empty amendment bracket
   (`3[ ]`, `4[ 5[ ] ]`) that used to end up inside the *previous* section's
   segment (236O carried 18 footnotes spanning 236P–236X).
   `pipeline.claim_placeholder_lines` maps each bracket line to its section —
   exactly, via the page+marker of the footnote naming it ("Section “236T”
   omitted by …" has marker 5 → the `5[` bracket) — and the placeholder
   renders the bracket with live `<sup>` citations for every marker on it
   (both the insertion and omission notes). 64 omitted sections gained their
   cited bracket bodies.
12. **Citation markers invisible in html.** A marker inside the dropped
   heading region (`1[236Y. …`, `1[DIVISION VII`) anchored an attached
   footnote with no visible citation. Heading-region markers are now surfaced
   as `<sup class="cite">` prefixes inside the `<h4>` (202 leaves), for both
   chapter sections and schedule divisions. Guarded by the
   `leading_marker_cited` invariant.
13. **Duplicate TOC codes.** The TOC lists 236Y twice (omitted 2021 +
   re-inserted 2022); keying built sections by code duplicated one body into
   both rows. Sections are now keyed by TOC-entry identity and the body
   heading goes to whichever duplicate row expects it closest, so the other
   row becomes a genuine placeholder.
14a. **Footnote rate tables scrambled / truncated / half-missing.** The old
   fn-table renderer flattened each row's wrapped lines into one word list and
   dealt words to columns by x-position, interleaving cell text ("Where
   holding than six months. / period of a security is less"); multi-line
   headers were dumped as jumbled paragraphs above the grid; "2 [TABLE"
   keyword lines went unrecognised; a wide wrapped line ended the table early
   (502.1 lost half its rows *and* its whole second table). Rebuilt around
   tolerant whitespace-valley column detection (a boundary is an x-range
   almost no line crosses; a numbering row fixes the column *count*),
   per-column reading-order cell assembly, multi-table scanning, and prose
   detection by vocabulary + position. Verified on 502.1 (both tables),
   502.3, 504.1, 505.2 (assembled header) and by a document-wide diff: all 81
   fn-tables re-render, none lost, footnote texts byte-identical.
14. **Fully-justified lines jammed into one run of letters.** Justified text
   compresses real inter-word gaps below the 2pt glue threshold (sec 30's
   "creditedtoasuspenseaccountinaccordancewiththe…", 40 leaves affected, worst
   76 glued characters). The PDF's own space characters are the ground truth:
   `pagemodel._mark_space_before` stamps every word a space glyph precedes,
   and such a word is never glued (`builder._render_words`) or merged
   (`_merge_split_words`) — while true fragments with no space between
   ("ar"+"m’s" → "arm’s", "8"+"[Non-") still join. Guarded by the
   `no_jammed_words` invariant (no 25+ letter runs anywhere).
   *Verified: body word-token conservation 99.998%; the 4 residual audit
   misses are source-tokenizer artifacts ("ar m’s" fragments the pipeline
   correctly joins; "[See …]" lines rendered as the h4), each hand-checked.*

15. **Schedule leaves carrying their neighbours' footnotes.** Schedule
   divisions were attaching every footnote on every page they *span* — and
   divisions routinely share a PDF page (Division V started on the page where
   Divisions IV/IVA end, so it showed their 501.1–501.3 alongside its own
   502.x–505.x). Footnote assignment is now **by citation** everywhere: a
   footnote binds to the leaf whose text carries its superscript marker — in
   body lines, on heading lines (`_heading_marker_prefix` records what it
   renders), or *inside grid tables* (marker words swallowed by a table block
   are preserved on `pagemodel.Table.marker_words` and registered by
   `builder._cite_table_markers`). Footnotes cited by nobody (their markers
   sit inside another footnote's quoted text, e.g. 489.2–489.7 anchor inside
   489.1's quoted rate table) are adopted exactly once by the leaf covering
   their page (`builder.adopt_orphan_footnotes`). Guarded by the
   `footnote_on_citing_leaf` invariant and `footnote_refs_exact` cases.
16. **Misprinted footer page numbers minting wrong / duplicate refs.** The PDF
   misprints 11 footers (188→"189", 224, 233, 240, 436, 475, 499, 507, 533,
   537, 538). The by-citation path derived refs from the constant offset while
   orphan adoption used the raw footer, so on those pages the `(ref, text)`
   dedup missed and the same footnote attached twice under two refs (section
   99 gained phantom `189.x` beside its real `169.x`; 113 phantom `217.x`;
   237 phantom `483.x`), and schedule refs were simply wrong (`517.1` instead
   of `514.1` on Division IX). `pipeline.sanitize_printed_pages` repairs every
   footer by local consensus before any ref is minted; all refs now match the
   reference on the affected pages.

17. **Body tables misclassified as footnotes (rule-less pages).** Zone
   splitting had a font-size fallback for pages without the printed footnote
   separator rule — but body tables are set at 8–9pt (the same sizes as
   footnote text), so 17 table-only pages (the Twelfth Schedule's PCT lists,
   the section-182 penalty grid, a Sixth-Schedule equipment list) walked
   wholesale into the footnote zone and were spliced into the *previous*
   page's real footnotes as garbage legal text (footnote 779.1 gained a page
   of live PCT entries; section 182 minted six phantom `381.x` footnotes from
   its own rows). Verified across all 802 pages: **footnotes exist iff the
   separator rule is printed** — so the fallback is gone; no rule means no
   footnote zone. Guarded by `footnote_refs_exact` cases on the affected
   leaves and `footnote_not_contains` leak cases.
18. **Citations inside grid tables invisible.** Cells extracted from
   gridlines are plain text, so a superscript marker rendered as a literal
   glued digit (`1[ ]`, `2[9405.1090`) with no `<sup class="cite">` — the
   footnote was *attached* (via `Table.marker_words`) but unciteable on
   screen. Each true marker is now located in its cell and wrapped in a
   sentinel (`pagemodel.cite_sentinel`) that survives escaping and
   continuation-table merging; `builder._expand_table_cites` expands it to
   the same `<sup class="cite" title="…">{printed}.{n}</sup>` the body uses
   (75 in-table citations document-wide). A sentinel matching no parsed
   footnote is restored to its literal text. Text-heuristic (gridless) tables
   get the same treatment in `tables._group_logical_rows`. Guarded by the
   `no_control_chars` invariant (no sentinel may leak) and in-cell citation
   cases.
19. **Table content digits false-matching as markers.** Dense tables are set
   at 9pt — under the absolute superscript threshold tuned for 10pt body —
   so quantities like `650`/`280` and even serials matched as "markers".
   `pagemodel._true_table_marker` requires a marker to be visibly smaller
   than the table's own dominant text size and a small serial (< 100).
   Citation titles also now include cross-page continuation text (the
   footnote map is rebuilt after `merge_footnote_continuations`).

20. **Quoted tables in footnotes rendered as paragraphs.** The footnote
   renderer detected tables only by text signatures (a `TABLE` keyword, an
   `S.No` header, a `(1) (2)` numbering row). A quoted table with none of
   those — e.g. footnote 779.1's five omitted PCT-code rows, or the
   Engine-Capacity rate grid — flattened into `<p>` lines even though the PDF
   prints real cell borders around it. The footnote-zone gridline bboxes are
   now kept on the page model (`PageModel.footnote_tables`); each footnote
   line falling inside one is flagged on its record (so the flag survives
   cross-page splicing and re-rendering), and flagged runs render as
   `fn-table` grids (`footnotes._render_grid_run`) — **as a fallback only**,
   so every heuristically-detected table keeps its existing rendering
   byte-for-byte. One-row quotes print no gridlines at all (footnote 774.2's
   single 72.04 row), so a second fallback catches them by shape + context:
   a row-code first token (`“72.04`, `9405.1090`, `(d)`) followed by a ≥15pt
   column gap, directly after a line ending in `:` (the "read as follows:"
   idiom that introduces every quoted amendment table). The whitespace-valley
   detector's tolerance is clamped below the row count so a single row can
   form column blocks at all.

21. **Title-line citations lost on large-type headings.** Superscript markers
   scale with their heading's type size: the 16pt `1 [ELEVENTH SCHEDULE`
   title carries a 10.6pt marker — above the absolute 9.4pt superscript
   cutoff tuned for 10pt body text — so five heading citations (the Seventh/
   Ninth/Tenth/Eleventh Schedule titles and `1 [PART IX`) rendered nowhere
   and their footnotes attached only via the orphan net, invisibly.
   `builder._is_heading_marker` now also accepts a digit/`*` visibly smaller
   than the heading's own dominant size. Container schedules (the Ninth has
   PARTs, so its title has no leaf of its own) surface the title citation on
   their first content leaf (`schedules._attach_sched_head_citations`). The
   chapter-side `1 [PART IX` structural line has no leaf in this design or
   the reference's — its footnote stays attached (uncited) to the covering
   section, identical to the reference.

22. **Formulas, provisos, definitions and omitted brackets glued into the
   paragraph (QA report 06-Jul).** The PDF sets several kinds of line apart
   from running text, and `plain_text` (line-based) always preserved them —
   but the html renderer merged every continuation line into the surrounding
   paragraph/`<li>`. `builder._layout_blocks` now wraps each in a
   `display:block` span so the html shows the same break without touching the
   list/paragraph structure or `plain_text`: **formulas** (short symbol-only
   lines centred between the margins after a "namely: —"/"equal to-" intro:
   `A x B/C`, `(A + B) – C`, 20 document-wide) render centred; the two
   **stacked fractions** the PDF prints with a real bar (`A` over `B` in
   s.24(3), `A x 15` over `85` in s.233(2A)) render as num/den blocks with a
   `border-top` bar; **provisos** (`Provided that …`, 297) and
   **explanations** (`Explanation. –`, 80) open their own indented block, as
   printed; **quoted-term definitions** (`“scientific research” means …`, 32)
   likewise; an **empty omitted-clause bracket** on its own printed line
   (`5[ ]`, 674) gets its own line — while a bracket the PDF prints at the end
   of a text line (s.114(1)(ac)) correctly stays inline. Guarded by the
   promoted `qa_*` html cases on ss. 12, 14, 24, 26, 35, 37A, 38, 114, 115,
   233.

Boundary detection is **page-anchored**: each section's heading must appear near
its expected PDF page, so a stray `8.` deep in the text is never mistaken for
the section-8 heading.

## Validation (vs the reference JSON)

- 443 section nodes, 13 chapters — matches the reference counts exactly.
- `plain_text` similarity to the reference: **median 0.998**, 301 / 409 sections
  above 0.90.
- **0** malformed HTML fragments (sections *and* footnotes), **0** page-number
  bleeds, **0** stray glyphs.
- Footnote refs are printed-page (range 1–486), matching the reference.
- Footnote coverage: **2071 / 2300** (~90%) of the reference's footnotes; the
  gap is inline superscript markers not yet detected (see limitations). All 3
  real footnote rate-tables render as `fn-table` grids.

## Design note: omitted / repealed sections

Sections that were repealed appear in the PDF only as an empty amendment bracket
`N[ ]`, with their name and historical text living in a **footnote**. The old
model tried to inline that historical text into the body, which produced several
of the QA defects (`"3[ ] 3[ ]"`, *"should be combined with above page"*).

This pipeline instead keeps the current operative text in `html`/`plain_text`
and preserves the full historical text in `footnotes[]` (nothing is lost). A
section with no operative body text gets a clean heading-only placeholder. This
is a deliberate improvement; if you'd rather reproduce the reference's inlining
behaviour it can be switched on.

## Known limitations / next steps

- **Footnote coverage ~90%.** ~10% of inline citation markers aren't detected
  yet (some superscripts share a size band with body text, or sit on
  table-heavy pages), so their footnotes aren't attached. Improving superscript
  recall is the main lever to close this.
- **Footnote-table cell boundaries are approximate.** Tables render with the
  correct column count and styling, but a cell's text can be split slightly
  differently from the reference where the header and numbering rows use
  different x-positions.
- **Schedules are now extracted** (First–Fifteenth) with real content nested by
  Schedule → Part → Division, rendered `html`/`plain_text`/`footnotes` on each
  terminal node. ~95% of the reference's schedule text is captured. Two notes:
  leaf *granularity* is coarser than the reference (67 vs ~95 leaves — some
  First-Schedule divisions are merged), and this document contains a **Fifteenth
  Schedule** (added by a recent amendment) that the older reference JSON omits.
- **Body / schedule tables render** as `<table class="fbr-table">` (~31 in total:
  the s.182 penalties table, First-Schedule rate slabs, the Fourteenth-Schedule
  SME tables, the Fifteenth-Schedule threshold table, etc.). A table is detected
  by an `S. No.` / `Sr. No.` header or `TABLE` keyword anchored on a `(1) (2) …`
  numbering row, and ends when a subsection `(N)` or a line to the left of the
  table resumes. Columns are recovered geometrically: header row, row grouping
  and thead/tbody split are reliable, but on very dense, wide tables an odd word
  can land in a neighbouring column at a boundary. *Footnote* tables render as
  `fn-table` grids.
- **Bold text is preserved.** Runs of bold words (`Arial-BoldMT`) are wrapped in
  `<strong>` — e.g. the bold rule names in the Schedules (`1. Application.-`) and
  bold titles. Note the reference JSON does *not* keep bold, so this is a
  deliberate enhancement and a point where the output intentionally diverges.
- **Numbered rules** in the Schedules (`1.`, `2.`, …) each start their own
  paragraph rather than collapsing into one block, and all-caps titles are kept
  as their own heading paragraph.
