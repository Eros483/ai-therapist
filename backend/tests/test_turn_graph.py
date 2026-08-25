"""Tests for F010 — turn graph assembly (impl §7.3).

The turn graph is the per-exchange LangGraph: START → safety_L1_lexicon →
hit → crisis path (crisis_node → notify → END) OR miss → parallel [L2 safety ‖
register ‖ affect ‖ extraction] → join → L2 gate → phase_agent[session.phase]
(conditional edge, 5 nodes) → END.

The load-bearing property (§7.3, §7.8): the phase agent NEVER runs on a crisis
utterance. L1 hit routes immediately; L2 hit gates the join.

Routing functions are pure and unit-tested directly. The assembled graph is
integration-tested with a prompt-content-faked `litellm.acompletion` (no live
provider). Checkpointer integration targets the local `aitherapy_test` Postgres,
mirroring test_course_store.
"""

import json
import uuid

import pytest_asyncio

from app.graph.nodes.crisis import notify_emergency_contact as _real_notify
from app.graph.state import PHASES, make_thread_id, new_session_state
from app.graph.turn_graph import (
    build_turn_graph,
    phase_paths,
    route_from_join,
    route_from_l1,
)
from app.storage.course_store import delete_participant
from app.storage.db import init_db, make_checkpointer


# emergency_notification is not a SessionState key, so langgraph drops the notify
# node's return value from the final state. To prove the notify node is on the
# crisis path we spy on it instead, recording the state it saw.
def _spy_notify(monkeypatch, calls: list) -> None:
    def spy(state):
        calls.append(state)
        return _real_notify(state)

    monkeypatch.setattr("app.graph.turn_graph.notify_emergency_contact", spy)


TEST_URL = "postgresql+asyncpg://aitherapy:aitherapy@localhost:5432/aitherapy_test"
CHECKPOINTER_URL = "postgresql://aitherapy:aitherapy@localhost:5432/aitherapy_test"

PARALLEL_NODES = [
    "safety_l2_small_model",
    "register_classifier",
    "affect_from_audio",
    "state_extractor",
]


# --- routing functions (pure) ---


def test_route_from_l1_hit_routes_to_crisis():
    assert route_from_l1({"crisis_verdict": {"crisis": True, "category": "suicide"}}) == [
        "crisis_node"
    ]


def test_route_from_l1_miss_fans_out_to_four_parallel_nodes():
    assert route_from_l1({"crisis_verdict": {"crisis": False}}) == PARALLEL_NODES
    # no verdict yet (e.g. benign L1 gate) → miss
    assert route_from_l1({}) == PARALLEL_NODES


def test_route_from_join_l2_crisis_routes_to_crisis_node():
    assert route_from_join({"crisis_verdict": {"crisis": True}}) == "crisis_node"


def test_route_from_join_selects_phase_by_state():
    assert (
        route_from_join({"crisis_verdict": {"crisis": False}, "phase": "deepening"}) == "deepening"
    )
    # unknown phase defaults to landing
    assert route_from_join({"crisis_verdict": {"crisis": False}}) == "landing"


def test_phase_paths_covers_all_phases_and_crisis():
    assert set(phase_paths) == set(PHASES) | {"crisis_node"}
    for phase in PHASES:
        assert phase_paths[phase] == phase
    assert phase_paths["crisis_node"] == "crisis_node"


# --- integration: prompt-content-faked litellm.acompletion ---


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


def _completion(content: str) -> _FakeCompletion:
    return _FakeCompletion(content)


def _non_crisis_verdict() -> str:
    return json.dumps({"crisis": False, "category": "none", "confidence": 0.1})


def _crisis_verdict() -> str:
    return json.dumps({"crisis": True, "category": "suicide", "confidence": 0.9})


def _extraction_diff() -> str:
    return json.dumps({"primary_thread": "work", "next_technique": "reflection"})


def _make_fake_by_prompt(phase_sentinel: str = "normal phase response"):
    """Fake acompletion whose content depends on the prompt's sentinel blocks."""

    async def fake_acompletion(**kwargs):
        prompt = kwargs["messages"][0]["content"]
        if "crisis-safety classifier" in prompt:
            return _completion(_non_crisis_verdict())
        if "[PHASE INSTRUCTION]" in prompt:
            return _completion(phase_sentinel)
        if "crisis-response voice" in prompt:
            return _completion("crisis response")
        if "state-tracker" in prompt:
            return _completion(_extraction_diff())
        raise AssertionError(f"unexpected prompt: {prompt[:120]!r}")

    return fake_acompletion


