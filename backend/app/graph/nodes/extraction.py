"""State extraction node (F006) — separate lightweight small-model call that
updates SessionState after each exchange and emits `next_technique`.

Rationale (docs/implementation.md):
  * §5.2 state ownership — the session state JSON is updated by this separate
    extraction call, NOT self-reported by the main therapist model (keeps the
    therapist in character; state is deterministic and auditable).
  * §5.3 next-technique recommendation — the same call emits the next
    response-act, which rides in the phase agent's technique-library slot.
  * §7.5 node contract — `state_extractor` | small | transcript + prev
    SessionState | updated SessionState JSON + `next_technique`. One of the two
    accepted serial LLM hops per turn — must run the small/fast model
    (`settings.extraction_model`), never the main model.

Canonical `next_technique` set (response-acts drawn from the §6 technique
subsets, methodology.md): body question, check-in, exploration, normalize,
open question, reflection, reframe, silence, summarize, validation. Anything
outside this set is clamped to "" so the phase agent never receives an
unimplemented technique.

`language_map` values are topic → register: "formal-en" | "hinglish" |
"hindi-led" (per implementation.md §2.4).

The model emits a strict-JSON DIFF against the prior state (append to lists,
merge into language_map, carry forward unchanged scalars); this node merges
that diff onto the prior state and returns only SessionState-schema keys.
"""

import json
import re

import litellm

from app.config.settings import settings
from app.graph.state import SessionState
from app.logger import logger

NEXT_TECHNIQUES: frozenset[str] = frozenset(
    {
        "body question",
        "check-in",
        "exploration",
        "normalize",
        "open question",
        "reflection",
        "reframe",
        "silence",
        "summarize",
        "validation",
    }
)

# The §5.1 tracked fields the extraction call may update, plus next_technique.
# The node never returns any key outside this set.
_TRACKED_KEYS = (
    "primary_thread",
    "dropped_threads",
    "key_words_used",
    "language_map",
    "body_locations_mentioned",
    "tentative_pattern",
    "next_technique",
)
_LIST_KEYS = ("dropped_threads", "key_words_used", "body_locations_mentioned")

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)

# Template uses .replace() placeholders (not str.format) so the JSON braces in
# the schema description can't collide with format fields.
_PROMPT_TEMPLATE = (
    "You are the state-tracker for a therapy session. You update the session "
    "state JSON after each patient exchange. Your output is a DIFF against the "
    "prior state: APPEND to lists (never wipe existing items), merge new "
    "entries into language_map, carry forward unchanged scalar fields. "
    "Emit STRICTLY this JSON shape and nothing else:\n"
    '{"primary_thread": str, "dropped_threads": [str], "key_words_used": [str], '
    '"language_map": {str: str}, "body_locations_mentioned": [str], '
    '"tentative_pattern": str, "next_technique": str}\n'
    "language_map values are topic -> register, one of: formal-en, hinglish, "
    "hindi-led.\n"
    "next_technique is ONE of: " + ", ".join(sorted(NEXT_TECHNIQUES)) + ".\n"
    "Prior session state:\n{prior_state}\n"
    "Current patient utterance:\n{utterance}\n"
    "Return only the JSON diff."
)


def parse_extraction(content: str) -> dict:
    """Strict-JSON parse of the model's extraction output.

    Extracts the first {...} block, tolerating prose or markdown fences around
    it. Documented contract: on any parse failure (or non-dict result) returns
    {} — the node logs and degrades rather than crashing the turn.
    """
    match = _JSON_BLOCK_RE.search(content or "")
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _merge_diff(prior: SessionState, diff: dict) -> dict:
    """Merge the model's diff onto prior tracked state — append, don't wipe.

    Lists: prior items kept, model additions appended, duplicates dropped.
    language_map: merged, model entry wins on topic collision.
    Scalars (incl. next_technique): model value wins when non-empty, else the
    prior value is carried forward.
    """
    merged: dict = {}
    for key in _TRACKED_KEYS:
        value = diff.get(key)
        if key in _LIST_KEYS:
            additions = value if isinstance(value, list) else []
            prior_items = prior.get(key, [])
            merged[key] = list(prior_items) + [v for v in additions if v not in prior_items]
        elif key == "language_map":
            prior_map = prior.get("language_map") or {}
            merged[key] = {**prior_map, **(value if isinstance(value, dict) else {})}
        else:
            merged[key] = value if value else prior.get(key, "")
    if merged.get("next_technique") not in NEXT_TECHNIQUES:
        merged["next_technique"] = ""
    return merged


def _build_prompt(utterance: str, state: SessionState) -> str:
    prior_json = json.dumps(
        {
            key: state.get(key, []) if key in _LIST_KEYS else state.get(key, "")
            for key in _TRACKED_KEYS
        },
        ensure_ascii=False,
    )
    return _PROMPT_TEMPLATE.replace("{utterance}", utterance).replace("{prior_state}", prior_json)


async def extraction_node(state: SessionState) -> dict:
    """LangGraph node: small-model extraction of the current exchange onto the
    prior SessionState. Pure function of state; returns the partial update.

    Reads state["patient_utterance"] and the prior tracked fields, calls
    `litellm.acompletion` with `settings.extraction_model`, merges the strict
    JSON diff onto the prior state, and always includes the incremented
    `exchange_count`. A model or parse failure logs and returns the minimal
    safe update ({"exchange_count": n + 1}) — the turn must not crash.
    """
    utterance = state.get("patient_utterance", "")

    try:
        completion = await litellm.acompletion(
            model=settings.extraction_model,
            messages=[{"role": "user", "content": _build_prompt(utterance, state)}],
            temperature=0.0,
        )
        diff = parse_extraction(completion.choices[0].message.content)
    except Exception as exc:  # pipeline error must not crash the turn
        logger.warning("extraction_node: model call failed: %s", exc)
        diff = {}

    if not diff:
        logger.warning("extraction_node: parse failure for utterance %r", utterance)
        return {"exchange_count": state.get("exchange_count", 0) + 1}

    update = _merge_diff(state, diff)
    update["exchange_count"] = state.get("exchange_count", 0) + 1
    return update
