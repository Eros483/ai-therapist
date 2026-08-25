"""F011 pipeline tests — the pure timer logic lives in test_timers.py; here we
prove the SmallWebRTC pieces construct and the turn-bridge logic works."""

import pytest

from app.voice.pipeline import build_stt, build_tts, build_vad, build_webrtc_transport, run_turn


def test_timers_importable():
    from app.voice.timers import (
        phase_prosody_directive,
        silence_checkin_should_fire,
        vad_threshold_for_phase,
    )

    assert vad_threshold_for_phase("deepening") > vad_threshold_for_phase("landing")
    assert phase_prosody_directive("deepening")
    assert silence_checkin_should_fire(90)


def test_webrtc_transport_constructs():
    from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

    transport = build_webrtc_transport(SmallWebRTCConnection())
    assert transport is not None


def test_vad_processor_constructs():
    assert build_vad() is not None


def test_services_construct():
    assert build_stt() is not None
    assert build_tts() is not None


@pytest.mark.asyncio
async def test_run_turn_invokes_graph():
    from app.graph.state import new_session_state

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
