"""Landing phase agent — let the person arrive, calibrate baseline.

Behaviour (methodology §4.2 Phase 1): open with a present-moment question, not a
problem-oriented one; maximum one question per exchange; do not ask about the
problem. Technique subset: open question, reflection, check-in, validation.
"""

from app.graph.nodes.phases._common import (
    build_prompt,
    call_phase_model,
    technique_library,
)
from app.graph.state import SessionState

_PHASE_INSTRUCTIONS = (
    "This is the very start of the session. Your goal is to let the person "
    "arrive and calibrate their emotional baseline.\n"
    "- Open with a present-moment question, NOT a problem-oriented one. Good: "
    '"How are you coming in today?" Bad: "What brings you here today?"\n'
    "- Do NOT ask about the problem in this phase.\n"
    "- Ask AT MOST one question per exchange — no follow-up question piles.\n"
    "- Observe and note how the person arrives: tense, flat, scattered, "
    "energised — name it gently."
)


async def landing_node(state: SessionState) -> dict:
    """Return {"response": <main-model text>} for the landing phase."""
    prompt = build_prompt(
        state,
        "landing",
        _PHASE_INSTRUCTIONS,
        technique_library("landing"),
    )
    return {"response": await call_phase_model(state, prompt)}
