.PHONY: up down build sync seed test test-api test-pipeline test-web convert-ordinance convert-acts export-qa logs shell-api health vendor-corpora

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
