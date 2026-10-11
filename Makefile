# PauseGuard: one entry point for local dev, tests and deploys.
# Every target runs from the repo root. Targets marked "phase NN" are filled in by that phase.

SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND := backend
WEB     := web
UV      := uv --directory $(BACKEND)

# Google Cloud (phase 10). The project comes from GOOGLE_CLOUD_PROJECT in .env.
PROJECT ?= $(shell grep -E '^GOOGLE_CLOUD_PROJECT=' .env 2>/dev/null | cut -d= -f2 | awk '{print $$1}')
REGION  ?= asia-southeast1
SERVICE := pauseguard-api
# Cloud Run min instances: 0 while building, 1 from submission day on (DEPLOYMENT §7).
MIN_INSTANCES ?= 0

# Firebase CLI: a global install if there is one, else a pinned copy through npx (no sudo).
FIREBASE ?= $(shell command -v firebase 2>/dev/null || echo npx --yes firebase-tools@15.31.0)
# Homebrew's openjdk@21 is keg-only (not on PATH); the emulators need it, so add it if present.
BREW_JDK := /opt/homebrew/opt/openjdk@21/bin
export PATH := $(if $(wildcard $(BREW_JDK)),$(BREW_JDK):)$(PATH)

.PHONY: help setup dev dev-api dev-web emulators test test-rules lint format seed-local seed-cloud history \
        a11y playwright eval-drafts eval-render eval-dataset eval-verify demo-evidence \
        evidence-dev agent-evals scenario demo-curl api-live drills eval infra analyst deploy-api deploy-web smoke \
        console-live

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
	echo "▶ API  http://localhost:8000/health   ▶ Web  http://localhost:5173"; \
	$(UV) run uvicorn app.main:app --reload --port 8000 & \
	(cd $(WEB) && npm run dev) & \
	wait

dev-api: ## API only, with reload
	$(UV) run uvicorn app.main:app --reload --port 8000

dev-web: ## Web only
	cd $(WEB) && npm run dev

emulators: ## Firestore + Auth emulators only
	$(FIREBASE) emulators:start --only firestore,auth --project demo-pauseguard

test: ## Backend pytest (live tests excluded; fusion policy needs 100% branch coverage) + web Vitest + Firestore rules
	$(UV) run pytest --cov=app/policy --cov-branch --cov-report=term-missing:skip-covered --cov-fail-under=100
	cd $(WEB) && npm test
	@if java -version >/dev/null 2>&1; then $(MAKE) --no-print-directory test-rules; \
	else echo "ℹ Firestore rules tests skipped (need Java 11+: brew install openjdk@21)."; fi

test-rules: ## Firestore rules (infra/firestore.rules) in a throwaway emulator on :8181 (never the dev one)
	$(FIREBASE) emulators:exec --config infra/firebase.rules-test.json --only firestore \
	  --project demo-pauseguard-rules "npm --prefix $(CURDIR)/$(WEB) run test:rules"

a11y: ## Customer app in Chromium: 3 scenarios + axe (WCAG 2.1 AA) + keyboard, API mocked (screens in web/test-results/screens)
	cd $(WEB) && npx playwright install --only-shell chromium && npm run test:e2e

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

playwright: ## One-time: Playwright + headless Chromium for the evidence renderers (datagen group)
	$(UV) run --group datagen playwright install --only-shell chromium

eval-drafts: ## Eval set: slot plan + drafts -> data/eval/drafts.jsonl + REVIEW.md (needs seed-local)
	$(UV) run python ../data/generate/make_eval_messages.py draft

eval-render: ## Eval set: render chat/SMS/email PNGs and PDFs into data/eval/img|pdf
	$(UV) run --group datagen python ../data/generate/render_chats.py

eval-dataset: eval-render ## Eval set: render, then write data/eval/cases.jsonl + eval/TEST_SPLIT_HASH
	$(UV) run python ../data/generate/make_eval_messages.py assemble

eval-verify: ## Check that the frozen test split (cases + evidence files) is unchanged
	$(UV) run python ../data/generate/make_eval_messages.py verify

demo-evidence: ## Render the demo personas' evidence into data/demo/
	$(UV) run --group datagen python ../data/generate/render_chats.py --demo

evidence-dev: ## Evidence agent on the DEV split (live Gemini): typology accuracy + misses
	$(UV) run python ../eval/evidence_dev.py $(if $(IDS),--ids $(IDS))

