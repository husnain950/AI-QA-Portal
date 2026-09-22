# Prune the corpus to the 2021+ shortlist — before / after

Source of truth: `Untitled spreadsheet - 1. Shortlist 2021+.csv`, 68 rows.
Run 2026-09-22 against the local Compose stack. **Production not yet pruned.**

## Local portal

| | before | after |
|---|---:|---:|
| documents | 116 | **44** |
| sections | 23,588 | 9,647 |
| document_versions | 299 | 121 |
| findings | 5,381 | 1,454 |
| statute_families | 29 | 11 |
| jobs | 4 | 2 |
| review_events | 91 | 91 *(append-only, trigger rejects DELETE)* |
| users | 2 | 1 *(admin recreated from `.env` on restart)* |
| annotations | 1 | 0 |

## Disk

| | before | after |
|---|---:|---:|
| corpus PDFs | 168 | 61 |
| corpus `output/*.json` | 103 | 44 |
| blobs (`data/uploads`) | 411 (794 MB) | 169 (432 MB) |

Round-snapshot history under `data/corpora/*/output/_pre_*` (1,846 files, 1.9 GB) was
**left in place** — it is pipeline regression history, not portal documents.

## Why 44 and not 68

The shortlist has 68 rows. Only 48 of them had a document in the portal; 24 rows are not
ingested locally at all (16 have a PDF on disk and could be converted, 8 have no PDF
anywhere). Of the 48, four were exact duplicate ingests of the same PDF under the
ordinance lane's two naming conventions — same sha256, same section count, one backed by
a corpus JSON with 3 versions and one stale copy with 1 version and no JSON. The stale
copies were removed, leaving **44 distinct documents**.

### Shortlist rows with no document in the portal (24)

Tax Laws (Amendment) Ordinance 2025 · ICT (Tax on Services) Ordinance 2001 (30-06-2025,
30-06-2023, 15.01.2022, 30.06.2022, 30.06.2021) · PSW Deputation/Secondment Regulations
2021 · Federal Excise Rules 2005 (31-10-2023) · Income Tax Rules 2002 (24.11.2023) · PSW
Evidence of Identity Regulations 2023 · PSW Integrated Risk Management System Rules 2023 ·
S.R.O 406(I)/2023 PSW Trade Data Rules · Sales Tax Rules 2006 (31.10.2023, 31.08.2021) ·
Sharing of Declaration of Assets of Civil Servants Rules 2023 · Income Tax (Amendment)
Ordinance 2022 & 2021 · Tax Laws (Second Amendment) Ordinance 2022 & 2021 · Tax Laws
(Amendment) Ordinance 2021 · Tax Laws (Third Amendment) Ordinance 2021 · PSW Evidence of
Identity (EOI) Rules 2022 · PSW Trade Data Rules 2022 · Inland Revenue Uniform Rules 2021

## The matching trap this avoids

The ordinance lane renames on ingest: shortlist `Income Tax Ordinance, 2001 Amended upto
20.02.2026.pdf` is stored as `Income Tax Ordinance 2001 - amended upto 20.02.2026`.
Fourteen shortlist rows also carry a leading space or no `.pdf`. Matching on name alone
deletes documents the shortlist asked to keep, so the tool matches on the PDF's **sha256**
(`documents.pdf_filename` is `pdf/<sha256>.pdf`) and falls back to a normalised name only
for rows whose PDF is not staged locally. Every 2021+ ordinance edition resolved to *keep*;
every pre-2021 edition to *delete*.

## Verification

- Re-run of the dry run after applying: **delete set 0, keep set still resolving** — idempotent.
- Orphan check: `findings`, `sections`, `document_versions`, `statute_families` with a
  missing parent all **0**.
- `tools/sync_corpus.py --dry-run`: `added 0, updated 0, withdrawn 0, unmatched 0` —
  corpus and database agree exactly.
- `tools/run_tests_smoke.py`: **pipeline gate passed** — ordinance 7, acts 34, rules 3 editions.
- `pytest apps/api/backend/tests tools/tests`: **897 passed, 3 skipped**.
- `npm run test` (web): **17 failed / 215 passed** — unchanged from this tree's standing baseline.
- `ruff check`: clean.
- All 88 blobs for the 44 survivors return 200; 9,647/9,647 sections have HTML.

## Rollback

Three archives in `data/backups/` (gitignored):
`crx-preprune-*.dump` (44 MB, `pg_restore`), `corpus-preprune-*.tar` (533 MB, 166 corpus
files), `blobs-preprune-*.tar` (362 MB, 242 blobs).

## Pre-existing issues found, not introduced here

1. **`crx-api` and `crx-worker` were restart-looping** on
   `Can't locate revision '0006_section_instrument_context'`. The images were built
   2026-08-20; the migration landed 2026-09-09. A rebuild fixed it. Stale image, not code.
2. **Compose blob mount mismatch.** `api` mounts the named volume `blob-cache` at
   `/app/data/uploads`, which was empty, while the real blobs sat in the host's
   `./data/uploads`. Every PDF request 404'd before this work. The referenced blobs were
   copied into the volume so the viewer works; the mount itself is still worth a decision.

