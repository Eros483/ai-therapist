"""F011 pipeline assembly smoke tests — the pure timer logic lives in
test_timers.py; here we only prove the Pipecat pieces construct in-process
(no audio hardware needed to build them) and the turn-bridge logic."""

import pytest

from app.voice.pipeline import build_pipeline, build_stt, build_transport, build_tts


class _FakeWebsocket:
    pass


def test_timers_importable():
    from app.voice.timers import (
        phase_prosody_directive,
        silence_checkin_should_fire,
        vad_threshold_for_phase,
    )

    assert vad_threshold_for_phase("deepening") > vad_threshold_for_phase("landing")
    assert phase_prosody_directive("deepening")
    assert silence_checkin_should_fire(90)


def test_transport_constructs():
    transport = build_transport(_FakeWebsocket())
    assert transport is not None


def test_services_construct():
    assert build_stt() is not None
    assert build_tts() is not None


def test_pipeline_constructs():
    def invoker(thread_id, state):
        return {"response": "hello"}

    pipeline = build_pipeline(_FakeWebsocket(), invoker, "participant:test:session:1")
    assert pipeline is not None


@pytest.mark.asyncio
async def test_run_turn_invokes_graph():
    from app.graph.state import new_session_state
    from app.voice.pipeline import run_turn

    calls = []

    async def invoker(thread_id, state):
        calls.append((thread_id, state["patient_utterance"]))
        return {"response": "namaste", "phase": "deepening"}

    state = new_session_state(patient_utterance="mujhe aaj bahut ajeeb lag raha hai")
    updated, response, phase = await run_turn(state, invoker, "participant:t:session:1")

    assert calls == [("participant:t:session:1", "mujhe aaj bahut ajeeb lag raha hai")]
    assert response == "namaste"
    assert phase == "deepening"
    assert updated["phase"] == "deepening"
