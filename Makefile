COMPOSE := docker compose
EXEC := $(COMPOSE) exec -T backend
# Development/verification commands run in a dedicated `backend-dev` container
# (build target `dev`) that contains pytest/ruff/mypy on top of the runtime,
# keeping the production `backend` image lean.
DEV := $(COMPOSE) run --rm -T backend-dev

.PHONY: help up down down-v build logs ps seed test test-unit lint format format-check typecheck \
        migrate migration shell

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
