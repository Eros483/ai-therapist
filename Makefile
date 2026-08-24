POSTGRES_CONTAINER := ai-therapy-postgres
POSTGRES_IMAGE := postgres:16

## setup: uv sync backend deps + Postgres up
setup:
	cd backend && uv sync
	$(MAKE) docker-up

## dev: FastAPI dev server (control surface + /ws voice endpoint)
dev:
	cd backend && uv run uvicorn app.server.main:app --reload --port 8000

## test: pytest
test:
	cd backend && uv run pytest

## style: ruff format + check (includes import sorting)
style:
	cd backend && uv run ruff format . && uv run ruff check --fix .

## build: placeholder/reserved
build:
	@echo "build reserved — no packaging target yet"

## clean: removes caches, __pycache__, build artifacts
clean:
	find . \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -type d -prune -exec rm -rf {} +
	find . -name '*.pyc' -delete
	rm -rf backend/.venv backend/dist backend/build

## docker-up: start Postgres container if not running (idempotent)
docker-up:
	@if docker ps --format '{{.Names}}' | grep -q '^$(POSTGRES_CONTAINER)$$'; then \
		echo "postgres already running"; \
	elif docker ps -a --format '{{.Names}}' | grep -q '^$(POSTGRES_CONTAINER)$$'; then \
		docker start $(POSTGRES_CONTAINER); \
	else \
		docker run -d --name $(POSTGRES_CONTAINER) \
			-e POSTGRES_USER=aitherapy \
			-e POSTGRES_PASSWORD=aitherapy \
			-e POSTGRES_DB=aitherapy \
			-p 5432:5432 \
			$(POSTGRES_IMAGE); \
	fi

## docker-down: stop Postgres container
docker-down:
	@if docker ps --format '{{.Names}}' | grep -q '^$(POSTGRES_CONTAINER)$$'; then \
		docker stop $(POSTGRES_CONTAINER); \
	fi

.PHONY: setup dev test style build clean docker-up docker-down