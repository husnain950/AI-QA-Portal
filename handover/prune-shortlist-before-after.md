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

---

# Ingest round (2026-09-22): the 21 staged shortlist rows

The prune round left 24 shortlist rows with no document. 21 of them had a PDF sitting in
`data/corpora/` that had simply never been converted. This round converted those 21 and
synced them. **Local only — production is untouched.**

Targets: 11 ordinance, 10 rules. Resolved by re-running `prune_corpus.resolve` against the
live portal, so the list is the tool's own unmatched set, not a hand transcription.

## Result

| | before | after |
|---|---:|---:|
| portal documents | 44 | **63** |
| sections | 9,647 | **9,874** |
| corpus `output/*.json` | 44 | 63 |
| shortlist rows with no document | 24 | **5** |

Sync reported `added 11` (ordinance) + `added 8` (rules), `failed 0`, `withdrawn 0`,
`unmatched 0`, stderr empty. New lanes appear for the rules documents:
`federal_excise_rules` (1) and `other_rules` (7).

## Two documents were refused, and should be

Both fail the OCR fidelity floor, which refuses to emit a statute from a recognition it
cannot stand behind. This is the pipeline working, not a failure to fix:

| document | pages | agreement | floor |
|---|---:|---:|---:|
| Income Tax Rules, 2002 Amended upto 24.11.2023 | 946 (15 image-backed) | **62.7%** | 85% |
| PSW (Deputation/Secondment of Civil Servants) Regulations, 2021 | 20 | **74.3%** | 85% |

Neither can be ingested without a cleaner source PDF. `--admit-below-floor` would not help:
it redirects to `output/_provisional/`, which the corpus glob never reads.

So the 5 rows still absent are these 2 plus the 3 that have no PDF anywhere (ICT Ordinance
upto 30.06.2022, Sales Tax Rules 2006 upto 31.08.2021 and upto 31.10.2023).

## The pipeline gate now fails, and most of it is the wrong invariant

`tools/run_tests_smoke.py`: acts 34 pass (unchanged); **ordinance fails on all 11 new
editions**, **rules on 3 of 8**. Split it before acting on it.

**Wrong invariant (ordinance, all 11).** Until this round the ordinance lane held only
Income Tax Ordinance 2001 editions, so assertions about *that* statute held everywhere by
accident. The lane now also holds amendment ordinances and the ICT Ordinance:

- `structure_counts` fires on every new edition with `chapters in tree 1 < 13` and
  `no ordinal-titled schedules in tree`. Both numbers are the Income Tax Ordinance's shape.
  A 3-page amendment ordinance has one chapter and no schedules by nature.
- **10 of the 374 ordinance cases carry no edition scope** — `ch1_sec1_heading`,
  `ch1_sec2_body`, `sec207_operative_first_line`, `sec230E_real_body`,
  `qa_114_no_phantom_table` and five siblings. The other 364 are scoped and skip correctly
  (`skipped (other edition) 364`). Unscoped, they assert Income Tax Ordinance content against
  every edition in the lane: `heading 'Interpretation' != 'Definitions'`,
  `target not found: section 207`. Scoping those 10 to the Income Tax Ordinance editions is
  the fix; nothing about the new documents is wrong here.

**Real hits (rules, 3 of 8).** These are document defects, not scope problems:

| edition | invariant |
|---|---|
| Federal Excise Rules, 2005 (31-10-2023) | `no_split_ordinals` (1), `section_carries_its_body` (2), `bold_gate_unchanged_on_text_layer` (1) |
| Inland Revenue Uniform Rules, 2021 | `clause_codes_plausible` (1) |
| S.R.O 406(I)/2023 PSW Trade Data Rules | `preamble_carries_no_toc_tail` (1) |

One ordinance hit is also real: `preamble_present` on Tax Laws (Second Amendment) Ordinance,
2021 — that document lost its preamble and section 1 (see below).

## Parse defects found by reading the documents, independent of the gate

The gate does not catch these, so they are listed per document:

