# Rules corpus — conversion ledger

Working record of what the `rules` lane actually contains, what it does not, and why.
Written 2026-08-24 because the answer to "is every PDF converted?" was not recorded
anywhere: `data/corpora/rules/` is gitignored, so the corpus itself could not answer it,
and unlike the acts lane there was no `reports/`, no `output/_run/`, no skip list. This
file is that record. It is an audit trail, not a second source of truth beside
`README.md` — safe to delete once its contents are no longer news.

## The answer

**No. 11 of 48 source PDFs are converted — and with OCR skipped, that is already
everything that can be.**

| | count |
|---|---|
| source PDFs under `data/corpora/rules/Rules/` | **48** |
| converted to `data/corpora/rules/output/*.json` | **11** |
| unconverted, blocked on OCR | **36** (391 image-backed pages in 4,396) |
| unconverted, refused for a non-OCR reason | **1** (Urdu edition, below) |
| converted **this** session | **0** |

The 48 is itself a finding. A `*.pdf` glob sees only 36 — **12 files carry no extension**
(`Customs Rules, 2001 (Updated Up to 30.06.2023)`, four `The Sales Tax Rules, 2006 updated
upto …` editions, seven Recruitment SROs). They are real PDFs by magic bytes, and one of
them, the 563-page Customs compilation, is in the shipped corpus today — so any tool that
globs `*.pdf` under-counts this corpus by a quarter and misses a document that is already
live. `convert_all.is_pdf()` reads the first five bytes instead, which is why the target
list below says 48.

## Why nothing new converted

`legal_ingest` decides page by page, not file by file, whether a page is a **scan** —
`pagemodel._page_is_scan` (`packages/legal_ingest/pagemodel.py:680`), true when an image
covers half the sheet, or when the images cover 90% of the page's *ink* and a fifth of the
sheet. An image-backed page is OCR'd **regardless of how much text it carries**, because
text sitting on top of a scan is somebody else's recognition, and its volume says nothing
about whether it is right (`pagemodel.py:813-829`). If that OCR cannot run, the pipeline
**aborts the document**:

> `RuntimeError: OCR failed on page 55 of '…Federal Excise Rules, 2005 (updated upto
> 31-10-2023).pdf': No module named 'numpy'. This page carries no usable text layer, so
> refusing to emit a document that would silently omit it.`

That refusal is deliberate (`pagemodel.py:838-853`) and it is doing its job here. The OCR
extras — `rapidocr-onnxruntime`, `onnxruntime`, `numpy`, `opencv-python`, pinned in
`packages/legal_ingest/requirements-ocr.txt` — are **not installed in `.venv`**, and
`tesseract` is on PATH but unusable without them.

So "convert everything, skip only OCR" is a no-op on this corpus **today**, and the
census proves it exactly rather than approximately: of 48 sources, **12 have zero
image-backed pages, and 11 of those 12 are the converted corpus**. The twelfth is the Urdu
edition below. Every one of the other 36 has at least one scanned page. None of the 11
carries a `metadata.ocr` block, confirming no OCR has ever run in this lane.

### Measured, 2026-08-24 16:37 — `convert_all.py rules --skip-existing --skip-scanned`

The first run used the 8-page sampling heuristic `is_scanned()` to decide what to skip. It
called 12 of the 37 text-layer, and **all 12 failed**, each on an image-backed page the
sample had not looked at:

| file | died on page | after |
|---|---|---|
| Federal Excise Rules, 2005 (updated upto 31-10-2023) | 55 | 10s |
| THE SALES TAX RULES, 2006 UPDATED UPTO 11.08.2014 | 80 | 37s |
| Sales Tax Rules 2006 (amended up to 30th June 2015) | 113 | 40s |
| The Sales Tax Rules, 2006 updated upto 30.10.2018 | 114 | 50s |
| The Sales Tax Rules, 2006 updated upto 30.06.2020 | 137 | 59s |
| The Sales Tax Rules, 2006 updated upto 31.12.2020 | 162 | 64s |
| The Sales Tax Rules, 2006 updated upto 31.08.2021 | 178 | 81s |
| The Sales Tax Rules, 2006 updated upto 31.10.2023 | 189 | 85s |
| Income Tax Rules, 2002 Amended upto 10th, December, 2015 | 194 | 110s |
| Income Tax Rules, 2002 Amended upto 8th September, 2020 | 411 | 154s |
| Income Tax Rules, 2002 Amended upto 24.11.2023 | 482 | 158s |
| Asset Declaration … 2019 Urdu Version | — | 1s (see below) |

