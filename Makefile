# One-command workflow. Run `make help`.
PY := backend/.venv/bin/python
PIP := backend/.venv/bin/pip
# Override if your default python3 is too old:  make setup PYTHON=python3.12
PYTHON ?= python3

.PHONY: help setup models check bench calibrate ingest reset eval eval-fast api web dev test lint cost docker

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## Install backend (venv) + frontend deps, create .env
	@$(PYTHON) -c 'import sys; v=sys.version_info; sys.exit(0 if v >= (3, 11) else "Python 3.11+ required, found %d.%d. Install: brew install python@3.12  then: make setup PYTHON=python3.12" % v[:2])'
	test -f .env || cp .env.example .env
	rm -rf backend/.venv
	$(PYTHON) -m venv backend/.venv
	$(PIP) install -U pip -q
	$(PIP) install -r backend/requirements-dev.txt
	$(PY) -c "import yaml, chromadb, fastembed, fastapi; print('backend deps OK')"
	cd frontend && npm install

models: ## Pre-download embedding + reranker models (~3GB, do it at home!)
	cd backend && ../$(PY) -m scripts.download_models

check: ## Verify the LLM key + models work (both providers)
	cd backend && ../$(PY) -m scripts.check_setup

bench: ## Compare speed of free LLM models (MODELS="a b" to pick the fastest)
	cd backend && ../$(PY) -m scripts.bench_models $(MODELS)

calibrate: ## Suggest MIN_RELEVANCE_SCORE from the eval set (uses rewrite LLM calls)
	cd backend && ../$(PY) -m scripts.calibrate

ingest: ## Ingest backend/data/raw into ChromaDB
	cd backend && ../$(PY) -m scripts.ingest

reset: ## Wipe the vector DB and re-ingest from scratch
	cd backend && ../$(PY) -m scripts.ingest --reset

eval: ## Full evaluation (retrieval + LLM judge) -> backend/data/eval/results
	cd backend && ../$(PY) -m scripts.evaluate --tag $(or $(TAG),run)

eval-fast: ## Retrieval-only evaluation (free, seconds)
	cd backend && ../$(PY) -m scripts.evaluate --retrieval-only --tag $(or $(TAG),retrieval)

api: ## Run FastAPI on :8000
	cd backend && ../backend/.venv/bin/uvicorn app.main:app --reload --port 8000

web: ## Run Next.js on :3000
	cd frontend && npm run dev

dev: ## Run API + web together
	$(MAKE) -j2 api web

test: ## Backend tests
	cd backend && ../$(PY) -m pytest -q

lint: ## Lint backend + frontend
	cd backend && .venv/bin/ruff check . --exclude .venv
	cd frontend && npm run lint

cost: ## Unit economics for the business plan
	cd backend && ../$(PY) -m scripts.cost_calculator

docker: ## Run everything with Docker
	docker compose up --build
