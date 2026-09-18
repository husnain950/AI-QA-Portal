# Round 48 — the four push failures that had already landed

Round 47's push reported **85 sent, 4 failed**: three `409 stale_version` on Income Tax
Ordinance editions and one `500 Database update failed` on Customs Rules 2001. A second
run reported **0 to refresh, 116 already identical, 0 failed**. The note recorded the 500
as "intermittent … nothing here explains it" and attributed the 409s to "two local rows
resolving to one remote document".

The 409 attribution is wrong. Both failures come from one defect in the push client, and
the 500 is now reproduced in a test.

## The defect: a blind retry against a version-gated write

`send` retried once by replaying the **same** `Request` with the **same** `If-Match`, and
printed only attempt 2's error — attempt 1's exception was discarded entirely. The
expected version is snapshotted once in `existing_docs()` before any write and never
re-read.

`/replace-json` is version-gated (`versions.py:139-142` raises `StaleVersion`), and every
request runs under `SET LOCAL lock_timeout = '3s'` (`database.py:47`) while
`create_version` holds `FOR UPDATE` on the document row. So when attempt 1 fails at the
edge but the server keeps working:

| attempt 2, 5 s later | client sees | portal |
|---|---|---|
| attempt 1 already committed | `If-Match` stale → **409 stale_version** | correct |
| attempt 1 still inside its `FOR UPDATE` | aborts at the 3 s lock timeout → **500** | correct |

One mechanism, two outcomes, decided only by timing — which is exactly why all four were
already correct on the second run.

### The 500 reproduced, not inferred

`main.py:124-141` already maps 55P03 to a clean **503 `lock_timeout`**, and
`OperationalError` is in `UNREACHABLE_DB_ERRORS`, so the handler was registered for it all
along — but `_add_version`'s terminal `except Exception` caught it first.

Removing the new guard and re-running the test reproduces the round's error **verbatim**:

```
>       assert blocked.status_code == 503, blocked.text
E       AssertionError: {"detail":"Database update failed"}
E       assert 500 == 503
```

## Why the note's explanation cannot be right

Measured, not inferred.

| | local database | live portal |
|---|---|---|
| live documents | 116 | 115 |
| distinct names | 115 | — |
| distinct `source_key` | 115 (+1 null) | 115 |
| distinct `remote_key` | — | **115, zero collisions** |
| rows with no `source_key` | 1 | **0** |
| rows with no `active_version_id` | — | **0** |

The only duplicate-name pair is **`Fixture Finance Act 2024`** — a stray keyless
`manual`/`upload` row beside the real `finance`/`acts_corpus` one, sharing one blob. That
pair is the whole 116→115 arithmetic, it is in the **finance** lane, and since both
hash-match the remote, `plan_refresh` refreshes neither: it cannot produce a 409. On the
portal there are no key collisions at all and every row carries an `active_version_id`, so
no two ordinance rows can resolve to one remote document and every `If-Match` sent was
well-formed.

## What it uncovered: 9 editions are on the portal twice

`GET /api/documents` holds **21 Income Tax Ordinance rows for 12 editions**:

| edition | held as |
|---|---|
| 04-05-2024 | `…2001 - amended upto 04.05.2024` + `…, 2001 Amended upto 04.05.2024` |
| 11-03-2019 | `…2001 - amended upto 11.03.2019` + `…, 2001 amended upto 11th March, 2019` |
| 30-06-2018 | `…2001 - amended upto 30.06.2018` + `…, 2001 Amended upto 30-06-2018` |
| 30-06-2019 | `…2001 - amended upto 30.06.2019` + `…, 2001 amended upto 30th June, 2019` |
| 30-06-2020 | `…2001 - amended upto 30.06.2020` + `…, 2001 amended upto 30th June, 2020` |
| 30-06-2021 | `…2001 - amended upto 30.06.2021` + `…, 2001 updated upto 30 June 2021` |
| 30-06-2022 | `…2001 - amended upto 30.06.2022` + `…, 2001 amended up to 30th June 2022` |
| 30-06-2023 | `…2001 - amended upto 30.06.2023` + `…, 2001 Amended upto 30.06.2023` |
| 31-12-2019 | `…2001 - amended upto 31.12.2019` + `…, 2001 amended upto 31st December, 2019` |

Only 20.02.2026, 30.06.2024 and 31.07.2025 are held once. The old-naming copies were
seeded 2026-08-23, carry `corpus_origin = NULL` and hold a pre-round-39 parse. They are
stranded by design: `reconcile_corpus` is scoped by `corpus_origin` and states "Rows with
no origin are never candidates" (`corpus_sync.py:99-102`), while `local_documents()` pushes
every row with `withdrawn_at IS NULL`. Nothing will ever retire them.

**Not fixed here** — withdrawal of a corpus under legal review is its own reviewable change.

## The third defect, live but unfired

`push_corpus.py:497` unpacked **seven** names from an eight-field `LocalDoc` — the
surviving third instance of the bug `1c21588` fixed in the two refresh loops. The upload
path raised `ValueError: too many values to unpack` the moment anything was new; it never
fired only because every round had `0 to upload`.

## Before / after

| | before | after |
|---|---|---|
| attempt 1's error | discarded | printed (`attempt 1 refresh …: <error>`) |
| retry decision | replay the same body and `If-Match` | re-plan the one document first |
| write that landed | reported **FAILED** (409/500) | counted as sent, not re-sent |
| write that did not land | retried with the stale version | retried with the version the server has now |
| contended write | `500 Database update failed` | `503 lock_timeout` |
| `to_upload` non-empty | `ValueError: too many values to unpack` | uploads |

## Verification

```
ruff check                                    All checks passed!
pytest apps/api/backend/tests tools/tests -q  885 passed, 3 skipped   (baseline 881+3)
tools/run_tests_smoke.py                      Pipeline gate passed
```

Six mutations, each failing exactly its own test:

| mutation | test that fails |
|---|---|
| drop the `is_lock_timeout` re-raise | `…replace_json_is_a_503_not_an_opaque_500` (gets the verbatim 500) |
| blind replay, no re-check | `test_a_write_that_landed_is_not_replayed` |
| stop printing attempt 1's error | `test_a_write_that_landed_is_not_replayed` |
| never refresh `if_match` | `test_a_retry_names_the_version_the_server_has_now` |
| `remote_state` always says landed | `test_a_retry_names_the_version_the_server_has_now` |
| restore the 7-name unpack | `test_the_live_push_reaches_the_upload_it_planned` |

The lane suites SKIP in this worktree — the corpus is staged in the main checkout only.
This change touches no pipeline code.

**Left open:** *why* attempt 1 failed at the edge. The fix makes the next occurrence
self-reporting rather than silent; naming it needs the `crx-api` logs for that window.