Full report: `data/corpora/rules/output/_run/report.md`.

That is why `--skip-scanned` no longer samples. It now classifies with
`ocr.scanned_pages`, which shares `_page_is_scan` with the conversion path, so a file it
reports 0 for is a file that can never enter the OCR branch. One geometry pass over the
corpus, no recognition, against 167 seconds of conversions that could not finish — and,
more importantly, an exact skip list instead of a dozen identical `RuntimeError`s.

### Measured again, 16:50, with the exact classification

`0/1 converted in 194s`, and the run report now carries a **Skipped** table naming all 36
files with the page count each needs OCR for. The single attempt is the Urdu edition — the
one unconverted file with no scanned page — and it was refused for the reason below. No
document started work it could not finish, and the reason each of the 36 is absent is now
on disk in `_run/report.md` rather than only in a terminal that has since closed.

## The one non-OCR refusal

`Asset Declaration (Procedure and Conditions) Rules, 2019 - S.R.O 578(I)_2019 - Urdu
Version.pdf` has a real text layer (~5,000 chars/page) and no scanned pages, so it is the
only unconverted file OCR would not help. The conservation backstop
(`pipeline.py:745-783`) refused it:

> `20107 characters were read from the PDF but only 0 reached the document (0 section(s),
> 0 schedule(s)). The text was extracted and then dropped`

Correct outcome. Every parser above it — TOC grammar, section codes, ordinal repair — is
English-only, so the text is read and then matches nothing. The English version of the same
SRO is a scan, so this instrument has no readable edition in the corpus either way. Not a
bug and not on the OCR queue: it needs an Urdu-aware profile, which does not exist and is
not proposed here.

## The OCR queue

Everything in the table below needs, before it can be attempted:

```
.venv/bin/pip install -r packages/legal_ingest/requirements-ocr.txt   # + tesseract on PATH
python tools/convert_all.py rules --skip-existing
```

Two cautions on that run, neither of them hypothetical:

- **The fidelity floor was calibrated on the Acts corpus, not this one.**
  `AGREEMENT_FLOOR = 85.0` and `LOW_CONF_SHARE_CEILING = 15.0`
  (`packages/legal_ingest/ocr.py:56-59`) come from
  `data/corpora/acts/reports/ocr-exclusions.md`. A Rules edition below the floor will be
  **refused**, not shipped, and there is no equivalent review report for this lane to say
  how many that will be. The rules lane has no `ocr_review.py` (see below), so the first
  OCR run is also the measurement.
- **Cost is small — 391 pages, not 4,396.** The 36 queued files hold 4,396 pages between
  them, but only **391** are image-backed and need recognition; the rest have a text layer
  and parse the normal way. At the measured single-worker rate of 0.200 pg/s that is
  roughly **35 minutes of OCR** for the whole queue. `--ocr-batch` still defaults to 1
  (OCR is memory-bound, ~0.5-1 GB per ONNX session, and 4 workers measured 59% *worse*
  than 1), and `--timeout 5400` still applies per file — the 946-page edition needs its
  946 pages parsed either way.

The queue splits in two, and the halves carry very different risk:

| | files | pages needing OCR |
|---|---:|---:|
| **wholly scanned** — every page an image | 22 | 159 |
| **partly scanned** — text layer with scanned pages inside it | 14 | 232 |

The 22 wholly-scanned files are the short instruments: the Recruitment SROs, the PSW
regulations, FBR AML-CFT, Inland Revenue Uniform Rules 2021, Benami 2019. Their **entire**
text would come from recognition, so a sub-floor agreement refuses the whole document and
there is no partial result to fall back on. The 14 partly-scanned ones are the big
editions — Income Tax Rules 2002 needs 27 of its 946 pages, 46 of 377, 44 of 307 — where
OCR fills gaps in a document that is otherwise an exact text layer.

