"""Barge-in / interruption capture (F013) — pure capture → state logic.

Owned by the voice layer, not the graph (implementation.md §7.7, methodology.md
§6.8). The Pipecat loop cancels the streaming TTS stream on patient speech and
feeds the event here; this module produces the schema-valid `interruption_event`
and appends it to the NEXT turn-graph invocation's SessionState so the model
always knows what it was saying when cut off (§5.1, §6.2 key directive: if
interrupted, yield — never restart or finish the interrupted sentence).

All functions are pure and synchronous; the streaming cancellation itself is
the TTS infrastructure's job (F011).
"""

from app.graph.state import InterruptionEvent, SessionState

# Ceiling for "repeated interruptions" (§6.2/§6.8: repeated interruptions of
# reflections → slow down and shorten). At/above this count the phase agent
# should be told to yield short.
INTERRUPTION_CEILING = 3


def capture_interruption(interrupted_what: str, phase: str, when_min: float) -> InterruptionEvent:
    """Build a schema-valid interruption_event {interrupted_what, phase, when_min}."""
    return {
        "interrupted_what": interrupted_what,
        "phase": phase,
        "when_min": when_min,
    }


def append_interruption(state: SessionState, event: InterruptionEvent) -> dict:
    """Partial state update for the NEXT turn: prior events + this one.

    Appends, never wipes; handles a state that has no prior interruption_events
    key. Returns {"interruption_events": [...]} so it can be merged into the
    next turn-graph invocation's SessionState.
    """
    prior = list(state.get("interruption_events", []))
    prior.append(event)
    return {"interruption_events": prior}


def truncated_ai_text(spoken: str, spoken_so_far: str | None = None) -> str:
    """The AI text captured before cancellation — what TTS got to, never more.

    v0: with no progress signal, the full response is the record. When
    `spoken_so_far` is given (the voice layer's signal of how far playback got)
    and it is shorter, that is the truncated text. Never fabricates: a
    malformed progress signal longer than the response clamps to the full text.
    """
    if spoken_so_far is None:
        return spoken
    return spoken_so_far[: len(spoken)]


def interruption_history_ok(state: SessionState) -> bool:
    """True while interruptions are below the "repeated" ceiling.

    Feeds the §6.2 phase-agent directive: repeated interruptions of reflections
    mean slow down and shorten.
    """
    return len(state.get("interruption_events", [])) < INTERRUPTION_CEILING
