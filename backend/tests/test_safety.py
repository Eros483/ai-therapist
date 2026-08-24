"""Tests for the safety node (F003) — L1 lexicon + L2 small-model gate (§7.8).

Graph nodes are pure functions of state; the L2 node's only side effect is the
declared LiteLLM call. L1 is pure code (zero latency); L2 is mocked here so we
assert the contract (model from settings, strict-JSON parse, recall stance)
without a live provider.
"""

import json

from app.config.settings import settings
from app.graph.nodes.safety import (
    L1_CATEGORY_MAP,
    L1_LEXICON,
    l1_lexicon_check,
    l2_safety_node,
)
from app.graph.state import new_session_state

# --- L1: lexicon surface ---


def test_l1_lexicon_is_nonempty_frozenset():
    assert isinstance(L1_LEXICON, frozenset)
    assert len(L1_LEXICON) >= 15


def test_l1_category_map_covers_all_phrases():
    assert set(L1_CATEGORY_MAP) == set(L1_LEXICON)
    assert all(c in {"suicide", "self-harm"} for c in L1_CATEGORY_MAP.values())


def test_l1_hits_english():
    assert l1_lexicon_check("I want to kill myself tonight")["hit"] is True


def test_l1_hits_romanized_hindi():
    assert l1_lexicon_check("main khudkhushi kar lunga")["hit"] is True
    assert l1_lexicon_check("mujhe jeena nahin hai")["hit"] is True


def test_l1_category_correct():
    result = l1_lexicon_check("I want to kill myself")
    assert result["hit"] is True
    assert result["category"] == "suicide"


def test_l1_case_insensitive():
    assert l1_lexicon_check("I WANT TO KILL MYSELF")["hit"] is True


def test_l1_miss_benign_text():
    assert l1_lexicon_check("I had a rough day at work today")["hit"] is False


def test_l1_substring_safety():
    # "suicide" alone as a substring of a benign phrase must not fire.
    assert l1_lexicon_check("suicide prevention resources")["hit"] is False


def test_l1_word_boundary():
    # "end it all" inside another phrase shouldn't falsely match a prefix/suffix.
    assert l1_lexicon_check("friend it all the time")["hit"] is False
    assert l1_lexicon_check("I want to die happily")["hit"] is True


# --- L2: small-model gate ---


def _fake_completion(text):
    class _Message:
        content = text

    class _Choice:
        message = _Message()

    class _Completion:
        choices = [_Choice()]

    return _Completion()


async def test_l2_uses_settings_safety_model(monkeypatch):
    calls = {}

    async def fake_acompletion(**kwargs):
        calls.update(kwargs)
        return _fake_completion(
            json.dumps({"crisis": True, "category": "suicide", "confidence": 0.9})
        )

    monkeypatch.setattr("app.graph.nodes.safety.litellm.acompletion", fake_acompletion)

    state = new_session_state(patient_utterance="main khudkhushi kar lunga")
    result = await l2_safety_node(state)

    assert calls["model"] == settings.safety_model
    assert result["crisis_verdict"] == {
        "crisis": True,
        "category": "suicide",
        "confidence": 0.9,
    }


async def test_l2_valid_strict_json_response(monkeypatch):
    async def fake_acompletion(**kwargs):
        return _fake_completion('{"crisis": false, "category": "none", "confidence": 0.1}')

    monkeypatch.setattr("app.graph.nodes.safety.litellm.acompletion", fake_acompletion)

    result = await l2_safety_node(new_session_state(patient_utterance="having a normal day"))
    assert result["crisis_verdict"] == {"crisis": False, "category": "none", "confidence": 0.1}


async def test_l2_extracts_first_json_block_when_verbose(monkeypatch):
    async def fake_acompletion(**kwargs):
        content = (
            'Sure! {"crisis": true, "category": "self-harm", "confidence": 0.8} hope that helps'
        )
        return _fake_completion(content)

    monkeypatch.setattr("app.graph.nodes.safety.litellm.acompletion", fake_acompletion)

    result = await l2_safety_node(new_session_state(patient_utterance="i cut myself"))
    assert result["crisis_verdict"]["crisis"] is True
    assert result["crisis_verdict"]["category"] == "self-harm"


async def test_l2_parse_failure_returns_crisis_false(monkeypatch):
    async def fake_acompletion(**kwargs):
        return _fake_completion("not json at all")

    monkeypatch.setattr("app.graph.nodes.safety.litellm.acompletion", fake_acompletion)

    result = await l2_safety_node(new_session_state(patient_utterance="some text"))
    assert result["crisis_verdict"]["crisis"] is False


async def test_l2_missing_keys_returns_crisis_false(monkeypatch):
    async def fake_acompletion(**kwargs):
        return _fake_completion(json.dumps({"crisis": True}))

    monkeypatch.setattr("app.graph.nodes.safety.litellm.acompletion", fake_acompletion)

    result = await l2_safety_node(new_session_state(patient_utterance="some text"))
    assert result["crisis_verdict"]["crisis"] is False
