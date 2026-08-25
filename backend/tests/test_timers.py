from app.voice.timers import (
    phase_prosody_directive,
    silence_checkin_should_fire,
    vad_threshold_for_phase,
)


def test_vad_threshold_phase_dependent():
    # Deepening must hold more silence than Landing (§7.7, §6.4).
    deepening = vad_threshold_for_phase("deepening")
    landing = vad_threshold_for_phase("landing")
    assert deepening > landing


def test_vad_threshold_custom_table():
    thresholds = {"landing": 1.0, "deepening": 4.0}
    assert vad_threshold_for_phase("deepening", thresholds) == 4.0
    assert vad_threshold_for_phase("landing", thresholds) == 1.0


def test_vad_threshold_unknown_phase_falls_back():
    assert vad_threshold_for_phase("some_new_phase") == 1.5
    assert vad_threshold_for_phase("some_new_phase", fallback=2.0) == 2.0


def test_silence_checkin_fires_once():
    assert silence_checkin_should_fire(0, fired=False) is False
    assert silence_checkin_should_fire(89, fired=False) is False
    assert silence_checkin_should_fire(90, fired=False) is True
    assert silence_checkin_should_fire(120, fired=False) is True
    assert silence_checkin_should_fire(120, fired=True) is False  # never repeated


def test_phase_prosody_directive():
    assert "slower" in phase_prosody_directive("deepening")
    assert "settled" in phase_prosody_directive("closing")
    assert "warm" in phase_prosody_directive("landing")
    assert "natural" in phase_prosody_directive("unknown_phase")
