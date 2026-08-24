"""Deepening phase agent — sit with discomfort, event → emotion → body →
pattern → origin.

Behaviour (methodology §4.2 Phase 3): slow down (shorter sentences); use body
questions; connect the present feeling to a pattern; do not rescue from
difficult emotions; allow minimal responses and silence permission (§6.4); no
advice. Technique subset: body question, reflection, reframe, silence,
exploration, normalize.
"""

from app.graph.nodes.phases._common import (
    build_prompt,
    call_phase_model,
    technique_library,
)
from app.graph.state import SessionState

_PHASE_INSTRUCTIONS = (
    "This phase sits with discomfort. Work loosely through the sequence: "
    "Event -> Emotion -> Body -> Pattern -> Origin.\n"
    "- Slow down. Use SHORTER sentences and a slower pace.\n"
    '- Use body questions to ground feeling in the body, e.g. "Where do you '
    'feel that?" or "Some people notice this kind of feeling somewhere '
    'physically — does anything come up for you?"\n'
    '- Connect the present feeling to a pattern: "Has this feeling shown up '
    'before?"\n'
    "- Do NOT rescue the patient from difficult emotions — stay with them.\n"
    '- Hold silence. Minimal spoken responses like "Take your time." and '
    '"I\'m with you." are permitted after a held pause — never fill every pause '
    "with a question.\n"
    "- Do NOT give advice in this phase."
)


async def deepening_node(state: SessionState) -> dict:
    """Return {"response": <main-model text>} for the deepening phase."""
    prompt = build_prompt(
        state,
        "deepening",
        _PHASE_INSTRUCTIONS,
        technique_library("deepening"),
    )
    return {"response": await call_phase_model(state, prompt)}
