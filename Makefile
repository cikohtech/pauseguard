# PauseGuard: one entry point for local dev, tests and deploys.
# Every target runs from the repo root. Targets marked "phase NN" are filled in by that phase.

SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND := backend
WEB     := web
UV      := uv --directory $(BACKEND)

# Firebase CLI: a global install if there is one, else a pinned copy through npx (no sudo).
FIREBASE ?= $(shell command -v firebase 2>/dev/null || echo npx --yes firebase-tools@15.31.0)
# Homebrew's openjdk@21 is keg-only (not on PATH); the emulators need it, so add it if present.
BREW_JDK := /opt/homebrew/opt/openjdk@21/bin
export PATH := $(if $(wildcard $(BREW_JDK)),$(BREW_JDK):)$(PATH)

.PHONY: help setup dev dev-api dev-web emulators test lint format seed-local seed-cloud history \
        eval deploy-api deploy-web smoke

help: ## List the targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n",$$1,$$2}'

setup: ## Install backend + web deps, create .env, install git hooks
	@command -v uv >/dev/null || { echo "uv is required: brew install uv"; exit 1; }
	$(UV) sync
	cd $(WEB) && npm ci
	@test -f .env || { cp .env.example .env && echo "Created .env from .env.example"; }
	@if [ -d .git ]; then $(UV) run pre-commit install; fi

dev: ## API on :8000 + web on :5173 (+ Firestore/Auth emulators if installed). Ctrl-C stops all.
	@trap 'kill 0' INT TERM; \
	if command -v npx >/dev/null 2>&1 && java -version >/dev/null 2>&1; then \
		echo "▶ Firestore + Auth emulators (UI on :4000)"; \
		$(FIREBASE) emulators:start --only firestore,auth --project demo-pauseguard & \
	else \
		echo "ℹ Firestore emulator skipped (needs Node + Java 11+: brew install openjdk@21)."; \
	fi; \
	echo "▶ API  http://localhost:8000/healthz   ▶ Web  http://localhost:5173"; \
	$(UV) run uvicorn app.main:app --reload --port 8000 & \
	(cd $(WEB) && npm run dev) & \
	wait

dev-api: ## API only, with reload
	$(UV) run uvicorn app.main:app --reload --port 8000

dev-web: ## Web only
	cd $(WEB) && npm run dev

emulators: ## Firestore + Auth emulators only
	$(FIREBASE) emulators:start --only firestore,auth --project demo-pauseguard

test: ## Backend pytest (live tests excluded) + web Vitest
	$(UV) run pytest
	cd $(WEB) && npm test

lint: ## ruff + mypy (backend), oxlint + tsc (web)
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy app
	cd $(WEB) && npm run lint && npm run typecheck

format: ## Auto-fix formatting
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

seed-local: ## Regenerate synthetic data -> SQLite (+ watchlist/personas into the emulator if it runs)
	$(UV) run python -m app.data.seed local

seed-cloud: ## Regenerate synthetic data -> BigQuery (asia-southeast1) + Firestore (needs GCP auth)
	$(UV) run python -m app.data.seed cloud

history: ## Print a customer's 90-day history (CUSTOMER=cust_001 by default)
	$(UV) run python -m app.data.seed history $(or $(CUSTOMER),cust_001)

eval: ## phase 09: run the benchmark and write eval/reports/benchmark.md
	@echo "eval is implemented in phase 09 (prompts/phase-09-benchmark.md)"; exit 1

deploy-api: ## phase 10: Cloud Run deploy of backend/
	@echo "deploy-api is implemented in phase 10 (prompts/phase-10-deploy.md)"; exit 1

deploy-web: ## phase 10: build web/ and deploy to Firebase Hosting
	@echo "deploy-web is implemented in phase 10 (prompts/phase-10-deploy.md)"; exit 1

smoke: ## phase 10: /healthz + the 3 demo scenarios against an API
	@echo "smoke is implemented in phase 10 (prompts/phase-10-deploy.md)"; exit 1
