"""FastAPI server (F015) — one process hosts the control-surface page, the
``/ws`` Pipecat voice endpoint, and the graph invocations (impl §7.2).

No REST /api/v1/ and no text-chat mode: the visual surface is crisis resources
+ session controls + memory controls; voice is the only conversational input.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config.settings import settings
from app.graph.course_graph import build_course_graph
from app.graph.state import SessionState, make_thread_id
from app.graph.turn_graph import build_turn_graph
from app.logger import logger
from app.storage.course_store import delete_participant
from app.storage.db import init_db, make_checkpointer
from app.voice.pipeline import GraphInvoker, build_pipeline

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    logger.info("database ready")
    yield


app = FastAPI(title="ai-therapist", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def control_surface() -> str:
    """The minimal control-surface page (crisis resources + session + memory)."""
    page = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return page.replace("{{HELPLINE}}", settings.crisis_helpline_number).replace(
        "{{WEBSITE}}", settings.crisis_website or ""
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "environment": settings.environment}


@app.post("/participant/{participant_id}/delete")
async def delete_participant_history(participant_id: str) -> dict:
    """Memory control (§5.5): participant deletes session history — cascades
    course rows + checkpointer threads."""
    await delete_participant(participant_id)
    logger.info("deleted history for participant %s", participant_id)
    return {"status": "deleted", "participant_id": participant_id}


def make_graph_invoker(participant_id: str, session_number: int) -> GraphInvoker:
    """The server's turn-graph invoker: per-exchange graph invocation with the
    PostgresSaver checkpointer, seeded from the stored course state.

    Returns an async (thread_id, state) -> updated-state callable. The thread_id
    argument is ignored (we derive it from the participant + session) so the
    checkpointer context stays inside one invocation.
    """

    async def invoke(_thread_id: str, state: SessionState) -> dict:
        thread_id = make_thread_id(participant_id, session_number)
        async with make_checkpointer() as saver:
            await saver.setup()
            turn_graph = build_turn_graph(checkpointer=saver)
            result = await turn_graph.ainvoke(
                state, config={"configurable": {"thread_id": thread_id}}
            )
        return result

    return invoke


def make_course_closer(participant_id: str, session_number: int):
    """Post-session closer (§7.4): fire the course graph async with the final
    session state — zero turn latency."""

    async def close(final_state: SessionState, transcript: list[str]) -> None:
        course_graph = build_course_graph()
        try:
            await course_graph.ainvoke(
                {
                    "participant_id": participant_id,
                    "session_number": session_number,
                    "transcript": transcript,
                    "final_session_state": final_state,
                    "course": await _load_or_new_course(participant_id),
                }
            )
        except Exception as exc:  # post-session path must not crash
            logger.warning("course close failed for %s: %s", participant_id, exc)

    return close


async def _load_or_new_course(participant_id: str) -> dict:
    from app.graph.state import new_course_state
    from app.storage.course_store import get_course

    course = await get_course(participant_id)
    return course or new_course_state()


@app.websocket("/ws")
async def voice_endpoint(websocket: WebSocket) -> None:
    """The Pipecat voice endpoint (impl §7.7) — voice is the only conversational
    input. V0: a single anonymous session (participant "local", session 1)."""
    participant_id = "local"
    session_number = 1
    invoker = make_graph_invoker(participant_id, session_number)
    closer = make_course_closer(participant_id, session_number)
    pipeline = build_pipeline(
        websocket,
        invoker,
        make_thread_id(participant_id, session_number),
        on_close=closer,
    )
    logger.info("voice session start: %s", participant_id)
    try:
        await pipeline.run(handle_sigint=False)
    except Exception as exc:  # pragma: no cover - runtime surface
        logger.warning("voice session error: %s", exc)
