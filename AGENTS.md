# AGENT.md

**Authoritative documentation: `docs/methodology.md` (the *why*), `docs/implementation.md` (the *how*), `docs/research.md` (research grounding). These precede everything in this file — where they conflict with the conventions below, the docs win.** Check them before starting any task.

If a design document is missing for a task that warrants one, flag it before proceeding.

## Project Overview

A research project (not a product headed to users) building an AI-powered therapy companion that simulates the therapeutic experience — voice-first, model-agnostic, targeted at urban Indian users who code-switch between English, Hinglish, and Hindi. The system runs an 8-session course arc (Foundation → Exploration → Working → Termination) over 45-minute session arcs, orchestrated as a multi-agent LangGraph system with a Pipecat voice loop, five phase-specialized therapist agents, and shared session/course state. Deliverable: a demonstrable system plus an evaluation of therapeutic fidelity.

## Development Philosophy

- TDD first: write the test, then the implementation. Never skip.
- Tests mirror the structure of the module they test
- No function ships without a test
- **Graph nodes are pure functions of state** (`SessionState`, `CourseState`) — deterministic, auditable, testable without HTTP. This replaces the "API routes are thin — logic lives in core/" rule.
- Explicit over clever — readable code beats smart code
- If it isn't runnable via `make`, it isn't done

## Tech Stack

Per `docs/implementation.md` §7.1:

- **Orchestration**: `langgraph` + `langgraph-checkpoint-postgres`
- **Voice loop**: `pipecat` (websocket transport) + silero VAD
- **LLM access**: `litellm` — one interface over any provider. **Model-agnosticism is a hard rule: no provider/model is ever hardcoded; everything routes through LiteLLM + config.**
- **STT / TTS**: Sarvam (`sarvamai`), Rumik — always behind `STTProvider` / `TTSProvider` protocols
- **Backend**: FastAPI (single process: static control-surface page + `/ws` voice endpoint)
- **Database**: PostgreSQL (from day one) + SQLAlchemy 2.0 (async) + `psycopg`; Fernet app-layer encryption at rest
- **Config**: `pydantic-settings` in `app/config/` — every model, provider, and threshold env-swappable
- **No frontend framework** — minimal static control-surface page served by FastAPI (crisis resources + session controls + memory controls; voice is the only conversational input)
- Package Manager: `uv` · Tests: `pytest` · Build/Task Runner: **Make**

## Key Commands

All commands MUST be runnable via `make <target>` from the project root. Calling tools directly is for the Makefile's internal use only — humans and agents invoke `make`.

```bash
make setup                       # uv sync backend deps + Postgres up
make dev                         # FastAPI dev server (control surface + /ws voice endpoint)
make test                        # pytest
make style                       # ruff format + check (includes import sorting)
make build                       # placeholder/reserved — see Makefile
make clean                       # removes caches, __pycache__, build artifacts
```

The Makefile ships with the first scaffold; targets must match the stack above. Add targets as the project needs them, never remove the required set.

## Directory Structure

Per `docs/implementation.md` §7.10:

```
ai-therapist/
├── backend/
│   ├── app/
│   │   ├── config/              # pydantic-settings: models, providers, thresholds
│   │   ├── graph/
│   │   │   ├── state.py         # SessionState, CourseState TypedDicts
│   │   │   ├── nodes/
│   │   │   │   ├── safety.py    # L1 lexicon + L2 small-model gate
│   │   │   │   ├── register.py  # register + CMI
│   │   │   │   ├── affect.py    # audio affect
│   │   │   │   ├── extraction.py# state extractor + next_technique
│   │   │   │   ├── phases/      # landing.py opening.py deepening.py meaning.py closing.py
│   │   │   │   ├── crisis.py    # crisis protocol node
│   │   │   │   └── course/      # synthesis.py planner.py
│   │   │   ├── turn_graph.py    # per-turn graph assembly
│   │   │   └── course_graph.py  # post-session graph assembly
│   │   ├── voice/
│   │   │   ├── pipeline.py      # Pipecat pipeline assembly
│   │   │   ├── services/        # sarvam_stt.py rumik_tts.py bulbul_tts.py
│   │   │   ├── interruptions.py # barge-in capture → interruption_events
│   │   │   └── timers.py        # turn-end VAD (phase-dependent) vs 90s check-in
│   │   ├── storage/
│   │   │   ├── db.py            # async engine, checkpointer setup
│   │   │   ├── crypto.py        # Fernet
│   │   │   └── course_store.py  # CourseState persistence
│   │   └── server/
│   │       ├── main.py          # FastAPI: static page, /ws endpoint
│   │       └── static/          # minimal control-surface page
│   └── tests/                   # nodes are pure functions of state — test them directly
├── docs/
│   ├── methodology.md            # the discipline — authoritative
│   ├── implementation.md         # the system — authoritative
│   ├── research.md               # research grounding
│   └── features.json             # canonical feature tracker — always kept up to date
├── Makefile                     # single entry point for setup/dev/test/style/build
├── .env.example                 # committed, no secrets
├── .gitignore
├── README.md
└── AGENT.md
```

