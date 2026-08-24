"""Tests for the affect_from_audio node (F005).

v0 is a schema-only stub: real audio signal extraction is deferred. The node
must return a schema-valid partial state update for the audio_affect channel.
"""

from app.graph.nodes.affect import affect_node
from app.graph.state import new_session_state


def test_affect_node_returns_partial_state_with_audio_affect():
    out = affect_node(new_session_state())
    assert isinstance(out, dict)
    assert "audio_affect" in out


def test_affect_node_returns_schema_valid_defaults():
    out = affect_node(new_session_state())
    affect = out["audio_affect"]
    assert isinstance(affect["arousal_trajectory"], str)
    assert affect["arousal_trajectory"] != ""
    assert isinstance(affect["flat_prosody_streak"], bool)


def test_affect_node_defaults_match_session_state_default():
    out = affect_node(new_session_state())
    assert out["audio_affect"] == {
        "arousal_trajectory": "steady",
        "flat_prosody_streak": False,
    }


def test_affect_node_is_pure_of_prior_audio_affect():
    # Stub returns the same defaults regardless of incoming state.
    state = new_session_state(
        audio_affect={"arousal_trajectory": "rising", "flat_prosody_streak": True}
    )
    assert affect_node(state)["audio_affect"] == {
        "arousal_trajectory": "steady",
        "flat_prosody_streak": False,
    }
