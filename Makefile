SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c

UV := uv run --frozen --project backend

.PHONY: setup test verify build-ui serve mcp mcp-http mcp-smoke eval-smoke eval-dev eval-test tune agent-eval

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

serve:
	$(UV) uvicorn backend.api:app --host 127.0.0.1 --port 8000 --workers 1

mcp:
	$(UV) python -m backend.mcp_server

mcp-http:
	$(UV) python -m backend.mcp_server --http

agent-eval:
	$(UV) python -m backend.agent_eval

# Lists the tools, then calls assess_station and checks 44371 on 2022-06-03 reports INVESTIGATE (the known precursor).
mcp-smoke:
	npx --yes @modelcontextprotocol/inspector@2.12.0 --cli $(UV) python -m backend.mcp_server --method tools/list | grep -q assess_station
	npx --yes @modelcontextprotocol/inspector@2.12.0 --cli $(UV) python -m backend.mcp_server --method tools/call --tool-name assess_station --tool-arg 'station_id="44371"' --tool-arg as_of_utc=2022-06-03T00:00:00Z | grep -q INVESTIGATE

# David's evaluation harness (ARCHITECTURE.md §6). Dev only, except eval-test (once per frozen version).
eval-smoke:
	$(UV) python -m backend.scripts.evaluate smoke

eval-dev:
	$(UV) python -m backend.scripts.evaluate dev

eval-test:
	$(UV) python -m backend.scripts.evaluate test

tune:
	$(UV) python -m backend.scripts.tune
