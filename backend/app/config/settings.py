from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Central management for settings and configurations.

    Every model, provider, and threshold is env-swappable (§7.11). Fields
    without a default raise at startup when unset — copy `.env.example` to
    `.env` at the repo root.
    """

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- server / environment ---
    port: int = 8000
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://aitherapy:aitherapy@localhost:5432/aitherapy"
    secret_key: str

    # --- models (via LiteLLM — never hardcoded) ---
    main_model: str
    extraction_model: str
    safety_model: str

    # --- voice providers (eval-time swappable) ---
    stt_provider: str = "sarvam"
    tts_provider: str = "sarvam"

    # --- provider keys (LiteLLM routes by model prefix) ---
    sarvam_api_key: str | None = None
    rumik_api_key: str | None = None
    gemini_api_key: str | None = None
    groq_api_key: str | None = None

    # --- session / course / timing ---
    session_minutes: int = 45
    course_sessions: int = 8
    turn_end_vad_thresholds: dict[str, float] = {
        "landing": 1.5,
        "opening": 2.0,
        "deepening": 3.5,
        "meaning": 2.5,
        "closing": 2.0,
    }
    silence_checkin_seconds: int = 90

    # --- crisis resources (control surface + crisis protocol) ---
    crisis_helpline_number: str = "14416"
    crisis_website: str | None = None


settings = Settings()
