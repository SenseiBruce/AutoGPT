.PHONY: help setup up down test lint format typecheck check-env

help:
	@echo "AutoGPT local commands"
	@echo "  make setup      Copy env example files"
	@echo "  make up         Start the full stack with docker compose"
	@echo "  make down       Stop the stack"
	@echo "  make test       Run the root pytest suite (no Docker required)"
	@echo "  make lint       Run Ruff on Python sources"
	@echo "  make check-env  Verify .env.example covers required vars"
	@echo "  make format     Format Python sources with Ruff"

setup:
	cp -n autogpt_platform/.env.example autogpt_platform/.env || true
	cp -n autogpt_platform/backend/.env.example autogpt_platform/backend/.env || true
	cp -n autogpt_platform/frontend/.env.example autogpt_platform/frontend/.env || true

up: setup
	docker compose up --build -d

down:
	docker compose down

test:
	python3 -m pytest tests

check-env:
	python3 scripts/check_env_examples.py

lint: check-env
	python3 -m ruff check autogpt_platform/backend/backend tests

format:
	python3 -m ruff format autogpt_platform/backend/backend tests
