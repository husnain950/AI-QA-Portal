# FBR Corpus Platform (`crx`)

Unified monorepo: **PDF → JSON pipelines** (`packages/fbr_ingest`, `packages/acts_ingest`) and the **QA review portal** (`apps/api`, `apps/web`) share one Docker stack, Makefile, and sync CLI.

Live portal without a seed is empty; this repo is meant to run locally with in-tree corpora under `data/corpora/` and `make sync`.

## Closed loop

```
convert PDF  →  data/output JSON  →  make sync  →  review in UI  →  export QA JSON  →  import_qa_report
```

1. **Convert** — `make convert-ordinance PDF=…` or `make convert-acts PDF=…`
2. **Sync** — `make sync` loads Ordinance (~12) + Acts (~80) editions into SQLite from `data/corpora/`
3. **Review** — side-by-side PDF + HTML, versions, annotations
4. **Export** — dashboard JSON/CSV or `make export-qa DOC=<id>`
5. **Import findings** — `python tools/import_qa_report.py …` into pipeline regression cases

## Layout

```
apps/api          FastAPI (Python package name: backend)
apps/web          Vite + React review UI
packages/fbr_ingest   Income Tax Ordinance pipeline
packages/acts_ingest  Acts + OCR fork (kept separate on purpose)
tools/            sync_corpus, convert_*, import_qa, bootstrap_corpora, smoke tests
data/             gitignored db / uploads / corpora / output / ocr_cache
data/corpora/     Ordinance + Acts PDFs and pipeline JSON (local only)
```

## Quick start

```bash
cp .env.example .env   # defaults already point at data/corpora/
make up                # api :8000 + web :5173
make sync              # seed from data/corpora/*/output JSON
make health
```

Open http://localhost:5173 — dashboard should list Ordinance + Acts editions.

Corpora are vendored under `data/corpora/` (gitignored). Optional refresh from a sibling CC-FBR tree: `make vendor-corpora`.

### Environment

See [`.env.example`](.env.example). Important knobs:

| Variable | Purpose |
|----------|---------|
| `DATABASE_PATH` | SQLite file (default `./data/db/qa_portal.db`) |
| `UPLOAD_DIR` | Content-addressed PDF/JSON blobs |
| `CORPUS_ORDINANCE` | `./data/corpora/ordinance` (`output/*.json` + Ordinance PDFs) |
| `CORPUS_ACTS` | `./data/corpora/acts` (`output/*.json` + `Acts/**`) |

These `CORPUS_*` / `DATABASE_PATH` / `UPLOAD_DIR` values are **host-local**. Compose and the API image override them inside the container (`/data/corpus/...`, `/app/data/...`). `make deploy-prod` strips them from `--env-file` so a local `.env` cannot make production report missing mounts.

The Library subtitle (`last sync` / `seeded by upload` / `pipeline mounts not on this host`) is **pipeline-mount health** — whether those directories exist on the API host with `output/*.json` — not whether Ordinance or Acts documents are already in the library. `make push-remote` fills the library as uploads and does not record a corpus sync.

Compose mounts `./data/corpora/...` **read-only** into the API container. Large blobs stay out of git.

### Make targets

| Target | What it does |
|--------|----------------|
| `make up` / `down` | Docker Compose stack |
| `make vendor-corpora` | Optional re-copy from sibling CC-FBR |
| `make sync` | Sync Ordinance + Acts (`--metrics`) |
| `make convert-ordinance PDF=…` | Run `fbr_ingest` |
| `make convert-acts PDF=…` | Run `acts_ingest` |
| `make test` | API pytest + pipeline smoke + `npm run build` |
| `make export-qa DOC=…` | Download QA report JSON |

### Production web image

Dev Compose uses Vite. For a static nginx SPA:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build
```

## CI/CD

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | every PR and push to `main` | API pytest, pipeline import smoke, web lint/vitest/build |
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
the two services (`crx-api`, `crx-web`) in the `qa-pdf-portal` project. It is applied by running the
template in Northflank; the deploy workflow does not run it, it only builds and deploys the services
the template created.

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

API boot runs a versioned migrator (`schema_version` + `backend/migrations/m0001_initial.py`). Idempotent `CREATE IF NOT EXISTS` / guarded ALTERs remain so legacy DBs upgrade cleanly.

## CORS / auth note

CORS is open for local trusted reviewers (2–3 people). For a public deploy, tighten origins and add auth — out of scope for v1.

## Non-goals (v1)

- Merging `fbr_ingest` and `acts_ingest`
- Re-converting the full Acts corpus in-session
- Shipping PDFs or DB blobs in git
- LLM/vision in the conversion path
