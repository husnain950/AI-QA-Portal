# FBR Corpus Platform (`crx`)

Unified monorepo: **PDF → JSON pipelines** (`packages/fbr_ingest`, `packages/acts_ingest`) and the **QA review portal** (`apps/api`, `apps/web`) share one Docker stack, Makefile, and sync CLI.

Live portal without a seed is empty; this repo is meant to run locally with in-tree corpora under `data/corpora/` and `make sync`.

## Closed loop

```
convert PDF  →  data/output JSON  →  make sync  →  review in UI  →  export QA JSON  →  import_qa_report
```

1. **Convert** — `make convert-ordinance PDF=…` or `make convert-acts PDF=…`
2. **Sync** — `make sync` loads Ordinance (~12) + Acts (~80) editions into PostgreSQL from `data/corpora/`
3. **Review** — side-by-side PDF + HTML, versions, annotations
4. **Export** — dashboard JSON/CSV or `make export-qa DOC=<id>`
5. **Import findings** — feed portal findings back into the pipeline regression cases

## Layout

```
apps/api          FastAPI (Python package name: backend)
apps/web          Vite + React review UI
packages/fbr_ingest   Income Tax Ordinance pipeline
packages/acts_ingest  Acts + OCR fork (kept separate on purpose)
tools/            sync_corpus, convert_*, import_qa, bootstrap_corpora, smoke tests
data/             gitignored uploads / corpora / output / ocr_cache (the DB lives in PostgreSQL)
data/corpora/     Ordinance + Acts PDFs and pipeline JSON (local only)
```

## Quick start

```bash
cp .env.example .env   # defaults already point at data/corpora/ and Compose
# Set ADMIN_EMAIL and ADMIN_PASSWORD (12+ characters) in .env — the first admin is
# created from them on a database with no users, and there is no other way in.
make up                # postgres, minio, api :8000, worker, web :5173
make sync              # seed from data/corpora/*/output JSON
make health
```