## Not done

- **Production is untouched.** Prune it only after this PR merges and deploys, and take
  `make backup-remote` first. Note `deploy-northflank.yml` defaults to `crx-api,crx-web` —
  dispatch with `crx-api,crx-worker,crx-web` so the worker gets the new routes too.
- **Production users cannot be wiped**: no user-delete API, prod Postgres has
  `externalAccessEnabled: false`, and it would lock the portal out until `crx-api`
  restarts. Local wipe confirmed the admin is recreated from `ADMIN_EMAIL`/`ADMIN_PASSWORD`.
- **`review_events` kept** (91 rows) — dropping the append-only trigger to delete an audit
  log was not worth it without a decision.
- **`evidence/*.zip` and `render/*.png` blobs** are unreachable by any delete path
  (`blob_store.is_referenced` only knows `pdf`/`json`). Pre-existing; own cleanup.

---

# Production round (2026-09-22)

Prod is a separate managed Postgres, reachable only through the API. Backup first:
`review-snapshot-20260922-100617.json`, 40.9 MB, **112 of 115 documents**. The three that
failed with `Bad Gateway` — `Income Tax Ordinance 2001 - amended upto 30.06.2023`,
`Customs Act, 1969 as amended up to 30.06.2024`, `The Tax Laws (Amendment) Act, 2023` —
are all in the **keep** set, so every document being deleted is covered.

## Two defects that only appear against the deployed portal

Both were invisible locally and are fixed in the follow-up PR (#117).

1. **67 documents in one request → 504.** nginx stops waiting long before Postgres
   finishes the cascade; the transaction rolls back and the run changes nothing. The API
   was never the limit. Chunking is now `--chunk`, default **10** — sized so 67 documents
   is 7 requests plus the orphan sweep, inside the `HEAVY` budget of ten per hour per IP.
   A chunk of 7 would commit comfortably and then 429 halfway through.
2. **The delete reported contention as a broken document.** `_delete_documents` caught
   every exception and returned `500 Database deletion failed`, swallowing SQLSTATE 55P03
   that `main.py` already maps to a retryable 503. `replace_json` re-raises for exactly
   this reason and its comment records the same bug biting before. A cascade across a
   batch is where the 3s request lock timeout is most reachable, so pruning a deployed
   portal is the case that finds it. **The single-document route shares the helper**, so
   this was pre-existing there too, just rarely triggered by one document.

A single small document (`Income Tax (Third Amendment) Act, 2016`, 2 sections) deleted
cleanly with a 200 — that is how the route itself was cleared and the fault localised to
batch duration. It is also why prod reads 114 rather than 115 before the real run.

## Northflank reality vs the template

`crx-worker` **does not exist** in Northflank. The template declares it and
`deploy-northflank.yml` mentions it, but the project has only `crx-api` and `crx-web` —
dispatching a deploy with `crx-worker` fails with
`Could not find service 'crx-worker'`. PR #116's advice to include it is wrong.
Consequence beyond deploys: **prod runs no job worker at all** (`WORKER_IN_PROCESS=0` on
`crx-api`), so anything enqueued there never runs.

## Result

Production matches local exactly.

| | before | after |
|---|---:|---:|
| documents | 115 | **44** |
| sections | 23,585 | 9,647 |
| statute_families | — | 18 removed by the sweep |
| jobs | — | 2 removed by the sweep |
| review_events | 549 | 549 *(retained; append-only)* |

Verified after: dry run reports **keep 48 / delete 0**; `/health/ready` ok; `corpus/status`
reads 44; the largest surviving document (`Customs Rules, 2001 (Updated Up to 30.06.2023)`,
1,107 sections) serves its 9.3 MB PDF blob with HTTP 200.

The 48-vs-44 gap is the same four duplicate ordinance ingests found locally — identical
PDF hashes, the `-` spelling carrying one version against the other's two. The stale
copies were deleted, then the orphan sweep run.

### One thing to know about the failed attempts

Both the 504 and the subsequent 500s reported failure to the client while the server
**kept going and committed**. Immediately after the 500, prod still read 115; some minutes
later it read 48. So a failed prune run here is not evidence that nothing happened —
**always re-read the document count before retrying**, or a retry will be computed against
a portal that has already moved. The tool is idempotent, so the re-read costs nothing.

## Still open

- **Prod users were not wiped** — no user-delete API exists, prod Postgres is not
  externally reachable, and it would lock the portal out until `crx-api` restarts.
- **21 shortlist rows could be ingested** (PDF staged on disk, never converted); 3 have no
  PDF anywhere: ICT (Tax on Services) Ordinance 2001 upto 30.06.2022, Sales Tax Rules 2006
  upto 31.08.2021, and upto 31.10.2023.
- **`crx-worker` does not exist on Northflank**, so prod has no job worker at all.
- **The Compose blob mount** still points at an empty named volume rather than
  `./data/uploads`; blobs were copied in to make the local viewer work.
