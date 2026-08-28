# AGENTS.md

## Cursor Cloud specific instructions

FBR Corpus Platform (`crx`) is a single-product monorepo: PDF→JSON conversion pipelines
(`packages/fbr_ingest`, `packages/legal_ingest`) plus a QA review portal (`apps/api` FastAPI
backend + `apps/web` Vite/React frontend). Standard commands live in `README.md` and the
`Makefile`; below are only the non-obvious things for running this in a cloud VM.

### Environment layout
- Python deps install into a repo-local virtualenv at `.venv/` (gitignored). The `Makefile`
  auto-detects `.venv/bin/python`, so `make sync`, `make test-api`, etc. use it automatically.
- The startup update script provisions `.venv` (dev + pipeline deps), runs `npm ci` in
  `apps/web`, and creates `.env` from `.env.example` if missing.
- A **PostgreSQL 17** instance is required: `docker compose up -d postgres` covers it, and
  `DATABASE_URL` defaults to `postgresql+psycopg://crx:crx@127.0.0.1:5432/crx`. The backend
  test suite needs it too — it creates and migrates its own `_test` database, or the one
  named by `TEST_DATABASE_URL`. Blob storage is MinIO under Compose
  (`STORAGE_BACKEND=s3`) or local files (`STORAGE_BACKEND=filesystem`, the default).
- Non-obvious base-image dependency: creating the venv requires the system package
  `python3.12-venv` (base VM lacked `ensurepip`). It is already installed in the VM snapshot;
  if `python3 -m venv` ever fails with an `ensurepip` error, run `sudo apt-get install -y python3.12-venv`.

### Running the services (dev mode)
Run the API and web dev servers directly (do NOT rely on `make up`, which uses Docker):
- API: from repo root, `PYTHONPATH=apps/api:packages .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000`
  (load `.env` first, e.g. `set -a; . ./.env; set +a`). Health check: `curl http://localhost:8000/health`.
