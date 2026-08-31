# Architecture (slim)

## Components

- **apps/api** — FastAPI over PostgreSQL (SQLAlchemy async engine, Alembic, GIN full-text).
  Module name remains `backend` for import stability.
- **apps/api `backend/worker.py`** — the same image running the job queue: corpus sync,
  detectors, PDF renders, evidence exports, AI proposals.
- **apps/web** — Vite/React review UI (Zustand, vanilla CSS).
- **packages/fbr_ingest** — Ordinance digital-PDF pipeline (unchanged internals).
- **packages/legal_ingest** — Acts *and* Rules pipeline + OCR, one `Profile` per corpus
  (`packages/legal_ingest/profiles.py`). `acts_ingest` / `rules_ingest` are thin profile
  bindings that keep `from <lane>_ingest import run` working.
- **tools/sync_corpus** — Calls `backend.services.corpus_sync` for both corpus roots.

## Data path

Source PDFs + pipeline JSON live under `data/corpora/` (`CORPUS_ORDINANCE` / `CORPUS_ACTS`, gitignored). Conversion may also write under `data/output/`. Sync content-addresses PDF/JSON into the blob store (`UPLOAD_DIR` for the filesystem
backend, an S3 bucket otherwise) and indexes sections in PostgreSQL. Optional `make vendor-corpora` refreshes from a sibling CC-FBR tree.

The Library header's Ordinance/Acts line is that mount check (`output/*.json` on disk), not the document list.

Remote seed via `push_corpus` sends each document's `source_key` and `corpus_origin`, so the deployment mints the same deterministic id `sync_acts` does: a pushed row and a synced row are the same row. Pipeline health metrics (which match on `source_key`) therefore resolve in production, a re-push is a new version rather than a second document, and reconciliation can withdraw a document the pipeline has retired. `corpus_sync_state.last_sync_at` stays null on a deployment, because no sync ran there.

A document uploaded by hand has no corpus identity and keeps the old shape: a uuid4 id and `source_type=upload`.

## Version workflow

One static PDF per document; each corrected JSON is a new `document_versions` row with leaf diffs and annotation re-anchoring. Pipeline health badges come from ingested Acts_fbr reports (`--metrics`), never recomputed in the portal.
