"""Safety node (F003) — 3-layer crisis gate, layers L1 + L2 (§7.8).

L1 is pure code: a high-precision lexicon (English + romanized Hindi), zero
latency, catches blunt cases. L2 is a zero-shot small-model strict-JSON
classifier via LiteLLM, recall-tuned, runs parallel and gates the phase agent.

Graph nodes are pure functions of state: `l2_safety_node` performs no I/O
beyond the declared LiteLLM call and returns a partial state update.
"""

import json
import re

import litellm

from app.config.settings import settings
from app.graph.state import SessionState
from app.logger import logger

# --- L1: high-precision lexicon (English + romanized Hindi) ---

# phrase -> category
L1_CATEGORY_MAP = {
    # English — explicit self-harm ideation
    "suicide": "suicide",
    "kill myself": "suicide",
    "end my life": "suicide",
    "end it all": "suicide",
    "want to die": "suicide",
    "take my own life": "suicide",
    "killing myself": "suicide",
    "cut my wrists": "self-harm",
    "cut myself": "self-harm",
    "hurt myself": "self-harm",
    "self harm": "self-harm",
    "hurt myself on purpose": "self-harm",
    # romanized Hindi — explicit
    "khudkhushi": "suicide",
    "khudkushi": "suicide",
    "jeena nahin": "suicide",
    "jeena nahi": "suicide",
    "khatam kar du": "suicide",
    "khatam kar doon": "suicide",
    "marna chahta hoon": "suicide",
    "marna chahti hoon": "suicide",
    "apni jaan le": "suicide",
    "aage nahi jeena": "suicide",
    "aage nahin jeena": "suicide",
    "mar jau": "suicide",
    "mar jaun": "suicide",
}

L1_LEXICON = frozenset(L1_CATEGORY_MAP)


def _compile_phrase(phrase: str) -> re.Pattern:
    """Word-boundary pattern for a phrase (tokens are space-delimited).

    The bare word "suicide" is excluded when immediately followed by
    "prevention" — that collocation is the canonical benign mention and must
    not false-positive (substring/exact-phrase safety).
    """
    pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
    if phrase == "suicide":
        pattern += r"(?!\s+prevention)"
    return re.compile(pattern, re.IGNORECASE)


# Escaped so regex metacharacters inside phrases never corrupt the pattern.
_L1_MATCHERS = [(_compile_phrase(p), p) for p in L1_LEXICON]


def l1_lexicon_check(text: str) -> dict:
    """Pure-code, zero-latency crisis lexicon check.

    Returns ``{"hit": bool, "category": str | None}``. Matches whole phrases
    only (word-boundary aware) so a benign word containing a trigger substring
    does not false-positive.
    """
    for pattern, phrase in _L1_MATCHERS:
        if pattern.search(text):
            return {"hit": True, "category": L1_CATEGORY_MAP[phrase]}
    return {"hit": False, "category": None}


# --- L2: zero-shot small-model strict-JSON classifier ---

_L2_PROMPT = (
    "You are a crisis-safety classifier. The patient said:\n"
    '"{utterance}"\n\n'
    "Classify whether this is a crisis (suicide/self-harm ideation, hopelessness "
    "with finality, plans to harm self/others). Tune for RECALL: when ambiguous, "
    "classify as crisis — a false positive only interrupts a session, a false "
    "negative misses a crisis. Respond with ONLY a strict JSON object of the "
    'shape {"crisis": bool, "category": str, "confidence": float}. '
    'Category is one of "suicide", "self-harm", or "none".'
)


def _extract_json(text: str) -> dict | None:
    """Extract the first {...} block from the model output and parse it.

    The model is instructed to return strict JSON, but we defensively pull the
    first brace block so verbose wrappers don't break us. Returns None if the
    text has no brace block or it isn't valid JSON.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


async def l2_safety_node(state: SessionState) -> dict:
    """LangGraph node — zero-shot small-model crisis gate.

    Pure function of state; the only I/O is the declared LiteLLM call using
    ``settings.safety_model``. Returns a partial state update carrying
    ``crisis_verdict``.

    Recall-tuned (see `_L2_PROMPT`). A pipeline error is NOT a crisis signal:
    on any parse failure we return ``crisis=False`` and log, so the phase agent
    still runs. The emergency-contact notification is the backstop.
    """
    utterance = state.get("patient_utterance", "")

    try:
        completion = await litellm.acompletion(
            model=settings.safety_model,
            messages=[{"role": "user", "content": _L2_PROMPT.replace("{utterance}", utterance)}],
            temperature=0,
        )
        content = completion.choices[0].message.content
    except Exception as exc:  # pragma: no cover - provider errors surface at runtime
        logger.exception("L2 safety call failed; treating as non-crisis: %s", exc)
        return {"crisis_verdict": {"crisis": False, "category": "none", "confidence": 0.0}}

    parsed = _extract_json(content) if isinstance(content, str) else None
    if parsed is None or not all(k in parsed for k in ("crisis", "category", "confidence")):
        logger.warning("L2 safety returned unparseable output; treating as non-crisis: %r", content)
        return {"crisis_verdict": {"crisis": False, "category": "none", "confidence": 0.0}}

    return {
        "crisis_verdict": {
            "crisis": bool(parsed["crisis"]),
            "category": parsed["category"],
            "confidence": float(parsed["confidence"]),
        }
    }
