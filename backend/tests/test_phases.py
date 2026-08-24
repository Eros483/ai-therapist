"""Tests for the five phase-agent nodes (F007) — landing, opening, deepening,
meaning, closing.

Each node is a pure function of SessionState that calls the main model via
LiteLLM and returns {"response": <model text>}. Tests mock `litellm.acompletion`,
assert the shared scaffold uses `settings.main_model`, and check each phase's
prompt carries its distinctive behavioural constraints."""

from app.config.settings import settings
from app.graph.nodes.phases import (
    closing_node,
    deepening_node,
    landing_node,
    meaning_node,
    opening_node,
)
from app.graph.state import new_session_state


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


# (node, phase label, distinctive prompt markers)
NODES = [
    (landing_node, "landing", ["at most one question", "present-moment"]),
    (opening_node, "opening", ["one open question", "dropped thread"]),
    (
        deepening_node,
        "deepening",
        ["silence", "Take your time", "body", "shorter"],
    ),
    (meaning_node, "meaning", ["What I'm noticing", "I wonder if", "do not give advice"]),
    (
        closing_node,
        "closing",
        ["no new", "carry forward", "summar", "2-3"],
    ),
]


async def test_each_phase_node_returns_response_and_uses_main_model(monkeypatch):
    for node, label, _markers in NODES:
        captured = {}

        async def fake_acompletion(**kwargs):
            captured["kwargs"] = kwargs
            return _FakeCompletion(f"{label} response text")

        monkeypatch.setattr("litellm.acompletion", fake_acompletion)
        state = new_session_state(phase=label, patient_utterance="hello there")
        update = await node(state)
        assert update == {"response": f"{label} response text"}
        assert captured["kwargs"]["model"] == settings.main_model
        # the patient utterance must reach the model
        assert "hello there" in captured["kwargs"]["messages"][0]["content"]


async def test_prompt_carries_phase_specific_markers(monkeypatch):
    for node, label, markers in NODES:
        captured = {}

        async def fake_acompletion(**kwargs):
            captured["kwargs"] = kwargs
            return _FakeCompletion("ok")

        monkeypatch.setattr("litellm.acompletion", fake_acompletion)
        await node(new_session_state(phase=label, patient_utterance="x"))
        prompt = captured["kwargs"]["messages"][0]["content"]
        for marker in markers:
            assert marker.lower() in prompt.lower(), f"{label}: missing {marker!r}"


async def test_landing_uses_present_moment_not_problem_orientation(monkeypatch):
    captured = {}

    async def fake_acompletion(**kwargs):
        captured["kwargs"] = kwargs
        return _FakeCompletion("ok")

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)
    await landing_node(new_session_state(patient_utterance="x"))
    prompt = captured["kwargs"]["messages"][0]["content"].lower()
    # must direct toward a present-moment question, never a problem-oriented one
    assert "present-moment" in prompt
    assert "do not ask about the problem" in prompt
    assert "at most one question per exchange" in prompt


async def test_closing_has_no_new_threads_hard_rule(monkeypatch):
    captured = {}

    async def fake_acompletion(**kwargs):
        captured["kwargs"] = kwargs
        return _FakeCompletion("ok")

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)
    await closing_node(new_session_state(phase="closing", patient_utterance="x"))
    prompt = captured["kwargs"]["messages"][0]["content"].lower()
    assert "no new" in prompt
    assert "thread" in prompt


async def test_deepening_grants_silence_permission(monkeypatch):
    captured = {}

    async def fake_acompletion(**kwargs):
        captured["kwargs"] = kwargs
        return _FakeCompletion("ok")

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)
    await deepening_node(new_session_state(phase="deepening", patient_utterance="x"))
    prompt = captured["kwargs"]["messages"][0]["content"]
    assert "take your time" in prompt.lower()


async def test_prompt_includes_session_state_and_language_mode(monkeypatch):
    captured = {}

    async def fake_acompletion(**kwargs):
        captured["kwargs"] = kwargs
        return _FakeCompletion("ok")

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)
    state = new_session_state(
        phase="deepening",
        elapsed_minutes=20.0,
        primary_thread="work",
        patient_utterance="x",
        register={"register": 1, "cmi": 0.6},
    )
    await deepening_node(state)
    prompt = captured["kwargs"]["messages"][0]["content"]
    assert "hinglish" in prompt.lower()
    assert "work" in prompt  # session state present


async def test_interruption_directive_in_all_phase_prompts(monkeypatch):
    for node, label, _markers in NODES:
        captured = {}

        async def fake_acompletion(**kwargs):
            captured["kwargs"] = kwargs
            return _FakeCompletion("ok")

        monkeypatch.setattr("litellm.acompletion", fake_acompletion)
        await node(new_session_state(phase=label, patient_utterance="x"))
        prompt = captured["kwargs"]["messages"][0]["content"].lower()
        assert "interrupt" in prompt, f"{label}: missing interruption directive"


async def test_next_technique_rides_in_technique_library(monkeypatch):
    captured = {}

    async def fake_acompletion(**kwargs):
        captured["kwargs"] = kwargs
        return _FakeCompletion("ok")

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)
    await deepening_node(
        new_session_state(phase="deepening", patient_utterance="x", next_technique="body question")
    )
    prompt = captured["kwargs"]["messages"][0]["content"]
    assert "body question" in prompt