- Web: `cd apps/web && npm run dev -- --host 0.0.0.0` (serves http://localhost:5173, proxies to the API via `VITE_API_URL`).
- `make up` / `docker-compose` also work but require Docker-in-Docker setup; the local uvicorn+vite
  path above is the simpler dev loop in the cloud VM.

### How PDFs/blobs are served (dev vs prod)
- **Dev:** the Vite dev server proxies `/uploads/<key>` to the FastAPI `uploads` route
  (`apps/api/backend/routes/uploads.py`), which streams from the blob store. Tests use the
  same route.
- **Prod (Northflank / `docker-compose.prod.yml`):** `crx-web`'s nginx serves `/uploads/`
  **statically from the shared blob volume** (`apps/web/nginx.conf`, `BLOB_ROOT`), with native
  ranges/ETag and `immutable` caching — the API is not in the PDF request path at all. The
  nginx location is regex-guarded to content-addressed key shapes, so the volume's
  `.staging/`/`.cache/`/`.preflight/` dirs and legacy flat names answer 404 without touching
  disk. If the volume is not attached to the web container (template not re-run yet) or a blob
  is absent, nginx `try_files` falls back to the API route automatically, so merge and
  volume-attach can happen in either order. Blob reads are in the READ rate-limit tier;
  upload *writes* stay HEAVY.
- Keep both paths working: a change that only tests dev (Vite proxy) can silently break prod
  (static mount), and vice versa. `python -m backend.audit_pdf_serving --check-url <base>`
  validates every document's `/uploads` URL end-to-end against a live deployment.

### Seeding data (the portal is empty without it)
- Real corpora under `data/corpora/` are gitignored and NOT present in a fresh clone, so
  `make sync` has nothing to load and the dashboard starts empty. This is expected.
- The Library subtitle (`never synced` / `seeded by upload` · `pipeline mounts not on this
  host`) reports whether the Ordinance and Acts **pipeline directories** exist on the API
  host (`CORPUS_ORDINANCE` / `CORPUS_ACTS` with `output/*.json`). It is not a count of
  documents. A production instance filled by `make push-remote` still shows
  `seeded by upload` because that path never writes `corpus_sync_state`.
- **Preferred:** `make seed-fixtures` generates a micro-corpus (3 acts, 10 pages, real text
  PDFs) with `tools/fixture_corpus.py` and loads it through the normal acts sync, so the
  documents get `source_type='acts_corpus'` exactly like real ones. Needs no private data and
  no running API. Output lands in `data/fixtures/` (gitignored); re-running is idempotent.
- Alternatively upload a PDF + matching structure JSON via the UI "Upload" page or
  `POST /api/documents/upload` (multipart fields: `pdf`, `json_file`, `name`). Note this
  creates `source_type='upload'` documents. The JSON schema is `{"metadata": {...},
  "chapters": [{"sections": [{code, heading, start_page, end_page, html, plain_text,
  footnotes}]}], "schedules": []}` — see `apps/api/backend/tests/conftest.py::sample_document`.
- A blank/synthetic PDF is accepted for structural testing, but the in-browser PDF.js viewer
  cannot render blank/1-bit pages (shows a "did not render" message). The parsed-HTML pane and
  the annotation workflow still work fully; use a real text PDF if you need the PDF pane to
  render — this is why `tools/fixture_corpus.py` writes a genuine text layer instead of using
  `pypdf.add_blank_page()`.

### Review-page smoke test
- `cd apps/web && npm run smoke` (`scripts/visual_smoke.mjs`) drives Playwright over the
  dashboard and each target review page, asserting the PDF canvas rendered non-blank and the
  parsed-HTML pane has content. It exits non-zero on any failure.
- Needs a running API and web server. Override with `PORTAL_API` (default
  `http://127.0.0.1:8000/api`) and `PORTAL_BASE` (default `http://127.0.0.1:5173`).
- Targets come from `SMOKE_TARGETS`, defaulting to `data/fixtures/acts/smoke_targets.json`
  written by `make seed-fixtures`. With no manifest it falls back to the real corpus editions,
  so a synced private corpus behaves as before.
- First run needs `npx playwright install chromium` (~115 MB); it is not in the VM snapshot.
- The `smoke` CI job runs this on every PR: seed fixtures, start both servers, run the smoke,
  and upload the report plus screenshots as an artifact.

### Lint / test / build
- Backend lint: `.venv/bin/ruff check` (config in `pyproject.toml`). `apps/api` and `tools`
  are clean and gate merges; `packages/` carries a small advisory backlog (9 findings, all
  E741/E402/E702 style).
- Frontend lint: `cd apps/web && npm run lint` (`oxlint --deny-warnings`).
- Tests: `make test` runs API pytest (`apps/api/backend/tests` + `tools/tests`, ~441 tests)
  + the pipeline gate (`tools/run_tests_smoke.py`) + `apps/web` vite build. The web unit
  suite is separate: `cd apps/web && npm run test` (vitest, 134 tests).
- The pipeline gate has two tiers: package self-checks (`_demo()`) always run, and each
  lane's regression suite (`tools/run_suite.py <lane>`) runs only when its corpus is
  staged. Missing corpus is a SKIP; a present one that fails is a hard failure. All three
  lanes are green against a staged corpus (ordinance 12, acts 80, rules 11 editions).
- A handful of rules editions fail an invariant for a reason traced to the source PDF and
  not fixable in the parser (a compilation that embeds 44 separately-notified instruments;
  a PDF emitting one 75-char token with no space glyphs). Those are listed per document in
  `tools/suite/exemptions/rules.json` with their diagnosis: the invariant still runs and
  its hits are still printed, it just does not gate that one document, so the rest of the
  lane gates normally. Adding an entry needs the failure traced to its source first — see
  `tools/suite/README.md`.

### CI/CD
- GitHub Actions runs `.github/workflows/ci.yml` on every PR and push to `main`, then
  `.github/workflows/deploy-northflank.yml` builds and deploys the commit to Northflank via
  `tools/northflank_deploy.py`.
- The repo-wide ruff step is `continue-on-error` because of the `packages/` backlog; the
  blocking step lints all of `apps/api` and `tools`.
- Deploys need `NORTHFLANK_API_TOKEN` as a GitHub Actions repository secret. A token in `.env` is
  only usable for local runs of the script.
- `python tools/northflank_deploy.py enable-cicd` switches deploys over to Northflank's own CI/CD,
  which needs no GitHub Actions at all. Useful when Actions is unavailable.
- `pytest tools/tests` covers the deploy script against an in-process fake Northflank API
  (`tools/tests/fake_northflank.py`), so it can be exercised with no token and no network.
- Workflow YAML is checked with [actionlint](https://github.com/rhysd/actionlint); run
  `actionlint` from the repo root after editing anything under `.github/workflows/`.

### AI Fix feature
- The "AI Fix" action requires all three `OPENPATHS_*` env vars; without them the endpoint
  returns 503 by design. It is optional and not needed for core review/annotation flows.
