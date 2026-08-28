COMPOSE := docker compose
EXEC := $(COMPOSE) exec -T backend

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

test: ## run the full test suite (unit, api, integration) in the backend container
	$(EXEC) pytest

test-unit: ## run only tests that do not need infrastructure
	$(EXEC) pytest -m "not integration"

lint: ## run Ruff linter in the backend container
	$(EXEC) ruff check .

format: ## format code with Ruff
	$(EXEC) ruff format .

format-check: ## verify formatting without modifying files
	$(EXEC) ruff format --check .

typecheck: ## run mypy type checks on the backend
	$(EXEC) mypy app

migrate: ## apply all pending migrations
	$(EXEC) alembic upgrade head

migration: ## generate a new migration, e.g. make migration MSG="add cases table"
	$(if $(strip $(MSG)),,$(error MSG is required, e.g. make migration MSG="add cases table"))
	$(EXEC) alembic revision --autogenerate -m "$(MSG)"

shell: ## open a shell in the backend container
	$(COMPOSE) exec backend sh