# Seed Corpus

Pipeline output (PDFs + JSONs) baked into the Docker image for auto-seeding.

When the API container starts with an empty database (fresh persistent volume
or first deploy), it automatically syncs from these files to populate the
Library — no manual `push_corpus` needed.

## This directory is NOT committed to git

At ~500MB+ (source PDFs + output JSONs), it's a local build artifact only.
The `make seed-archive` command populates it from `data/corpora/`; the API image
then bakes it in (`apps/api/Dockerfile`: `COPY data/seed/ /seed/corpus/`).

## Structure

```
data/seed/
├── ordinance/
│   ├── Income Tax Ordinance, 2001/   ← Source PDFs
│   ├── output/*.json                 ← Pipeline JSONs
│   └── reports/                      ← Optional QA metrics
└── acts/
    ├── Acts/                         ← Source PDFs
    ├── output/*.json                 ← Pipeline JSONs
    └── reports/                      ← Optional QA metrics
```

## Usage

```bash
# Populate seed from local corpora (one-time or after pipeline re-run)
make seed-archive

# Push the local corpus to an already-deployed remote
make push-remote BASE_URL=https://your-portal.code.run
```

## How persistence works

1. **The database** is PostgreSQL — a managed addon in production, the `postgres`
   service under Compose. It is backed up, not baked into an image; see
   [`docs/operations.md`](../../docs/operations.md).

2. **The persistent volume** at `/app/data` keeps the content-addressed blob uploads
   alive across container restarts and redeploys.

3. **Seeding is explicit.** Boot only migrates the schema and creates the first admin;
   it no longer runs a corpus sync on an empty database, because an implicit sync on
   startup is indistinguishable from a hang. Enqueue one with
   `POST /api/v2/jobs/corpus_sync`, or run `make sync` against the deployment.

`make push-remote` is the fallback when the image has no baked seed: it signs in with
`ADMIN_EMAIL` / `ADMIN_PASSWORD`, then uploads PDF+JSON over HTTP as `source_type=upload`
and does **not** write `corpus_sync_state`. The Library subtitle then reads
`seeded by upload · pipeline mounts not on this host` instead of `last sync ok`. That is
mount health, not an empty library.

```bash
# On a machine that already has data/corpora/ and a synced local DB:
make sync
make push-remote BASE_URL=https://p01--crx-web--m4hljdfnbvqq.code.run
```

The image sets its own `CORPUS_*`, `SEED_CORPUS_*`, and `UPLOAD_DIR`
(`/data/corpus/...`, `/seed/corpus/...`, `/app/data/...`), so local host paths in a
`.env` never reach a deployed container.
