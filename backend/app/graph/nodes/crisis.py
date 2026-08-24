"""Crisis node (F008) — in-session crisis protocol response + emergency-contact
notification (methodology §7.3, impl §7.5).

This node is the RESPONSE half of the safety stack: it runs only after the
safety branch (L1 lexicon / L2 small-model gate, impl §7.8) has set
``crisis_verdict`` — crisis detection never runs through the main therapist
model. Per §7.3 the protocol is: 1. acknowledge with warmth, 2. stop
therapeutic exploration, 3. speak the helpline clearly + repeat once,
4. surface the resource on the visual surface (``crisis_surface``), 5. stay
present — the session ends only when the patient ends it, 6. crisis overrides
the time container.

Graph nodes are pure functions of state: the only I/O here is the declared
LiteLLM call (``settings.main_model``, protocol-constrained prompt). On model
failure we return a deterministic fallback that still speaks the helpline —
the protocol must not depend on the model.

The emergency-contact notification is a pure, LOGGED outbound signal in v0:
minimal metadata only (participant in crisis, category, timestamp, status) —
no transcript, no triggering utterance, no session content. The real
SMS/push transport is deployment-time.
"""

from datetime import UTC, datetime

import litellm

from app.config.settings import settings
from app.graph.state import SessionState
from app.logger import logger

# Protocol-constrained prompt for the main model (§7.3 steps 1, 2, 3, 5, 6).
_CRISIS_PROMPT = (
    "You are a calm, warm crisis-response voice. A participant is in crisis. "
    "Follow this protocol exactly:\n"
    "1. Acknowledge with warmth — never minimise what they said.\n"
    "2. Do NOT continue the therapeutic exploration — no questions about their "
    "feelings, no techniques.\n"
    "3. Speak this helpline clearly and slowly: {helpline}. Then repeat the "
    "number once.\n"
    "4. Stay present in a calm holding mode. The session ends only when the "
    "participant ends it. Never hang up.\n"
    "Keep your response SHORT (2-4 spoken sentences) — this is a voice response."
)

# Deterministic fallback: speaks the helpline so the protocol never depends on
# the model being available.
_FALLBACK_RESPONSE = (
    "I'm here with you, and I'm not going anywhere. Please call {helpline} — "
    "that's {helpline}. They are there to talk right now, and I'm staying "
    "right here with you."
)


async def crisis_node(state: SessionState) -> dict:
    """LangGraph node — crisis protocol response (main model, protocol-constrained).

    Pure function of state; the only I/O is the declared LiteLLM call using
    ``settings.main_model``. Returns a partial state update with ``response``
    (spoken to the patient) and ``crisis_surface`` (rendered by the visual
    control surface, §7.3 step 4).
    """
    helpline = settings.crisis_helpline_number
    prompt = _CRISIS_PROMPT.replace("{helpline}", helpline)

    try:
        completion = await litellm.acompletion(
            model=settings.main_model,
            messages=[{"role": "user", "content": prompt}],
        )
        response = completion.choices[0].message.content
    except Exception as exc:  # pragma: no cover - provider errors surface at runtime
        logger.exception("Crisis node model call failed; using fallback response: %s", exc)
        response = _FALLBACK_RESPONSE.replace("{helpline}", helpline)

    return {
        "response": response,
        "crisis_surface": {
            "helpline": helpline,
            "website": settings.crisis_website or "",
        },
    }


def notify_emergency_contact(state: SessionState) -> dict:
    """Emergency-contact notification — pure, logged outbound signal (v0).

    Fires immediately, in parallel with the in-session protocol (§7.3).
    Payload is MINIMAL METADATA ONLY: participant in crisis, category,
    timestamp, status — no transcript, no triggering utterance, no session
    content. If no emergency contact was captured at onboarding, only the
    in-session protocol runs: we log a skip and do nothing else.

    The actual SMS/push transport is deployment-time; v0 logs the outbound
    signal carrying the minimal metadata.
    """
    category = (state.get("crisis_verdict") or {}).get("category", "crisis")
    participant_id = state.get("participant_id", "")
    timestamp = datetime.now(UTC).isoformat()

    if not settings.emergency_contact_number:
        logger.warning(
            "Crisis notification SKIPPED — no emergency contact on file for %s", participant_id
        )
        status = "skipped"
    else:
        logger.info(
            "Crisis notification SENT — participant %s (%s) at %s; contact %s",
            participant_id,
            category,
            timestamp,
            settings.emergency_contact_number,
        )
        status = "sent"

    return {
        "emergency_notification": {
            "participant_id": participant_id,
            "category": category,
            "timestamp": timestamp,
            "status": status,
        }
    }
