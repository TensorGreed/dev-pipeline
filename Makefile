PYTHON ?= python
CONFIG ?= config/settings.example.yaml
REQ ?= app/examples/sample_requirement.md
REPO ?= .

.PHONY: install test lint typecheck run-api run-sample

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check app tests

typecheck:
	mypy app

run-api:
	uvicorn app.api:create_app --factory --host 0.0.0.0 --port 8000

run-sample:
	$(PYTHON) -m app.cli run --repo $(REPO) --requirement-file $(REQ) --base-branch main --config $(CONFIG)
