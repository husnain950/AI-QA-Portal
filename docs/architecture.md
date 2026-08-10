# Architecture (slim)

## Components

- **apps/api** — FastAPI + SQLite FTS5. Module name remains `backend` for import stability.
- **apps/web** — Vite/React review UI (Zustand, vanilla CSS).
- **packages/fbr_ingest** — Ordinance digital-PDF pipeline (unchanged internals).
- **packages/acts_ingest** — Acts pipeline + OCR fork (kept separate; intentional drift).
- **tools/sync_corpus** — Calls `backend.services.corpus_sync` for both corpus roots.

## Data path

Source PDFs + pipeline JSON live under `data/corpora/` (`CORPUS_ORDINANCE` / `CORPUS_ACTS`, gitignored). Conversion may also write under `data/output/`. Sync content-addresses PDF/JSON into `UPLOAD_DIR` and indexes sections in SQLite. Optional `make vendor-corpora` refreshes from a sibling CC-FBR tree.

## Version workflow

One static PDF per document; each corrected JSON is a new `document_versions` row with leaf diffs and annotation re-anchoring. Pipeline health badges come from ingested Acts_fbr reports (`--metrics`), never recomputed in the portal.