async def test_benign_utterance_runs_phase_agent_and_never_crisis(monkeypatch):
    monkeypatch.setattr("litellm.acompletion", _make_fake_by_prompt())
    graph = build_turn_graph()

    result = await graph.ainvoke(
        new_session_state(patient_utterance="I had a rough day at work"),
        config={"configurable": {"thread_id": make_thread_id("t-benign", 1)}},
    )

    assert result["response"] == "normal phase response"
    # crisis path never taken — no notification, no crisis surface
    assert "emergency_notification" not in result
    assert "crisis_surface" not in result
    # the four parallel nodes all ran and contributed their channels
    assert result["exchange_count"] == 1
    assert result["register"]["register"] == 0
    assert result["audio_affect"]["arousal_trajectory"] == "steady"
    assert result["crisis_verdict"]["crisis"] is False
    assert result["next_technique"] == "reflection"


async def test_l1_hit_routes_to_crisis_and_phase_agent_never_runs(monkeypatch):
    async def fake_acompletion(**kwargs):
        prompt = kwargs["messages"][0]["content"]
        if "[PHASE INSTRUCTION]" in prompt:
            raise AssertionError("phase agent must never run on a crisis utterance")
        if "crisis-response voice" in prompt:
            return _completion("crisis response")
        raise AssertionError(f"unexpected prompt on L1-hit path: {prompt[:120]!r}")

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)
    notify_calls: list = []
    _spy_notify(monkeypatch, notify_calls)
    graph = build_turn_graph()

    result = await graph.ainvoke(
        new_session_state(patient_utterance="main khudkhushi kar lunga"),
        config={"configurable": {"thread_id": make_thread_id("t-l1", 1)}},
    )

    assert result["response"] == "crisis response"
    # L1 category rode through the gate's verdict into the notification
    # (crisis_surface is a crisis_node output, not a SessionState key, so
    # langgraph drops it from the final state — it is rendered server-side)
    assert result["crisis_verdict"] == {
        "crisis": True,
        "category": "suicide",
        "confidence": 1.0,
    }
    assert (
        notify_calls and (notify_calls[0].get("crisis_verdict") or {}).get("category") == "suicide"
    )


async def test_l2_crisis_gates_join_and_phase_agent_never_runs(monkeypatch):
    async def fake_acompletion(**kwargs):
        prompt = kwargs["messages"][0]["content"]
        if "crisis-safety classifier" in prompt:
            return _completion(_crisis_verdict())
        if "state-tracker" in prompt:
            return _completion(_extraction_diff())
        if "[PHASE INSTRUCTION]" in prompt:
            raise AssertionError("phase agent must never run on a crisis utterance")
        if "crisis-response voice" in prompt:
            return _completion("crisis response")
        raise AssertionError(f"unexpected prompt on L2-crisis path: {prompt[:120]!r}")

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)
    notify_calls: list = []
    _spy_notify(monkeypatch, notify_calls)
    graph = build_turn_graph()

    result = await graph.ainvoke(
        new_session_state(patient_utterance="nothing matters anymore, I just want it to end"),
        config={"configurable": {"thread_id": make_thread_id("t-l2", 1)}},
    )

    assert result["response"] == "crisis response"
    assert result["crisis_verdict"]["crisis"] is True
    assert result["crisis_verdict"]["category"] == "suicide"
    assert (
        notify_calls and (notify_calls[0].get("crisis_verdict") or {}).get("category") == "suicide"
    )


async def test_conditional_edge_selects_phase_by_state(monkeypatch):
    captured = {}

    async def fake_acompletion(**kwargs):
        captured["prompt"] = kwargs["messages"][0]["content"]
        return _completion("deepening response")

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)
    graph = build_turn_graph()

    result = await graph.ainvoke(
        new_session_state(phase="deepening", patient_utterance="it keeps coming back"),
        config={"configurable": {"thread_id": make_thread_id("t-phase", 1)}},
    )

    assert result["response"] == "deepening response"
    # the deepening phase prompt must carry its phase instruction
    assert "[PHASE INSTRUCTION]" in captured["prompt"]


# --- checkpointer integration (Postgres test database) ---


@pytest_asyncio.fixture(scope="module")
async def _db():
    await init_db(TEST_URL)
    yield


async def test_checkpointer_persists_thread_for_invocation(_db, monkeypatch):
    pid = f"f010-{uuid.uuid4().hex[:8]}"
    thread_id = make_thread_id(pid, 1)
    monkeypatch.setattr("litellm.acompletion", _make_fake_by_prompt())

    try:
        async with make_checkpointer(CHECKPOINTER_URL) as saver:
            await saver.setup()
            graph = build_turn_graph(saver)
            await graph.ainvoke(
                new_session_state(patient_utterance="I feel tired today"),
                config={"configurable": {"thread_id": thread_id}},
            )

        async with make_checkpointer(CHECKPOINTER_URL) as saver:
            await saver.setup()
            thread_ids = [
                ckpt.config["configurable"]["thread_id"] async for ckpt in saver.alist(None)
            ]
        assert thread_id in thread_ids
    finally:
        await delete_participant(pid, TEST_URL)