- **ICT (Tax on Services) Ordinance 2001, all 4 editions** — 3 sections is correct (the
  PDF's own TOC lists exactly 1, 2, 3), but `THE SCHEDULE` with Table-1 and Table-2 — the
  rate tables, i.e. the substance — is swallowed into section 3's body and
  `schedules: 0`. Section 3 spans pages 4→15 of 15 and carries 11k–17k characters.
- **Tax Laws (Second Amendment) Ordinance, 2021** — emits section 2 only; section 1 and
  the preamble are gone, 21,906 characters in one node.
- **Tax Laws (Second Amendment) Ordinance, 2022** — codes 1, 2, 3, **5**; section 4 missing.
- **Inland Revenue Uniform Rules, 2021** — section codes come out as `1` and **`2021`**:
  the year in the title read as a rule number, 21,643 characters in one node.
- **OCR'd PSW scans** — gaps in rule numbering: IRMS 2023 has 1,3,5,7,8,9; Trade Data 2022
  has 1,2,3,6,7,8; SRO 406 has 1,2,3,4,5,7; Assets Rules 2023 starts at 2.

Clean: Federal Excise Rules 2005 parses as 2 instruments / 131 sections with contiguous
codes, and both Income Tax (Amendment) Ordinances parse as their true 2 sections.

## Verification

- All 63 documents' PDF blobs return **HTTP 200** (the 19 new ones after the blob copy below).
- `sections` with empty `html_content`: **0 of 9,874**. The one empty `plain_text` row is
  `Finance Act, 2022 / THE FIFTH SCHEDULE` and pre-dates this round.
- `prune_corpus.py` dry run: **keep 63, delete 0, 5 rows absent** — the corpus and the
  shortlist agree on everything that exists.
- `sync_corpus.py --dry-run` after the run: `validated 63, failed 0, unmatched 0,
  withdrawn 0` — every corpus JSON still validates and still pairs with a PDF.

**A dry run's `added` count is not evidence of anything.** `run_sync` returns before it
opens the database when `dry_run` is set, so `added` is *always* 0 — it read 0 before this
round with 24 documents missing, and it reads 0 now. The earlier section above cites
`added 0 ... corpus and database agree exactly`; that conclusion happened to be true but
the number does not support it. `validated` (JSONs seen) and `failed`/`unmatched` are the
signals a dry run actually carries.

Note the API list endpoint `/api/documents/{id}/sections` returns no `html`/`plain_text`
for any document, old or new — checking HTML coverage through it reports 100% missing and
means nothing. Query `sections.html_content` directly.

## The Compose blob mount bit again

Sync wrote the 19 new PDF blobs to the host `./data/uploads`, but `crx-api` mounts the named
volume `blob-cache` at `/app/data/uploads`. All 19 new documents 404'd their PDF until the
blobs were copied in with `docker cp`, exactly as the prune round had to. The mount itself
is still unfixed — anything that writes a blob from the host needs this copy.

## Not done

- **Production is untouched** — it still reads 44 documents. Pushing these 19 is a separate
  decision, and the parse defects above argue for reviewing them locally first.
- **The 10 unscoped ordinance cases are not scoped.** Left alone deliberately: it is a suite
  change, and the gate failing loudly is better than a quiet exemption.
- **No parser change was made.** Every defect above is recorded, none fixed — the corpus
  was converted at one revision (`4fec3ef`) and editing the parser mid-round would have
  produced a mixed-revision corpus.

---

# Round (2026-09-23): the three "no PDF anywhere" rows, and production

## They were never missing

The three rows recorded above as having no PDF anywhere (ICT Ordinance upto 30.06.2022,
Sales Tax Rules 2006 upto 31.08.2021 and upto 31.10.2023) were staged in `data/corpora/`
all along, saved **without a `.pdf` extension**. Every discovery glob is `**/*.pdf`, so the
tools could not see them. `file` reports all three as PDF documents. The user's source folder
(`~/Downloads/FBR Ordinance `) holds the same files under the same extensionless names. That
folder also has five other extensionless PDFs (Customs Act 2021/2022/2023, Customs Rules 2023,
Finance (Supplementary) Act 2022). Those were already ingested, so something upstream renamed
them at some point. Any future "no PDF" finding needs `file`, not a glob.

The three were renamed in place to add `.pdf` (gitignored, no diff) and converted one file at
a time with `-o`. The parser has no diff since `4fec3ef`, so the corpus is still single-revision.

## One ingested, two refused

| document | result |
|---|---|
| ICT (Tax on Services) Ordinance 2001 upto 30.06.2022 | converted, 3 sections, synced (`added 1`, stderr empty) |
| Sales Tax Rules 2006 upto 31.08.2021 | **refused**: 5 OCR pages, 51.7% agreement < 85%, low-confidence 16.8% > 15% |
| Sales Tax Rules 2006 upto 31.10.2023 | **refused**: 6 OCR pages, 51.5% agreement < 85% |

The ICT edition has the same defect as its four siblings: s.3 spans pp. 4→15 and swallows
THE SCHEDULE (15,656 chars). It is recorded, not fixed.

The source folder's copies of Income Tax Rules 2002 (24.11.2023) and the PSW
Deputation/Secondment Regulations 2021 are **byte-identical** (sha256) to the staged copies
that were refused last round. The folder offers no cleaner source for them.

**Four shortlist rows now fall short, and all four for the same reason:** the OCR fidelity
floor. Each needs a clean text-layer source PDF. The pipeline is right to refuse them.

## Production

`make backup-remote` first: `review-snapshot-20260923-101717.json`, 17.8 MB, **44 of 44**
documents. Then `push_corpus --dry-run`: `20 to upload, 0 to refresh, 44 already identical`.
That means none of the existing prod documents drifted. Then the real push:
`20 sent, 0 failed, 1.5 min`, and pipeline health `37/37`.

This pushes last round's 19 documents as well as today's one. That includes every parse
defect recorded in the ingest round above: the ICT schedule swallow, the missing sections in
Tax Laws (Second Amendment) 2021 and 2022, the Inland Revenue Uniform Rules `2021` code, and
the gaps in PSW rule numbering. The user chose to ship them rather than hold them.

## Result

| | local before | local after | prod before | prod after |
|---|---:|---:|---:|---:|
| documents | 63 | **64** | 44 | **64** |
| shortlist rows absent | 5 | **4** | 24 | **4** |

## Verification

- `prune_corpus.py` dry run, local and prod: **keep 64, delete 0, absent 4**. The four absent
  rows are the OCR-refused documents.
- New local document: 4 section rows (3 sections plus the synthetic root), 0 with empty
  `html_content`. Its PDF returns HTTP 200 (670,911 bytes) with a session.
- Prod: `/health/ready` 200. All 20 new documents' PDFs return **HTTP 200**.
- `audit_pdf_serving --check-url` reports `url_mismatch` for all 64 documents. That is an
  unauthenticated 401: the audit predates the auth migration and sends no session. The
  on-disk check in the same report (page count, size) passes.

## The Compose blob mount, third time

Sync wrote the PDF and JSON blobs to the host `./data/uploads`, and both had to be
`docker cp`'d into the `blob-cache` volume. Still unfixed.
