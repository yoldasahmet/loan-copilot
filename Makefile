SHELL := /bin/bash
API := apps/api
WEB := apps/web

.PHONY: setup dev migrate test lint fmt schema reindex eval check-no-data

setup:
	cd $(API) && uv sync
	cd $(WEB) && pnpm install
	$(MAKE) migrate

dev:
	@trap 'kill 0' EXIT; \
	(cd $(API) && uv run uvicorn loancopilot.main:app --reload --port 8000) & \
	(cd $(WEB) && pnpm dev --port 3000) & \
	wait

migrate:
	cd $(API) && uv run alembic upgrade head

test:
	cd $(API) && uv run pytest -q
	cd $(WEB) && pnpm typecheck

lint:
	cd $(API) && uv run ruff check . && uv run ruff format --check .
	cd $(WEB) && pnpm exec biome check .

fmt:
	cd $(API) && uv run ruff check --fix . && uv run ruff format .
	cd $(WEB) && pnpm exec biome check --write .

schema:
	cd $(API) && uv run python -m loancopilot.history > ../../docs/import-format.md

reindex:
	cd $(API) && uv run python -m loancopilot.embeddings

eval:
	@test -n "$(EVAL_DIR)" || (echo "Set EVAL_DIR, e.g. make eval EVAL_DIR=local/eval" && exit 1)
	cd $(API) && EVAL_DIR=$(abspath $(EVAL_DIR)) uv run python -m eval.run

check-no-data:
	./scripts/check-no-data.sh
