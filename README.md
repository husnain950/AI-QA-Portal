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

## Schema migrations

API boot runs a versioned migrator (`schema_version` + `backend/migrations/m0001_initial.py`). Idempotent `CREATE IF NOT EXISTS` / guarded ALTERs remain so legacy DBs upgrade cleanly.

## CORS / auth note

CORS is open for local trusted reviewers (2–3 people). For a public deploy, tighten origins and add auth — out of scope for v1.

## Non-goals (v1)

- Merging `fbr_ingest` and `acts_ingest`
- Re-converting the full Acts corpus in-session
- Shipping PDFs or DB blobs in git
- LLM/vision in the conversion path
