"""Course-graph tests (F009) — synthesis → planner → persist pipeline.

Main-flow tests mock `litellm.acompletion` (the fake content depends on the
prompt) and monkeypatch `app.storage.course_store.put_course` so the pipeline
runs without touching Postgres. One DB-backed test exercises the real persist
node against the local `aitherapy_test` database.
"""

import json
import uuid

import pytest_asyncio

from app.graph.course_graph import build_course_graph
from app.graph.state import new_course_state, new_session_state
from app.storage.course_store import delete_participant, get_course
from app.storage.db import init_db

TEST_URL = "postgresql+asyncpg://aitherapy:aitherapy@localhost:5432/aitherapy_test"

SYNTHESIS_JSON = {
    "n": 3,
    "distillation": "surface: work stress; underneath: feeling unseen by father",
    "carry_forward": "notice when 'small' shows up at work",
    "outcome": "partially-addressed",
}

PLANNER_JSON = {
    "presenting_threads": ["work stress", "relationship with father"],
    "working_pattern": "feeling unseen by authority figures",
    "confirmed_insight": "I disappear so no one can reject me",
    "next_session_intention": "open with the 'small' noticing",
}


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


def _pid() -> str:
    return f"course-{uuid.uuid4().hex[:8]}"


async def _fake_acompletion(**kwargs):
    prompt = kwargs["messages"][0]["content"]
    if "synthesis" in prompt:
        return _FakeCompletion(json.dumps(SYNTHESIS_JSON))
    return _FakeCompletion(json.dumps(PLANNER_JSON))


def _input_state(session_number: int = 3):
    course = new_course_state(
        session_number=2,
        course_phase="foundation",
        session_summaries=[
            {
                "n": 1,
                "distillation": "session one",
                "carry_forward": "carry one",
                "outcome": "addressed",
            },
            {
                "n": 2,
                "distillation": "session two",
                "carry_forward": "carry two",
                "outcome": "open",
            },
        ],
        next_session_intention="",
    )
    final_session_state = new_session_state(
        phase="closing",
        primary_thread="work stress",
        key_words_used=["small", "invisible"],
    )
    return {
        "participant_id": _pid(),
        "session_number": session_number,
        "transcript": [
            "patient: work is too much",
            "therapist: tell me more about that",
            "patient: my father never listens to me",
        ],
        "final_session_state": final_session_state,
        "course": course,
    }


async def test_graph_invoke_updates_course_and_calls_persist(monkeypatch):
    monkeypatch.setattr("litellm.acompletion", _fake_acompletion)
    calls = []

    async def fake_put_course(participant_id, state, database_url=None):
        calls.append((participant_id, state, database_url))

    monkeypatch.setattr("app.graph.course_graph.put_course", fake_put_course)

    graph = build_course_graph()
    initial = _input_state(session_number=3)
    pid = initial["participant_id"]
    result = await graph.ainvoke(initial)

    course = result["course"]

    # session_number set from state, not the model
    assert course["session_number"] == 3
    # prior summaries preserved + new one appended (n=3)
    assert [s["n"] for s in course["session_summaries"]] == [1, 2, 3]
    assert course["session_summaries"][-1] == SYNTHESIS_JSON
    # course_phase computed by the predicate (confirmed insight -> termination)
    assert course["course_phase"] == "termination"
    # next_session_intention updated
    assert course["next_session_intention"] == PLANNER_JSON["next_session_intention"]
    # formulation updated: threads + working_pattern + confirmed insight appended
    form = course["formulation"]
    assert form["presenting_threads"] == PLANNER_JSON["presenting_threads"]
    assert form["working_pattern"] == PLANNER_JSON["working_pattern"]
    assert form["confirmed_insights"] == [PLANNER_JSON["confirmed_insight"]]

    # persist node called with participant_id + updated course
    assert len(calls) == 1
    call_pid, call_state, call_url = calls[0]
    assert call_pid == pid
    assert call_state == course
    assert call_url is None


async def test_graph_planner_appends_insight_without_duplicates(monkeypatch):
    planner = dict(PLANNER_JSON)
    planner["confirmed_insight"] = "already present insight"

    def fake_acompletion(**kwargs):
        prompt = kwargs["messages"][0]["content"]
        if "synthesis" in prompt:
            return _FakeCompletion(json.dumps(SYNTHESIS_JSON))
        return _FakeCompletion(json.dumps(planner))

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)
    calls = []

    async def fake_put_course(pid, state, database_url=None):
        calls.append((pid, state))

    monkeypatch.setattr("app.graph.course_graph.put_course", fake_put_course)

    initial = _input_state(session_number=3)
    initial["course"]["formulation"]["confirmed_insights"] = ["already present insight"]

    result = await build_course_graph().ainvoke(initial)
    assert result["course"]["formulation"]["confirmed_insights"] == ["already present insight"]


async def test_graph_model_failure_degrades_without_crash(monkeypatch):
    async def failing_acompletion(**kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("litellm.acompletion", failing_acompletion)
    calls = []

    async def fake_put_course(pid, state, database_url=None):
        calls.append((pid, state))

    monkeypatch.setattr("app.graph.course_graph.put_course", fake_put_course)

    initial = _input_state(session_number=3)
    prior = initial["course"]
    result = await build_course_graph().ainvoke(initial)

    course = result["course"]
    # session_number still set from state
    assert course["session_number"] == 3
    # prior summaries preserved; the degraded minimal summary (outcome "open")
    # is appended by the deterministic planner code (contract §4.2 step 2)
    assert course["session_summaries"][:2] == prior["session_summaries"]
    assert course["session_summaries"][-1] == {
        "n": 3,
        "distillation": "",
        "carry_forward": "",
        "outcome": "open",
    }
    # formulation carried forward unchanged
    assert course["formulation"] == prior["formulation"]
    assert len(calls) == 1


# --- DB-backed persist test ---


@pytest_asyncio.fixture(scope="module")
async def _db():
    await init_db(TEST_URL)
    yield


async def test_graph_persists_course_to_db(monkeypatch, _db):
    async def fake_acompletion(**kwargs):
        prompt = kwargs["messages"][0]["content"]
        if "synthesis" in prompt:
            return _FakeCompletion(json.dumps(SYNTHESIS_JSON))
        return _FakeCompletion(json.dumps(PLANNER_JSON))

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)

    pid = _pid()
    initial = _input_state(session_number=3)
    initial["participant_id"] = pid

    graph = build_course_graph(TEST_URL)
    result = await graph.ainvoke(initial)

    stored = await get_course(pid, TEST_URL)
    assert stored is not None
    assert stored == result["course"]
    assert stored["session_number"] == 3

    await delete_participant(pid, TEST_URL)
    assert await get_course(pid, TEST_URL) is None
