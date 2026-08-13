# AGENTS.md

## Cursor Cloud specific instructions

FBR Corpus Platform (`crx`) is a single-product monorepo: PDF→JSON conversion pipelines
(`packages/fbr_ingest`, `packages/acts_ingest`) plus a QA review portal (`apps/api` FastAPI
backend + `apps/web` Vite/React frontend). Standard commands live in `README.md` and the
`Makefile`; below are only the non-obvious things for running this in a cloud VM.

### Environment layout
- Python deps install into a repo-local virtualenv at `.venv/` (gitignored). The `Makefile`
  auto-detects `.venv/bin/python`, so `make sync`, `make test-api`, etc. use it automatically.
- The startup update script provisions `.venv` (dev + pipeline deps), runs `npm ci` in
  `apps/web`, and creates `.env` from `.env.example` if missing. No external DB/broker is
  needed — the app uses an embedded SQLite file under `data/db/` created + migrated on API boot.
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

### Seeding data (the portal is empty without it)
- Real corpora under `data/corpora/` are gitignored and NOT present in a fresh clone, so
  `make sync` has nothing to load and the dashboard starts empty. This is expected.
- To get a usable document without corpora, upload a PDF + matching structure JSON via the
  UI "Upload" page or `POST /api/documents/upload` (multipart fields: `pdf`, `json_file`,
  `name`). The JSON schema is `{"metadata": {...}, "chapters": [{"sections": [{code, heading,
  start_page, end_page, html, plain_text, footnotes}]}], "schedules": []}` — see
  `apps/api/backend/tests/conftest.py::sample_document` for a minimal valid example.
- A blank/synthetic PDF is accepted for structural testing, but the in-browser PDF.js viewer
  cannot render blank/1-bit pages (shows a "did not render" message). The parsed-HTML pane and
  the annotation workflow still work fully; use a real text PDF if you need the PDF pane to render.

### Lint / test / build
- Backend lint: `.venv/bin/ruff check` (config in `pyproject.toml`). Note: the repo currently
  has many pre-existing ruff findings — treat existing findings as baseline, not regressions.
- Frontend lint: `cd apps/web && npm run lint` (oxlint; warnings only).
- Tests: `make test` runs API pytest (`apps/api/backend/tests`, ~121 tests) + pipeline import
  smoke (`tools/run_tests_smoke.py`) + `apps/web` vite build. The web unit suite is separate:
  `cd apps/web && npm run test` (vitest, ~93 tests). All pass on a clean setup.

### AI Fix feature
- The "AI Fix" action requires all three `OPENPATHS_*` env vars; without them the endpoint
  returns 503 by design. It is optional and not needed for core review/annotation flows.