## Full inventory — 48 sources

| # | source (relative to `Rules/`) | pp | pages needing OCR | status |
|---:|---|---:|---:|---|
| 1 | `AML-CFT Sanction Rules, 2020/AML_CFT Sanction Rules, 2020.pdf` | 6 | 0 | **converted** |
| 2 | `Asset Declaration (Procedure and Conditions) Rules, 2019/Asset Declaration (Procedure and Conditions) Rules, 2019 - S.R.O 578(I)_2019 - English Version.pdf` | 3 | 3 | skipped — needs OCR (first at p1) |
| 3 | `Asset Declaration (Procedure and Conditions) Rules, 2019/Asset Declaration (Procedure and Conditions) Rules, 2019 - S.R.O 578(I)_2019 - Urdu Version.pdf` | 4 | 0 | not converted, no scanned page — see Urdu note |
| 4 | `Benami Transactions (Prohibition) Rules, 2019/Benami Transactions (Prohibition) Rules, 2019.pdf` | 9 | 9 | skipped — needs OCR (first at p1) |
| 5 | `Counter-Measures for High Risk Jurisdiction Rules, 2020/Counter-Measures for High Risk Jurisdiction Rules, 2020.pdf` | 4 | 0 | **converted** |
| 6 | `Customs Reward Rules, 2012/Customs Reward Rules, 2012.pdf` | 5 | 5 | skipped — needs OCR (first at p1) |
| 7 | `Customs Rules, 2001 (Updated Up to 30.06.2023)/Customs Rules, 2001 (Updated Up to 30.06.2023)` | 563 | 0 | **converted** |
| 8 | `FBR AML-CFT Regulations/FBR AML_CFT Regulations.pdf` | 18 | 18 | skipped — needs OCR (first at p1) |
| 9 | `Federal Excise Rules 2005/Federal Excise Rule Updated Upto 10.07.2014.pdf` | 77 | 0 | **converted** |
| 10 | `Federal Excise Rules 2005/Federal Excise Rules 2005 (amended up to 30th June 2015).pdf` | 78 | 0 | **converted** |
| 11 | `Federal Excise Rules 2005/Federal Excise Rules, 2005 (updated upto 31-10-2023).pdf` | 95 | 6 | skipped — needs OCR (first at p55) |
| 12 | `Income Tax Rules, 2002/ Income Tax Rules, 2002 Amended upto 10th February, 2017.pdf` | 318 | 29 | skipped — needs OCR (first at p1) |
| 13 | `Income Tax Rules, 2002/ Income Tax Rules, 2002 Amended upto 10th, December, 2015..pdf` | 248 | 18 | skipped — needs OCR (first at p1) |
| 14 | `Income Tax Rules, 2002/ Income Tax Rules, 2002 Amended upto 18th October, 2016.pdf` | 307 | 44 | skipped — needs OCR (first at p1) |
| 15 | `Income Tax Rules, 2002/ Income Tax Rules, 2002 Amended upto 24.11.2023.pdf` | 946 | 27 | skipped — needs OCR (first at p1) |
| 16 | `Income Tax Rules, 2002/ Income Tax Rules, 2002 Amended upto 8th September, 2020.pdf` | 631 | 23 | skipped — needs OCR (first at p411) |
| 17 | `Income Tax Rules, 2002/Income Tax Rules, 2002 Amended up to August, 2008.pdf` | 377 | 46 | skipped — needs OCR (first at p1) |
| 18 | `Inland Revenue Uniform Rules, 2021/Inland Revenue Uniform Rules, 2021.pdf` | 26 | 26 | skipped — needs OCR (first at p1) |
| 19 | `Pakistan Single Window Evidence of Identity (EOI) Regulations/PSW Evidence of Identity Regulations, 2023.pdf` | 5 | 5 | skipped — needs OCR (first at p1) |
| 20 | `Pakistan Single Window Evidence of Identity (EOI) Regulations/Pakistan Single Window Evidence of Identity (EOI) Rules, 2022.pdf` | 3 | 3 | skipped — needs OCR (first at p1) |
| 21 | `Pakistan Single Window Integrated Risk Management System Rules, 2023/Pakistan Single Window Integrated Risk Management System Rules, 2023.pdf` | 6 | 6 | skipped — needs OCR (first at p1) |
| 22 | `Pakistan Single Window Trade Data Dissemination, Exchange and Utilization Rules/Pakistan Single Window Trade Data Dissemination, Exchange and Utilization Rules, 2022.pdf` | 7 | 7 | skipped — needs OCR (first at p1) |
| 23 | `Pakistan Single Window Trade Data Dissemination, Exchange and Utilization Rules/S.R.O406(I)_2023 - PSW Trade Data Dissemination, Exchange and Utilization Rules, 2023.pdf` | 7 | 7 | skipped — needs OCR (first at p1) |
| 24 | `Recruitment Rules/Administration Wing of the Federal Board of Revenue (HQ)/ SRO 1127(I)_2012 dated 12.09.2012` | 5 | 5 | skipped — needs OCR (first at p1) |
| 25 | `Recruitment Rules/Administration Wing of the Federal Board of Revenue (HQ)/ SRO 350(I)_2018 dated 02.03.2018` | 3 | 3 | skipped — needs OCR (first at p1) |
| 26 | `Recruitment Rules/Auditors of Sales Tax Department under SRO 1126(I)_2010 dated 27.11.2010` | 5 | 5 | skipped — needs OCR (first at p1) |
| 27 | `Recruitment Rules/Department of Research and Statistics/SRO 1018(I)_1984,1019(I)_1984,1020(I)_1984.pdf` | 4 | 4 | skipped — needs OCR (first at p1) |
| 28 | `Recruitment Rules/Department of Research and Statistics/SRO 716(I)_2000 dated 22.09.2000` | 5 | 5 | skipped — needs OCR (first at p1) |
| 29 | `Recruitment Rules/Small Cadre of Inland Revenue Sales Tax SRO 44(I)_2015 dated 16.01.2015` | 3 | 3 | skipped — needs OCR (first at p1) |
| 30 | `Recruitment Rules/Unified IT Cadre of Inland Revenue Department/SRO 82(I)_2018 dated 18.01.2018` | 5 | 5 | skipped — needs OCR (first at p1) |
| 31 | `Recruitment Rules/Unified IT Cadre of Inland Revenue Department/SRO 953(I)_2012 dated 02.08.2012` | 7 | 7 | skipped — needs OCR (first at p1) |
| 32 | `Sales Tax Rules 2006/Sales Tax Rules 2006 (amended up to 30th June 2015).pdf` | 149 | 6 | skipped — needs OCR (first at p113) |
| 33 | `Sales Tax Rules 2006/Sales Tax Rules 2006 updated upto 30-06-2025.pdf` | 224 | 0 | **converted** |
| 34 | `Sales Tax Rules 2006/Sales Tax Rules, 2006 (Updated upto 01-01-2025).pdf` | 241 | 0 | **converted** |
| 35 | `Sales Tax Rules 2006/THE SALES TAX RULES, 2006 UPDATED UPTO 11.08.2014.pdf` | 113 | 6 | skipped — needs OCR (first at p80) |
| 36 | `Sales Tax Rules 2006/The Sales Tax Rules, 2006 updated upto 30.06.2020` | 193 | 6 | skipped — needs OCR (first at p137) |
| 37 | `Sales Tax Rules 2006/The Sales Tax Rules, 2006 updated upto 30.10.2018.pdf` | 150 | 4 | skipped — needs OCR (first at p114) |
| 38 | `Sales Tax Rules 2006/The Sales Tax Rules, 2006 updated upto 31.08.2021` | 241 | 5 | skipped — needs OCR (first at p178) |
| 39 | `Sales Tax Rules 2006/The Sales Tax Rules, 2006 updated upto 31.10.2023` | 251 | 6 | skipped — needs OCR (first at p189) |
| 40 | `Sales Tax Rules 2006/The Sales Tax Rules, 2006 updated upto 31.12.2020` | 218 | 6 | skipped — needs OCR (first at p162) |
| 41 | `Sales Tax Special Procedure (Withholding) Rules, 2007/Sales Tax Special Procedure (Withholding) Rules, 2007 (amended up to 30th June 2015).pdf` | 12 | 0 | **converted** |
| 42 | `Sales Tax Special Procedure (Withholding) Rules, 2007/THE SALES TAX SPECIAL PROCEDURE (WITHHOLDING) RULES, 2007 UPDATED UPTO 05.08.2014.pdf` | 12 | 0 | **converted** |
| 43 | `Sales Tax Special Procedures Rules, 2007/SALES TAX SPECIAL PROCEDURES RULES,, 2007 UPDATED UPTO 05.03.2015.pdf` | 60 | 0 | **converted** |
| 44 | `Sales Tax Special Procedures Rules, 2007/Sales Tax Special Procedures Rules, 2007 (amended up to 30th June 2015).pdf` | 59 | 0 | **converted** |
| 45 | `Sharing of Declaration of Assets of Civil Servants Rules, 2023/Sharing of Declaration of Assets of Civil Servants Rules, 2023.pdf` | 5 | 5 | skipped — needs OCR (first at p1) |
| 46 | `The Federal Board of Revenue Rules, 2007/The Federal Board of Revenue Rules, 2007.pdf` | 3 | 3 | skipped — needs OCR (first at p1) |
| 47 | `The Inland Revenue Reward Rules, 2021/The Inland Revenue Reward Rules, 2021.pdf` | 5 | 5 | skipped — needs OCR (first at p1) |
| 48 | `The Pakistan Single Window (Deputation-Secondment of Civil Servants) Regulations, 2021/The Pakistan Single Window (Deputation_Secondment of Civil Servants) Regulations, 2021.pdf` | 20 | 20 | skipped — needs OCR (first at p1) |
*48 sources · 11 converted · 12 with zero image-backed pages · 36 with at least one · 0 unreadable.*

