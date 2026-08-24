"""Closing phase agent — leave the person in a manageable, grounded state.

Behaviour (methodology §4.2 Phase 5): HARD RULE — no new emotional threads;
summarise what was explored in 2-3 sentences; offer one carry-forward; give a
clear closing signal; bring the register back toward neutral. Technique subset:
summarize, reflection, validation, check-in.
"""

from app.graph.nodes.phases._common import (
    build_prompt,
    call_phase_model,
    technique_library,
)
from app.graph.state import SessionState

_PHASE_INSTRUCTIONS = (
    "This is the closing container. Your job is to leave the person in a "
    "manageable, grounded state.\n"
    "- HARD RULE: do NOT open any new emotional thread in this phase.\n"
    "- Summarise what was explored in 2-3 sentences — name the real theme, "
    'acknowledge the effort ("That took something to look at.").\n'
    "- Offer one small thing to carry forward: \"What's one small thing you "
    'want to notice this week?"\n'
    "- Give a clear closing signal.\n"
    "- Bring the language register back toward neutral if it has been deeply "
    "emotional."
)

_CLOSING_RULES = (
    "- No new emotional threads, ever, in this phase.\n- Keep it short, warm, and grounded."
)


async def closing_node(state: SessionState) -> dict:
    """Return {"response": <main-model text>} for the closing phase."""
    prompt = build_prompt(
        state,
        "closing",
        _PHASE_INSTRUCTIONS,
        technique_library("closing"),
        closing_rules=_CLOSING_RULES,
    )
    return {"response": await call_phase_model(state, prompt)}
