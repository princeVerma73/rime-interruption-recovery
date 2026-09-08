"""Application Configuration Module

Provides safe loading, validation, and masked representation of application secrets
and runtime provider settings without ever exposing secret values in logs or exceptions.
"""

import os
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Search for .env in current working directory, backend folder, or project root
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ROOT_DIR = _BACKEND_DIR.parent

# Load environment files quietly
for env_candidate in [_BACKEND_DIR / ".env", _ROOT_DIR / ".env"]:
    if env_candidate.exists():
        load_dotenv(dotenv_path=env_candidate, override=False)


class Settings(BaseModel):
    """Safe application settings model."""

    # Required API Keys
    rime_api_key: str = Field(default_factory=lambda: os.getenv("RIME_API_KEY", ""))
    groq_api_key: str = Field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    tavily_api_key: str = Field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))

    # Optional Providers
    llm_provider: str = Field(default_factory=lambda: os.getenv("LLM_PROVIDER", "groq").lower())
    stt_provider: str = Field(default_factory=lambda: os.getenv("STT_PROVIDER", "groq").lower())

    # Tavily Search Configuration
    tavily_api_url: str = Field(
        default_factory=lambda: os.getenv("TAVILY_API_URL", "https://api.tavily.com/search")
    )

    # Rime TTS Configuration
    rime_api_url: str = Field(
        default_factory=lambda: os.getenv("RIME_API_URL", "https://users.rime.ai/v1/rime-tts")
    )
    rime_default_model: str = Field(
        default_factory=lambda: os.getenv("RIME_DEFAULT_MODEL", "coda")
    )
    rime_default_speaker: str = Field(
        default_factory=lambda: os.getenv("RIME_DEFAULT_SPEAKER", "celeste")
    )
    rime_default_format: str = Field(
        default_factory=lambda: os.getenv("RIME_DEFAULT_FORMAT", "mp3")
    )

    # Groq STT Configuration
    groq_stt_url: str = Field(
        default_factory=lambda: os.getenv("GROQ_STT_URL", "https://api.groq.com/openai/v1/audio/transcriptions")
    )
    groq_stt_model: str = Field(
        default_factory=lambda: os.getenv("GROQ_STT_MODEL", "whisper-large-v3")
    )

    # Groq LLM Configuration
    groq_llm_url: str = Field(
        default_factory=lambda: os.getenv("GROQ_LLM_URL", "https://api.groq.com/openai/v1/chat/completions")
    )
    groq_model: str = Field(
        default_factory=lambda: os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    )

    def validate_required_keys(self) -> None:
        """Validate that all required environment variables are present and non-empty.
        
        Raises:
            ValueError: If any required key is missing. Names of missing keys are reported,
                        never the secret values.
        """
        missing: List[str] = []
        if not self.rime_api_key or self.rime_api_key.strip() == "":
            missing.append("RIME_API_KEY")
        if not self.groq_api_key or self.groq_api_key.strip() == "":
            missing.append("GROQ_API_KEY")
        if not self.gemini_api_key or self.gemini_api_key.strip() == "":
            missing.append("GEMINI_API_KEY")

        if missing:
            raise ValueError(
                f"Missing required configuration key(s): {', '.join(missing)}. "
                "Ensure these are defined in your environment or backend/.env file."
            )

    @property
    def is_rime_configured(self) -> bool:
        return bool(self.rime_api_key and self.rime_api_key.strip())

    @property
    def is_tavily_configured(self) -> bool:
        return bool(self.tavily_api_key and self.tavily_api_key.strip())

    @property
    def is_fully_configured(self) -> bool:
        try:
            self.validate_required_keys()
            return True
        except ValueError:
            return False

    def __repr__(self) -> str:
        """Safe representation masking all secret values."""
        return (
            f"Settings("
            f"rime_api_key='{'***' if self.rime_api_key else ''}', "
            f"groq_api_key='{'***' if self.groq_api_key else ''}', "
            f"gemini_api_key='{'***' if self.gemini_api_key else ''}', "
            f"tavily_api_key='{'***' if self.tavily_api_key else ''}', "
            f"llm_provider='{self.llm_provider}', "
            f"stt_provider='{self.stt_provider}')"
        )

    def __str__(self) -> str:
        return self.__repr__()


_cached_settings: Optional[Settings] = None


def get_settings(force_reload: bool = False) -> Settings:
    """Retrieve the cached Settings instance or instantiate a new one."""
    global _cached_settings
    if _cached_settings is None or force_reload:
        _cached_settings = Settings()
    return _cached_settings
