# ai-therapist — backend

Voice-first, model-agnostic AI therapy companion (research prototype). See
`../docs/implementation.md` for the authoritative build spec and
`../docs/methodology.md` for the discipline.

## Environment

Copy `.env.example` (repo root) to `.env` and fill in keys. Every model,
provider, and threshold is env-swappable — nothing is hardcoded.

## Commands (run from repo root via Makefile)

```bash
make setup   # uv sync backend deps + Postgres container up
make dev     # FastAPI dev server (control surface + /ws voice endpoint)
make test    # pytest
make style   # ruff format + check
make build   # reserved
make clean   # caches, .venv, build artifacts
```