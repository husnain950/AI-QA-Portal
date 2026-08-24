.PHONY: seed-archive up down build sync seed-fixtures test check test-api test-pipeline test-web convert-ordinance convert-acts convert-rules convert-all export-qa logs shell-api health vendor-corpora push-remote backup-remote backfill-provenance

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ifneq (,$(wildcard $(ROOT)/.venv/bin/python))
PYTHON := $(ROOT)/.venv/bin/python
else
PYTHON ?= python3
endif
export PYTHONPATH := $(ROOT)/apps/api:$(ROOT)/packages:$(PYTHONPATH)

-include .env
export

up:
	docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f --tail=100

# Readiness covers the database, the migration revision, and the blob root. The API
# itself needs a session for everything else, so there is nothing further to curl here.
health:
	@curl -sf http://localhost:$${API_PORT:-8000}/health/ready | $(PYTHON) -m json.tool
	@curl -sf http://localhost:$${API_PORT:-8000}/health/worker | $(PYTHON) -m json.tool || echo "worker: not running"

vendor-corpora:
	bash $(ROOT)/tools/bootstrap_corpora.sh

# BASE_URL drives a deployment over HTTP; without it, the local database.
backfill-provenance:
	$(PYTHON) tools/backfill_provenance.py $(if $(BASE_URL),--base-url "$(BASE_URL)",)

sync:
	$(PYTHON) tools/sync_corpus.py --metrics


# Populate a fresh clone with a generated micro-corpus, for review-page smoke tests
# and local UI work. Independent of `sync`, which needs the private data/corpora/.
seed-fixtures:
	$(PYTHON) tools/fixture_corpus.py
	$(PYTHON) tools/sync_corpus.py --acts $(ROOT)/data/fixtures/acts --acts-only

# One converter, one recipe per lane so the documented command surface is unchanged.
convert-ordinance convert-acts convert-rules:
	@test -n "$(PDF)" || (echo "Usage: make $@ PDF=path/to.pdf [OUT=data/output/x.json]"; exit 1)
	$(PYTHON) tools/convert.py $(@:convert-%=%) "$(PDF)" $(if $(OUT),-o "$(OUT)",)

# A whole corpus, one process per PDF, resumable. ARGS is passed straight through:
# --skip-existing to resume, --skip-scanned to convert only what needs no OCR,
# --list to see the targets. Audit trail lands in <corpus>/output/_run/.
convert-all:
	@test -n "$(LANE)" || (echo "Usage: make convert-all LANE=rules [ARGS='--skip-existing --skip-scanned']"; exit 1)
	$(PYTHON) tools/convert_all.py $(LANE) $(ARGS)

export-qa:
	@test -n "$(DOC)" || (echo "Usage: make export-qa DOC=<document_id> [OUT=report.json]"; exit 1)
	curl -sf "http://localhost:$${API_PORT:-8000}/api/documents/$(DOC)/export?format=json" -o "$(or $(OUT),qa-report-$(DOC).json)"
	@echo "Wrote $(or $(OUT),qa-report-$(DOC).json)"

test: test-api test-pipeline test-web

# Both suites, matching CI: tools/tests covers the deploy and snapshot scripts and
# was only ever run there, so a green `make test-api` could hide a break in them.
test-api:
	cd $(ROOT) && PYTHONPATH=$(ROOT)/apps/api $(PYTHON) -m pytest apps/api/backend/tests tools/tests -q

test-pipeline:
	$(PYTHON) tools/run_tests_smoke.py

test-web:
	cd $(ROOT)/apps/web && npm run lint && npm run test && npm run build

# What CI gates on, minus the jobs that need a container: `npm audit` and the
# Playwright review-page smoke (see AGENTS.md for running that one).
check: test-api test-pipeline test-web
	$(ROOT)/.venv/bin/ruff check apps/api tools 2>/dev/null || ruff check apps/api tools

shell-api:
	docker compose exec api bash

# --- Persistence & deployment ---

seed-archive:
	@echo "Packaging corpus (PDFs + JSONs) into data/seed/ for Docker image..."
	@mkdir -p $(ROOT)/data/seed/ordinance $(ROOT)/data/seed/acts
	@if [ -d "$(ROOT)/data/corpora/ordinance/output" ]; then \
		rsync -a --delete "$(ROOT)/data/corpora/ordinance/output/" "$(ROOT)/data/seed/ordinance/output/"; \
		echo "  ordinance JSONs: $$(ls $(ROOT)/data/seed/ordinance/output/*.json 2>/dev/null | wc -l | tr -d ' ')"; \
	else \
		echo "  ordinance: skipped (no data/corpora/ordinance/output/)"; \
	fi
	@if [ -d "$(ROOT)/data/corpora/ordinance/Income Tax Ordinance, 2001" ]; then \
		rsync -a --delete "$(ROOT)/data/corpora/ordinance/Income Tax Ordinance, 2001/" "$(ROOT)/data/seed/ordinance/Income Tax Ordinance, 2001/"; \
		echo "  ordinance PDFs: ok"; \
	fi
	@if [ -d "$(ROOT)/data/corpora/acts/output" ]; then \
		rsync -a --delete "$(ROOT)/data/corpora/acts/output/" "$(ROOT)/data/seed/acts/output/"; \
		echo "  acts JSONs: $$(ls $(ROOT)/data/seed/acts/output/*.json 2>/dev/null | wc -l | tr -d ' ')"; \
	else \
		echo "  acts: skipped (no data/corpora/acts/output/)"; \
	fi
	@if [ -d "$(ROOT)/data/corpora/acts/Acts" ]; then \
		rsync -a --delete "$(ROOT)/data/corpora/acts/Acts/" "$(ROOT)/data/seed/acts/Acts/"; \
		echo "  acts PDFs: ok"; \
	fi
	@if [ -d "$(ROOT)/data/corpora/ordinance/reports" ]; then \
		rsync -a --delete "$(ROOT)/data/corpora/ordinance/reports/" "$(ROOT)/data/seed/ordinance/reports/"; \
	fi
	@if [ -d "$(ROOT)/data/corpora/acts/reports" ]; then \
		rsync -a --delete "$(ROOT)/data/corpora/acts/reports/" "$(ROOT)/data/seed/acts/reports/"; \
	fi
	@echo "Seed archive ready (local build artifact, not committed to git)."
	@du -sh $(ROOT)/data/seed

# Re-seed a deployed portal from the local Postgres corpus. Needs ADMIN_EMAIL /
# ADMIN_PASSWORD in .env (admin role) and a prior `make sync` so local blobs exist.
push-remote:
	@test -n "$(BASE_URL)" || (echo "Usage: make push-remote BASE_URL=https://your-portal.code.run"; exit 1)
	$(PYTHON) -m backend.push_corpus --base-url "$(BASE_URL)"

# Backs up review state, which push-remote cannot rebuild -- re-uploading resets every
# section to pending. Volume snapshots would be better but Northflank gates that API.
# Needs ADMIN_EMAIL / ADMIN_PASSWORD (reader role is enough).
backup-remote:
	@test -n "$(BASE_URL)" || (echo "Usage: make backup-remote BASE_URL=https://your-portal.code.run"; exit 1)
	$(PYTHON) tools/snapshot_review.py --base-url "$(BASE_URL)" $(if $(OUT),--out "$(OUT)",)
