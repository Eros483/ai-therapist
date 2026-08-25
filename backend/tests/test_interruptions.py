"""Tests for barge-in / interruption capture (F013).

Pure capture -> state logic owned by the voice layer (implementation.md §7.7,
methodology.md §6.8). Cancellation itself lives in the streaming TTS
infrastructure (F011); this module turns a barge-in into a schema-valid
`interruption_event` appended to the NEXT turn-graph invocation's
SessionState.
"""

from app.graph.state import InterruptionEvent, SessionState, new_session_state
from app.voice.interruptions import (
    INTERRUPTION_CEILING,
    append_interruption,
    capture_interruption,
    interruption_history_ok,
    truncated_ai_text,
)


def test_capture_interruption_returns_schema_valid_event():
    event = capture_interruption("body question", "deepening", 21.0)
    assert isinstance(event, dict)
    assert set(event.keys()) == {"interrupted_what", "phase", "when_min"}
    assert isinstance(event["interrupted_what"], str)
    assert isinstance(event["phase"], str)
    assert isinstance(event["when_min"], float)
    # The TypedDict accepts it — InterruptionEvent is structurally that dict.
    typed: InterruptionEvent = event
    assert typed["interrupted_what"] == "body question"
    assert typed["phase"] == "deepening"
    assert typed["when_min"] == 21.0


def test_append_interruption_to_empty_state_returns_partial_dict():
    state = new_session_state()
    event = capture_interruption("reflection", "landing", 3.5)
    out = append_interruption(state, event)
    assert isinstance(out, dict)
    assert set(out.keys()) == {"interruption_events"}
    assert out["interruption_events"] == [event]


def test_append_interruption_appends_does_not_wipe():
    first = capture_interruption("body question", "deepening", 21.0)
    second = capture_interruption("reflection", "deepening", 23.0)
    state = new_session_state(interruption_events=[first])
    out = append_interruption(state, second)
    assert out["interruption_events"] == [first, second]
    # The caller's state is untouched — pure function returns a new list.
    assert state["interruption_events"] == [first]


def test_append_interruption_handles_state_without_prior_events():
    # SessionState is total=False — the key may be absent entirely.
    state: SessionState = {"phase": "deepening"}
    event = capture_interruption("body question", "deepening", 21.0)
    assert append_interruption(state, event)["interruption_events"] == [event]


def test_truncated_ai_text_returns_full_text_when_no_progress():
    full = "It sounds like there is something about the way he responds that"
    assert truncated_ai_text(full) == full


def test_truncated_ai_text_returns_spoken_so_far_when_shorter():
    full = "It sounds like there is something about the way he responds that"
    spoken_so_far = "It sounds like there is something"
    assert truncated_ai_text(full, spoken_so_far) == spoken_so_far


def test_truncated_ai_text_never_longer_than_full_response():
    full = "It sounds like there is something"
    # A bad voice-layer signal (spoken > full) must clamp, never fabricate.
    assert truncated_ai_text(full, full + " about the way he responds") == full
    # Zero progress is honest — nothing was spoken yet.
    assert truncated_ai_text(full, "") == ""


def test_interruption_history_ok_false_at_ceiling():
    state = new_session_state(
        interruption_events=[
            capture_interruption("reflection", "deepening", 1.0),
            capture_interruption("reflection", "deepening", 2.0),
            capture_interruption("body question", "deepening", 3.0),
        ]
    )
    assert not interruption_history_ok(state)


def test_interruption_history_ok_false_above_ceiling():
    events = [capture_interruption("reflection", "deepening", float(i)) for i in range(4)]
    assert not interruption_history_ok(new_session_state(interruption_events=events))


def test_interruption_history_ok_true_below_ceiling():
    state = new_session_state(
        interruption_events=[
            capture_interruption("reflection", "deepening", 1.0),
            capture_interruption("body question", "deepening", 2.0),
        ]
    )
    assert interruption_history_ok(state)


def test_interruption_history_ok_true_when_no_events():
    assert interruption_history_ok(new_session_state())


def test_ceiling_constant_is_three():
    assert INTERRUPTION_CEILING == 3
