import pytest
from pydantic import ValidationError

from app.config.settings import Settings

REQUIRED = {"secret_key": "k", "main_model": "m", "extraction_model": "e", "safety_model": "s"}


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **{**REQUIRED, **overrides})


def test_required_fields_raise_when_unset(monkeypatch):
    for key in ("SECRET_KEY", "MAIN_MODEL", "EXTRACTION_MODEL", "SAFETY_MODEL"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_defaults():
    s = make_settings()
    assert s.port == 8000
    assert s.session_minutes == 45
    assert s.course_sessions == 8
    assert s.silence_checkin_seconds == 90
    assert s.stt_provider == "sarvam"
    assert s.tts_provider == "sarvam"
    assert s.crisis_helpline_number == "14416"
    assert s.turn_end_vad_thresholds["deepening"] > s.turn_end_vad_thresholds["landing"]


def test_env_var_mapping(monkeypatch):
    monkeypatch.setenv("SESSION_MINUTES", "30")
    monkeypatch.setenv("COURSE_SESSIONS", "12")
    monkeypatch.setenv("TTS_PROVIDER", "sarvam")
    monkeypatch.setenv("TURN_END_VAD_THRESHOLDS", '{"landing": 1.0, "deepening": 4.0}')
    s = make_settings()
    assert s.session_minutes == 30
    assert s.course_sessions == 12
    assert s.tts_provider == "sarvam"
    assert s.turn_end_vad_thresholds == {"landing": 1.0, "deepening": 4.0}


def test_provider_keys_optional():
    s = make_settings()
    assert s.sarvam_api_key is None
    assert s.gemini_api_key is None
    assert s.rumik_api_key is None


def test_explicit_override_wins():
    s = make_settings(port=9000, database_url="postgresql+asyncpg://x")
    assert s.port == 9000
    assert s.database_url == "postgresql+asyncpg://x"


def test_module_level_settings_imports():
    from app.config.settings import settings

    assert settings.main_model == "test/main-model"
