# AI Fix hung because nothing in production ran the job queue

`POST /api/v2/jobs/ai_proposal` writes a `jobs` row and returns 202. The only thing that
executes that row is `python -m backend.worker`. In production no such process existed, so
every AI Fix sat at `state='queued'` and the review panel spun on *"Sending the section
JSON and PDF pages to the model…"* until the browser's 30-minute poll gave up.

## Before — evidence from live prod

| Check | Result |
|---|---|
| `GET /health` | `{"status":"ok","db":"ok","storage":"ok","schema":"0006_section_instrument_context"}` |
| `GET /health/worker` | `503 {"status":"degraded","detail":"no worker heartbeat"}` — `worker_heartbeats` empty, so no worker had *ever* beaten |
| Northflank `qa-pdf-portal` services | `crx-api`, `crx-web` — no `crx-worker` |
| `crx-api` runtime env | `OPENPATHS_API_KEY` / `_BASE_URL` / `_MODELS` all set |
| OpenPaths catalog (live) | 273 models; `gpt-5.4-nano` present |

So the gateway, the key, the model id and the prompt were all fine. `northflank.template.json:136-193`
declares a `crx-worker` service, but it was never created, and CI never deploys it:
`tools/northflank_deploy.py:73` and `.github/workflows/deploy-northflank.yml:35` both
hardcode `crx-api,crx-web`. Six other job types (`export`, `detectors`, `render_pdf`,
`corpus_sync`, `provenance_scan`, `regression_bundle`) were equally dead.

## Why not just deploy `crx-worker`

`ai_proposal` reads blobs off the local filesystem — `versions.read_version_json`
(`services/versions.py:109`) and `render_pdf_pages` (`services/ai_fix.py:81-111`) both open
real paths — and prod runs `STORAGE_BACKEND=filesystem`. The `crx-api-data` volume is
`ReadWriteOnce` and attached only to `crx-api`, so a separate worker service needs that RWO
volume co-mounted or an S3 migration first. The API process already has the volume, the env
vars and the database.

## After

The API process runs the queue itself (`main.py` lifespan), default on, with
`WORKER_IN_PROCESS=0` set in the two places that *do* run a dedicated worker
(`docker-compose.yml`'s `api` service, `northflank.template.json`'s `crx-api`).

Verified against a throwaway clone of the local dev database, running this branch's code
with the live OpenPaths key:

```
GET /health/worker
{"status":"ok","worker_id":"c58564225c7d:1","state":"idle","job_id":null}   [200]

POST /api/v2/jobs/ai_proposal  {"model":"gpt-5.4-nano", ...}                [202]
  t=3s  state=running
  t=6s  state=succeeded
  result: {"status":"failed","proposal_id":"0804d910-…"}
```

The job was claimed, executed and settled in about five seconds. Its evidence record shows
the round-trip was real:

```
model: gpt-5.4-nano        vision: True        images_sent: True
expected_pages: [2, 3]
rendered_pages: [{page: 2, bytes: 59874, sha256: 72a07fe2…},
                 {page: 3, bytes: 59965, sha256: 7d9f6b36…}]
prompt_version: ai-fix-prompt-v1   validator_version: legal-leaf-validator-v2
```

The proposal's own status is `failed` with `html_plain_parity — HTML textContent and
plain_text differ`: the validator rejecting a model reply, which is the designed outcome
and what the panel now shows on the compare screen. The infrastructure question is settled
either way — the job ran.

An earlier attempt on the filesystem backend failed with
`FileNotFoundError: /app/data/uploads/json/290a7d47….json` after 3 attempts, with the error
written back to `jobs.error`. That is the local blob volume being empty, and it is worth
recording: even a broken job now *reports*. Before, it stayed `queued` forever.

## No more silent spinning

Every enqueue route calls `deps.require_worker(db)` immediately before `jobs.enqueue`
(`routes/v2/jobs.py`, `routes/corpus.py`, `routes/v2/operations.py`,
`routes/v2/governance.py`, `routes/findings.py`). With the worker off:

```
GET  /health/worker                     503 {"detail":"worker heartbeat is stale"}
POST /api/v2/jobs/ai_proposal           503 in 0.0076s
  {"code":"worker_offline","message":"no worker is running, so background jobs
   cannot be processed; check /health/worker"}
jobs rows created: 0
```

7 milliseconds and a readable message, instead of thirty minutes of nothing. The check is
called inline rather than declared as a `Depends` so a route's own validation still answers
first — an unmounted corpus says so instead of blaming the worker.

The panel also distinguishes the two waits it used to merge: `queued` now reads *"Queued —
waiting for a worker to pick it up…"*, and the poll runs at 1s for 5 minutes rather than
750ms for 30 (the gateway's own ceiling is 180s, and 750ms polling is 80 GET/min against a
120/min read limit). The loading line no longer claims PDF pages were sent when a text-only
model was chosen.

## Two bugs found while fixing this

**`LEASE_SECONDS = 60` was shorter than the 180s gateway timeout** (`services/jobs.py`), and
`_ai_proposal` never heartbeats. One worker is safe because `claim()` only runs between
jobs, but a second worker reclaims a proposal that is still in flight — duplicate paid
gateway calls, duplicate `fix_proposals` rows, and a `LeaseExpired` failure after three
attempts. Now 240s.

**`worker.run()` swallowed `asyncio.CancelledError`** (`worker.py`): it marked the current
job cancelled and then kept claiming new work, so a worker told to stop did not.
Unreachable while the worker was its own process getting SIGTERM'd; reachable the moment it
shares the API's lifecycle. It now re-raises, and the lifespan waits a bounded 5s for it.

## Tests

`apps/api/backend/tests/test_worker.py` is new — nothing in the repo imported
`backend.worker`, which is why `_HANDLERS`, `_execute` and `run()` could all be correct
while no process called them. Seven tests: every `JOB_TYPES` entry has a handler; an
`ai_proposal` job runs enqueue → claim → execute → succeed and leaves a `fix_proposals`
row; a malformed payload fails without spending retries; booting the API starts an executor
**and stops it on shutdown**; `WORKER_IN_PROCESS=0` starts none; `worker_online` tracks the
heartbeat; and the enqueue route answers 503 then 202 either side of a heartbeat.

The shared AI-fix fixtures (`gateway`, `model_reply`, `synced_document`, `FIXED_TEXT`,
`FIXED_HTML`, `LEAF_KEY`) moved from `test_ai_fixes.py` into `conftest.py` so both files use
them as fixtures rather than cross-importing.

```
767 passed, 2 skipped        apps/api/backend/tests + tools/tests
ruff check                   All checks passed
oxlint --deny-warnings       clean
vitest                       17 failed / 206 passed — this repo's standing baseline
                             (libraryPage, libraryFavorites; localStorage in jsdom), unchanged
npm run build                clean
```

## Still open, deliberately

- `or/qwen3.7-plus`, the third entry in `OPENPATHS_MODELS`, is not in the live catalog and
  shows as a stub in the dropdown. A `.env` correction, not code.
- `resolve_model_async` sits outside `create_proposal`'s try/except (`ai_fix.py:358` vs
  `:418`), so an unknown model or a catalog hiccup leaves no `fix_proposals` row at all.
- `aiFixStore.js:43-47` swallows a failed proposal list into `[]`.
- `POST /api/v2/jobs` requires **admin** (`middleware/security.py:87`) while the older
  synchronous route `routes/ai_fixes.py:84` needs only reviewer, so reviewers cannot use AI
  Fix at all.
- Splitting `crx-worker` back out as its own service, which needs the blob-storage decision
  (shared volume vs S3) first.
