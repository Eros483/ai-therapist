from app.graph.state import (
    SessionState,
    new_course_state,
    new_session_state,
)


def test_session_state_defaults():
    s = new_session_state()
    assert s["phase"] == "landing"
    assert s["elapsed_minutes"] == 0.0
    assert s["exchange_count"] == 0
    assert s["dropped_threads"] == []
    assert s["interruption_events"] == []
    assert s["audio_affect"] == {"arousal_trajectory": "steady", "flat_prosody_streak": False}
    assert s["language_map"] == {}


def test_session_state_overrides_merge():
    s = new_session_state(phase="deepening", exchange_count=4)
    assert s["phase"] == "deepening"
    assert s["exchange_count"] == 4
    assert s["dropped_threads"] == []


def test_session_state_accepts_transient_channels():
    s: SessionState = {
        "patient_utterance": "kabhi kabhi main akela feel hota hoon",
        "register": {"register": 2, "cmi": 0.6},
        "crisis_verdict": {"crisis": False},
    }
    assert s["patient_utterance"].startswith("kabhi kabhi")


def test_course_state_defaults():
    c = new_course_state()
    assert c["session_number"] == 1
    assert c["course_phase"] == "foundation"
    assert c["session_summaries"] == []
    assert c["formulation"]["working_pattern"] is None
    assert c["formulation"]["confirmed_insights"] == []
    assert c["next_session_intention"] == ""
    assert c["unresolved_threads"] == []


def test_course_state_overrides():
    c = new_course_state(
        session_number=5,
        course_phase="working",
        formulation={
            "presenting_threads": ["work"],
            "working_pattern": "x",
            "confirmed_insights": ["a"],
        },
    )
    assert c["session_number"] == 5
    assert c["course_phase"] == "working"
    assert c["formulation"]["working_pattern"] == "x"


def test_course_state_is_dict():
    c = new_course_state()
    assert isinstance(c, dict)


def test_session_state_is_dict():
    s = new_session_state()
    assert isinstance(s, dict)