## Conventions

### Makefile (required)
- A root-level `Makefile` is **mandatory** and is the canonical control surface for the project. No setup, run, test, style, or build step should exist only as a "remember to run this manually" instruction — it belongs in the Makefile.
- Required targets: `setup`, `dev`, `test`, `style`, `build`, `clean`. Add more (`migrate`, `seed`, `docker-up`, etc.) as needed, never remove the required set.
- Each target is a thin wrapper into `backend/` calling the underlying tool (`uv`, `pytest`, `ruff`) — the Makefile is an orchestration layer, not a place for business logic.
- `make setup` must be idempotent and safe to re-run.
- Every target has a `## short description` comment on the same line.

### Python (Backend)
- **Package manager: `uv`** — never `pip` directly.
- Formatter/linter: `ruff` (includes import sorting). Naming: snake_case everywhere.
- **Model-agnosticism (hard rule):** never hardcode an LLM/STT/TTS provider or model name in code — always via LiteLLM + `app/config/` settings. Providers are eval-time swappable, never defaults.
- **Voice providers behind protocols:** STT/TTS always through `STTProvider` / `TTSProvider` async streaming protocols (`app/voice/services/`) — never called directly.
- **Graph nodes are pure functions of state** — no I/O inside phase/safety/register/extraction nodes beyond their declared model calls; deterministic given `SessionState`/`CourseState`.
- Env vars are accessed exclusively via the settings object in `app/config/` — never `os.environ` directly.

Config is a Pydantic `BaseSettings` in `app/config/`, instantiated once as `settings`:

```
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Central management for settings and configurations."""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    port: int = 8000
    database_url: str = "postgresql+asyncpg://localhost:5432/aitherapy"
    environment: str = "development"
    secret_key: str

    # Project-specific — every model, provider, threshold lives here (§7.11):
    main_model: str                      # via LiteLLM
    extraction_model: str                # small, fast
    safety_model: str                    # L2 zero-shot crisis classifier
    stt_provider: str = "sarvam"         # "sarvam" | "rumik" | ...
    tts_provider: str = "rumik"          # "rumik" | "sarvam" | ...
    session_minutes: int = 45
    course_sessions: int = 8
    turn_end_vad_thresholds: dict = {"landing": 1.5, "deepening": 3.5}
    silence_checkin_seconds: int = 90
    # crisis resource numbers, etc.

settings = Settings()
```

`pydantic-settings` maps `UPPER_CASE` env vars to lowercase fields; fields without defaults raise at startup if missing. No `load_dotenv()` or `os.environ` needed.

All logging uses a project logger (no `print`, no stdlib `logging` directly). Define a shared logger in `app/` (e.g. `app/logger.py` imported as `logger`) mirroring the template pattern — file logs under `logs/` plus console.

### Frontend
- **There is no frontend framework.** The visual surface is a minimal static page served by FastAPI (crisis resources + session controls + memory controls). Voice is the only conversational input — no text-chat mode, ever.

### General
- Commits: conventional commits format (feat:, fix:, chore:, docs:, test:, refactor:)
- Env vars: never committed, always have a `.env.example` with keys but no values
- **All setup, dev, test, style, and build steps run through the root `Makefile`.**
- No REST `/api/v1/` mandate — the docs define no REST API, only the minimal control surface and the `/ws` voice endpoint.

## Deployment

**Research prototype — no deployment target.** If deployment is ever pursued, the default pattern is: ML/model work on Hugging Face Spaces, backend on Render free tier. **Go-portability does not apply** — this backend is not HTTP plumbing; it runs LangGraph, Pipecat, and voice dependencies.

## Multi-Agent Workflow

When `docs/features.json` contains 3 or more independent features, the Build agent parallelizes implementation using subagents.

### Flow

1. **Plan**: Identify independent features from `features.json`. Features touching the same files are dependent and batched sequentially.
2. **Build**: Spawn up to 3 builder subagents at a time via the Task tool.
3. **E2E** (if applicable): Playwright-tester covers the visual control surface only — voice conversation is not browser-testable.
4. **Review**: Spawn the ponytail-reviewer to audit the combined diff for over-engineering.
5. **Verify**: Run `make test && make style`.

