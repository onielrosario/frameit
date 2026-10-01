# Common tasks. Run `make help` for the list.
# Assumes Python 3.12 and Node 22+ (see README).

VENV := services/api/.venv
BIN  := $(VENV)/bin

.PHONY: help setup api extension test lint format eval-mock validate-dataset

help:  ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

setup:  ## Create the Python venv and install everything
	python3.12 -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e "services/api[dev]"
	npm ci

api:  ## Run the API on :8000 (reads .env)
	cd services/api && .venv/bin/uvicorn app.main:app --reload --reload-dir app --port 8000 --env-file ../../.env

extension:  ## Build the extension into apps/extension/dist
	npm run build:extension

test:  ## Run every test suite
	cd services/api && .venv/bin/pytest -q
	cd evaluation && ../$(BIN)/pytest -q
	npm test --workspace apps/extension

lint:  ## Lint, format-check and type-check everything
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .
	cd services/api && .venv/bin/mypy
	npm run typecheck --workspace apps/extension

format:  ## Auto-format Python
	$(BIN)/ruff check . --fix
	$(BIN)/ruff format .

eval-mock:  ## Run the harness with no model and no key (exits 1 while the dataset is empty)
	cd evaluation && PYTHONPATH=runners:../services/api ../$(BIN)/python -m frame_eval.cli --split dev --analyzer mock --no-write

validate-dataset:  ## Check the labeled dataset's format and composition
	cd evaluation && PYTHONPATH=runners:../services/api ../$(BIN)/python -m frame_eval.validate
