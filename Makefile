SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c

UV := uv run --frozen --project backend

.PHONY: setup test verify build-ui

setup:
	cd backend && uv sync --frozen
	cd frontend && npm ci

test:
	$(UV) ruff check backend
	$(UV) ruff format --check backend
	$(UV) pytest -q

verify:
	tools/verify

build-ui:
	cd frontend && npm run build
