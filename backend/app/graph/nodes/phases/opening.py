"""Opening phase agent — find the real thread, the patient leads topic selection.

Behaviour (methodology §4.2 Phase 2): ask one open question and follow where it
goes; watch for dropped threads (these are often the real topic); no
interpretations; no advice. Technique subset: open question, reflection,
reframe, validation.
"""

from app.graph.nodes.phases._common import (
    build_prompt,
    call_phase_model,
    technique_library,
)
from app.graph.state import SessionState

_PHASE_INSTRUCTIONS = (
    "This phase finds the real thread. The patient leads the topic selection.\n"
    "- Ask ONE open question and follow where it goes — do not stack questions.\n"
    "- Watch for dropped threads: if the patient mentions something significant "
    "and immediately pivots away, that topic is often the real one. Address the "
    "thing they moved past first.\n"
    "- Do NOT offer interpretations yet.\n"
    "- Do NOT give advice.\n"
    "- Notice which topic the patient returns to more than once."
)


async def opening_node(state: SessionState) -> dict:
    """Return {"response": <main-model text>} for the opening phase."""
    prompt = build_prompt(
        state,
        "opening",
        _PHASE_INSTRUCTIONS,
        technique_library("opening"),
    )
    return {"response": await call_phase_model(state, prompt)}
