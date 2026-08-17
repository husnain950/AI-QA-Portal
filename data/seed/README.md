# Seed Corpus

Pipeline output (PDFs + JSONs) baked into the Docker image for auto-seeding.

When the API container starts with an empty database (fresh persistent volume
or first deploy), it automatically syncs from these files to populate the
Library — no manual `push_corpus` needed.

## This directory is NOT committed to git

At ~500MB+ (source PDFs + output JSONs), it's a local build artifact only.
The `make seed-archive` command populates it from `data/corpora/`, and
`make deploy-prod` runs that automatically before building the image.

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

# Deploy to CodeRun with persistent volume + baked seed
make deploy-prod

# Alternative: push local corpus to an already-deployed remote
make push-remote BASE_URL=https://your-portal.code.run
```

## How persistence works

1. **CodeRun persistent volume** (`--storage-size 5Gi --storage-path /app/data`)
   keeps the SQLite DB + blob uploads alive across container restarts/redeploys.

2. **Auto-seed on first boot**: if the DB is empty and seed files exist in the
   image, `bootstrap_runtime()` runs corpus sync automatically.

3. **Subsequent deploys** find existing data in the volume and skip seeding.

`make push-remote` is the fallback when the image has no baked seed: it uploads PDF+JSON
over HTTP as `source_type=upload` and does **not** write `corpus_sync_state`. The Library
subtitle then reads `seeded by upload · pipeline mounts not on this host` instead of
`last sync ok`. That is mount health, not an empty library.

`tools/deploy_coderun.sh` filters `CORPUS_*`, `DATABASE_PATH`, and `UPLOAD_DIR` out of
`--env-file` so local host paths cannot override the image defaults
(`/data/corpus/ordinance`, `/data/corpus/acts`, `/seed/corpus/...`, `/app/data/...`).
