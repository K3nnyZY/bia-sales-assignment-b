SHELL := /bin/sh
UV ?= uv
COMPOSE := docker compose

.PHONY: help env demo-env seed runtime-seed runtime-smoke provider-smoke config up down logs ps migrate test test-unit lint web-check smoke verify install dev-api dev-web e2e

help:
	@echo "make env       Create .env without overwriting existing configuration"
	@echo "make up        Build, migrate and start the complete Docker stack"
	@echo "make verify    Start stack, run PostgreSQL tests, lint, web checks and smoke test"
	@echo "make down      Stop stack (database volume is preserved)"
	@echo "make install   Install native dependencies (Python 3.14, uv, Node 24)"

env:
	@test -f .env || cp .env.example .env

demo-env: env
	sh scripts/demo-env.sh

seed: env
	$(COMPOSE) run --rm --build migrate python -m app.seed

runtime-seed: env
	$(COMPOSE) run --rm --build migrate python -m app.runtime.seed

e2e:
	npm run test:e2e

config: env
	$(COMPOSE) config --quiet

up: config
	$(COMPOSE) up --build --wait --wait-timeout 180

down:
	$(COMPOSE) --profile test down --remove-orphans

logs:
	$(COMPOSE) logs --tail=100 -f

ps:
	$(COMPOSE) ps -a

migrate: env
	$(COMPOSE) run --rm --build migrate

test: env
	$(COMPOSE) --profile test run --rm --build tests

test-unit:
	$(UV) run --frozen pytest -m "not integration"

lint: env
	$(COMPOSE) --profile test run --rm --no-deps --build tests ruff check --no-cache apps/api scripts
	$(COMPOSE) --profile test run --rm --no-deps tests ruff format --check --no-cache apps/api scripts

web-check: env
	$(COMPOSE) --profile test run --rm --no-deps --build web-check

smoke:
	$(COMPOSE) exec -T api python - --api-url http://api:8000 --web-url http://web:3000 < scripts/smoke.py

runtime-smoke:
	$(COMPOSE) exec -T api python - < scripts/runtime_smoke.py

provider-smoke:
	$(COMPOSE) exec -T api python - < scripts/provider_smoke.py

verify:
	$(MAKE) up
	$(MAKE) seed
	$(MAKE) runtime-seed
	$(MAKE) test
	$(MAKE) lint
	$(MAKE) web-check
	$(MAKE) smoke
	$(MAKE) runtime-smoke

install: env
	$(UV) sync --frozen
	npm ci

dev-api:
	$(UV) run --frozen --env-file .env -- sh -c 'uvicorn app.main:app --app-dir apps/api --reload --host 127.0.0.1 --port "$${API_PORT:-8000}"'

dev-web:
	$(UV) run --frozen --env-file .env -- sh -c 'npm run dev -- --port "$${WEB_PORT:-3000}"'
