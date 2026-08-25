"""Synthesis node (F009) — transcript + final SessionState → per-session
summary against the ConSum/MentalCLOUDS counseling-components schema.

Runs as the first node of the post-session graph (impl §4.2, §7.4), off the
live path — latency is irrelevant. Per §7.5 this node runs the MAIN model
(`settings.main_model`, never hardcoded) and emits strict JSON:

    {n, distillation, carry_forward, outcome}

distillation = recurring symptoms/pattern + history + discovered behavior
pattern (the §6.7 counseling-components schema). carry_forward = one
noticing/question for the next session. outcome ∈ {addressed,
partially-addressed, open}.

On model or parse failure the node logs and returns a schema-valid minimal
summary (outcome "open") so the course graph never crashes.
"""

import json
import re

import litellm

from app.config.settings import settings
from app.graph.state import SessionSummary
from app.logger import logger

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)

_OUTCOMES = ("addressed", "partially-addressed", "open")

# Template uses .replace() placeholders (not str.format) so the JSON braces in
# the schema description can't collide with format fields (same pattern as
# app/graph/nodes/extraction.py).
_PROMPT_TEMPLATE = (
    "You are the course-synthesis engine for a therapy session. From the "
    "session transcript and the final session state, produce a per-session "
    "summary against the counseling-components schema (ConSum/MentalCLOUDS). "
    "Emit STRICTLY this JSON shape and nothing else:\n"
    '{"n": int, "distillation": str, "carry_forward": str, "outcome": str}\n'
    "- n: the session number (see final session state).\n"
    "- distillation: recurring symptoms/pattern + history + discovered "
    "behavior pattern in one or two sentences.\n"
    "- carry_forward: one noticing or question to open the next session with.\n"
    "- outcome: one of addressed | partially-addressed | open.\n"
    "Final session state:\n{session_state}\n"
    "Transcript:\n{transcript}\n"
    "Return only the JSON."
)


def parse_summary(content: str) -> dict:
    """Strict-JSON parse of the synthesis output.

    Extracts the first {...} block, tolerating prose or markdown fences around
    it (identical in style to app/graph/nodes/extraction.parse_extraction).
    Returns {} on any failure — the node logs and degrades.
    """
    match = _JSON_BLOCK_RE.search(content or "")
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _minimal_summary(session_number: int) -> dict:
    """Schema-valid fallback used when the model or parse fails."""
    return {
        "n": session_number,
        "distillation": "",
        "carry_forward": "",
        "outcome": "open",
    }


def _build_prompt(session_number: int, session_state: dict, transcript: list[str]) -> str:
    # n must be grounded: the model reads the session number from the state JSON.
    state_json = json.dumps({**session_state, "session_number": session_number}, ensure_ascii=False)
    transcript_text = "\n".join(transcript or [])
    return _PROMPT_TEMPLATE.replace("{session_state}", state_json).replace(
        "{transcript}", transcript_text
    )


async def synthesis_node(state: dict) -> dict:
    """LangGraph node: transcript + final SessionState → per-session summary.

    Pure function of state; returns {"summary": <SessionSummary>}. Model
    failures degrade to a schema-valid minimal summary (outcome "open") rather
    than crashing the post-session graph.
    """
    session_number = state.get("session_number", 1)
    session_state = state.get("final_session_state", {})
    transcript = state.get("transcript", [])

    try:
        completion = await litellm.acompletion(
            model=settings.main_model,
            messages=[
                {
                    "role": "user",
                    "content": _build_prompt(session_number, session_state, transcript),
                }
            ],
            temperature=0.0,
        )
        parsed = parse_summary(completion.choices[0].message.content)
    except Exception as exc:  # post-session path must not crash the pipeline
        logger.warning("synthesis_node: model call failed: %s", exc)
        parsed = {}

    if not parsed:
        logger.warning("synthesis_node: parse failure for session %s", session_number)
        parsed = _minimal_summary(session_number)

    summary: SessionSummary = {
        "n": parsed.get("n", session_number),
        "distillation": str(parsed.get("distillation", "")),
        "carry_forward": str(parsed.get("carry_forward", "")),
        "outcome": parsed.get("outcome", "open") if parsed.get("outcome") in _OUTCOMES else "open",
    }
    return {"summary": summary}