agent-evals: ## ADK eval sets: 3 golden cases per agent through AgentEvaluator (live Gemini)
	$(UV) run --group agent-evals pytest -m live -k agent_evals

scenario: ## The full pipeline on a demo scenario (live Gemini): SCENARIO=tan|raj|aisyah|all, RUNS=1
	$(UV) run python -m app.agents.orchestrator --scenario $(or $(SCENARIO),all) --runs $(or $(RUNS),1)

demo-curl: ## The 3 demo scenarios through a running API (make dev first) with curl: BASE=, ADMIN_TOKEN=
	scripts/demo_curl.sh $(SCENARIO)

api-live: ## The API end to end with the real agents (live Gemini): upload, answer, verdict, REPORT_SCAM
	$(UV) run pytest -m live -k api_live

drills: ## Failure drills (live Gemini): model down, slow model, 10 MB image, bad files, injection -> eval/reports/drills.md; then the UI side in Chromium
	$(UV) run pytest -m live -k drills -v
	cd $(WEB) && npx playwright install --only-shell chromium && npx playwright test e2e/drills.spec.ts

eval: ## phase 09: run the benchmark and write eval/reports/benchmark.md
	@echo "eval is implemented in phase 09 (prompts/phase-09-benchmark.md)"; exit 1

infra: ## One-time GCP infrastructure (idempotent; creates billable resources): infra/setup.sh
	PROJECT_ID=$(PROJECT) REGION=$(REGION) infra/setup.sh

analyst: ## Create/refresh the demo analyst (role=analyst) in Firebase Auth; ARGS=--emulator for local
	$(UV) run python ../infra/set_analyst_claim.py $(ARGS)

deploy-api: ## Cloud Run deploy of backend/ (Cloud Build, asia-southeast1); MIN_INSTANCES=1 for judging
	gcloud run deploy $(SERVICE) --project $(PROJECT) --region $(REGION) --quiet \
	  --source $(BACKEND) --image $(REGION)-docker.pkg.dev/$(PROJECT)/pauseguard/$(SERVICE) \
	  --build-service-account projects/$(PROJECT)/serviceAccounts/pauseguard-build@$(PROJECT).iam.gserviceaccount.com \
	  --service-account pauseguard-api@$(PROJECT).iam.gserviceaccount.com \
	  --env-vars-file infra/cloudrun.env.yaml --set-secrets ADMIN_RESET_TOKEN=admin-reset-token:latest \
	  --allow-unauthenticated --min-instances $(MIN_INSTANCES) --max-instances 5 --concurrency 20 \
	  --memory 1Gi --cpu 1 --timeout 180 --no-cpu-throttling --cpu-boost

deploy-web: ## Build web/ against the live API, deploy Firebase Hosting + Firestore rules/indexes
	@API_URL="$$(gcloud run services describe $(SERVICE) --project $(PROJECT) --region $(REGION) --format='value(status.url)')"; \
	test -n "$$API_URL" || { echo "No Cloud Run service $(SERVICE) yet: make deploy-api first"; exit 1; }; \
	echo "▶ VITE_API_BASE_URL=$$API_URL"; \
	cd $(WEB) && VITE_API_BASE_URL="$$API_URL" npm run build
	$(FIREBASE) deploy --project $(PROJECT) --only hosting,firestore:rules,firestore:indexes --non-interactive

smoke: ## The live stack: /health, Hosting, CORS, Firebase Auth, the 3 scenarios, then reset-demo
	PROJECT=$(PROJECT) REGION=$(REGION) scripts/smoke.sh

console-live: ## The live demo's two windows: Tan's transfer -> case in the console within 1 s -> Report -> watchlist, then reset-demo
	@API_URL="$$(gcloud run services describe $(SERVICE) --project $(PROJECT) --region $(REGION) --format='value(status.url)')"; \
	ADMIN_TOKEN="$$(gcloud secrets versions access latest --secret admin-reset-token --project $(PROJECT))"; \
	cd $(WEB) && npx playwright install --only-shell chromium >/dev/null && \
	API_URL="$$API_URL" ADMIN_TOKEN="$$ADMIN_TOKEN" node e2e-live/console-live.mjs $(or $(SITE),https://$(PROJECT).web.app)