Open http://localhost:5173 and sign in. Every API path requires a session; see
[Accounts and roles](#accounts-and-roles).

Corpora are vendored under `data/corpora/` (gitignored). Optional refresh from a sibling CC-FBR tree: `make vendor-corpora`.

### Without the corpora

A fresh clone has no `data/corpora/`, so `make sync` has nothing to load and the dashboard
starts empty. For UI work and review-page smoke tests, generate a micro-corpus instead:

```bash
make seed-fixtures     # 3 small acts with real text PDFs, via tools/fixture_corpus.py
cd apps/web && npm run smoke
```

The fixtures are generated rather than committed, so they are byte-identical everywhere and
no binaries live in git. They are a test scaffold, not a stand-in for the real corpus.

### Environment

See [`.env.example`](.env.example). Important knobs:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL DSN (default `postgresql+psycopg://crx:crx@localhost:5432/crx`) |
| `STORAGE_BACKEND` | `s3` (Compose/MinIO) or `filesystem` (blobs under `UPLOAD_DIR`) |
| `UPLOAD_DIR` | Content-addressed PDF/JSON blobs, and the local cache for the S3 backend |
| `S3_*` | Endpoint, bucket, and keys when `STORAGE_BACKEND=s3` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | The first admin, created on a user table with no rows |
| `SESSION_HOURS` | Session lifetime (default 12) |
| `INSECURE_COOKIES` | `1` drops `Secure` from the session cookie — plain-http local dev only |
| `CSP_ENFORCE` | `1` enforces the CSP instead of only reporting violations |
| `METRICS_TOKEN` | Shared token for `GET /api/v2/metrics`, so a scraper needs no session |
| `CORPUS_ORDINANCE` | `./data/corpora/ordinance` (`output/*.json` + Ordinance PDFs) |
| `CORPUS_ACTS` | `./data/corpora/acts` (`output/*.json` + `Acts/**`) |

These `CORPUS_*` / `DATABASE_URL` / `UPLOAD_DIR` values are **host-local**. Compose and the API image override them inside the container (`/data/corpus/...`, `/app/data/...`), and Northflank injects its own, so a local `.env` is never shipped to production.

The Library subtitle (`last sync` / `seeded by upload` / `pipeline mounts not on this host`) is **pipeline-mount health** — whether those directories exist on the API host with `output/*.json` — not whether Ordinance or Acts documents are already in the library. `make push-remote` fills the library as uploads and does not record a corpus sync. Northflank builds from git have no baked seed and no pipeline mounts, so a fresh (or post-migration) deploy shows an empty Library until someone runs:

```bash
# machine that already has data/corpora/ + a synced local DB, and ADMIN_* in .env
make sync
make push-remote BASE_URL=https://p01--crx-web--m4hljdfnbvqq.code.run
```

Compose mounts `./data/corpora/...` **read-only** into the API container. Large blobs stay out of git.

### Make targets

| Target | What it does |
|--------|----------------|
| `make up` / `down` | Docker Compose stack |
| `make vendor-corpora` | Optional re-copy from sibling CC-FBR |
| `make sync` | Sync Ordinance + Acts (`--metrics`) |
| `make seed-fixtures` | Generate + load a micro-corpus (no private data needed) |
| `make convert-ordinance PDF=…` | Run `fbr_ingest` |
| `make convert-acts PDF=…` | Run `acts_ingest` |
| `make test` | API pytest + pipeline smoke + web lint/tests/build |
| `make check` | Exactly what CI gates on, including `ruff check apps/api tools` |
| `make export-qa DOC=…` | Download QA report JSON |

### Production web image

Dev Compose uses Vite. For a static nginx SPA:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build
```

## CI/CD

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | every PR and push to `main` | API pytest, pipeline import smoke, web lint/vitest/build, review-page smoke |
| [`.github/workflows/deploy-northflank.yml`](.github/workflows/deploy-northflank.yml) | CI succeeding on `main`, or manual dispatch | builds the merged commit on Northflank and rolls it out |

Deploys run [`tools/northflank_deploy.py`](tools/northflank_deploy.py), which talks to the
Northflank REST API using only the standard library. For each service it starts a build of the
exact commit, waits for that build to finish, and then deploys it — unless the service already has
Northflank's own continuous deployment enabled, in which case Northflank rolls the build out.

### Enabling deploys

`NORTHFLANK_API_TOKEN` must exist as a **GitHub Actions repository secret** (Settings → Secrets and
variables → Actions). A token in your local `.env` only works for local runs; GitHub Actions cannot
read it, because `.env` is gitignored. Optional repository *variables* override the defaults:
`NORTHFLANK_PROJECT_ID` (default `qa-pdf-portal`) and `NORTHFLANK_TEAM_ID`.

Run it locally against the token in your `.env`:

```bash
python tools/northflank_deploy.py check                     # report project/service state
python tools/northflank_deploy.py deploy --sha "$(git rev-parse HEAD)"
python tools/northflank_deploy.py deploy --dry-run          # resolve config, change nothing
```

[`northflank.template.json`](northflank.template.json) is the infrastructure-as-code definition of
the PostgreSQL addon, the data volume, and the three services (`crx-api`, `crx-worker`,
`crx-web`) in the `qa-pdf-portal` project. `ADMIN_EMAIL` and `ADMIN_PASSWORD` are secrets and
are deliberately **not** in the template — set them on `crx-api` in the Northflank dashboard
before the first boot, or no account exists to sign in with. It is applied by running the
template in Northflank; the deploy workflow does not run it, it only builds and deploys the services
the template created.

### Persistence

Production keeps its two kinds of state in two places:

- **The database** is a Northflank **managed PostgreSQL addon** (`crx-postgres`), declared as
  the first step of the template. `DATABASE_URL` is injected from the addon, never written
  into the template or an env file.
- **The blobs** (source PDFs, versioned JSON, evidence bundles) stay content-addressed on the
  6 GB nvme volume mounted at `/app/data`, where `UPLOAD_DIR` (`/app/data/uploads`) points,
  with `STORAGE_BACKEND=filesystem`. The volume is attached to both `crx-api` and
  `crx-worker` so the worker writes renders and exports to the same store. Compose uses
  MinIO instead, over the same S3 code path.

Blobs survive redeploys and image rebuilds: documents uploaded 2026-08-13 were still served
after a full rebuild on 2026-08-18.

The volume is declared with `updateMode: "patch"`, mirroring the live volume field-for-field so re-running the template is a
no-op against the existing one. It used to exist only as a hand-made resource in the Northflank UI,
which meant rebuilding the project from the template produced a silently ephemeral service. Check
the template's plan view reports **no change** on that step before applying it.

A volume is not a backup — it survives redeploys, not deletion, corruption, or a bad migration:

```bash
make backup-remote BASE_URL=https://p01--crx-web--m4hljdfnbvqq.code.run
```

That writes `data/backups/review-snapshot-<timestamp>.json` via
[`tools/snapshot_review.py`](tools/snapshot_review.py), and
[`.github/workflows/backup-review-state.yml`](.github/workflows/backup-review-state.yml) runs it
daily, keeping each snapshot as a 90-day workflow artifact.

It backs up **review state specifically**, because that is the only thing nothing else can rebuild:
`make push-remote` re-uploads documents but the upload route inserts every row as `pending`, so it
resets each section's `review_status` and carries no annotations. Detector `findings` are omitted —
they are machine output that a re-sync regenerates.

Restoring is not automated: there is no import route yet, so the snapshot preserves the data rather
than offering one-click rollback. Full-fidelity volume snapshots would cover all of this and are
already implemented as `python tools/northflank_deploy.py backup`, but Northflank answers that
endpoint with `403 Feature disabled for your account` on the current plan; the command starts
working the moment the feature is enabled.

### Deploying without GitHub Actions

Northflank has its own CI/CD that watches the repo directly, so deploys do not have to go through
GitHub Actions at all. Either flip the **CI** and **CD** toggles in each service's header in the
Northflank dashboard, or do both services at once with your local token:

```bash
python tools/northflank_deploy.py enable-cicd --set-branch --branch main
```

That clears `disabledCI` so Northflank builds every new commit on `main`, and sets each deployment's
`buildSHA` to `latest` so it rolls each successful build out. `--set-branch` also repoints the
services at `main`; drop it to leave the watched branch alone.

The two mechanisms coexist safely: `tools/northflank_deploy.py deploy` detects a service running in
that mode and lets Northflank perform the rollout instead of pinning a build itself. Use
`python tools/northflank_deploy.py check` to see which mode each service is in.

## Schema migrations

API boot runs `alembic upgrade head` against `DATABASE_URL`
([`apps/api/backend/alembic`](apps/api/backend/alembic)); the worker does the same, and
Alembic's own lock makes the race safe. The schema itself is declared once in
[`apps/api/backend/db_schema.py`](apps/api/backend/db_schema.py), and the baseline revision
builds it with `metadata.create_all`. **A later revision must therefore be idempotent** —
guard it with `IF NOT EXISTS` — because on a fresh database the baseline has already
created whatever `db_schema` declares.

## Accounts and roles

Identity is a server-side session behind an HttpOnly `SameSite=Strict` cookie. Passwords
are scrypt-derived, and only the sha256 of a session token is stored. The actor recorded
against every change comes from the session, so a client cannot attribute its edits to
someone else.

| Role | Can |
|------|-----|
| `reader` | Read everything: library, sections, findings, search, exports |
| `reviewer` | Everything above, plus verdicts, annotations, footnotes, triage, AI fixes |
| `admin` | Everything above, plus upload, delete, corpus sync, version rollback, jobs, operator diagnostics |

Accounts are managed from the shell:

```bash
docker compose exec api python -m backend.manage_users list
docker compose exec api python -m backend.manage_users add alice@example.com --name Alice --role reviewer
docker compose exec api python -m backend.manage_users role alice@example.com admin
docker compose exec api python -m backend.manage_users password alice@example.com
docker compose exec api python -m backend.manage_users disable alice@example.com
```

`disable` and `password` both revoke every live session for that account.

`ALLOWED_ORIGINS` still controls CORS. Behind the nginx reverse proxy on `crx-web` the
browser never makes a cross-origin request, so it can stay empty in production.

## Background jobs

Corpus sync, detectors, PDF renders, evidence exports, and AI proposals run in the
`crx-worker` service ([`apps/api/backend/worker.py`](apps/api/backend/worker.py)) against
a durable job table with leases, retries, and cancellation — not inside the request that
asked for them. `POST /api/v2/jobs/{type}` enqueues, `GET /api/v2/jobs/{id}` reports
progress, and `GET /health/worker` is 503 when no worker has beaten in the last 30 s.

Operations, backup, and restore are in [`docs/operations.md`](docs/operations.md).

## Non-goals (v1)

- Merging `fbr_ingest` and `acts_ingest`
- Re-converting the full Acts corpus in-session
- Shipping PDFs or DB blobs in git
- LLM/vision in the conversion path
