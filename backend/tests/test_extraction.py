"""Tests for the state extraction node (F006) — strict-JSON parse, model call,
and merge of the diff onto the prior SessionState."""

import json

from app.config.settings import settings
from app.graph.nodes.extraction import extraction_node, parse_extraction
from app.graph.state import SessionState, new_session_state

# A full valid diff as the model would emit it.
VALID_DIFF = {
    "primary_thread": "relationship with father",
    "dropped_threads": ["sister's wedding"],
    "key_words_used": ["small", "invisible"],
    "language_map": {"family": "hinglish"},
    "body_locations_mentioned": ["chest"],
    "tentative_pattern": "feeling unseen by authority figures",
    "next_technique": "body question",
}


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


# --- parse_extraction() ---


def test_parse_extraction_valid_json():
    content = '{"primary_thread": "work stress", "next_technique": "reflection"}'
    assert parse_extraction(content) == {
        "primary_thread": "work stress",
        "next_technique": "reflection",
    }


def test_parse_extraction_json_embedded_in_prose_and_backticks():
    content = (
        "Here is the updated state:\n```json\n"
        + json.dumps(VALID_DIFF)
        + "\n```\nLet me know if you need more."
    )
    assert parse_extraction(content) == VALID_DIFF


def test_parse_extraction_garbage_returns_empty_dict():
    # Documented contract: garbage in -> {} out (node logs and degrades).
    assert parse_extraction("no json here at all") == {}
    assert parse_extraction("") == {}
    assert parse_extraction('{"unclosed": [') == {}
    assert parse_extraction("42") == {}
    assert parse_extraction('["a", "list"]') == {}


# --- extraction_node(): merge onto prior state ---


async def test_extraction_node_returns_merged_partial_update(monkeypatch):
    async def fake_acompletion(**kwargs):
        return _FakeCompletion(json.dumps(VALID_DIFF))

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)

    state = new_session_state(
        patient_utterance="My father never listens to me. I feel so small.",
        primary_thread="work stress",
        dropped_threads=["sister's wedding"],
        key_words_used=["not enough"],
        language_map={"family": "hindi"},
        body_locations_mentioned=["throat"],
        tentative_pattern="",
        exchange_count=3,
    )

    update = await extraction_node(state)

    # scalars: model value wins when non-empty
    assert update["primary_thread"] == "relationship with father"
    assert update["tentative_pattern"] == "feeling unseen by authority figures"
    # lists: prior preserved, additions appended, duplicates dropped
    assert update["dropped_threads"] == ["sister's wedding"]
    assert update["key_words_used"] == ["not enough", "small", "invisible"]
    assert update["body_locations_mentioned"] == ["throat", "chest"]
    # dict: merged, model entry wins on collision
    assert update["language_map"] == {"family": "hinglish"}
    assert update["next_technique"] == "body question"
    assert update["exchange_count"] == 4
    # auditable: only SessionState schema keys ever returned
    assert set(update.keys()) <= set(SessionState.__annotations__)


async def test_extraction_node_empty_additions_preserve_prior_lists(monkeypatch):
    diff = dict(VALID_DIFF)
    diff["dropped_threads"] = []
    diff["key_words_used"] = []

    async def fake_acompletion(**kwargs):
        return _FakeCompletion(json.dumps(diff))

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)

    state = new_session_state(
        patient_utterance="blah",
        dropped_threads=["job offer"],
        key_words_used=["small"],
        exchange_count=1,
    )

    update = await extraction_node(state)
    assert update["dropped_threads"] == ["job offer"]
    assert update["key_words_used"] == ["small"]
    assert update["exchange_count"] == 2


async def test_extraction_node_clamps_unknown_next_technique(monkeypatch):
    diff = dict(VALID_DIFF)
    diff["next_technique"] = "totally made up move"

    async def fake_acompletion(**kwargs):
        return _FakeCompletion(json.dumps(diff))

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)

    update = await extraction_node(new_session_state(patient_utterance="x"))
    assert update["next_technique"] == ""


# --- extraction_node(): model call contract ---


async def test_extraction_node_uses_extraction_model_and_includes_utterance(monkeypatch):
    captured = {}

    async def fake_acompletion(**kwargs):
        captured["kwargs"] = kwargs
        return _FakeCompletion(json.dumps(VALID_DIFF))

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)

    utterance = "my father yaar, he just doesn't listen to me"
    await extraction_node(new_session_state(patient_utterance=utterance))

    assert captured["kwargs"]["model"] == settings.extraction_model
    prompt = captured["kwargs"]["messages"][0]["content"]
    assert utterance in prompt


# --- extraction_node(): parse-failure degradation ---


async def test_extraction_node_parse_failure_degrades_gracefully(monkeypatch):
    async def fake_acompletion(**kwargs):
        return _FakeCompletion("totally not json at all")

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)

    state = new_session_state(patient_utterance="blah", exchange_count=2)
    update = await extraction_node(state)
    # minimal safe partial update: no crash, exchange_count still advances
    assert update == {"exchange_count": 3}


async def test_extraction_node_model_error_degrades_gracefully(monkeypatch):
    async def failing_acompletion(**kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("litellm.acompletion", failing_acompletion)

    state = new_session_state(patient_utterance="blah", exchange_count=7)
    update = await extraction_node(state)
    assert update == {"exchange_count": 8}
