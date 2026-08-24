"""Meaning phase agent — synthesize, name the pattern, offer tentative reflection.

Behaviour (methodology §4.2 Phase 4): offer ONE clear synthesis observation
using tentative framing (\"What I'm noticing is...\", \"I wonder if...\");
leave the patient in control of confirming or correcting; use the patient's own
words; still no advice — insight is not advice. Technique subset: reflection,
reframe, normalize, summarize, validation.
"""

from app.graph.nodes.phases._common import (
    build_prompt,
    call_phase_model,
    technique_library,
)
from app.graph.state import SessionState

_PHASE_INSTRUCTIONS = (
    "This phase synthesises: name the pattern, offer a tentative reflection.\n"
    "- Offer ONE clear synthesis observation using tentative framing — "
    '"What I\'m noticing is...", "I wonder if...", "It sounds like maybe...". '
    "Not too certain, not clinical.\n"
    "- Leave the patient in control of confirming or correcting the insight.\n"
    "- Use the patient's own words as much as possible.\n"
    "- Still do NOT give advice — an insight is not advice.\n"
    "- Do not present a synthesis as diagnosis or fact."
)


async def meaning_node(state: SessionState) -> dict:
    """Return {"response": <main-model text>} for the meaning phase."""
    prompt = build_prompt(
        state,
        "meaning",
        _PHASE_INSTRUCTIONS,
        technique_library("meaning"),
    )
    return {"response": await call_phase_model(state, prompt)}
