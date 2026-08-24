# ai-therapist

Voice-first, model-agnostic AI therapy companion — research prototype.
Authoritative specs: `docs/methodology.md` (why), `docs/implementation.md` (how),
`docs/research.md` (grounding). Design doc: `docs/features.json`.

## Quick start

```bash
make setup    # uv sync backend deps + Postgres container up
make dev      # FastAPI dev server (control surface + /ws voice endpoint)
make test     # pytest
make style    # ruff format + check
```

## Environment / API keys

Copy `.env.example` to `.env` and fill in the values. **Never commit `.env`.**

| Key | Where to get it |
|---|---|
| `MAIN_MODEL`, `EXTRACTION_MODEL`, `SAFETY_MODEL` | LiteLLM model strings — https://docs.litellm.ai/docs/providers |
| `GEMINI_API_KEY` | https://aistudio.google.com/app/apikey |
| `GROQ_API_KEY` | https://console.groq.com/keys |
| `SARVAM_API_KEY` | https://dashboard.sarvam.ai (Saaras STT, Bulbul TTS) |
| `RUMIK_API_KEY` | https://rumik.ai (Silk — Mulberry/Muga TTS) — optional, no free tier |
| `SECRET_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `DATABASE_URL` | Provided — matches the Postgres container from `make setup` |

## Architecture

```mermaid
flowchart TD
    subgraph CS["CONTROL SURFACE (static page, FastAPI)"]
        CS1["crisis resources"]
        CS2["session controls"]
        CS3["memory controls"]
    end

    subgraph VL["VOICE LOOP (Pipecat)"]
        VL1["mic → streaming STT (Sarvam)"]
        VL2["VAD / endpointing · timers"]
        VL3["streaming TTS (Rumik / Sarvam)"]
        VL4["barge-in → cancel playback"]
    end

    subgraph TG["TURN GRAPH (LangGraph)"]
        TG1["L1 safety lexicon (pure code, <1ms)"]
        TG2{"hit?"}
        TG3["parallel: L2 safety gate · register · affect · state extraction"]
        TG4["phase agent [session.phase] — landing · opening · deepening · meaning · closing (5 nodes, scoped prompt + techniques)"]
        TG5["CRISIS NODE"]
        TG6["emergency contact (minimal metadata)"]
    end

    subgraph CG["COURSE GRAPH (LangGraph, async post-session)"]
        CG1["synthesis node"]
        CG2["course planner node"]
        CG3["course store — 8-session arc: Foundation → Exploration → Working → Termination"]
    end

    subgraph DB["POSTGRES"]
        DB1["PostgresSaver checkpointer"]
        DB2["course store (Fernet at rest)"]
    end

    CS <--> VL

    VL -->|"patient utterance (transcript)"| TG1
    TG1 --> TG2
    TG2 -->|"hit"| TG5
    TG2 -->|"miss"| TG3
    TG3 -->|"L2-safe ∧ extraction done"| TG4
    TG4 -->|"response tokens"| VL
    TG5 --> TG6

    VL -->|"session close"| CG1
    CG1 --> CG2
    CG2 --> CG3

    CG3 --> DB2
    TG -.->|"thread_id checkpointer"| DB1
```