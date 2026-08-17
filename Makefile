# ============================================
# JARVIS MAKEFILE — quick commands
# Usage: make <command>   (e.g. make dev)
# ============================================

.PHONY: help setup dev test test-coverage verify deploy format lint clean install update

.DEFAULT_GOAL := help

help: ## Show this help message
	@echo "Jarvis — available commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-15s %s\n", $$1, $$2}'

setup: ## First-time setup (creates venv, installs deps, configures .env)
	@./scripts/setup.sh

dev: ## Start the development server
	@./scripts/dev.sh

test: ## Run the test suite
	@./scripts/test.sh

verify: ## Verify credentials actually work (Supabase, R2, Replicate)
	@./scripts/verify.sh

deploy: ## Push to trigger Vercel auto-deploy
	@git push
	@echo "Pushed — GitHub Actions will deploy to Vercel."

format: ## Auto-format code with Black and isort
	@venv/bin/black src/ tests/
	@venv/bin/isort src/ tests/

lint: ## Run flake8 and mypy
	@venv/bin/flake8 src/ tests/
	@venv/bin/mypy src/

clean: ## Remove caches and build artifacts
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name '*.pyc' -delete
	@rm -rf .pytest_cache .mypy_cache htmlcov .coverage

install: ## Install/refresh dependencies
	@venv/bin/pip install -r requirements.txt

update: ## Upgrade all dependencies to latest allowed versions
	@venv/bin/pip install -r requirements.txt --upgrade
