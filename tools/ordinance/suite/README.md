# Post-conversion regression tests

> **Vendored.** Copied from the standalone pipeline repository (`CC-FBR/tests/`), which is
> not part of this monorepo. Paths below are written for that layout; here the runner is
> [`tools/ordinance/run_tests.py`](../run_tests.py) and the corpus it defaults to is `$CORPUS_ORDINANCE`
> (`data/corpora/ordinance/`), not `./output/`. The package is imported as `suite`, not
> `tests`, so it cannot collide with `tools/tests` (the deploy-script tests).
>
> `python tools/run_tests_smoke.py` runs this suite whenever that corpus is present, and
> skips it when it is not — which is what CI does, since the corpus is gitignored.
>
> Re-syncing from upstream is an `rsync` plus the two edits above; keep it that way.

A safety net so that fixing one extraction issue can't silently break another.
It runs against a converted JSON and checks both broad invariants and specific,
per-issue cases (seeded from this project's discussions and the QA report).

## Completeness gate (nothing dropped)

For a legally binding text, the worst failure is *silent loss* — a missing `[`,
`.`, or amendment marker. `run_tests.py` guards behaviour; **`audit_completeness.py`
guards conservation**. Run it after every regeneration:

```bash
python scripts/audit_completeness.py            # compares source (page cache) vs output
python scripts/audit_completeness.py --pdf X.pdf  # or scan the PDF directly
```

It reconstructs the text the pipeline *saw* (zoned body + footnote words for every
page) and compares it, as multisets, to what landed in the output (section/leaf
text + table cells + footnote text + preamble). It prints every word and every
key punctuation mark present in the source but missing from the output.

Current conservation: **body ≈ 99.97%, footnotes ≈ 99.96%**. The small residual is
audit tokenization noise (a word split across two table cells, hyphenation across
a line break) rather than real loss — the report lets you tell them apart quickly
(a genuinely missing token appears nowhere in the output; a split one does). Treat
a *drop in the conservation number* between runs as a regression to investigate.

## Working habit: a case for every scenario

Every fix or reported issue gets a locked-in test **in the same change**, so it
can never silently regress. The rule of thumb:

1. **Reproduce** — inspect the target (`python scripts/add_test_case.py inspect --section N`)
   and confirm what's wrong.
2. **Fix** the pipeline.
3. **Lock it** — add an `active` case asserting the corrected behaviour
   (`add_test_case.py add ...`, or by hand in `cases.json`). If the class of bug
   can occur elsewhere, add a **global invariant** instead of / in addition to
   the case (e.g. `no_page_number_bleed`, `no_footnote_text_in_body`).
4. **Re-run everything** — `python scripts/run_tests.py` must be green before moving on.

Guidelines:
- Prefer the **most specific** assertion that still reads as intent (e.g.
  `division_table_count == 2`, `schedule_max_table_rows >= 100`) over a vague
  substring check.
- A recurring *class* of defect → a global invariant (catches it document-wide).
  A one-off location → a data-driven case.
- Un-verifiable / subjective items go in as `needs_review` (tracked, non-failing)
  until they can be turned into a real assertion.
- New QA reports: `python scripts/import_qa_report.py REPORT.json`, then triage the
  `needs_review` items into `active` as they're addressed.

The suite currently covers, among others: page-number bleed, PUA glyph, printed-
page footnote refs, footnote html + tables (fn-table), inserted subsections as
their own `<li>`, wrapped/dash-less heading duplication, structural-heading
bleed, omitted-section footnotes, schedule codes + division headings, the two
`Division I` entries, body/footnote/schedule tables via gridlines,
page-spanning table merges, and — from the Division V root-cause pass —
title-case **bold heading detection** (lifted out of the body, canonical TOC
casing), the **list-item vs wrapped-cross-reference** disambiguation
(previous-line context, not just the following word), 8–9pt **amendment markers
rendered as `<sup class="cite">`** (marker size threshold), and **hyphenated
compounds** split across a TOC line ("Non-resident"). The 06-Jul QA import
added the **block-layout** cases: centred formula blocks (ss. 12/14/24/35/37A/38),
the two stacked fractions rendered with a real bar (s.24(3) `A/B`, s.233(2A)
`A x 15/85`), proviso / explanation / definition lines opening their own
indented block, and omitted-clause brackets (`5[ ]`) on their own line
(ss. 114/115). The 08-Jul QA screenshots added the **table-structure** cases
(`qa0708_*` + `review_*`): merged-cell colspans in body tables (Division II
company/super-tax, Division VIIIA builders, Eleventh Schedule bands), the
sub-header + `(1) (2) …` numbering rows kept inside `<thead>` (also the
global `numbering_row_in_thead` invariant), a page-split ruled header box
merged onto its next-page data grid (Part IV Division III), and grid-backed
fn-tables: spanning headers (fn 533.1 "Rate applicable on the amount of
payment."), wrapped header lines assembled into cells (fn 535.1/535.4), and
a page-split last row re-joined (fn 535.4) — all conservation-guarded so a
grid whose box does not contain its whole table falls back to the text
heuristics instead of dropping words (fn 504.1). The 10-Jul QA screenshots
added the `qa0710_*` cases (25): geometric colspan **and rowspan** from cell
bboxes (Division VIII/IIB tall rate cells, s.182's empty column preserved on
continuation fragments), struct-based continuation merges (s.182 rows 25-28,
Division IIB row 8's wrapped tail fused whole, single-row fragments demoted
to text when nothing merges), per-table sliver healing (Division VIIIB's
six-column developers grid), fn grid-fit trimming with marker-token fusing
(fns 510.1/514.2/546.1/502.3), and the gridless-quoted-table heuristics:
columnar-run starts (fns 698.1/495.3), prose-end with serial-sequence
exemption (PEMRA fn 546.1, fn 504.1's data rows), numbering-centre column
fallback (fn 502.3's "Nil" interleave), per-line spanning headers
(fn 521.1), and ALL-CAPS band rows (fn 698.1's BUILDINGS/FURNITURE). The
14-Jul QA screenshots added the `qa0714_*` cases: TOC division rows carrying
their printed page inline ("Division I 533") must classify as divisions —
First Schedule Part IV's heading had swallowed its whole division listing as
continuation text, leaving Divisions II/III without their canonical headings
(also guarded document-wide by the `no_toc_row_in_heading` invariant).

## Run

```bash
python scripts/run_tests.py                       # test ./output/*.json
python scripts/run_tests.py path/to/output.json   # test a specific file
python scripts/run_tests.py --pdf INPUT.pdf       # (re)convert first, then test
python scripts/run_tests.py --json report.json    # also write a machine-readable report
```

Exit code is non-zero if any invariant or **active** case fails — drop it into CI
or a pre-commit hook.

## Two layers

**Global invariants** (`tests/invariants.py`) hold for the whole document, so a
regression anywhere is caught, not just in the one section originally reported:

| invariant | guards against |
|---|---|
| `no_pua_glyphs` | the U+F0D8 asterisk / other private-use glyphs |
| `no_page_number_bleed` | a running-footer page number leaking into text |
| `footnote_schema` | every footnote has `ref/marker/text/html` |
| `footnote_refs_printed_page` | refs are `<printed-page>.<marker>` |
| `no_year_marker_refs` | a quoted year ("2020") minting a bogus footnote marker |
| `no_split_ordinals` | a raised `st/nd/rd/th` emitted as its own stray word/`<p>` |
| `leading_marker_cited` | a heading-region marker with no visible `<sup>` citation |
| `no_jammed_words` | justified lines glued into 25+ letter runs |
| `html_well_formed` | every `html` fragment parses (incl. footnotes) |
| `strong_balanced` | `<strong>` tags are balanced |
| `no_heading_word_duplication` | wrapped heading word restarting the body |
| `schedules_have_content` | no schedule is an empty shell |
| `no_footnote_text_in_body` | footnote-zone text spliced into body content |
| `footnote_on_citing_leaf` | a footnote attached to a leaf that doesn't cite it while another leaf does (the shared-page leak, e.g. Division V carrying IV/IVA's 501.x); duplicate attachment of an uncited footnote; a rendered citation whose footnote is attached elsewhere only |
| `no_control_chars` | a table-cell citation sentinel (`\x01…\x02`) leaking unexpanded into html/plain_text (guards `builder._expand_table_cites` coverage) |
| `preamble_present` | the pre-section-1 preamble going missing |
| `no_toc_row_in_heading` | a TOC row ("Division I 533") swallowed into a structural heading |
| `structure_counts` | 13 chapters, ≥440 sections, ≥14 schedules |

**Data-driven cases** (`tests/cases.json`) pin specific issues. Each case targets
a section / schedule / footnote and runs one `check`. `status: active` must pass;
`status: known_gap` is tracked but doesn't fail the build (documents something we
don't fully match yet, e.g. the ~8% of citations with no resolved footnote text).

## Importing a QA report

When you get a new QA-review export, turn its findings into cases automatically:

```bash
python scripts/import_qa_report.py QA_Report.json --dry-run   # preview classification
python scripts/import_qa_report.py QA_Report.json             # append new cases
python scripts/run_tests.py                                   # see which are open
```

Each annotation becomes a case with a **stable id** (hash of section + flagged
text + issue), so re-importing the same report adds nothing and a newer report
only contributes its new findings. Classification is deliberately conservative:

| annotation kind | check generated | status |
|---|---|---|
| page-number bleed (`"...] 168"`, `"inheritance. 157"`) | `plain_not_contains` | **active** |
| private-use glyph (U+F0D8) | `html_not_matches` (PUA range) | **active** |
| "missing X" | `plain_contains` (guessed phrase) | needs_review |
| formatting / "as per PDF" / bullets / line-breaks | `plain_not_contains` (suggested) | needs_review |

Only the reliably-checkable items are **active** (they must pass). Everything
subjective lands as **needs_review** — tracked and reported, but never fails the
build until you refine the assertion and promote it to `active`. This avoids
turning free-text review notes into false test failures.

## The capture workflow

Point at an issue, see what the output currently is, then log the expected
behaviour as a case:

```bash
# 1) inspect what a section/schedule currently produces
python scripts/add_test_case.py inspect --section 4
python scripts/add_test_case.py inspect --schedule FIFTEENTH

# 2) log the expectation (it is verified against the current output before saving)
python scripts/add_test_case.py add --id sec3_no_page_31 --section 3 \
    --check plain_not_matches --arg "\b31\s*$" \
    --desc "Sec 3: page number 31 must not bleed into text"

# 3) fix the pipeline, then re-run everything
python scripts/run_tests.py
```

### check types

Plain/html on the target section: `plain_contains`, `plain_not_contains`,
`plain_matches`, `plain_not_matches`, `html_contains`, `html_not_contains`,
`html_matches`, `html_not_matches`, `has_fbr_table`, `has_subsection_li`,
`body_not_starts_with`; document-wide: `section_code_count`,
`any_section_html_contains`.

Footnotes: `footnote_text_nonempty`, `footnote_any_contains`,
`footnote_contains`, `footnote_html_contains`, `footnote_html_has_table`,
`footnote_ref_distinct_texts`, `footnote_refs_exact` (the target leaf's — or,
with `div`/`div_heading`, division's — footnote refs equal `arg` exactly; pins
the footnote-to-leaf mapping), `footnote_not_contains` (no footnote with that
ref may contain `arg`; guards body text leaking into footnotes),
`footnote_html_not_contains` (the ref's html must not contain `arg`; guards
quoted prose clauses from rendering as fn-tables).

Schedules and their divisions: `schedule_has_table`, `schedule_code_equals`,
`schedule_max_table_rows`, `division_table_count`, `division_code_count`,
`division_heading_contains`, `division_body_excludes`, `division_html_contains`,
`division_html_not_contains`, `division_page_range`,
`division_footnote_contains` (the `division_*` checks match a division by
**code + heading substring**, so they pin the right one when several parts share
a code; `div` also matches a content-bearing PART, e.g. `"PART II"` of the
Twelfth Schedule).

Chapter tree: `tree_division_heading_contains` (a division with code `div` must
exist under some *chapter* with a heading containing `arg` — pins structural
headings like Chapter III's "Division II — Deductions: General Principles",
which the old reference JSON had swallowed into a neighbouring section's body).

Add a new kind of assertion by adding one function to `tests/checks.py` and the
name to its `REGISTRY`.

## Making this a Cowork skill

The `inspect → add → fix → run` loop is exactly a skill-shaped workflow. Skills
are installed from **Settings → Capabilities** (they can't be registered from a
chat session). To package this, wrap these two scripts in a `SKILL.md` that tells
the agent to (1) `inspect` the reported target, (2) `add` a case for the expected
behaviour, (3) fix the pipeline, (4) `run_tests.py` until green.
