# `fbr_ingest` — the pdfplumber pipeline

The primary PDF → JSON extraction package (MIT-licensed dependency stack).
Entry point: `python tools/convert.py ordinance <PDF>` from the repository root.
Output schema, design decisions and the full numbered list of QA fixes live in
the [top-level README](../README.md).

| Module | Responsibility |
|---|---|
| `toc.py` | Parses the Table of Contents into the Chapter→Part→Division→Section tree and an ordered section list with printed page numbers. |
| `pagemodel.py` | Per-page geometry. Splits every page into header / body / footnote-block / footer zones, normalises glyphs, merges split words, marks superscript markers, keeps gridline table bboxes. |
| `footnotes.py` | Reads each page's footnote block into ordered `{marker: text}` entries; splices cross-page continuations; renders footnote html incl. `fn-table` grids. |
| `builder.py` | Splits the running body into sections, resolves inline citation markers, renders `html` + `plain_text` + `footnotes`. `_layout_blocks` gives PDF-distinct lines (centred formulas & stacked fractions, provisos, explanations, quoted-term definitions, empty omitted brackets) their own block in the html. |
| `schedules.py` | Extracts the Schedules (First–Fifteenth), segmented by Schedule/Part/Division headings, content attached to each terminal node. |
| `tables.py` | Detects tables in body/schedule text and renders `<table class="fbr-table">`. |
| `pipeline.py` | Orchestrates: TOC → calibrate page offset → sanitize misprinted footers → scan body + schedules → assemble → JSON. |

Every behaviour change must keep `python tools/run_suite.py ordinance` green (51 invariants +
the active cases in `tests/cases.json`).
