"""affect_from_audio node (§7.5).

v0 STUB: real audio signal extraction (pace/volume/pitch/flatness →
arousal_trajectory, flat_prosody_streak) is deferred. The node exists so the
turn graph (F010) has a schema-valid, testable affect channel. It is a pure
function of state and returns the schema-valid defaults, ignoring any incoming
audio_affect value — real extraction will consume audio stream stats, not
config.
"""

from app.graph.state import SessionState


def affect_node(state: SessionState) -> dict:
    return {
        "audio_affect": {
            "arousal_trajectory": "steady",
            "flat_prosody_streak": False,
        }
    }
