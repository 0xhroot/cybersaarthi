COMPOSE := docker compose
EXEC := $(COMPOSE) exec -T backend
# Development/verification commands run in a dedicated `backend-dev` container
# (build target `dev`) that contains pytest/ruff/mypy on top of the runtime,
# keeping the production `backend` image lean.
DEV := $(COMPOSE) run --rm -T backend-dev

.PHONY: help up down down-v build logs ps seed admin demo-seed demo-status demo-validate demo-reset \
        test test-unit lint format format-check typecheck migrate migration shell \
        dataset dataset-validate train-setup train-check train-pilot train-metrics \
        eval eval-final model-compare model-rollback

help: ## list available make targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

up: ## build and start the full local stack
	$(COMPOSE) up -d --build

down: ## stop the stack (keeps volumes)
	$(COMPOSE) down

down-v: ## stop the stack and delete all volumes (destructive)
	$(COMPOSE) down -v

build: ## build images without starting
	$(COMPOSE) build

logs: ## follow logs for all services
	$(COMPOSE) logs -f

ps: ## show service status
	$(COMPOSE) ps

seed: ## seed the deterministic demo case (idempotent)
	$(EXEC) python -m scripts.seed_demo

demo-seed: ## seed the SIH showcase demo case via the real API (idempotent)
	$(COMPOSE) exec -T -e CS_API_BASE=$(CS_API_BASE) -e CS_SEED_JOB_TIMEOUT=$(CS_SEED_JOB_TIMEOUT) \
		-e CS_SEED_RETRY_FAILED=$(CS_SEED_RETRY_FAILED) backend python -m scripts.showcase_seed seed

demo-status: ## read-only checklist of the SIH showcase demo data
	$(COMPOSE) exec -T -e CS_API_BASE=$(CS_API_BASE) backend python -m scripts.showcase_seed status

demo-validate: ## static validation of the synthetic dataset fixtures (no server needed)
	python3 backend/scripts/validate_showcase_dataset.py

demo-reset: ## delete ONLY the SIH-2026-xxx showcase cases (DEMO_RESET_CONFIRM=sih-showcase)
	$(COMPOSE) exec -T -e DEMO_RESET_CONFIRM=$(DEMO_RESET_CONFIRM) backend \
		python -m scripts.showcase_seed reset

admin: ## bootstrap the first ADMIN user (idempotent)
	$(EXEC) python -m scripts.create_admin

test: ## run the full test suite (unit, api, integration) in the dev container
	$(DEV) pytest

test-unit: ## run only tests that do not need infrastructure
	$(DEV) pytest -m "not integration"

lint: ## run Ruff linter in the dev container
	$(DEV) ruff check .

format: ## format code with Ruff in the dev container
	$(DEV) ruff format .

format-check: ## verify formatting without modifying files
	$(DEV) ruff format --check .

typecheck: ## run mypy type checks on the backend
	$(DEV) mypy app

migrate: ## apply all pending migrations
	$(EXEC) alembic upgrade head

migration: ## generate a new migration, e.g. make migration MSG="add cases table"
	$(if $(strip $(MSG)),,$(error MSG is required, e.g. make migration MSG="add cases table"))
	$(EXEC) alembic revision --autogenerate -m "$(MSG)"

shell: ## open a shell in the backend container
	$(COMPOSE) exec backend sh

# --- AI dataset / training / evaluation ------------------------------------

dataset: ## regenerate the synthetic SFT dataset, validate it, emit splits
	python3 scripts/ai/build_dataset.py
	python3 scripts/ai/validate_dataset.py \
		--dataset ai_runtime/data/cybersaarthi_sft.jsonl \
		--emit-splits ai_runtime/data/splits

dataset-validate: ## re-validate an existing dataset without regenerating it
	python3 scripts/ai/validate_dataset.py \
		--dataset ai_runtime/data/cybersaarthi_sft.jsonl \
		--emit-splits ai_runtime/data/splits

train-setup: ## build/refresh the isolated soup training venv (needs uv)
	./scripts/ai/setup_training.sh

train-check: ## verify the local training environment and dry-run the config
	@test -x ai_runtime/soup/.venv/bin/soup || \
		(echo "training venv missing — run 'make train-setup' first" && exit 1)
	ai_runtime/soup/.venv/bin/soup doctor
	@ai_runtime/soup/.venv/bin/python -c "import liger_kernel" 2>/dev/null || \
		(echo "error: liger-kernel is missing but soup.yaml sets use_liger: true." && \
		 echo "       install it: uv pip install --python ai_runtime/soup/.venv/bin/python liger-kernel" && \
		 exit 1)
	@echo "liger-kernel: ok (soup.yaml sets use_liger: true)"
	@PYTHONPATH=scripts/ai ai_runtime/soup/.venv/bin/python -c "import peft_upcast_guard as g; raise SystemExit(0 if g.APPLIED else 'error: peft upcast guard did not install')" \
		&& echo "peft upcast guard: ok (scripts/ai/sitecustomize.py)"
	ai_runtime/soup/.venv/bin/soup --no-telemetry train \
		--config soup.yaml --yes --dry-run

train-pilot: ## run the measured local QLoRA training job (records duration + peak VRAM)
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ./scripts/ai/train_local.sh

train-metrics: ## print the recorded training duration / peak VRAM / exit code
	@test -f ai_runtime/train/metrics.json || \
		(echo "no ai_runtime/train/metrics.json — run 'make train-pilot' first" && exit 1)
	@cat ai_runtime/train/metrics.json

eval: ## score the frozen golden set against the live stack (needs the stack up)
	./scripts/ai/eval_model.sh

eval-final: ## run the combined ten-feature evaluation harness
	./scripts/ai/eval_final.sh

model-compare: ## diff two eval reports: make model-compare A=baseline.json B=tuned.json
	$(if $(strip $(A)),,$(error A= is required, e.g. A=ai_runtime/eval_report.json))
	$(if $(strip $(B)),,$(error B= is required, e.g. B=ai_runtime/eval_report_tuned.json))
	python3 scripts/ai/compare_eval.py "$(A)" "$(B)"

model-rollback: ## point AI_MODEL_PATH back at the original Q4_K_M weights
	@if ! grep -q '^AI_MODEL_PATH=' .env 2>/dev/null; then \
		echo "AI_MODEL_PATH not set in .env — nothing to roll back"; exit 1; \
	fi
	sed -i 's|^AI_MODEL_PATH=.*|AI_MODEL_PATH=Qwen3-8B-Q4_K_M.gguf|' .env
	@grep -n '^AI_MODEL_PATH=' .env
	@echo "restart the model server for this to take effect"
