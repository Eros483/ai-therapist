"""Tests for the register classifier node (F004) — pure functions of text/state."""

from app.graph.nodes.register import (
    CMI_THRESHOLD,
    PARTICLES,
    classify_register,
    cmi,
    register_node,
)
from app.graph.state import new_session_state

# --- cmi() ---


def test_cmi_pure_english_is_zero():
    assert cmi("I have been feeling really anxious about my work lately") == 0.0


def test_cmi_pure_devanagari_is_zero():
    assert cmi("मुझे बहुत परेशानी हो रही है") == 0.0


def test_cmi_balanced_hinglish_is_high():
    # 3 English + 3 Hindi tokens -> CMI = 1 - 3/6 = 0.5
    assert cmi("my problem hai bahut big hai") >= CMI_THRESHOLD


def test_cmi_empty_is_zero():
    assert cmi("") == 0.0
    assert cmi("   ") == 0.0


def test_cmi_mostly_english_low():
    # one Hindi word among many English ones -> low CMI
    assert cmi("I am very stressed these days and cannot sleep yaar") < CMI_THRESHOLD


# --- classify_register() ---


def test_classify_formal_english():
    result = classify_register("I would like to talk about my anxiety today")
    assert result["register"] == 0
    assert result["cmi"] == 0.0


def test_classify_devanagari_heavy_is_hindi_led():
    result = classify_register("मैं बहुत दुखी हूँ और कुछ समझ नहीं आ रहा")
    assert result["register"] == 2


def test_classify_particle_hinglish():
    assert classify_register("I just don't know what to do, yaar")["register"] == 1


def test_classify_balanced_cmi_hinglish():
    assert classify_register("mujhe bahut problem ho rahi hai with my sleep")["register"] == 1


def test_classify_high_hindi_word_ratio_hindi_led():
    # romanized-Hindi words dominate -> hi_ratio >= 0.5 -> register 2
    result = classify_register("mujhe bahut dukh ho raha hai aaj kal")
    assert result["register"] == 2


# --- register_node() ---


def test_register_node_returns_partial_update():
    state = new_session_state(patient_utterance="I'm really struggling, yaar")
    update = register_node(state)
    assert set(update.keys()) == {"register"}
    reg = update["register"]
    assert reg["register"] == 1
    assert isinstance(reg["cmi"], float)


def test_register_node_empty_utterance():
    state = new_session_state(patient_utterance="")
    update = register_node(state)
    assert update["register"]["register"] == 0
    assert update["register"]["cmi"] == 0.0


def test_particles_exposed():
    assert isinstance(PARTICLES, frozenset)
    assert {"yaar", "matlab", "na", "bas"} <= PARTICLES
