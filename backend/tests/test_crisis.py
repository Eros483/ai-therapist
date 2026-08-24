"""Tests for the crisis node (F008) — in-session crisis protocol response +
emergency-contact notification (methodology §7.3, impl §7.5/§7.8).

The crisis node is the RESPONSE half of the safety stack: it runs only after
the safety branch (L1/L2) has set ``crisis_verdict``. It is a pure function
of state whose only declared I/O is the LiteLLM call (main model,
protocol-constrained). ``notify_emergency_contact`` is fully pure — the v0
"notification" is a logged outbound signal carrying minimal metadata; the
real SMS/push transport is deployment-time.
"""

from datetime import datetime

from app.config.settings import settings
from app.graph.nodes.crisis import _FALLBACK_RESPONSE, crisis_node, notify_emergency_contact
from app.graph.state import new_session_state

CRISIS_VERDICT = {"crisis": True, "category": "suicide", "confidence": 0.95}

ALLOWED_NOTIFICATION_KEYS = {"participant_id", "category", "timestamp", "status"}


def _fake_completion(text):
    class _Message:
        content = text

    class _Choice:
        message = _Message()

    class _Completion:
        choices = [_Choice()]

    return _Completion()


# --- crisis_node: protocol response ---


async def test_crisis_node_uses_settings_main_model_and_protocol_prompt(monkeypatch):
    calls = {}

    async def fake_acompletion(**kwargs):
        calls.update(kwargs)
        return _fake_completion("I'm here with you. Please call 14416.")

    monkeypatch.setattr("app.graph.nodes.crisis.litellm.acompletion", fake_acompletion)

    state = new_session_state(crisis_verdict=CRISIS_VERDICT)
    result = await crisis_node(state)

    assert calls["model"] == settings.main_model
    content = calls["messages"][0]["content"]
    assert "warmth" in content  # protocol step 1: acknowledge with warmth
    assert settings.crisis_helpline_number in content  # protocol step 3: speak the resource
    assert result["response"] == "I'm here with you. Please call 14416."


async def test_crisis_node_surfaces_helpline_and_website(monkeypatch):
    async def fake_acompletion(**kwargs):
        return _fake_completion("I'm here with you.")

    monkeypatch.setattr("app.graph.nodes.crisis.litellm.acompletion", fake_acompletion)

    result = await crisis_node(new_session_state(crisis_verdict=CRISIS_VERDICT))

    assert result["crisis_surface"] == {
        "helpline": settings.crisis_helpline_number,
        "website": settings.crisis_website or "",
    }


async def test_crisis_node_model_failure_returns_deterministic_fallback(monkeypatch):
    async def fake_acompletion(**kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("app.graph.nodes.crisis.litellm.acompletion", fake_acompletion)

    result = await crisis_node(new_session_state(crisis_verdict=CRISIS_VERDICT))

    # Protocol must not depend on the model: the fallback still speaks the
    # helpline, and the surface payload is still valid.
    assert settings.crisis_helpline_number in result["response"]
    assert result["response"] == _FALLBACK_RESPONSE.replace(
        "{helpline}", settings.crisis_helpline_number
    )
    assert result["crisis_surface"]["helpline"] == settings.crisis_helpline_number


# --- notify_emergency_contact: minimal-metadata notification ---


def test_notify_skipped_when_no_emergency_contact(monkeypatch):
    monkeypatch.setattr(settings, "emergency_contact_number", None)

    result = notify_emergency_contact(new_session_state(crisis_verdict=CRISIS_VERDICT))

    notification = result["emergency_notification"]
    assert notification["status"] == "skipped"
    assert set(notification) == ALLOWED_NOTIFICATION_KEYS


def test_notify_sent_payload_is_minimal_metadata_only(monkeypatch):
    monkeypatch.setattr(settings, "emergency_contact_number", "+919999999999")

    result = notify_emergency_contact(new_session_state(crisis_verdict=CRISIS_VERDICT))

    notification = result["emergency_notification"]
    assert notification["status"] == "sent"
    # MINIMAL METADATA ONLY — no transcript, no utterance, no session content.
    assert set(notification) == ALLOWED_NOTIFICATION_KEYS
    assert notification["category"] == "suicide"
    assert notification["participant_id"] == ""
    # timestamp is a UTC ISO-8601 string
    datetime.fromisoformat(notification["timestamp"])
    assert notification["timestamp"].endswith("+00:00") or notification["timestamp"].endswith("Z")


def test_notify_carries_participant_id_when_present(monkeypatch):
    monkeypatch.setattr(settings, "emergency_contact_number", "+919999999999")

    result = notify_emergency_contact(
        new_session_state(participant_id="p-42", crisis_verdict=CRISIS_VERDICT)
    )

    assert result["emergency_notification"]["participant_id"] == "p-42"
    assert result["emergency_notification"]["status"] == "sent"


def test_notify_category_falls_back_when_verdict_missing(monkeypatch):
    monkeypatch.setattr(settings, "emergency_contact_number", "+919999999999")

    result = notify_emergency_contact(new_session_state())

    assert result["emergency_notification"]["category"] == "crisis"
    assert result["emergency_notification"]["status"] == "sent"
