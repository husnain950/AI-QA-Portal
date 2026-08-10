# `scripts/` — CLI entry points

Each script bootstraps the repo root onto `sys.path` and anchors its default
paths there, so they can be run from any working directory.

| Script | Purpose |
|---|---|
| `fbr_pdf_to_json.py` | Convert the PDF to structured JSON via the pdfplumber pipeline (`-o` to choose the output path). |
| `run_tests.py` | Run the shared regression suite (17 invariants + `tests/cases.json`) against an output JSON; defaults to `output/*.json`. Non-zero exit on failure (CI-friendly). |
| `add_test_case.py` | `inspect` what a section/schedule currently produces; `add` a regression case (verified against the current output before saving). |
| `import_qa_report.py` | Turn a QA-review export into regression cases with stable ids (re-import adds nothing). See `tests/README.md` for the triage workflow. |
| `audit_completeness.py` | Word/punctuation conservation audit: compares what the pipeline *saw* (`--pdf`, or a page-model pickle cache via `--cache`) against what landed in the output. |