If fewer than 3 independent features exist, implement directly without subagents.

### Subagents

Defined in `~/.config/opencode/agents/`. All use `model: opencode-go/deepseek-v4-flash`.

| Agent | File | Purpose | Permissions |
|-------|------|---------|-------------|
| builder | `builder.md` | TDD one feature, writes tests then implementation | edit: allow, bash: allow, task: { \*: deny, playwright-tester: allow } |
| playwright-tester | `playwright-tester.md` | E2E browser tests via playwright-cli | edit: deny, bash: allow |
| ponytail-reviewer | `ponytail-reviewer.md` | Bloat/over-engineering audit on combined diff | edit: deny, bash: allow |

### Edge cases

- **Dependent features** (same files): Sequenced within the same builder subagent.
- **Ponytail finds issues**: Main agent decides fix-now vs file-as-debt.
- **No E2E tests defined**: Playwright-tester step is skipped.

## Agent Guidelines

- **Check `docs/methodology.md` and `docs/implementation.md` before starting any task — they are authoritative and precede these conventions.**
- Always run `make style` before considering any code done
- Always use snake_case for Python files/variables/functions/DB columns
- Never modify files in `/docs` unless explicitly asked
- Always run `make test` after making changes — if tests fail, fix before moving on
- **Never hardcode a model or provider** — everything through LiteLLM + `app/config/` settings
- Never use `os.environ` directly — always the settings object
- Never use `print` or stdlib `logging` — always the project logger
- Always use `uv` — never invoke `pip` directly
- Always update `docs/features.json` after completing any task
- Any new setup/run/test/style/build step must be added as a Makefile target, not just documented in prose
- **Do not reintroduce banned designs** (documented in methodology/implementation): no serial critic/self-refinement loop before response (voice latency), no text-conversation mode, no product-y scope creep — this is a research prototype with fixed-session-course framing
- If something feels out of scope or conflicts with the docs, flag it rather than silently doing it
- If >=3 independent features exist in docs/features.json, spawn builder subagents per the Multi-Agent Workflow

`docs/features.json`

```json
{
  "project": "ai-therapist",
  "last_updated": "YYYY-MM-DD",
  "summary": {
    "total": 0,
    "completed": 0,
    "in_progress": 0,
    "planned": 0,
    "tests_passing": 0,
    "tests_failing": 0,
    "tests_missing": 0
  },
  "features": [
    {
      "id": "F001",
      "name": "[Feature Name]",
      "description": "[What it does and why it exists]",
      "status": "planned",
      "priority": "high",
      "module": "backend/app/graph/nodes",
      "design_doc": "docs/implementation.md",
      "tests": {
        "status": "missing",
        "files": [],
        "notes": ""
      },
      "subtasks": [
        {
          "id": "F001-1",
          "name": "[Subtask name]",
          "status": "planned"
        }
      ],
      "notes": "",
      "added": "YYYY-MM-DD",
      "completed": null
    }
  ]
}
```

## Project-Specific Notes

- **External APIs / keys** (all in `.env`, `.env.example` has keys with no values):
  - LLM providers via LiteLLM (`MAIN_MODEL`, `EXTRACTION_MODEL`, `SAFETY_MODEL`, provider API keys)
  - Sarvam (`SARVAM_API_KEY`) — Saaras STT, Bulbul TTS
  - Rumik (`RUMIK_API_KEY`) — Mulberry/Muga TTS (expects Hindi in Devanagari — drives TTS-boundary script normalization, impl §2.2)
- **Postgres**: `DATABASE_URL` in `.env` (asyncpg driver); LangGraph `PostgresSaver` checkpointer; `make setup` brings it up.
- **Non-standard setup**: Pipecat may require system audio dependencies (check its docs); voice eval (impl §8.3) measures code-mixing accuracy, romanization, latency, prosody control, cancelable streaming — never select a provider by default.
- **Files never to touch**: `docs/` (authoritative), `.env`.
- **Known gotchas**:
  - Two distinct timers, never conflated: phase-dependent turn-end VAD threshold (impl §7.7) vs the 90-second silence check-in.
  - Safety gate is a parallel small-model branch (impl §7.8, 3 layers: L1 lexicon, L2 zero-shot, L3 deferred fine-tuned) — crisis routing must never wait on or run through the main therapist model.
  - Barge-in/interruption is owned by the voice layer (Pipecat), not the graph; events feed the *next* turn's `SessionState.interruption_events`.
  - Two serial LLM hops per turn (extraction → phase agent) is accepted by design — extraction must use the small/fast model.
  - No serial critic/self-refinement loop before response — rejected on voice-latency grounds.