Generated from `data/corpora/rules/reports/scan-census.json` (`legal_ingest.ocr.scanned_pages`, the same `_page_is_scan` predicate the
conversion path applies). That file is gitignored with the rest of the corpus, so this table is the committed copy.


## Gate

`python tools/run_suite.py rules` — **green, unchanged from `main`**: 11 editions, 53
invariants, exit 0. Nothing was added to the corpus, so nothing new is gated and no
exemption was added to `tools/suite/exemptions/rules.json` (still the 8 Phase-6b entries).
`make check` is unaffected.

Once the OCR queue lands, this is where it will be spent: the eight existing exemptions
were each traced to a source PDF before being written, and ~36 new documents will need the
same treatment for whatever they fail. That triage is not this change.

## Still open for this lane

- **No `ocr_review.py`, no `audit_all.py`, no `audit_completeness.py` equivalent.** All
  three are acts-only under `tools/acts/`, and two of them are **broken at import today**:
  `audit_all.py:26` does `from scripts.convert_all import …`, a path that has not existed
  for two refactors, and `ocr_review.py:44` does `from acts_ingest import ocr`. So the
  fidelity review that ought to precede an OCR run cannot be run for any lane right now.
  Deliberately not fixed here.
- **`make seed-archive` still packages only ordinance and acts** (`Makefile:82-112`), so
  the rules corpus is not in the API image.
- **`data/corpora/rules/reports/` is empty** apart from the census this change writes. The
  acts lane has `ocr-exclusions.md`, `ocr-queue-*.txt`, `anomalies-ocr.md`,
  `qa-*.json`; none of those exist for rules.

## What this change actually shipped

| | |
|---|---|
| `tools/acts/convert_all.py` → `tools/convert_all.py` | lane is an argument, as in `convert.py` and `run_suite.py`. Closes the asymmetry logged at `tasks.md:645-647`. `--family`/`--phase` stay acts-only and now say so instead of silently matching nothing. |
| `--skip-scanned` | new. Classifies with the exact per-page predicate and reports the skips into `_run/report.md`. |
| `make convert-all LANE=… ARGS='…'` | new target; `README.md` command table updated. |
| `data/corpora/rules/reports/scan-census.json` | new. Per-file page count, scanned-page count, first scanned page. Gitignored, so the table above is the committed copy. |
| documents converted | **0** — see "Why nothing new converted". |
