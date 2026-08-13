.PHONY: up down build sync seed test test-api test-pipeline test-web convert-ordinance convert-acts export-qa logs shell-api health vendor-corpora seed-archive deploy-prod push-remote

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

health:
	@curl -sf http://localhost:$${API_PORT:-8000}/health | $(PYTHON) -m json.tool
	@curl -sf http://localhost:$${API_PORT:-8000}/api/documents >/dev/null && echo "documents: ok"

vendor-corpora:
	bash $(ROOT)/tools/bootstrap_corpora.sh

sync:
	$(PYTHON) tools/sync_corpus.py --metrics

seed: sync

convert-ordinance:
	@test -n "$(PDF)" || (echo "Usage: make convert-ordinance PDF=path/to.pdf [OUT=data/output/x.json]"; exit 1)
	$(PYTHON) tools/convert_ordinance.py "$(PDF)" $(if $(OUT),-o "$(OUT)",)

convert-acts:
	@test -n "$(PDF)" || (echo "Usage: make convert-acts PDF=path/to.pdf [OUT=data/output/x.json]"; exit 1)
	$(PYTHON) tools/convert_acts.py "$(PDF)" $(if $(OUT),-o "$(OUT)",)

export-qa:
	@test -n "$(DOC)" || (echo "Usage: make export-qa DOC=<document_id> [OUT=report.json]"; exit 1)
	curl -sf "http://localhost:$${API_PORT:-8000}/api/documents/$(DOC)/export?format=json" -o "$(or $(OUT),qa-report-$(DOC).json)"
	@echo "Wrote $(or $(OUT),qa-report-$(DOC).json)"

test: test-api test-pipeline test-web

test-api:
	cd $(ROOT) && PYTHONPATH=$(ROOT)/apps/api $(PYTHON) -m pytest apps/api/backend/tests -q

test-pipeline:
	$(PYTHON) tools/run_tests_smoke.py

test-web:
	cd $(ROOT)/apps/web && npm run build

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

deploy-prod: seed-archive
	bash $(ROOT)/tools/deploy_coderun.sh

push-remote:
	@test -n "$(BASE_URL)" || (echo "Usage: make push-remote BASE_URL=https://your-portal.code.run"; exit 1)
	$(PYTHON) -m backend.push_corpus --base-url "$(BASE_URL)"
