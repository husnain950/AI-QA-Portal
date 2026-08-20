# Operations

Backup, restore, and the checks worth running when something looks wrong.

## What state exists

| State | Where | Rebuildable? |
|---|---|---|
| Reviews, annotations, findings, versions, sign-off, accounts | PostgreSQL | **No.** This is the product. |
| Source PDFs and versioned JSON | Content-addressed blobs under `UPLOAD_DIR` | Yes, from `data/corpora/` — but only if that tree still exists |
| Evidence bundles and PDF renders | Same blob store, under `evidence/` and `render/` | Yes, re-run the job |
| Detector findings | PostgreSQL | Yes, `POST /api/v2/jobs/detectors` |

The database is the thing that cannot be recreated. A volume is not a backup: it survives a
redeploy, not a deletion, a corruption, or a bad migration.

## Backups

### Database

```bash
pg_dump --format=custom --no-owner "$DATABASE_URL_LIBPQ" > crx-$(date -u +%Y%m%dT%H%M%SZ).dump
```

`DATABASE_URL_LIBPQ` is `DATABASE_URL` with the SQLAlchemy driver suffix removed
(`postgresql+psycopg://…` → `postgresql://…`); `pg_dump` does not understand the `+psycopg`
form. On Northflank the managed addon has scheduled backups of its own — turn them on, and
keep a copy off-platform: a backup that only exists inside the thing being backed up is not
one.

Verify a dump before trusting it. A dump that has never been restored is a guess:

```bash
createdb crx_restore_check
pg_restore --no-owner --dbname crx_restore_check crx-<timestamp>.dump
psql crx_restore_check -c "SELECT
  (SELECT COUNT(*) FROM documents)   AS documents,
  (SELECT COUNT(*) FROM sections)    AS sections,
  (SELECT COUNT(*) FROM annotations) AS annotations,
  (SELECT COUNT(*) FROM review_events) AS events,
  (SELECT version_num FROM alembic_version) AS schema"
dropdb crx_restore_check
```

### Blobs

The blob store is content-addressed and append-only, so any file-level copy is consistent:

```bash
# Filesystem backend (production volume)
tar -C "$UPLOAD_DIR" -czf crx-blobs-$(date -u +%Y%m%dT%H%M%SZ).tar.gz pdf json

# S3/MinIO backend
mc mirror "local/$S3_BUCKET" ./crx-blobs-mirror
```

Every blob name is its own sha256, which makes verification a checksum walk rather than a
diff:

```bash
find "$UPLOAD_DIR/pdf" -name '*.pdf' -exec sh -c \
  'test "$(basename "$1" .pdf)" = "$(shasum -a 256 "$1" | cut -d" " -f1)" || echo "CORRUPT $1"' _ {} \;
```

### Review-state snapshot

[`tools/snapshot_review.py`](../tools/snapshot_review.py) still writes a portable JSON
snapshot of review state over HTTP, and
[`.github/workflows/backup-review-state.yml`](../.github/workflows/backup-review-state.yml)
runs it daily, keeping each as a 90-day artifact:

```bash
make backup-remote BASE_URL=https://your-portal.code.run
```

It is narrower than `pg_dump` — review state only, no versions or events — and exists so a
snapshot survives even without database access. Prefer `pg_dump`; keep this as the second
copy.

## Restore drill

Run this on a schedule, not for the first time during an incident.

1. Restore the newest dump into a scratch database and run the count query above.
2. Point a scratch API at it: `DATABASE_URL=…/crx_restore_check uvicorn backend.main:app`.
3. `curl -sf localhost:8000/health/ready` — it reports the Alembic revision and whether the
   blob root is writable.
4. Sign in, open a document that had review history, and confirm the verdicts, annotations,
   and version list are the ones you expect.
5. Untar the blob backup into a scratch `UPLOAD_DIR` and run the checksum walk.

Record the date of the last successful drill somewhere a person will see it.

## Health and diagnostics

| Endpoint | Reports | Auth |
|---|---|---|
| `GET /health/live` | The process is up | public |
| `GET /health/ready` | Database reachable, migration revision, blob root writable | public |
| `GET /health/worker` | 503 unless a worker beat within 30 s | public |
| `GET /api/v2/system` | Corpus totals, server and detector versions, last sync | admin |
| `GET /api/v2/detectors/status` | Last detector run, its state, and its result | reader |
| `GET /api/v2/operator/audit-events` | The `review_events` tail — who changed what | admin |
| `GET /api/v2/operator/backups` | Recorded backup runs | admin |
| `GET /api/v2/metrics` | Prometheus text: job states, document statuses | admin session, or `X-Metrics-Token` |

Requests log as one JSON line each with `request_id`, `actor`, `role`, `status`, and
`duration_ms`. A client that saw an error can quote its `X-Request-ID` response header, which
is the fastest way to find the request that did it.

## Common situations

**A job is stuck.** `GET /api/v2/jobs/{id}` shows state, attempts, and progress. A worker that
dies mid-job leaves a lease that expires after 60 s, and the job is requeued until
`max_attempts`; then it fails with `LeaseExpired`. `POST /api/v2/jobs/{id}/cancel` cancels a
queued job immediately and asks a running one to stop at its next heartbeat.

**Nothing can be signed into.** The first admin is only created on a user table with no rows.
If the table has rows and no password is known, add one from the shell:
`python -m backend.manage_users add you@example.com --role admin`.

**A migration fails on a fresh database with "already exists".** A revision re-added something
`db_schema.metadata` already declares, so `create_all` in the baseline made it first. Guard the
revision with `IF NOT EXISTS`.

**Corpus sync does nothing.** Sync reconciles by content hash, so an unchanged JSON is a skip,
not a failure. `make sync` with `--force` pushes it through anyway. Check
`GET /api/corpus/status` for whether the pipeline mounts are even visible to the API host.
