"""Application configuration. Loads from environment variables."""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "CardioSynth AI"
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # PostgreSQL URL, e.g. postgresql+psycopg://user:pass@localhost:5432/cardiosynth
    # If empty, SQLite is used (see database.py).
    database_url: str = ""

    uploads_dir: str = "uploads"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Logged URL hints — should match uvicorn --host and --port (avoids confusion when multiple backends run).
    api_advertised_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("API_ADVERTISED_HOST", "api_advertised_host"),
    )
    api_advertised_port: int = Field(
        default=8000,
        validation_alias=AliasChoices("API_ADVERTISED_PORT", "api_advertised_port", "PORT"),
    )

    # ECG classifier inference (TensorFlow) — see app/services/prediction_service.py
    ecg_classifier_model_path: str = ""
    ecg_default_sampling_rate_hz: float = 360.0
    ecg_classifier_input_length: int = 187
    # ENABLE_MOCK_INFERENCE=true: legacy fake-success prediction dicts when classifier is unavailable.
    enable_mock_inference: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_MOCK_INFERENCE", "enable_mock_inference"),
    )
    # If true, skip ensure_classifier_model() at startup (use pre-baked images / manual weights only)
    skip_classifier_auto_bootstrap: bool = False
    # If true and NPZ missing during bootstrap, run setup_dataset.py --max-records (network + disk heavy)
    ecg_auto_prepare_dataset: bool = False

    # DDPM synthetic generator (inference only — train via training/train_synthetic_ddpm.py)
    ecg_ddpm_model_path: str = ""
    ecg_ddpm_signal_length: int = 128
    ecg_ddpm_num_timesteps: int = 200
    ecg_ddpm_schedule: str = "linear"
    # If true: only DDPM is allowed; missing/failed weights → HTTP 503 (no parametric fallback).
    synthetic_require_ddpm: bool = Field(
        default=False,
        validation_alias=AliasChoices("SYNTHETIC_REQUIRE_DDPM", "synthetic_require_ddpm"),
    )
    # If false: when DDPM is unavailable, generation is rejected entirely.
    synthetic_procedural_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("SYNTHETIC_PROCEDURAL_ENABLED", "synthetic_procedural_enabled"),
    )

    # LLM assistant (OpenAI-compatible Chat Completions). If disabled or no API key, chat falls back to rules.
    llm_enabled: bool = Field(default=False, validation_alias=AliasChoices("LLM_ENABLED", "llm_enabled"))
    openai_api_key: str = Field(default="", validation_alias=AliasChoices("OPENAI_API_KEY", "openai_api_key"))
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("OPENAI_BASE_URL", "openai_base_url"),
    )
    llm_model: str = Field(default="gpt-4o-mini", validation_alias=AliasChoices("LLM_MODEL", "llm_model"))
    llm_timeout_seconds: float = Field(default=60.0, validation_alias=AliasChoices("LLM_TIMEOUT_SECONDS", "llm_timeout_seconds"))
    chat_memory_max_turns: int = Field(default=10, ge=2, le=30, validation_alias=AliasChoices("CHAT_MEMORY_MAX_TURNS", "chat_memory_max_turns"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
