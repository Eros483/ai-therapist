"""Shared prompt scaffolding + main-model call for the five phase agents.

Realizes implementation.md §6.1 (common blocks: [PERSONA], [LANGUAGE MODE],
[SESSION STATE], [SAFETY RULES] + per-phase [PHASE INSTRUCTION], [TECHNIQUE
LIBRARY], [CLOSING RULES]) and §6.2 (key directives carried by all agents).

The technique library is a discrete named set plus the `next_technique`
recommendation emitted by the state-extraction call (§5.3, methodology §6.10) —
the initiation mechanism that stops the model defaulting to pure inquiry.

Prompt assembly uses `.replace()` placeholders, NOT str.format, so the JSON
braces in the session-state block can't collide with format fields.
"""

import json

import litellm

from app.config.settings import settings
from app.graph.state import SessionState
from app.logger import logger

# --- canonical technique set (mirrors extraction.NEXT_TECHNIQUES) ---
ALL_TECHNIQUES = (
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
)

# Language mode labels by register score (methodology §3.2 mirroring rules).
_REGISTER_LABELS = {0: "formal English", 1: "Hinglish", 2: "hindi-led"}

# §6.2 key directives carried by every phase agent.
_KEY_DIRECTIVES = (
    "- Hold silence rather than filling it. If the patient trails off or says "
    '"I don\'t know", wait before speaking. A 3-word spoken response after a '
    "held pause is sometimes right.\n"
    "- If you were interrupted, yield. Do NOT restart or finish the interrupted "
    "sentence. Repeated interruptions of your reflections mean slow down and "
    "shorten.\n"
    "- Never parrot back the patient's exact words. Reframe slightly (intentional "
    "mismatch).\n"
    "- If the patient mentions something and pivots away, address the thing they "
    "moved past first.\n"
    "- Do not give advice before the Meaning phase.\n"
    "- Use the patient's own words as bridges to deeper questions.\n"
    "- Do not open new emotional threads once Closing begins."
)

_COMMON_BLOCKS = (
    "[PERSONA]\n"
    "You are a warm, non-judgmental therapist speaking with a client. You are "
    "reflective, present, and unhurried. You speak in short, human sentences. "
    "You never lecture, diagnose, or rush.\n\n"
    "[LANGUAGE MODE]\n"
    "Current client register: {language_mode}\n"
    "Mirror the client's register, with a one-exchange lag. If the client speaks "
    "formal English, respond in formal English — never inject Hinglish. If they "
    "code-mix, match them lightly. Keep it natural, never mechanical.\n\n"
    "[SESSION STATE]\n"
    "{session_state_json}\n\n"
    "[SAFETY RULES]\n"
    "Crisis detection is handled by the pipeline. Your job: if the client is in "
    "distress, acknowledge with warmth, stop exploring further, and stay present "
    "with them. Do not diagnose.\n\n"
    "[KEY DIRECTIVES]\n"
    "{key_directives}\n\n"
    "[TECHNIQUE LIBRARY]\n"
    "Available techniques (discrete, named): {techniques}\n"
    "Recommended next technique (from the session state-tracker): "
    "{next_technique}\n\n"
    "The client's most recent utterance:\n{utterance}\n\n"
    "Respond now as the therapist — spoken aloud, short and human."
)

# Subsets per phase; the recommended next technique is injected on top.
PHASE_TECHNIQUES = {
    "landing": ("open question", "reflection", "check-in", "validation"),
    "opening": ("open question", "reflection", "reframe", "validation"),
    "deepening": (
        "body question",
        "reflection",
        "reframe",
        "silence",
        "exploration",
        "normalize",
    ),
    "meaning": ("reflection", "reframe", "normalize", "summarize", "validation"),
    "closing": ("summarize", "reflection", "validation", "check-in"),
}


def _language_mode(state: SessionState) -> str:
    register = (state.get("register") or {}).get("register")
    return _REGISTER_LABELS.get(register, "formal English")


def build_prompt(
    state: SessionState,
    phase_name: str,
    phase_instructions: str,
    technique_library: str,
    closing_rules: str = "",
) -> str:
    """Assemble the §6.1 common blocks + phase block + technique library."""
    session_state_json = json.dumps(
        {
            "phase": state.get("phase", phase_name),
            "elapsed_minutes": state.get("elapsed_minutes", 0),
            "exchange_count": state.get("exchange_count", 0),
            "primary_thread": state.get("primary_thread", ""),
            "dropped_threads": state.get("dropped_threads", []),
            "key_words_used": state.get("key_words_used", []),
            "language_map": state.get("language_map", {}),
            "interruption_events": state.get("interruption_events", []),
            "tentative_pattern": state.get("tentative_pattern", ""),
        },
        ensure_ascii=False,
    )

    prompt = _COMMON_BLOCKS
    prompt = prompt.replace("{language_mode}", _language_mode(state))
    prompt = prompt.replace("{session_state_json}", session_state_json)
    prompt = prompt.replace("{key_directives}", _KEY_DIRECTIVES)
    prompt = prompt.replace("{techniques}", technique_library)
    prompt = prompt.replace("{next_technique}", state.get("next_technique", "") or "none")
    prompt = prompt.replace("{utterance}", state.get("patient_utterance", ""))

    prompt += "\n\n[PHASE INSTRUCTION]\n" + phase_instructions
    if closing_rules:
        prompt += "\n\n[CLOSING RULES]\n" + closing_rules
    return prompt


async def call_phase_model(state: SessionState, prompt: str) -> str:
    """Call the main therapist model via LiteLLM and return the trimmed text."""
    completion = await litellm.acompletion(
        model=settings.main_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    text = completion.choices[0].message.content or ""
    logger.debug("phase_agent response (%s): %r", state.get("phase"), text[:200])
    return text.strip()


def technique_library(phase_name: str) -> str:
    """Render a phase's technique subset as a discrete, named, selectable set."""
    names = PHASE_TECHNIQUES[phase_name]
    return "; ".join(f"{name}" for name in names)
