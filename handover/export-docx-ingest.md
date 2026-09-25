# Ingest the Word-derived export (2026-09-25): five 2026 editions

Source: `~/Documents/Claude/Projects/export/`, five folders, each with a Word file and a
converted JSON. **No converter in this repo made them**: `metadata.filename` names the
`.docx`/`.doc`, `pipeline_revision` is `unknown`, `source_kind` is `docx`/`doc`, and the
page numbers are Word's saved page breaks (the `.doc` has a character-share estimate).
There is no PDF.

**Local: ingested. Production: pushed 2026-09-25**, 68 → 73 documents (see the end).

## What stood in the way, and what this PR does about it

| problem | measured | change |
|---|---|---|
| The two rules files say `rules[]` where the contract says `sections[]`, and carry a root `forms[]` (STR: 43 forms + 15 annexes) | portal parse: FED Rules **1** leaf, STR **1** leaf (the preamble) | `json_parser.LEAF_LISTS = ("sections", "rules", "forms")`; `overlays._LEAF_SEGMENTS` reads it too, or an AI-fix overlay on a rule would never resolve |
| No PDF | — | rendered with `soffice --headless --convert-to pdf` (1 min for all five) |
| LibreOffice does not paginate like Word, and the gap **grows** through the document | ITO s.114 declared p210, prints p224; s.147 p286 → p304; s.236G p454 → p487 | `tools/remap_pages_to_pdf.py` re-pages each leaf by finding its heading in the rendered PDF |
| `source_kind: docx` is not a kind the backend knows, so it fell back to scanning the rendered PDF | ITO badged **Mixed OCR · pdf-inferred**, OCR badge on every leaf | `document_provenance.WORD_SOURCE_KINDS` → native-digital |
| `push-remote` pushes every local document, and the local DB holds the 19 editions held back from production last round | local 68 vs production 44 at its last count (#119) | `push_corpus --match TEXT` (repeatable) |

### The re-paging

Each leaf is looked up by `code` + `heading` (or else by the first substantial line of
`plain_text`), near where the running offset says it should be, and never before the
leaf above it. Four rules came out of the measurement:

- **Contents pages are skipped.** A page naming ≥10 leaf headings is contents. On this
  export every contents page names 10–30 and no body page names more than 8. LibreOffice
  lays STR's Word contents field out as 16 pages, which puts rule 1 13 pages past its
  declared page. Without the skip, STR located **4 of 420** leaves.
- **The window is wider (±36) until the first leaf is found**, and ±12 after that, since
  the offset from the front matter is unknown until then.
- **A leaf whose declared page is a default is placed only on a unique match.** A
  default here means a page more than 12 behind one already passed in tree order.
  The export declares ITO's Division IX and Twelfth Schedule parts, and STR's six omitted
  chapters, on page 1. They are placed only where their heading prints exactly once,
  and are otherwise left as declared.
- End pages follow the next leaf's start, and footnote pages move with their leaf.

Every rule has a test that fails when the rule is reverted (`python -B`, one mutant at a
time).

**Independent check:** does each leaf's *last* line of text print inside its
`[start_page, end_page]`? The remap placed leaves by their *first* line, so this is not
circular.

| edition | lane | leaves | footnotes | Word → PDF pages | located | contents pp. skipped | last line in span: before → after |
|---|---|---:|---:|---|---:|---:|---|
| Federal Excise Act, 2005 updated upto 30-06-2026 final 22-07-2026 | federal_excise | 77 | 373 | 103 → 109 | 62/77 | 3 | 11.1% → **88.9%** |
| Federal Excise Rules, 2005 updated upto 16-09-2026 | federal_excise_rules | 137 | 167 | 106 → 117 | 129/136 | 7 | 0.8% → **97.7%** |
| Income Tax Ordinance, 2001 Amended upto 30.06.2026 | ordinance | 450 | 3,703 | 821 → 831 | 415/452 | 0 | 0.7% → **89.1%** |
| Sales Tax Act, 1990 updated by Finance Act, 2026 upto 30.06.2026 final 22-07-2026 | sales_tax | 179 | 1,083 | 229 → 242 | 126/178 | 5 | 0.0% → **87.3%** |
| Sales Tax Rules, 2006 Updated upto 10-08-2026 | sales_tax_rules | 415 | 420 | 232 → 237 | 385/420 | 15 | 0.0% → **94.2%** |

The misses after the remap are a median of **1 page** off. Before, the median miss was
4–38 pages. "Located" counts paged nodes; the preamble has no page, so it is not among
them.

Checked by eye in the review page: ITO s.114 opens on PDF p224 showing "114. Return of
income", and STR form STR-1 opens on p166 showing the Taxpayer Registration Form. Both
are badged Native digital. The Playwright smoke passes 5/5 on these documents.

## How they were ingested

- Staged at `data/corpora/_imports/export-2026-09-25/<name>/<name>.{json,pdf}`. That
  directory is gitignored and is not a lane, so convert-all, the lane suites and
  reconciliation never see it. The originals in `~/Documents` are untouched.
- Folder names were normalised so lane and statute family resolve by name: `FED Act`
  → `Federal Excise Act`, `FED-Rules` → `Federal Excise Rules`, `STR-2006` →
  `Sales Tax Rules, 2006`, and double spaces collapsed. Checked with `classify_lane`
  and `family_key_from_name`: each joins its existing family.
- `python -m backend.sync_acts --source <that dir>` ran on this branch's code. That is
  the existing one-folder-per-edition mode, giving `source_type=acts_corpus`,
  source_key = folder name, and deterministic ids. It sets no `corpus_origin`, so a
  later `make sync` never withdraws these editions.
- Ten blobs were copied into the `crx-api-1` volume with `docker cp`, because the
  Compose blob mount still points at an empty named volume.

| local portal | before | after |
|---|---:|---:|
| documents | 68 | **73** |
| sections | 10,761 | **12,019** |

## Side effects of the sync, and a bug it exposed

`run_sync` always ends with a corpus-wide detector pass. Across the two runs it did this:

- **New documents:** 109 detector findings, plus 25 quality-flag findings. The quality
  flags were seeded by run 1 and **marked `fixed` by run 2 while the flags are still on
  the sections** (ITO still has 11 `heading_body_bleed`).
  - **This is a pre-existing bug, and it hits the whole corpus.**
    `run_detectors_and_store` calls `close_stale` *before* `seed_from_quality_flags`.
    `close_stale` closes every seeded finding as stale, and the seeder then skips the
    fingerprint because it exists, so it never reopens.
  - Every second sync therefore marks every seeded quality flag `fixed`. Not fixed here:
    it is its own PR.
- **Older editions:** 111 findings opened and 21 closed. Adding an edition changes the
  cross-edition detectors' pairings (`markup_only_drift` on the ITO editions). The local
  DB is also rounds stale.

## Known gaps

- **Three ITO leaves are still on page 1**: Twelfth Schedule Parts I, II and III. None has
  a heading, and all three open with the same `PCT CODE | DESCRIPTION` table header, so
  no match is unique. The tool refuses to guess.
- **The PDF is LibreOffice's rendering**, not FBR's print. Page numbers now index that
  PDF. An official PDF would need its own remap.
- **Footnote markers read like `209.1`** (Word page.footnote index) where the page
  prints `1`. They are baked into the export's HTML.
- Form leaves label as "Section STR-1" in the sidebar, because `FORM` is not in the web
  `CONTAINER_CODE_RE`. Cosmetic.
- A container node carrying `html` *and* children loses its own html. This is existing
  portal behaviour; ITO has 3 such nodes, e.g. First Schedule Part I "(See Chapter II)".
- The Compose `web` container's Vite proxy targets `127.0.0.1:8000` inside its own
  container, so every document's PDF 502s through :5173, old ones included. Verified
  through a host Vite on :5174 instead.
- Whatever produced this export emits `rules[]`/`forms[]` outside the contract. The
  portal now reads it; the producer should still be fixed if more exports come.

## Production

Done on 2026-09-25, after #122 merged and its deploy of `6865dca` went green
(run 36126923216).

- **Dry run:** `--match` with each of the five full edition names printed `5 selected`,
  `68 on production: 0 to refresh, 5 to upload (44 MB)`. Full names are needed:
  `Sales Tax Rules, 2006` alone also matches editions held back from production.
- **Backup:** `make backup-remote` wrote `review-snapshot-20260925-123033.json`, 18.8 MB,
  **68 of 68**. The first attempt got 67 because of a truncated read, so it was re-run.
- **Canary:** FED Rules alone was sent in 0.3 min. Prod read `total_sections` **137**, badged
  native-digital, with its PDF at full size (4,424,533 bytes). Prod was on the new parser,
  so the delete-and-stop branch was not needed.
- **The other four:** `4 sent, 0 failed` in 5.9 min (ITO's 23 MB took 1.5 min). Prod now
  has **73** documents.
  - The first three attempts died before sending anything. Each got an `IncompleteRead`
    on the 86 KB `GET /api/documents` inside `existing_docs()`, which has no retry.
  - The same truncation hits curl and plain `urllib`: about 4 in 30 reads today, not tied
    to login or HTTP version. Re-running is safe, because the tool re-plans from prod on
    every run.
- **Verification:**
  - A second dry run shows `73 on production: 5 already identical`, with no duplicate names.
  - `total_sections` matches local for each: 77 / 137 / 450 / 179 / 415. All five are
    native-digital. `/health/ready` returns 200.
  - All five PDFs return 200. ITO's first fetch came back short (973 KB of 18.0 MB), but
    prod's `Content-Length` is 17,984,339, and two full downloads hash to its
    content address `5e33bf68…`. The blob is intact; the fetch was truncated.
- **Shortlist:** a `prune_corpus.py` dry run against prod reads **keep 68, delete 5**. The
  shortlist CSV names none of these five, so a `--apply` would delete all of them.
  Nothing was deleted. Add them to the shortlist, or leave `--apply` alone, before the
  next prune.
