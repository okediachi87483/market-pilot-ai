# Convenience wrapper around the commands in README.md. Requires `make`
# (not preinstalled on Windows) — every target here has a raw-command
# equivalent documented in the README, so `make` is optional, not required.

.PHONY: up down build logs \
        api-install api-test api-lint api-format api-typecheck \
        web-install web-test web-lint web-typecheck web-build

up: ## Start the full stack
	docker compose up --build

down: ## Stop the full stack
	docker compose down

build: ## Build all images without starting them
	docker compose build

logs: ## Follow logs for all services
	docker compose logs -f

api-install: ## Install API dependencies into apps/api/.venv
	cd apps/api && python -m venv .venv && . .venv/Scripts/activate && python -m pip install -e ".[dev]"

api-test: ## Run backend tests
	cd apps/api && . .venv/Scripts/activate && python -m pytest -v

api-lint: ## Lint the backend
	cd apps/api && . .venv/Scripts/activate && python -m ruff check .

api-format: ## Format the backend
	cd apps/api && . .venv/Scripts/activate && python -m ruff format .

api-typecheck: ## Type-check the backend
	cd apps/api && . .venv/Scripts/activate && python -m mypy app

web-install: ## Install frontend dependencies
	cd apps/web && npm install

web-test: ## Run frontend tests
	cd apps/web && npm test

web-lint: ## Lint the frontend
	cd apps/web && npm run lint

web-typecheck: ## Type-check the frontend
	cd apps/web && npm run typecheck

web-build: ## Production build the frontend
	cd apps/web && npm run build
